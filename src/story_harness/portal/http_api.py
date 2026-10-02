"""FastAPI adapter for the independent player portal service."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

from story_harness.portal.service import PlayerPortal
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


class TurnBody(BaseModel):
    text: str
    request_id: str | None = None


def _http_error(error: Exception) -> HTTPException:
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
        try:
            yield
        finally:
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
                           allow_methods=["GET", "POST", "DELETE"],
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
        needs_json = (request.url.path in {"/v1/accounts", "/v1/sessions", "/v1/saves"}
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
            return {"player_id": session["player_id"]} if online_cookie else session
        except (ValueError, PermissionError) as error:
            raise _http_error(error) from error

    @app.post("/v1/sessions")
    def login(body: AccountBody, response: Response) -> dict:
        try:
            session = portal.login(body.username, body.password)
            set_session_cookie(response, session["token"])
            return {"player_id": session["player_id"]} if online_cookie else session
        except (ValueError, PermissionError) as error:
            raise _http_error(error) from error

    @app.get("/v1/sessions/current")
    def current_session(request: Request, auth: str = Depends(token)) -> dict:
        return {"player_id": request.state.user_id}

    @app.delete("/v1/sessions/current")
    def logout(response: Response, auth: str = Depends(token)) -> dict:
        portal.logout(auth)
        response.delete_cookie(cookie_name, path="/", secure=online_cookie,
                               httponly=True, samesite="lax")
        return {"status": "logged_out"}

    @app.get("/v1/catalog")
    def catalog(auth: str = Depends(token)) -> dict:
        return {"games": portal.games(auth)}

    @app.get("/v1/my-scenarios")
    def my_scenarios(auth: str = Depends(token)) -> dict:
        return {"scenarios": portal.my_scenarios(auth)}

    @app.post("/v1/my-scenarios", status_code=201)
    async def upload_scenario(title: str = Form(...), summary: str = Form(""),
                              file: UploadFile = File(...), auth: str = Depends(token)) -> dict:
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
        try:
            return portal.upload_scenario(auth, title, summary, bytes(content))
        except ValueError as error:
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
            return await portal.create_save(auth, body.catalog_id)
        except (ValueError, KeyError, PermissionError) as error:
            raise _http_error(error) from error

    @app.post("/v1/saves/{game_id}/resume")
    async def resume(game_id: str, auth: str = Depends(token)) -> dict:
        try:
            return await portal.resume_save(auth, game_id)
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
