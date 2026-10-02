"""One offline smoke test for persisted preferences and the HTTP adapter."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from story_harness.portal.http_api import create_app
from story_harness.portal.local_config import LocalPreferences
from story_harness.portal.service import PlayerPortal


ROOT = Path(__file__).resolve().parents[1]


class PortalLocalApiSmokeTest(unittest.TestCase):
    def test_streamed_turn_reports_progress_and_final_view(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": ""},
        ):
            portal = PlayerPortal(ROOT / "config" / "games.example.json",
                                  ROOT / "config" / "local.json", str(Path(temp) / "game.sqlite3"))
            token = portal.register("stream-user", "stream-pass-123")["token"]

            async def scripted_turn(auth, game_id, text, request_id, progress=None):
                self.assertEqual((auth, game_id, text, request_id),
                                 (token, "sample", "你好", "request-1"))
                await progress({"type": "stage", "stage": "thinking"})
                await progress({"type": "preview", "segments": [{"kind": "dialogue", "text": "你好！"}]})
                return {"body": "你好！", "segments": [{"kind": "dialogue", "text": "你好！"}]}

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

    def test_local_secret_file_allows_a_save_without_key_environment_variable(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_BAILIAN_API_KEY": "", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": ""},
        ):
            root = Path(temp)
            config = json.loads((ROOT / "config" / "local.json").read_text(encoding="utf-8"))
            (root / "local.json").write_text(json.dumps(config), encoding="utf-8")
            (root / "application.local.json").write_text(json.dumps({
                "schema_version": 1, "models": {"api_key": "file-test-key"},
            }), encoding="utf-8")
            portal = PlayerPortal(ROOT / "config" / "games.example.json",
                                  root / "local.json", str(root / "game.sqlite3"))
            try:
                token = portal.register("file-user", "file-pass-123")["token"]
                view = asyncio.run(portal.create_save(token, "npc-chat"))
                self.assertEqual(view["catalog_id"], "npc-chat")
            finally:
                portal.close()

    def test_local_settings_login_and_api_save(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ,
            {"STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
             "LANGFUSE_SECRET_KEY": ""},
        ):
            db = Path(temp) / "portal.sqlite3"
            catalog = ROOT / "config" / "games.example.json"
            config = ROOT / "config" / "bailian-token-plan.json"
            preferences = LocalPreferences(Path(temp) / "settings")
            preferences.save_settings(catalog, config, db)
            preferences.save_model_key("STORY_BAILIAN_API_KEY", "offline-test")
            portal = PlayerPortal(catalog, config, str(db))

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
                self.assertEqual(restored.model_key("STORY_BAILIAN_API_KEY"), "offline-test")
                self.assertEqual(restored.session(db)["token"], token)
                self.assertNotIn(token, (preferences.directory / "settings.json").read_text())
                self.assertNotIn("offline-test", (preferences.directory / "settings.json").read_text())
                if os.name == "nt":
                    encrypted = (preferences.directory / "credentials.dpapi").read_bytes()
                    self.assertNotIn(token.encode(), encrypted)
                    self.assertNotIn(b"offline-test", encrypted)

                headers = {"Authorization": f"Bearer {token}"}
                self.assertEqual(client.get("/v1/billing/wallet", headers=headers)
                                 .json()["balance_points"], "500.000")
                self.assertEqual(client.get("/v1/catalog", headers=headers).json()["games"][0]["id"],
                                 "npc-chat")
                save = client.post("/v1/saves", json={"catalog_id": "npc-chat"}, headers=headers)
                self.assertEqual(save.status_code, 201)
                game_id = save.json()["game_id"]
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
