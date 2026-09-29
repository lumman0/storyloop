"""FastAPI adapter for the independent player portal service."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from story_harness.portal.service import PlayerPortal


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
    bearer = HTTPBearer(auto_error=False)

    @app.middleware("http")
    async def local_request_only(request: Request, call_next):
        host = request.headers.get("host", "").split(":", 1)[0]
        if host not in {"127.0.0.1", "localhost"}:
            return JSONResponse({"error": "invalid local host"}, status_code=401)
        origin = request.headers.get("origin")
        if origin and origin not in {f"http://{host}:{request.url.port}", f"http://{host}"}:
            return JSONResponse({"error": "cross-origin requests are not allowed"}, status_code=401)
        needs_json = (request.url.path in {"/v1/accounts", "/v1/sessions", "/v1/saves"}
                      or request.url.path.endswith("/turns"))
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

    return app


def serve(portal: PlayerPortal, host: str = "127.0.0.1", port: int = 8765) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("player portal HTTP login is available on localhost only")
    import uvicorn

    uvicorn.run(create_app(portal), host=host, port=port)
