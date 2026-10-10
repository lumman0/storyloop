"""One offline smoke test for persisted preferences and the HTTP adapter."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from httpx2 import Request
from openai import APIConnectionError

from storyloop_platform.portal.http_api import create_app
from storyloop_platform.portal import local_config
from storyloop_platform.portal.local_config import LocalPreferences
from storyloop_platform.config import load_settings
from storyloop_platform.bootstrap import build_portal


ROOT = Path(__file__).resolve().parents[1]


class PortalLocalApiSmokeTest(unittest.TestCase):
    def test_non_windows_preferences_never_persist_credentials(self) -> None:
        # Replace only this module's OS binding; do not change pathlib's host OS.
        posix = SimpleNamespace(name="posix", environ=os.environ, replace=os.replace)
        with tempfile.TemporaryDirectory() as temp, patch.object(local_config, "os", posix):
            root = Path(temp)
            preferences = LocalPreferences(root / "settings")
            preferences.save_settings(root / "catalog.json", root / "config.json", root / "game.db")
            preferences.save_model_key("TEST_MODEL_KEY", "secret-model-key")
            preferences.save_session(root / "game.db", "tester", "secret-session-token")
            restored = LocalPreferences(preferences.directory)
            self.assertIsNone(restored.model_key("TEST_MODEL_KEY"))
            self.assertIsNone(restored.session(root / "game.db"))
            self.assertEqual(Path(restored.load_settings()["db"]).resolve(),
                             (root / "game.db").resolve())
            self.assertEqual({path.name for path in preferences.directory.iterdir()}, {"settings.json"})
            content = (preferences.directory / "settings.json").read_text(encoding="utf-8")
            self.assertNotIn("secret-model-key", content)
            self.assertNotIn("secret-session-token", content)

    def test_model_connection_failure_is_reported_as_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_MODEL_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": ""},
        ):
            portal = build_portal(ROOT / "examples" / "catalog.json",
                                  load_settings(ROOT / "config" / "local.json"), str(Path(temp) / "game.sqlite3"))
            token = portal.register("offline-user", "stream-pass-123")["token"]

            async def unavailable(*_args, **_kwargs):
                raise APIConnectionError(request=Request("POST", "https://example.invalid/v1"))

            portal.turn = unavailable
            with TestClient(create_app(portal), base_url="http://127.0.0.1") as client:
                headers = {"Authorization": f"Bearer {token}"}
                streamed = client.post("/v1/saves/sample/turns/stream", json={
                    "text": "hi", "request_id": "request-1",
                }, headers=headers)
                regular = client.post("/v1/saves/sample/turns", json={
                    "text": "hi", "request_id": "request-1",
                }, headers=headers)
            events = [json.loads(line[6:]) for line in streamed.text.splitlines()
                      if line.startswith("data: ")]
            self.assertEqual(events[-1]["type"], "error")
            self.assertIn("模型服务", events[-1]["message"])
            self.assertIn("重试", events[-1]["message"])
            self.assertEqual(regular.status_code, 503)
            self.assertIn("模型服务", regular.json()["detail"])

    def test_streamed_turn_reports_progress_and_final_view(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_MODEL_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": ""},
        ):
            portal = build_portal(ROOT / "examples" / "catalog.json",
                                  load_settings(ROOT / "config" / "local.json"), str(Path(temp) / "game.sqlite3"))
            token = portal.register("stream-user", "stream-pass-123")["token"]

            async def scripted_turn(auth, game_id, text, request_id, progress=None):
                self.assertEqual((auth, game_id, text, request_id),
                                 (token, "sample", "你好", "request-1"))
                await progress({"type": "stage", "stage": "thinking"})
                await progress({"type": "preview", "body": "你好！", "segments": [{"kind": "dialogue", "text": "你好！"}]})
                return {"game_id": game_id, "catalog_id": "npc-chat", "mode": "freeform",
                        "presentation_mode": "interactive", "opening": "", "body": "你好！",
                        "segments": [{"kind": "dialogue", "text": "你好！"}], "interaction": None,
                        "suggestions": [], "action_options": [], "status_fields": [], "tick": 1,
                        "state_version": 1, "day": None, "time_of_day": None,
                        "complete": False, "turn_id": "portal-request-1"}

            portal.turn = scripted_turn
            with TestClient(create_app(portal), base_url="http://127.0.0.1") as client:
                response = client.post("/v1/saves/sample/turns/stream", json={
                    "text": "你好", "request_id": "request-1",
                }, headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/event-stream", response.headers["content-type"])
            events = [json.loads(line[6:]) for line in response.text.splitlines()
                      if line.startswith("data: ")]
            self.assertEqual([event["type"] for event in events],
                             ["stage", "stage", "preview", "complete"])
            self.assertEqual(events[-1]["view"]["body"], "你好！")

    def test_local_settings_login_and_api_save(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ,
            {"STORY_MODEL_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
             "LANGFUSE_SECRET_KEY": ""},
        ):
            db = Path(temp) / "portal.sqlite3"
            catalog = ROOT / "examples" / "catalog.json"
            config = ROOT / "config" / "local.json"
            preferences = LocalPreferences(Path(temp) / "settings")
            preferences.save_settings(catalog, config, db)
            preferences.save_model_key("STORY_MODEL_API_KEY", "offline-test")
            portal = build_portal(catalog, load_settings(config), str(db))

            with TestClient(create_app(portal), base_url="http://127.0.0.1") as client:
                self.assertEqual(client.get("/docs").status_code, 200)
                account = client.post("/v1/accounts", json={
                    "username": "tester", "password": "test-pass-123",
                })
                self.assertEqual(account.status_code, 201)
                token = account.json()["token"]
                preferences.save_session(db, "tester", token)
                restored = LocalPreferences(Path(temp) / "settings")
                self.assertEqual(restored.load_settings()["catalog"], str(catalog))
                self.assertNotIn(token, (preferences.directory / "settings.json").read_text())
                self.assertNotIn("offline-test", (preferences.directory / "settings.json").read_text())
                if os.name == "nt":
                    self.assertEqual(restored.model_key("STORY_MODEL_API_KEY"), "offline-test")
                    self.assertEqual(restored.session(db)["token"], token)
                    encrypted = (preferences.directory / "credentials.dpapi").read_bytes()
                    self.assertNotIn(token.encode(), encrypted)
                    self.assertNotIn(b"offline-test", encrypted)
                else:
                    self.assertIsNone(restored.model_key("STORY_MODEL_API_KEY"))
                    self.assertIsNone(restored.session(db))
                    self.assertEqual({path.name for path in preferences.directory.iterdir()},
                                     {"settings.json"})

                headers = {"Authorization": f"Bearer {token}"}
                self.assertEqual(client.get("/v1/billing/wallet", headers=headers)
                                 .json()["balance_points"], "500.000")
                self.assertEqual(client.get("/v1/catalog", headers=headers).json()["games"][0]["id"],
                                 "npc-chat")
                save = client.post("/v1/saves", json={"catalog_id": "npc-chat"}, headers=headers)
                self.assertEqual(save.status_code, 201)
                game_id = save.json()["game_id"]
                self.assertEqual(client.get(f"/v1/saves/{game_id}/player-card", headers=headers).json(),
                                 {"name": "", "fields": []})
                intro = client.get(f"/v1/saves/{game_id}/history", headers=headers)
                self.assertEqual(intro.status_code, 200)
                self.assertIn("港口广场", intro.json()["intro"]["opening"])
                self.assertEqual(intro.json()["turns"], [])
                portal.accounts.store_turn_response(game_id, "test-turn", "我走向码头", {
                    **save.json(), "body": "码头工看向你。", "turn_id": "portal-test-turn",
                })
                history = client.get(f"/v1/saves/{game_id}/history", headers=headers).json()
                self.assertEqual(history["turns"][0]["input"], "我走向码头")
                self.assertEqual(history["turns"][0]["response"]["body"], "码头工看向你。")
                stranger = client.post("/v1/accounts", json={
                    "username": "stranger", "password": "test-pass-123",
                }).json()["token"]
                self.assertEqual(client.get(f"/v1/saves/{game_id}/history", headers={
                    "Authorization": f"Bearer {stranger}",
                }).status_code, 404)
                self.assertEqual(client.post(f"/v1/saves/{game_id}/resume", headers=headers).status_code, 200)
                self.assertEqual(client.get("/v1/saves", headers=headers).json()["saves"][0]["game_id"],
                                 game_id)
                self.assertEqual(client.delete("/v1/sessions/current", headers=headers).status_code, 200)
                self.assertEqual(client.get("/v1/saves", headers=headers).status_code, 401)


if __name__ == "__main__":
    unittest.main()
