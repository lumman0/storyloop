import asyncio
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from story_harness.cli.react_play import DEFAULT_CONFIG, play


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "freeform"


class ReactPlayCliTests(unittest.TestCase):
    def test_new_game_shows_opening_once_before_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            db = str(Path(directory) / "game.sqlite3")
            with patch.dict("os.environ", {"STORY_BAILIAN_API_KEY": "test-key"}), patch(
                "builtins.input", return_value="/quit"
            ), redirect_stdout(output):
                asyncio.run(play(str(EXAMPLE), str(DEFAULT_CONFIG), "game", db))
                asyncio.run(play(str(EXAMPLE), str(DEFAULT_CONFIG), "game", db))
            self.assertEqual(output.getvalue().count("你来到港口广场"), 1)
            self.assertIn("你现在想做什么？", output.getvalue())

    def test_completed_turn_shows_guidance_after_story_and_status(self) -> None:
        class FakeSession:
            def __init__(self, store):
                self.store = store

            async def run_turn(self, game_id, player_text, turn_id):
                return SimpleNamespace(narration="【码头工】\n你好。",
                                       snapshot=self.store.load(game_id),
                                       narration_fallback=False)

        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            db = str(Path(directory) / "game.sqlite3")
            with patch.dict("os.environ", {"STORY_BAILIAN_API_KEY": "test-key"}), patch(
                "builtins.input", side_effect=["你好", "/quit"]
            ), patch("story_harness.cli.react_play.make_react_session",
                     side_effect=lambda config, package, store, values, telemetry: FakeSession(store)), \
                    redirect_stdout(output):
                asyncio.run(play(str(EXAMPLE), str(DEFAULT_CONFIG), "game", db))

            rendered = output.getvalue()
            self.assertLess(rendered.index("【码头工】\n你好。"), rendered.index("[tick 0 | turn "))
            self.assertLess(rendered.index("[tick 0 | turn "), rendered.index("── 下一步建议 ──"))
            self.assertIn("可以和码头工交谈", rendered)


if __name__ == "__main__":
    unittest.main()
