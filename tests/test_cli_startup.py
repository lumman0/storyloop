"""Both launch commands obey the same deployment and local launch contract."""
import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from storyloop_platform.config import ModelFactory, PlatformSettings
from storyloop_platform.portal.local_config import LocalPreferences


@pytest.fixture(params=["portal_api", "portal_play"])
def launch(request, tmp_path, monkeypatch):
    command = importlib.import_module("storyloop_platform.cli." + request.param)
    preferences = LocalPreferences(tmp_path / "preferences")
    monkeypatch.setattr(command, "LocalPreferences", lambda: preferences)
    monkeypatch.delenv("STORY_CATALOG", raising=False)
    monkeypatch.delenv("STORY_MODEL_API_KEY", raising=False)
    monkeypatch.setattr(preferences, "model_key", lambda name: None)
    monkeypatch.setattr(preferences, "save_model_key", lambda *args: None)
    creations = []

    def create(catalog, settings, db):
        assert isinstance(settings, PlatformSettings)
        creations.append((catalog, settings, db))
        return SimpleNamespace(settings=settings, model_factory=ModelFactory(settings),
                               db_path=db or settings.storage.path)

    monkeypatch.setattr(command, "PlayerPortal", create)
    if request.param == "portal_api":
        monkeypatch.setattr(command, "serve", lambda *args: None)
    else:
        async def play(*args):
            pass
        monkeypatch.setattr(command, "play", play)
    monkeypatch.setattr(command, "sys", SimpleNamespace(
        stdin=SimpleNamespace(isatty=lambda: False),
        stdout=SimpleNamespace(reconfigure=lambda **kwargs: None)))
    catalog = Path(__file__).resolve().parents[1] / "examples/catalog.json"
    config = tmp_path / "deployment.json"
    config.write_text(json.dumps({"storage": {"path": "selected.sqlite3"}}))
    preferences.save_settings(catalog, config, tmp_path / "saved.sqlite3")

    def run(*args):
        monkeypatch.setattr(sys, "argv", [request.param, *map(str, args)])
        command.main()

    return SimpleNamespace(command=command, preferences=preferences, catalog=catalog,
                           config=config, creations=creations, run=run, root=tmp_path)


def test_explicit_config_uses_its_storage_not_saved_database(launch):
    launch.run("--config", launch.config, "--catalog", launch.catalog)
    assert launch.creations[0][2] is None
    assert launch.creations[0][1].storage.path == str(launch.root / "selected.sqlite3")


def test_explicit_config_does_not_restore_saved_catalog(launch):
    original = (launch.preferences.directory / "settings.json").read_bytes()
    with pytest.raises(SystemExit):
        launch.run("--config", launch.config)
    assert not launch.creations
    assert (launch.preferences.directory / "settings.json").read_bytes() == original


def test_explicit_database_overrides_config_storage(launch):
    override = launch.root / "override.sqlite3"
    launch.run("--config", launch.config, "--catalog", launch.catalog, "--db", override)
    assert launch.creations[0][2] == str(override)


def test_saved_launch_is_restored_as_a_bundle(launch):
    launch.run()
    assert str(launch.creations[0][0]) == str(launch.catalog)
    assert launch.creations[0][2] == str(launch.root / "saved.sqlite3")


def test_environment_catalog_overrides_saved_catalog_but_flag_wins(launch, monkeypatch):
    monkeypatch.setenv("STORY_CATALOG", str(launch.root / "missing.json"))
    with pytest.raises(SystemExit):
        launch.run()
    launch.run("--catalog", launch.catalog)
    assert str(launch.creations[0][0]) == str(launch.catalog)


@pytest.mark.parametrize("failure", ["missing_config", "missing_catalog", "profile", "construction"])
def test_failed_startup_preserves_settings_and_secret_files(launch, monkeypatch, failure):
    path = launch.preferences.directory / "settings.json"
    secret = launch.preferences.directory / "credentials.dpapi"
    secret.write_bytes(b"untouched")
    original = path.read_bytes()
    args = ["--catalog", launch.catalog, "--config", launch.config]
    expected = SystemExit
    if failure == "missing_config":
        args[-1] = launch.root / "missing.json"
    elif failure == "missing_catalog":
        args[1] = launch.root / "missing.json"
    elif failure == "profile":
        launch.config.write_text('{"environment":"online"}')
    else:
        expected = RuntimeError
        monkeypatch.setattr(launch.command, "PlayerPortal", lambda *args: (_ for _ in ()).throw(RuntimeError("failed")))
    with pytest.raises(expected):
        launch.run(*args)
    assert path.read_bytes() == original
    assert secret.read_bytes() == b"untouched"


def test_default_launch_persists_no_package_installation_path(launch):
    launch.run("--config", launch.config, "--catalog", launch.catalog)
    launch.preferences.save_settings(launch.catalog, None, launch.root / "default.sqlite3")
    launch.run()
    assert "config" not in launch.preferences.load_settings()
    assert launch.creations[-1][1].environment == "local"


def test_explicit_configuration_is_loaded_once(launch, monkeypatch):
    from storyloop_platform.cli import startup
    real = startup.load_settings
    loads = []
    def load(path):
        settings = real(path)
        loads.append(settings)
        return settings
    monkeypatch.setattr(startup, "load_settings", load)
    launch.run("--config", launch.config, "--catalog", launch.catalog)
    assert loads == [launch.creations[0][1]]


def test_preference_write_failure_closes_constructed_portal(launch, monkeypatch):
    closed = []
    monkeypatch.setattr(launch.command, "PlayerPortal", lambda *args: SimpleNamespace(
        db_path=str(launch.root / "db"), close=lambda: closed.append(True)))
    monkeypatch.setattr(launch.preferences, "save_settings", lambda *args: (_ for _ in ()).throw(OSError("full")))
    with pytest.raises(OSError):
        launch.run("--config", launch.config, "--catalog", launch.catalog)
    assert closed == [True]


def test_provider_credentials_are_restored_before_construction(launch, monkeypatch):
    from storyloop_platform.config import default_settings
    data = default_settings().model_dump(mode="json")
    data["providers"]["other"] = {"base_url": "https://other.invalid/v1", "api_key_env": "OTHER_KEY"}
    data["providers"]["shared"] = {"base_url": "https://shared.invalid/v1", "api_key_env": "OTHER_KEY"}
    data["models"]["other"] = {"kind": "chat", "provider": "other", "model": "other", "rate": None}
    data["models"]["extract"] = {"kind": "chat", "provider": "shared", "model": "extract"}
    data["models"]["embed"] = {"kind": "embedding", "provider": "other", "model": "embed", "dimensions": 8}
    data["routes"]["narration"] = "other"
    data["credits"] = None
    data["player_memory"] = {"driver": "mem0", "extraction_profile": "extract", "embedding_profile": "embed"}
    launch.config.write_text(json.dumps(data))
    monkeypatch.delenv("OTHER_KEY", raising=False)
    activated = []
    def activate(name, **kwargs):
        activated.append(name)
        os.environ[name] = "offline-key"
        return True
    monkeypatch.setattr(launch.preferences, "activate_model_key", activate)
    def create(catalog, settings, db):
        assert os.environ["OTHER_KEY"] == os.environ["STORY_MODEL_API_KEY"] == "offline-key"
        return SimpleNamespace(db_path=settings.storage.path)
    monkeypatch.setattr(launch.command, "PlayerPortal", create)
    launch.run("--config", launch.config, "--catalog", launch.catalog)
    assert sorted(activated) == ["OTHER_KEY", "STORY_MODEL_API_KEY"]


@pytest.mark.parametrize("missing", ["key", "database", "hosts", "upload", "memory", "memory_flag"])
def test_online_preflight_fails_before_service_or_writes(launch, monkeypatch, missing):
    launch.config.write_text('{"environment":"online"}')
    for name, value in {"STORY_MODEL_API_KEY": "offline", "DATABASE_URL": "postgresql+psycopg://a:b@localhost/game",
                        "STORY_ALLOWED_HOSTS": "story.invalid", "STORY_UPLOAD_DIR": str(launch.root / "uploads"),
                        "STORY_MEMORY_DIR": str(launch.root / "memory"), "STORY_PLAYER_MEMORY_ENABLED": "0"}.items():
        monkeypatch.setenv(name, value)
    name = {"key": "STORY_MODEL_API_KEY", "database": "DATABASE_URL", "hosts": "STORY_ALLOWED_HOSTS",
            "upload": "STORY_UPLOAD_DIR", "memory": "STORY_MEMORY_DIR", "memory_flag": "STORY_PLAYER_MEMORY_ENABLED"}[missing]
    if missing == "memory_flag":
        monkeypatch.setenv(name, "invalid")
    else:
        monkeypatch.delenv(name)
    with pytest.raises(SystemExit):
        launch.run("--profile", "online", "--config", launch.config, "--catalog", launch.catalog)
    assert not launch.creations
    assert not (launch.root / "uploads").exists()
    assert not (launch.root / "memory").exists()
