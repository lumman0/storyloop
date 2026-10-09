import json
import os
import subprocess
import sys
import unittest

from storyloop_platform.cli.demo import run_demo


class DemoTests(unittest.TestCase):
    def test_window_event_propagates_only_through_observation_and_telling(self) -> None:
        result = run_demo()

        self.assertTrue(result["window_broken"])
        self.assertEqual(result["A"], ["亲眼看到玩家打破窗户"])
        self.assertEqual(result["B"], ["A 告诉我玩家打破了窗户"])
        self.assertEqual(result["C"], [])
        self.assertEqual(result["player"], ["亲眼看到玩家打破窗户"])
        self.assertEqual(result["processed"], ["break", "tell"])

    def test_absent_witness_cannot_spread_the_event(self) -> None:
        result = run_demo(a_present=False)

        self.assertEqual(result["A"], [])
        self.assertEqual(result["B"], [])
        self.assertEqual(result["C"], [])
        self.assertEqual(result["processed"], ["break"])

    def test_cli_outputs_chinese_when_terminal_default_is_cp950(self) -> None:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["PYTHONIOENCODING"] = "cp950"

        completed = subprocess.run(
            [sys.executable, "-m", "storyloop_platform.cli.demo"],
            env=environment,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", errors="replace"))
        self.assertEqual(json.loads(completed.stdout.decode("utf-8"))["A"], ["亲眼看到玩家打破窗户"])


if __name__ == "__main__":
    unittest.main()
