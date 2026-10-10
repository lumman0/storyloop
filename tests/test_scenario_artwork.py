"""Private scenario artwork follows player-visible character discovery."""

import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from storyloop_platform.portal.http_api import create_app
from storyloop_platform.config import load_settings
from storyloop_platform.portal.service import PlayerPortal
from storyloop_harness.core.contracts import Observation, WorldEvent
from storyloop_platform.runtime.campaign import CampaignProgram, CampaignSession


ROOT = Path(__file__).resolve().parents[1]


class ScenarioArtworkTests(unittest.TestCase):
    def test_portrait_is_unavailable_until_actor_enters_visible_scene(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_MODEL_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": ""},
        ):
            root = Path(temp)
            package_path = root / "scenario"
            shutil.copytree(ROOT / "examples/freeform", package_path)
            art = package_path / "art"
            art.mkdir()
            (art / "cover.png").write_bytes(b"cover-image")
            (art / "dockhand.png").write_bytes(b"portrait-image")
            manifest_path = package_path / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            program = CampaignProgram.from_dict({
                "id": manifest["id"], "ticks_per_day": manifest["ticks_per_day"],
                "final_tick": 4,
                "steps": [
                    {"id": "arrival", "at": 0, "kind": "scene", "text": "门外是空的。"},
                    {"id": "enter", "at": 0, "kind": "continue", "prompt": "门还关着。", "label": "进门"},
                    {"id": "meeting", "at": 0, "kind": "scene", "text": "码头工走进屋里。"},
                    {"id": "choice", "at": 0, "kind": "choice", "prompt": "打招呼？",
                     "options": [{"id": "yes", "label": "你好"}]},
                    {"id": "ending", "at": 4, "kind": "finale", "choice_key": "choice",
                     "threshold": 0, "success_text": "结束", "other_text": "结束"},
                ],
            })
            (package_path / "campaign.json").write_text(json.dumps({
                "id": program.program_id, "ticks_per_day": program.ticks_per_day,
                "final_tick": program.final_tick, "steps": program.steps,
            }), encoding="utf-8")
            manifest["initial_state"]["campaign"] = program.initial_state(["dockhand"])
            manifest["authored_prologue"] = "你站在门外。"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"games": [{
                "id": "scenario", "title": "测试", "mode": "campaign", "package": "scenario",
                "artwork": {"cover": "art/cover.png",
                            "portraits": {"dockhand": "art/dockhand.png"}},
                "public_profiles": {"dockhand": "在码头工作，熟悉来往船只。"},
            }]}), encoding="utf-8")
            portal = PlayerPortal(catalog, load_settings(ROOT / "config/local.json"), str(root / "game.sqlite3"))
            with TestClient(create_app(portal), base_url="http://127.0.0.1") as client:
                owner = portal.register("owner", "password-123")["token"]
                other = portal.register("other", "password-123")["token"]
                view = asyncio.run(portal.create_save(owner, "scenario"))
                game_id = view["game_id"]
                cover = client.get("/v1/catalog/scenario/artwork/cover",
                                   headers={"Authorization": f"Bearer {owner}"})
                self.assertEqual(cover.status_code, 200)
                self.assertEqual(portal.cast(owner, game_id), [])
                detail = f"/v1/saves/{game_id}/cast/dockhand"
                self.assertEqual(client.get(detail,
                    headers={"Authorization": f"Bearer {owner}"}).status_code, 404)
                portrait = f"/v1/saves/{game_id}/cast/dockhand/portrait"
                self.assertEqual(client.get(portrait,
                    headers={"Authorization": f"Bearer {owner}"}).status_code, 404)
                asyncio.run(CampaignSession(portal.store, program).submit(game_id, "/continue", "enter"))
                self.assertEqual([actor["name"] for actor in portal.cast(owner, game_id)], ["码头工"])
                self.assertEqual(client.get(portrait,
                    headers={"Authorization": f"Bearer {owner}"}).content, b"portrait-image")
                self.assertEqual(client.get(portrait,
                    headers={"Authorization": f"Bearer {other}"}).status_code, 404)
                before = portal.store.load(game_id)
                portal.store.commit(game_id, before.version,
                    WorldEvent("private-news", "noticed", None, None, before.tick, ()),
                    (Observation("private-heard", "private-news", "dockhand", "rumor",
                                 "只有码头工知道的秘密", before.tick),), ())
                before = portal.store.load(game_id)
                portal.store.commit(game_id, before.version,
                    WorldEvent("shared-meeting", "met", None, None, before.tick, ()),
                    (Observation("actor-meeting", "shared-meeting", "dockhand", "shared_experience",
                                 "玩家向你打了招呼", before.tick),
                     Observation("player-meeting", "shared-meeting", "player", "shared_experience",
                                 "你和码头工打了招呼", before.tick)), ())
                card = client.get(detail, headers={"Authorization": f"Bearer {owner}"})
                self.assertEqual(card.status_code, 200)
                self.assertEqual(card.json()["profile"], "在码头工作，熟悉来往船只。")
                self.assertEqual(card.json()["memories"], ["你和码头工打了招呼"])
                self.assertNotIn("秘密", str(card.json()))
                self.assertEqual(client.get(detail,
                    headers={"Authorization": f"Bearer {other}"}).status_code, 404)
