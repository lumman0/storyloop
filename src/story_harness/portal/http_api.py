"""FastAPI adapter for the independent player portal service."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

from story_harness.portal.service import PlayerPortal


logger = logging.getLogger(__name__)


class AccountBody(BaseModel):
    username: str
    password: str


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
        needs_json = (request.url.path in {"/v1/accounts", "/v1/sessions", "/v1/saves"}
                      or request.url.path.endswith(("/turns", "/turns/stream")))
        if request.method in {"POST", "PUT", "PATCH"} and needs_json:
            content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                return JSONResponse({"error": "Content-Type must be application/json"}, status_code=400)
        return await call_next(request)

    def token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        if credentials is None:
            raise HTTPException(status_code=401, detail="Bearer token required")
        try:
            portal.accounts.resolve_token(credentials.credentials)
        except PermissionError as error:
            raise _http_error(error) from error
        return credentials.credentials

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/v1/accounts", status_code=201)
    def register(body: AccountBody) -> dict:
        try:
            return portal.register(body.username, body.password)
        except (ValueError, PermissionError) as error:
            raise _http_error(error) from error

    @app.post("/v1/sessions")
    def login(body: AccountBody) -> dict:
        try:
            return portal.login(body.username, body.password)
        except (ValueError, PermissionError) as error:
            raise _http_error(error) from error

    @app.delete("/v1/sessions/current")
    def logout(auth: str = Depends(token)) -> dict:
        portal.logout(auth)
        return {"status": "logged_out"}

    @app.get("/v1/catalog")
    def catalog(auth: str = Depends(token)) -> dict:
        return {"games": portal.games(auth)}

    @app.get("/v1/saves")
    def saves(auth: str = Depends(token)) -> dict:
        return {"saves": portal.saves(auth)}

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
