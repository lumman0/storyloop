import json
import tempfile
import unittest
from pathlib import Path

from story_harness.portal.catalog import GameCatalog
from story_harness.portal.service import PlayerPortal
from story_harness.world.scenario import ScenarioPackage


ROOT = Path(__file__).resolve().parents[1]


class CatalogRetirementTests(unittest.TestCase):
    def test_retired_game_is_hidden_but_remains_resolvable_for_old_saves(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "games.json"
            package = str(ROOT / "examples" / "freeform")
            path.write_text(json.dumps({"games": [
                {"id": "old", "title": "旧游戏", "mode": "freeform",
                 "package": package, "retired": True},
                {"id": "new", "title": "新游戏", "mode": "freeform",
                 "package": package},
            ]}), encoding="utf-8")
            catalog = GameCatalog.load(path)
            self.assertEqual([item.game_id for item in catalog.list_games()], ["new"])
            self.assertTrue(catalog.get("old").retired)

    def test_retired_scenario_remains_in_owners_save_list(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "games.json"
            package = str(ROOT / "examples" / "freeform")
            path.write_text(json.dumps({"games": [
                {"id": "old", "title": "旧游戏", "mode": "freeform",
                 "package": package, "retired": True},
            ]}), encoding="utf-8")
            portal = PlayerPortal(path, ROOT / "config/local.json",
                                  str(Path(temp) / "portal.sqlite3"))
            player_id = portal.accounts.register("old-save-owner", "password-123")
            token = portal.accounts.issue_token(player_id)
            listing = portal.catalog.get("old")
            ScenarioPackage.load(listing.package_path).seed_game(portal.store, "old-save")
            portal.accounts.create_save(player_id, "old", "old-save", listing.package_id,
                                        listing.package_version, listing.fingerprint)

            self.assertEqual(portal.saves(token)[0]["title"], "旧游戏")
            self.assertTrue(portal.saves(token)[0]["available"])
