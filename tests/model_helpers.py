"""Small typed model fixture for offline SDK behavior tests."""

from storyloop_platform.config import ModelFactory, PlatformSettings, default_settings


def create_test_model(
    model="test-model",
    key="test-key",
    base_url="https://example.invalid/v1",
    *,
    tool_choice_policy="native",
    task="model",
):
    raw = default_settings().model_dump(mode="json")
    raw["providers"]["default"]["base_url"] = base_url
    raw["models"]["story"]["extra_body"] = {}
    raw["models"]["story"]["model"] = model
    raw["models"]["story"]["tool_choice_policy"] = tool_choice_policy
    raw["models"]["story"]["structured_output_transport"] = "auto"
    return ModelFactory(
        PlatformSettings.model_validate(raw), env={"STORY_MODEL_API_KEY": key}
    ).create_profile("story", task=task)
