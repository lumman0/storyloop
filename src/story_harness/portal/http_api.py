"""FastAPI adapter for the independent player portal service."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

from story_harness.portal.service import PlayerPortal
from story_harness.portal.access import AccessDenied
from story_harness.portal.sql_repository import SESSION_TTL_SECONDS
from story_harness.portal.user_scenarios import MAX_ARCHIVE_BYTES


logger = logging.getLogger(__name__)
TRANSIENT_MODEL_ERRORS = (APIConnectionError, RateLimitError, InternalServerError)


def _model_failure_message(error: Exception) -> str:
    if isinstance(error, APITimeoutError):
        cause = "模型服务响应超时"
    elif isinstance(error, RateLimitError):
        cause = "模型服务暂时繁忙（请求限流）"
    elif isinstance(error, APIConnectionError):
        cause = "模型服务暂时无法连接"
    else:
        cause = "模型服务暂时不可用"
    return f"{cause}。请稍后重试这条行动；使用原请求重试不会重复扣费。"


def _model_http_error(error: Exception) -> HTTPException:
    status = 504 if isinstance(error, APITimeoutError) else 429 if isinstance(error, RateLimitError) else 503
    return HTTPException(status_code=status, detail=_model_failure_message(error))


class AccountBody(BaseModel):
    username: str
    password: str
    invite_code: str | None = Field(default=None, max_length=128)


class SaveBody(BaseModel):
    catalog_id: str
    play_mode: Literal["campaign", "freeform"] | None = None
    story_setup: dict[str, str] | None = None


class SaveSettingsBody(BaseModel):
    temperature: float
    context_window_tokens: int


class TurnBody(BaseModel):
    text: str
    request_id: str | None = None


class PlayerMemorySettingsBody(BaseModel):
    enabled: bool


class ReviewDecisionBody(BaseModel):
    decision: str
    reason: str = ""


class RoleBody(BaseModel):
    role: str
    enabled: bool


class AccountStatusBody(BaseModel):
    status: str


class ReleaseStateBody(BaseModel):
    state: str
    reason: str = ""


class InvitationIssueBody(BaseModel):
    count: int = Field(default=1, ge=1, le=20)


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, AccessDenied):
        return HTTPException(status_code=403, detail=str(error))
    if isinstance(error, PermissionError):
        return HTTPException(status_code=401, detail=str(error))
    if isinstance(error, KeyError):
        return HTTPException(status_code=404, detail=str(error.args[0]))
    if isinstance(error, ValueError):
        return HTTPException(status_code=400, detail=str(error))
    raise error


def create_app(portal: PlayerPortal) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        worker = (asyncio.create_task(portal.run_memory_worker())
                  if getattr(portal, "memory_feature_enabled", False) is True else None)
        try:
            yield
        finally:
            if worker is not None:
                worker.cancel()
                with suppress(asyncio.CancelledError):
                    await worker
            portal.close()

    app = FastAPI(title="Story Harness Player Portal", version="0.1.0", lifespan=lifespan)
    app.state.active_turn_tasks = set()
    online_cookie = portal.config.profile == "online"
    cookie_name = "__Host-storyloop" if online_cookie else "storyloop-session"

    async def model_error_response(_request: Request, error: Exception) -> JSONResponse:
        logger.warning("model unavailable during portal request: %s", type(error).__name__)
        mapped = _model_http_error(error)
        return JSONResponse({"detail": mapped.detail}, status_code=mapped.status_code)

    for error_type in TRANSIENT_MODEL_ERRORS:
        app.add_exception_handler(error_type, model_error_response)

    bearer = HTTPBearer(auto_error=False)
    if portal.config.profile == "online":
        app.add_middleware(CORSMiddleware, allow_origins=list(portal.config.allowed_origins()),
                           allow_methods=["GET", "POST", "PUT", "DELETE"],
                           allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def validate_request(request: Request, call_next):
        host = request.headers.get("host", "").split(":", 1)[0].lower()
        if host not in portal.config.allowed_hosts():
            return JSONResponse({"error": "invalid host"}, status_code=401)
        origin = request.headers.get("origin")
        if portal.config.profile == "local":
            origins = {f"http://{host}:{request.url.port}", f"http://{host}",
                       "http://127.0.0.1:5173", "http://localhost:5173"}
        else:
            origins = set(portal.config.allowed_origins())
        if origin and origin not in origins:
            return JSONResponse({"error": "cross-origin requests are not allowed"}, status_code=401)
        if (online_cookie and request.url.path.startswith("/v1/")
                and request.method in {"POST", "PUT", "PATCH", "DELETE"} and not origin):
            return JSONResponse({"error": "Origin required"}, status_code=403)
        needs_json = (request.url.path in {"/v1/accounts", "/v1/sessions", "/v1/saves",
                                               "/v1/me/memory/settings", "/v1/manage/invites"}
                      or (request.url.path.startswith("/v1/manage/")
                          and request.url.path.endswith(("/decision", "/role", "/status", "/state")))
                      or request.url.path.endswith("/settings")
                      or request.url.path.endswith(("/turns", "/turns/stream")))
        if request.method in {"POST", "PUT", "PATCH"} and needs_json:
            content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                return JSONResponse({"error": "Content-Type must be application/json"}, status_code=400)
        response = await call_next(request)
        if request.url.path.startswith("/v1/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def token(request: Request,
              credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        if online_cookie:
            if credentials is not None:
                raise HTTPException(status_code=401, detail="Cookie session required")
            session_token = request.cookies.get(cookie_name)
        else:
            session_token = credentials.credentials if credentials else request.cookies.get(cookie_name)
        if not session_token:
            raise HTTPException(status_code=401, detail="Login required")
        try:
            player_id = portal.accounts.resolve_token(session_token)
        except PermissionError as error:
            raise _http_error(error) from error
        request.state.user_id = player_id
        return session_token

    def set_session_cookie(response: Response, session_token: str) -> None:
        response.set_cookie(cookie_name, session_token, max_age=SESSION_TTL_SECONDS,
                            path="/", secure=online_cookie, httponly=True, samesite="lax")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/v1/accounts", status_code=201)
    def register(body: AccountBody, response: Response) -> dict:
        try:
            session = portal.register(body.username, body.password, body.invite_code)
            set_session_cookie(response, session["token"])
            info = portal.session_info(session["token"])
            return info if online_cookie else {**session, **info}
        except (ValueError, PermissionError) as error:
            raise _http_error(error) from error

    @app.post("/v1/sessions")
    def login(body: AccountBody, response: Response) -> dict:
        try:
            session = portal.login(body.username, body.password)
            set_session_cookie(response, session["token"])
            info = portal.session_info(session["token"])
            return info if online_cookie else {**session, **info}
        except (ValueError, PermissionError) as error:
            raise _http_error(error) from error

    @app.get("/v1/sessions/current")
    def current_session(request: Request, auth: str = Depends(token)) -> dict:
        return portal.session_info(auth)

    @app.delete("/v1/sessions/current")
    def logout(response: Response, auth: str = Depends(token)) -> dict:
        portal.logout(auth)
        response.delete_cookie(cookie_name, path="/", secure=online_cookie,
                               httponly=True, samesite="lax")
        return {"status": "logged_out"}

    @app.get("/v1/catalog")
    def catalog(auth: str = Depends(token)) -> dict:
        return {"games": portal.games(auth)}

    @app.get("/v1/catalog/{catalog_id}/artwork/cover")
    def catalog_cover(catalog_id: str, auth: str = Depends(token)) -> FileResponse:
        try:
            return FileResponse(portal.cover_artwork(auth, catalog_id))
        except (KeyError, PermissionError, ValueError) as error:
            raise _http_error(error) from error

    @app.get("/v1/saves/{game_id}/cast")
    def visible_cast(game_id: str, auth: str = Depends(token)) -> dict:
        try:
            return {"cast": portal.cast(auth, game_id)}
        except (KeyError, PermissionError, ValueError) as error:
            raise _http_error(error) from error

    @app.get("/v1/saves/{game_id}/player-card")
    def player_card(game_id: str, auth: str = Depends(token)) -> dict:
        try:
            return portal.player_card(auth, game_id)
        except (KeyError, PermissionError, ValueError) as error:
            raise _http_error(error) from error

    @app.get("/v1/saves/{game_id}/cast/{actor_id}")
    def character_detail(game_id: str, actor_id: str, auth: str = Depends(token)) -> dict:
        try:
            return portal.character_detail(auth, game_id, actor_id)
        except (KeyError, PermissionError, ValueError) as error:
            raise _http_error(error) from error

    @app.get("/v1/saves/{game_id}/cast/{actor_id}/portrait")
    def cast_portrait(game_id: str, actor_id: str,
                      auth: str = Depends(token)) -> FileResponse:
        try:
            return FileResponse(portal.portrait_artwork(auth, game_id, actor_id))
        except (KeyError, PermissionError, ValueError) as error:
            raise _http_error(error) from error

    @app.get("/v1/me/memory")
    async def player_memory(auth: str = Depends(token)) -> dict:
        try:
            return await portal.memory_status(auth)
        except Exception as error:
            logger.exception("player memory status failed")
            raise HTTPException(status_code=503, detail="玩家画像暂时不可用") from error

    @app.post("/v1/me/memory/settings")
    async def set_player_memory(body: PlayerMemorySettingsBody,
                                auth: str = Depends(token)) -> dict:
        try:
            return await portal.set_memory_enabled(auth, body.enabled)
        except ValueError as error:
            raise _http_error(error) from error

    @app.delete("/v1/me/memory")
    async def clear_player_memory(auth: str = Depends(token)) -> dict:
        try:
            return await portal.clear_memory(auth)
        except ValueError as error:
            raise _http_error(error) from error

    @app.get("/v1/my-scenarios")
    def my_scenarios(auth: str = Depends(token)) -> dict:
        return {"scenarios": portal.my_scenarios(auth)}

    async def read_scenario_archive(file: UploadFile) -> bytes:
        if file.content_type not in {"application/zip", "application/x-zip-compressed",
                                     "application/octet-stream"}:
            raise HTTPException(status_code=415, detail="file must be a ZIP archive")
        content = bytearray()
        try:
            while chunk := await file.read(64 * 1024):
                content.extend(chunk)
                if len(content) > MAX_ARCHIVE_BYTES:
                    raise HTTPException(status_code=413, detail="ZIP file exceeds 4 MiB")
        finally:
            await file.close()
        return bytes(content)

    @app.post("/v1/my-scenarios", status_code=201)
    async def upload_scenario(title: str = Form(...), summary: str = Form(""),
                              file: UploadFile = File(...), auth: str = Depends(token)) -> dict:
        content = await read_scenario_archive(file)
        try:
            return await asyncio.to_thread(portal.upload_scenario, auth, title, summary, content)
        except ValueError as error:
            raise _http_error(error) from error
        except (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError) as error:
            raise _model_http_error(error) from error

    @app.post("/v1/my-scenarios/{scenario_id}/versions", status_code=201)
    async def upload_scenario_version(scenario_id: str, title: str = Form(...),
                                      summary: str = Form(""), file: UploadFile = File(...),
                                      auth: str = Depends(token)) -> dict:
        content = await read_scenario_archive(file)
        try:
            return await asyncio.to_thread(portal.upload_scenario_version, auth, scenario_id,
                                           title, summary, content)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error
        except (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError) as error:
            raise _model_http_error(error) from error

    @app.post("/v1/my-scenarios/{scenario_id}/submit", status_code=201)
    def submit_scenario(scenario_id: str, auth: str = Depends(token)) -> dict:
        try:
            return portal.submit_scenario(auth, scenario_id)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.get("/v1/my-submissions")
    def my_submissions(auth: str = Depends(token)) -> dict:
        return {"submissions": portal.my_submissions(auth)}

    @app.delete("/v1/my-submissions/{submission_id}")
    def withdraw_submission(submission_id: str, auth: str = Depends(token)) -> dict:
        try:
            return portal.withdraw_submission(auth, submission_id)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.get("/v1/manage/submissions")
    def review_queue(status: str = "pending", auth: str = Depends(token)) -> dict:
        try:
            return {"submissions": portal.review_queue(auth, status)}
        except (ValueError, PermissionError) as error:
            raise _http_error(error) from error

    @app.get("/v1/manage/submissions/{submission_id}")
    def review_detail(submission_id: str, auth: str = Depends(token)) -> dict:
        try:
            return portal.review_detail(auth, submission_id)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.post("/v1/manage/submissions/{submission_id}/preview")
    async def review_preview(submission_id: str, auth: str = Depends(token)) -> dict:
        try:
            return await portal.create_review_preview(auth, submission_id)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.post("/v1/manage/submissions/{submission_id}/decision")
    def review_decide(submission_id: str, body: ReviewDecisionBody,
                      auth: str = Depends(token)) -> dict:
        try:
            return portal.review_decide(auth, submission_id, body.decision, body.reason)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.get("/v1/manage/users")
    def admin_users(auth: str = Depends(token)) -> dict:
        try:
            return {"users": portal.admin_users(auth)}
        except PermissionError as error:
            raise _http_error(error) from error

    @app.get("/v1/manage/invites")
    def admin_invitations(auth: str = Depends(token)) -> dict:
        try:
            return {"invites": portal.admin_invitations(auth)}
        except PermissionError as error:
            raise _http_error(error) from error

    @app.post("/v1/manage/invites", status_code=201)
    def admin_issue_invitations(body: InvitationIssueBody,
                                auth: str = Depends(token)) -> dict:
        try:
            return portal.admin_issue_invitations(auth, body.count)
        except (ValueError, PermissionError) as error:
            raise _http_error(error) from error

    @app.post("/v1/manage/invites/{invitation_id}/revoke")
    def admin_revoke_invitation(invitation_id: str,
                                auth: str = Depends(token)) -> dict:
        try:
            return portal.admin_revoke_invitation(auth, invitation_id)
        except (ValueError, PermissionError) as error:
            raise _http_error(error) from error

    @app.post("/v1/manage/users/{player_id}/role")
    def admin_role(player_id: str, body: RoleBody, auth: str = Depends(token)) -> dict:
        try:
            return portal.admin_set_role(auth, player_id, body.role, body.enabled)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.post("/v1/manage/users/{player_id}/status")
    def admin_status(player_id: str, body: AccountStatusBody,
                     auth: str = Depends(token)) -> dict:
        try:
            return portal.admin_set_status(auth, player_id, body.status)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.get("/v1/manage/releases")
    def admin_releases(auth: str = Depends(token)) -> dict:
        try:
            return {"releases": portal.admin_releases(auth)}
        except PermissionError as error:
            raise _http_error(error) from error

    @app.post("/v1/manage/releases/{scenario_id}/state")
    def admin_release_state(scenario_id: str, body: ReleaseStateBody,
                            auth: str = Depends(token)) -> dict:
        try:
            return portal.admin_release_state(auth, scenario_id, body.state, body.reason)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.get("/v1/manage/audit")
    def admin_audit(auth: str = Depends(token)) -> dict:
        try:
            return {"events": portal.admin_audit(auth)}
        except PermissionError as error:
            raise _http_error(error) from error

    @app.post("/v1/my-scenarios/{scenario_id}/publish")
    def publish_scenario(scenario_id: str, auth: str = Depends(token)) -> dict:
        try:
            return portal.publish_scenario(auth, scenario_id)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.delete("/v1/my-scenarios/{scenario_id}")
    def delete_scenario_draft(scenario_id: str, auth: str = Depends(token)) -> dict:
        try:
            return portal.delete_scenario_draft(auth, scenario_id)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.get("/v1/saves")
    def saves(auth: str = Depends(token)) -> dict:
        return {"saves": portal.saves(auth)}

    @app.get("/v1/billing/wallet")
    def wallet(auth: str = Depends(token)) -> dict:
        try:
            return portal.wallet(auth)
        except (ValueError, PermissionError) as error:
            raise _http_error(error) from error

    @app.get("/v1/billing/ledger")
    def credit_ledger(limit: int = 30, auth: str = Depends(token)) -> dict:
        try:
            return {"entries": portal.credit_ledger(auth, limit)}
        except (ValueError, PermissionError) as error:
            raise _http_error(error) from error

    @app.get("/v1/saves/{game_id}/history")
    def history(game_id: str, auth: str = Depends(token)) -> dict:
        try:
            return portal.history(auth, game_id)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.post("/v1/saves", status_code=201)
    async def create_save(body: SaveBody, auth: str = Depends(token)) -> dict:
        try:
            return await portal.create_save(auth, body.catalog_id, body.play_mode,
                                            body.story_setup)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.post("/v1/saves/{game_id}/resume")
    async def resume(game_id: str, auth: str = Depends(token)) -> dict:
        try:
            return await portal.resume_save(auth, game_id)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.get("/v1/saves/{game_id}/settings")
    def save_settings(game_id: str, auth: str = Depends(token)) -> dict:
        try:
            return portal.get_save_settings(auth, game_id)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.put("/v1/saves/{game_id}/settings")
    async def update_save_settings(game_id: str, body: SaveSettingsBody,
                                   auth: str = Depends(token)) -> dict:
        try:
            return await portal.set_save_settings(auth, game_id,
                                                  body.temperature, body.context_window_tokens)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.post("/v1/saves/{game_id}/turns")
    async def turn(game_id: str, body: TurnBody, auth: str = Depends(token)) -> dict:
        try:
            return await portal.turn(auth, game_id, body.text, body.request_id)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.post("/v1/saves/{game_id}/turns/stream")
    async def stream_turn(game_id: str, body: TurnBody, auth: str = Depends(token)) -> StreamingResponse:
        async def events():
            queue: asyncio.Queue[dict | None] = asyncio.Queue()

            async def report(event: dict) -> None:
                await queue.put(event)

            async def run_turn() -> None:
                try:
                    view = await portal.turn(auth, game_id, body.text, body.request_id, progress=report)
                    await report({"type": "complete", "view": view})
                except (ValueError, KeyError, PermissionError) as error:
                    await report({"type": "error", "message": str(error)})
                except TRANSIENT_MODEL_ERRORS as error:
                    logger.warning("model unavailable during streamed turn: %s", type(error).__name__)
                    await report({"type": "error", "message": _model_failure_message(error)})
                except Exception:
                    logger.exception("streamed turn failed")
                    await report({"type": "error", "message": "请求未能完成，请稍后重试。"})
                finally:
                    await queue.put(None)

            task = asyncio.create_task(run_turn())
            app.state.active_turn_tasks.add(task)
            task.add_done_callback(app.state.active_turn_tasks.discard)
            yield 'data: {"type":"stage","stage":"received"}\n\n'
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if event is None:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
        })

    return app


def serve(portal: PlayerPortal, host: str = "127.0.0.1", port: int = 8765) -> None:
    if portal.config.profile == "local" and host not in {"127.0.0.1", "localhost"}:
        raise ValueError("local portal HTTP login must bind to localhost")
    import uvicorn

    uvicorn.run(create_app(portal), host=host, port=port)
