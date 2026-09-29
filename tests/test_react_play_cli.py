import asyncio
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
