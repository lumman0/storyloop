import json
import tempfile
import unittest
from pathlib import Path

from story_harness.adapters.runtime_config import HarnessConfig


DEFAULT = Path(__file__).resolve().parents[1] / "config" / "bailian-token-plan.json"


class HarnessConfigTests(unittest.TestCase):
    def test_default_routes_are_loaded_without_a_secret(self) -> None:
        config = HarnessConfig.load(DEFAULT)

        self.assertEqual(config.model_name("npc_selection"), "qwen3.8-flash")
        self.assertEqual(config.model_name("main_react"), "qwen3.8-max")
        self.assertEqual(config.runtime.max_steps, 8)
        self.assertEqual(config.runtime.max_npc_replies, 3)
        self.assertEqual(config.storage.driver, "sqlite")
        self.assertEqual(config.tool_choice_policy, "auto_only")
        self.assertNotIn("sk-sp-", DEFAULT.read_text(encoding="utf-8"))

        model = config.create_model("npc_reply", {"STORY_BAILIAN_API_KEY": "test-key"})
        self.assertEqual(model.model_name, "qwen3.8-max")
        self.assertEqual(str(model.client.base_url), "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/")

    def test_model_and_runtime_are_replaceable_in_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "harness.json"
            raw = json.loads(DEFAULT.read_text(encoding="utf-8"))
            raw["models"]["base_url"] = "https://example.invalid/v1"
            raw["models"]["tasks"]["main_react"] = "another-model"
            raw["runtime"]["max_steps"] = 3
            raw["runtime"]["max_npc_replies"] = 2
            path.write_text(json.dumps(raw), encoding="utf-8")

            config = HarnessConfig.load(path)

            self.assertEqual(config.model_name("main_react"), "another-model")
            self.assertEqual(config.runtime.max_steps, 3)
            self.assertEqual(config.runtime.max_npc_replies, 2)
            self.assertEqual(str(config.create_model("main_react", {"STORY_BAILIAN_API_KEY": "x"}).client.base_url), "https://example.invalid/v1/")

    def test_invalid_budget_and_missing_key_fail_before_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "harness.json"
            raw = json.loads(DEFAULT.read_text(encoding="utf-8"))
            raw["runtime"]["max_steps"] = 0
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "max_steps"):
                HarnessConfig.load(path)

        with self.assertRaisesRegex(ValueError, "STORY_BAILIAN_API_KEY"):
            HarnessConfig.load(DEFAULT).create_model("npc_reply", {})


if __name__ == "__main__":
    unittest.main()
