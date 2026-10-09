"""Prologue authoring restores only the provider used by its generation task."""
import json
import os
import sys
from types import SimpleNamespace

from storyloop_platform.config import default_settings
from storyloop_platform.portal.local_config import LocalPreferences


def test_prologue_restores_credentials_before_constructing_model(tmp_path, monkeypatch):
    from storyloop_platform.cli import prepare_prologue as command
    settings = default_settings().model_dump(mode="json")
    settings["providers"]["prologue"] = {"base_url": "https://prologue.invalid/v1", "api_key_env": "PROLOGUE_KEY"}
    settings["models"]["prologue"] = {"kind": "chat", "provider": "prologue", "model": "prologue-model"}
    settings["routes"]["prologue"] = "prologue"
    settings["credits"] = None
    config = tmp_path / "settings.json"
    config.write_text(json.dumps(settings))
    monkeypatch.delenv("PROLOGUE_KEY", raising=False)
    monkeypatch.delenv("STORY_MODEL_API_KEY", raising=False)
    preferences = LocalPreferences(tmp_path / "preferences")
    monkeypatch.setattr(preferences, "model_key", lambda name: "offline-prologue" if name == "PROLOGUE_KEY" else None)
    monkeypatch.setattr(command, "LocalPreferences", lambda: preferences, raising=False)
    saved = []
    monkeypatch.setattr(preferences, "save_model_key", lambda *args: saved.append(args))
    monkeypatch.setattr(command.ScenarioPackage, "load", lambda path: SimpleNamespace(authored_prologue=False))
    telemetry = SimpleNamespace(flush=lambda: None)
    monkeypatch.setattr(command, "configured_telemetry", lambda: telemetry)
    model_tasks = []
    class Factory:
        def __init__(self, settings, **kwargs):
            assert os.environ["PROLOGUE_KEY"] == "offline-prologue"
        def create_model(self, task):
            model_tasks.append(task)
            return object()
    monkeypatch.setattr(command, "ModelFactory", Factory)
    class Generator:
        def __init__(self, *args):
            pass
        async def generate(self, *args):
            return "prologue"
    monkeypatch.setattr(command, "ModelPrologueGenerator", Generator)
    monkeypatch.setattr(command, "save_prologue", lambda *args: saved.append(args))
    monkeypatch.setattr(sys, "argv", ["prepare_prologue", str(tmp_path), "--config", str(config), "--title", "Game"])
    command.main()
    assert model_tasks == ["prologue"]
    assert saved == [(tmp_path, "prologue")]
