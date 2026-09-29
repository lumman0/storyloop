"""Small localhost JSON API for account, catalog, save, and turn operations."""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

from story_harness.portal.service import PlayerPortal


def serve(portal: PlayerPortal, host: str = "127.0.0.1", port: int = 8765) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("player portal HTTP login is available on localhost only")
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, name="player-portal-loop", daemon=True)
    loop_thread.start()

    class Handler(BaseHTTPRequestHandler):
        @staticmethod
        def _run(coroutine):
            return asyncio.run_coroutine_threadsafe(coroutine, loop).result()

        def _body(self) -> dict:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                raise ValueError("Content-Type must be application/json")
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 65_536:
                raise ValueError("JSON request body must be 1–65536 bytes")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON request body must be an object")
            return payload

        def _token(self) -> str:
            scheme, _, token = self.headers.get("Authorization", "").partition(" ")
            if scheme.lower() != "bearer" or not token:
                raise PermissionError("Bearer token required")
            return token

        def _write(self, code: int, payload: dict | list) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _dispatch(self) -> None:
            method = self.command
            path = urlsplit(self.path).path
            allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host", "") not in allowed_hosts:
                raise PermissionError("invalid local host")
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://{host}" for host in allowed_hosts}:
                raise PermissionError("cross-origin requests are not allowed")
            if method == "GET" and path == "/health":
                self._write(200, {"status": "ok"})
                return
            if method == "POST" and path == "/v1/accounts":
                body = self._body()
                self._write(201, portal.register(body.get("username"), body.get("password")))
                return
            if method == "POST" and path == "/v1/sessions":
                body = self._body()
                self._write(200, portal.login(body.get("username"), body.get("password")))
                return
            token = self._token()
            if method == "DELETE" and path == "/v1/sessions/current":
                portal.logout(token)
                self._write(200, {"status": "logged_out"})
                return
            if method == "GET" and path == "/v1/catalog":
                self._write(200, {"games": portal.games(token)})
                return
            if method == "GET" and path == "/v1/saves":
                self._write(200, {"saves": portal.saves(token)})
                return
            if method == "POST" and path == "/v1/saves":
                body = self._body()
                self._write(201, self._run(portal.create_save(token, body.get("catalog_id"))))
                return
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["v1", "saves"] and parts[3] == "resume" and method == "POST":
                self._write(200, self._run(portal.resume_save(token, parts[2])))
                return
            if len(parts) == 4 and parts[:2] == ["v1", "saves"] and parts[3] == "turns" and method == "POST":
                body = self._body()
                self._write(200, self._run(portal.turn(token, parts[2], body.get("text"),
                                                       body.get("request_id"))))
                return
            self._write(404, {"error": "not found"})

        def do_GET(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def do_DELETE(self) -> None:
            self._handle()

        def _handle(self) -> None:
            try:
                self._dispatch()
            except PermissionError as error:
                self._write(401, {"error": str(error)})
            except KeyError as error:
                self._write(404, {"error": str(error.args[0])})
            except (ValueError, UnicodeError, json.JSONDecodeError) as error:
                self._write(400, {"error": str(error)})
            except Exception:
                self.log_exception()
                self._write(500, {"error": "internal error"})

        def log_exception(self) -> None:
            import logging
            logging.exception("player portal request failed")

    server = None
    try:
        server = HTTPServer((host, port), Handler)
        print(f"Player Portal API: http://{host}:{port}", flush=True)
        server.serve_forever()
    finally:
        if server is not None:
            server.server_close()
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=5)
        loop.close()
        portal.close()
