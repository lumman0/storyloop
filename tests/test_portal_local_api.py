"""One offline smoke test for persisted preferences and the HTTP adapter."""

from __future__ import annotations

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
