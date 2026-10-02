import json
import tempfile
import unittest
from pathlib import Path

from story_harness.portal.catalog import GameCatalog


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
