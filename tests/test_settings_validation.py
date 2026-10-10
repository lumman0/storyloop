import json
import traceback
from types import SimpleNamespace

import pytest

from storyloop_platform.config import (
    ModelFactory,
    PlatformSettings,
    default_settings,
    load_settings,
)


@pytest.mark.parametrize("entrypoint", ["model_validate", "load_settings"])
@pytest.mark.parametrize("kind", ["secret-kind-value", {"secret-kind-value": 1}])
def test_invalid_model_kind_does_not_leak_in_errors(tmp_path, entrypoint, kind):
    raw = default_settings().model_dump(mode="json")
    raw["models"]["story"]["kind"] = kind
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        if entrypoint == "model_validate":
            PlatformSettings.model_validate(raw)
        else:
            load_settings(path)
    error = caught.value
    assert "models.story" in str(error)
    assert "secret-kind-value" not in str(error)
    assert "secret-kind-value" not in "".join(traceback.format_exception(error))


def test_attribute_validation_does_not_leak_invalid_kind():
    raw = default_settings().model_dump(mode="json")
    raw["models"]["story"] = SimpleNamespace(kind="secret-kind-value")
    with pytest.raises(ValueError) as caught:
        PlatformSettings.model_validate(raw, from_attributes=True)
    assert "models.story" in str(caught.value)
    assert "secret-kind-value" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("entrypoint", ["model_validate", "load_settings", "env"])
@pytest.mark.parametrize(
    "url",
    [
        "https://:443/v1",
        "https://secret-host.invalid:bad/v1",
        "https://secret-host.invalid:65536/v1",
        "https://secret-host.invalid:0/v1",
        "https://secret-host.invalid:/v1",
        "https://[secret-host]/v1",
        "https://[::1]secret-host/v1",
        "https://secret-host\\invalid/v1",
        "https://secret-host..invalid/v1",
        "https://secret-host.invalid../v1",
        "https://999.999.999.999/v1",
    ],
)
def test_invalid_provider_authorities_are_rejected_without_echoing_url(
    tmp_path, entrypoint, url
):
    raw = default_settings().model_dump(mode="json")
    raw["providers"]["default"]["base_url"] = url
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        if entrypoint == "model_validate":
            PlatformSettings.model_validate(raw)
        elif entrypoint == "load_settings":
            load_settings(path)
        else:
            ModelFactory(
                default_settings(), env={"STORY_MODEL_BASE_URL": url}
            ).base_url("default")
    error = caught.value
    assert "base_url" in str(error)
    assert url not in str(error)
    assert "secret-host" not in "".join(traceback.format_exception(error))


@pytest.mark.parametrize("entrypoint", ["model_validate", "env"])
@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8080/v1",
        "http://127.0.0.1:8000/v1",
        "http://[::1]:8000/v1",
        "https://[2001:db8::1]/v1",
        "https://models.example.invalid/v1",
    ],
)
def test_provider_url_accepts_normal_network_endpoints(entrypoint, url):
    raw = default_settings().model_dump(mode="json")
    if entrypoint == "model_validate":
        raw["providers"]["default"]["base_url"] = url
        settings = PlatformSettings.model_validate(raw)
        assert settings.providers["default"].base_url == url
    else:
        factory = ModelFactory(default_settings(), env={"STORY_MODEL_BASE_URL": url})
        assert factory.base_url("default") == url


@pytest.mark.parametrize("environment", ["local", "online"])
def test_memory_profiles_preserve_timeout_and_retry_defaults(environment):
    settings = default_settings(environment)
    for name in ("memory_extraction", "memory_embedding"):
        profile = settings.models[name]
        assert profile.timeout_seconds == 60
        assert profile.connect_timeout_seconds == 10
        assert profile.max_retries == 1
    assert settings.models["story"].timeout_seconds == 90
    assert settings.models["story"].max_retries == 2
