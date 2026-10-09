"""Browser session behavior for the online portal."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from storyloop_platform.portal.http_api import create_app


def _client() -> tuple[TestClient, Mock]:
    portal = Mock()
    portal.resources = SimpleNamespace(
        environment="online",
        allowed_hosts=lambda: {"story.example"},
        allowed_origins=lambda: ("https://story.example",),
    )
    portal.settings = SimpleNamespace(environment="online")
    portal.login.return_value = {"player_id": "player-1", "token": "private-token"}
    portal.session_info.return_value = {"player_id": "player-1", "roles": [], "capabilities": []}
    portal.accounts.resolve_token.return_value = "player-1"
    portal.games.return_value = []
    return TestClient(create_app(portal), base_url="https://story.example"), portal


def test_login_sets_private_cookie_and_restores_session() -> None:
    client, portal = _client()
    with client:
        login = client.post("/v1/sessions", json={"username": "a", "password": "password123"},
                            headers={"Origin": "https://story.example"})
        assert login.status_code == 200
        assert login.json() == {"player_id": "player-1", "roles": [], "capabilities": []}
        cookie = login.headers["set-cookie"]
        assert "__Host-storyloop=" in cookie
        assert "HttpOnly" in cookie and "Secure" in cookie
        assert "SameSite=lax" in cookie and "Max-Age=604800" in cookie
        assert client.get("/v1/sessions/current").json() == {"player_id": "player-1", "roles": [], "capabilities": []}
        assert client.get("/v1/catalog").status_code == 200
        portal.accounts.resolve_token.assert_called_with("private-token")


def test_online_rejects_bearer_and_cross_site_writes() -> None:
    client, portal = _client()
    with client:
        assert client.get("/v1/catalog", headers={"Authorization": "Bearer private-token"}).status_code == 401
        assert client.post("/v1/sessions", json={"username": "a", "password": "password123"},
                           headers={"Origin": "https://other.example"}).status_code == 401
        assert client.post("/v1/sessions", json={"username": "a", "password": "password123"}).status_code == 403
        client.post("/v1/sessions", json={"username": "a", "password": "password123"},
                    headers={"Origin": "https://story.example"})
        assert client.post("/v1/saves", json={"catalog_id": "sample"},
                           headers={"Origin": "https://other.example"}).status_code == 401
        portal.create_save.assert_not_called()


def test_logout_revokes_and_clears_cookie() -> None:
    client, portal = _client()
    with client:
        client.post("/v1/sessions", json={"username": "a", "password": "password123"},
                    headers={"Origin": "https://story.example"})
        logout = client.delete("/v1/sessions/current", headers={"Origin": "https://story.example"})
        assert logout.status_code == 200
        assert "Max-Age=0" in logout.headers["set-cookie"]
        portal.logout.assert_called_once_with("private-token")
        assert client.get("/v1/sessions/current").status_code == 401


def test_local_browser_uses_cookie_while_cli_keeps_bearer() -> None:
    portal = Mock()
    portal.resources = SimpleNamespace(allowed_hosts=lambda: {"127.0.0.1"})
    portal.settings = SimpleNamespace(environment="local")
    portal.login.return_value = {"player_id": "player-1", "token": "local-token"}
    portal.session_info.return_value = {"player_id": "player-1", "roles": [], "capabilities": []}
    portal.accounts.resolve_token.return_value = "player-1"
    with TestClient(create_app(portal), base_url="http://127.0.0.1") as client:
        login = client.post("/v1/sessions", json={"username": "a", "password": "password123"})
        assert login.json()["token"] == "local-token"
        assert client.get("/v1/sessions/current").json() == {"player_id": "player-1", "roles": [], "capabilities": []}
        client.cookies.clear()
        assert client.get("/v1/sessions/current",
                          headers={"Authorization": "Bearer local-token"}).status_code == 200
