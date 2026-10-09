"""A campaign package can start as a guided story or an open world save."""

import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from storyloop_platform.portal.service import PlayerPortal
from storyloop_platform.runtime.campaign import CampaignProgram


ROOT = Path(__file__).resolve().parents[1]


class ForbiddenNovelPresenter:
    async def present(self, context):
        raise AssertionError("authored prologue must not wait for a model")


class PlayModeTests(unittest.TestCase):
    def test_mode_is_selected_when_creating_a_save_and_survives_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_path = root / "scenario"
            shutil.copytree(ROOT / "examples/freeform", package_path)
            manifest_path = package_path / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            program = {
                "id": manifest["id"], "ticks_per_day": manifest["ticks_per_day"],
                "final_tick": 4,
                "steps": [
                    {"id": "arrival", "at": 0, "kind": "scene", "text": "来到门前。"},
                    {"id": "enter", "at": 0, "kind": "continue", "prompt": "门还关着。", "label": "推门进去"},
                    {"id": "choice", "at": 0, "kind": "choice", "prompt": "找谁？",
                     "options": [{"id": "dockhand", "label": "码头工"}]},
                    {"id": "ending", "at": 4, "kind": "finale", "choice_key": "choice",
                     "threshold": 0, "success_text": "结束", "other_text": "结束"},
                ],
            }
            (package_path / "campaign.json").write_text(json.dumps(program), encoding="utf-8")
            manifest["initial_state"]["campaign"] = CampaignProgram.from_dict(program).initial_state(
                [actor["id"] for actor in manifest["actors"]]
            )
            manifest["authored_prologue"] = "你来到门前。\n\n门里有人在等你。"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"games": [{"id": "scenario", "title": "测试故事",
                "mode": "campaign", "play_modes": ["campaign", "freeform"],
                "package": "scenario"}]}), encoding="utf-8")
            db_path = str(root / "game.sqlite3")

            with patch.dict(os.environ, {"STORY_BAILIAN_API_KEY": "offline-test"}):
                portal = PlayerPortal(catalog, ROOT / "config/local.json", db_path)
                token = portal.register("mode-player", "password-123")["token"]
                portal._action_options = AsyncMock(return_value=())
                portal._novel_presenter = lambda *_: ForbiddenNovelPresenter()
                self.assertEqual(portal.games(token)[0]["play_modes"], ["campaign", "freeform"])

                guided = asyncio.run(portal.create_save(token, "scenario", "campaign"))
                self.assertEqual(guided["mode"], "campaign")
                self.assertEqual(guided["presentation_mode"], "novel")
                self.assertEqual(guided["opening"], manifest["authored_prologue"])
                self.assertEqual(guided["body"], "")
                self.assertEqual(guided["interaction"]["kind"], "continue")
                self.assertEqual(guided["interaction"]["label"], "推门进去")

                open_world = asyncio.run(portal.create_save(token, "scenario", "freeform"))
                self.assertEqual(open_world["mode"], "freeform")
                self.assertEqual(open_world["presentation_mode"], "interactive")
                self.assertIsNone(open_world["interaction"])
                self.assertNotIn("campaign", portal.store.load(open_world["game_id"]).data)
                self.assertEqual(asyncio.run(portal.resume_save(token, open_world["game_id"]))["mode"],
                                 "freeform")
                self.assertEqual({item["mode"] for item in portal.saves(token)},
                                 {"campaign", "freeform"})
                portal.close()

                reopened = PlayerPortal(catalog, ROOT / "config/local.json", db_path)
                self.assertEqual(asyncio.run(reopened.resume_save(token, open_world["game_id"]))["mode"],
                                 "freeform")
                reopened.close()
