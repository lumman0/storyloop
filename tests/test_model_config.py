import unittest

from story_harness.adapters.model_config import BailianModelRouter, NpcModelConfig


class NpcModelConfigTests(unittest.TestCase):
    def test_bailian_token_plan_routes_light_and_deep_tasks(self) -> None:
        router = BailianModelRouter.from_environment({"STORY_BAILIAN_API_KEY": "test-token"})

        light = router.create_model("npc_selection")
        deep = router.create_model("npc_reply")

        self.assertEqual(light.model_name, "qwen3.8-flash")
        self.assertEqual(deep.model_name, "qwen3.8-max")
        self.assertEqual(str(light.client.base_url), "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/")
        self.assertNotIn("test-token", repr(router))

    def test_openai_compatible_endpoint_is_configured_without_a_network_call(self) -> None:
        config = NpcModelConfig.from_environment({
            "STORY_NPC_MODEL": "cheap-model",
            "STORY_NPC_BASE_URL": "https://example.invalid/v1",
            "STORY_NPC_API_KEY": "test-token",
        })

        model = config.create_model()

        self.assertEqual(model.model_name, "cheap-model")
        self.assertEqual(str(model.client.base_url), "https://example.invalid/v1/")
        self.assertFalse(model.stream)

    def test_missing_model_or_key_is_reported_before_play(self) -> None:
        with self.assertRaisesRegex(ValueError, "STORY_NPC_MODEL"):
            NpcModelConfig.from_environment({})
        with self.assertRaisesRegex(ValueError, "STORY_NPC_API_KEY"):
            NpcModelConfig.from_environment({"STORY_NPC_MODEL": "small"})


if __name__ == "__main__":
    unittest.main()
