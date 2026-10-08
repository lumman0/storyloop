import json
import tempfile
import unittest
from pathlib import Path

from story_harness.adapters.runtime_config import HarnessConfig


DEFAULT = Path(__file__).resolve().parents[1] / "config" / "bailian-token-plan.json"


class HarnessConfigTests(unittest.TestCase):
    def test_standard_profiles_default_to_deepseek_and_keep_task_routing_replaceable(self) -> None:
        root = DEFAULT.parents[1]
        for name in ("local", "online"):
            config = HarnessConfig.load(root / "config" / f"{name}.json")
            self.assertEqual(set(config.task_models.values()), {"deepseek-v4.1-flash"})
            self.assertEqual(config.model_base_url({}),
                             "https://cn-hongkong.dashscope.aliyuncs.com/compatible-mode/v1")
            self.assertIn("deepseek-v4.1-flash", config.billing_policy.rates)
            self.assertEqual(config.runtime.turn_engine, "single_call")
            model = config.create_model("main_react", {"STORY_BAILIAN_API_KEY": "test-key"})
            self.assertEqual(model.extra_body, {"enable_thinking": False})
            self.assertEqual(model.tool_choice_policy, "auto_only")

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
            raw["billing"]["models"]["another-model"] = dict(raw["billing"]["models"]["qwen3.8-max"])
            raw["runtime"]["max_steps"] = 3
            raw["runtime"]["max_npc_replies"] = 2
            raw["runtime"]["turn_engine"] = "single_call"
            path.write_text(json.dumps(raw), encoding="utf-8")

            config = HarnessConfig.load(path)

            self.assertEqual(config.model_name("main_react"), "another-model")
            self.assertEqual(config.runtime.max_steps, 3)
            self.assertEqual(config.runtime.max_npc_replies, 2)
            self.assertEqual(config.runtime.turn_engine, "single_call")
            self.assertEqual(str(config.create_model("main_react", {"STORY_BAILIAN_API_KEY": "x"}).client.base_url), "https://example.invalid/v1/")

    def test_beta_and_unknown_engines_are_rejected(self) -> None:
        for engine in ("multi_agent_beta", "unknown"):
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "harness.json"
                raw = json.loads(DEFAULT.read_text(encoding="utf-8"))
                raw["runtime"]["turn_engine"] = engine
                path.write_text(json.dumps(raw), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "runtime.turn_engine must be single_call"):
                    HarnessConfig.load(path)

    def test_invalid_budget_and_missing_key_fail_before_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "harness.json"
            raw = json.loads(DEFAULT.read_text(encoding="utf-8"))
            raw["runtime"]["max_steps"] = 0
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "max_steps"):
                HarnessConfig.load(path)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "harness.json"
            raw = json.loads(DEFAULT.read_text(encoding="utf-8"))
            raw["models"]["api_key_file"] = "missing.local.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "STORY_BAILIAN_API_KEY"):
                HarnessConfig.load(path).create_model("npc_reply", {})

    def test_local_secret_file_is_loaded_at_startup_with_environment_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            raw = json.loads(DEFAULT.read_text(encoding="utf-8"))
            raw["models"]["api_key_file"] = "application.local.json"
            config_path = folder / "harness.json"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            (folder / "application.local.json").write_text(json.dumps({
                "schema_version": 1, "models": {"api_key": "file-test-key"},
            }), encoding="utf-8")

            config = HarnessConfig.load(config_path)

            self.assertEqual(config.model_api_key({}), "file-test-key")
            self.assertEqual(config.model_api_key({"STORY_BAILIAN_API_KEY": "env-test-key"}),
                             "env-test-key")
            self.assertNotIn("file-test-key", repr(config))
            self.assertEqual(config.create_model("main_react", {}).model_name, "qwen3.8-max")


if __name__ == "__main__":
    unittest.main()
