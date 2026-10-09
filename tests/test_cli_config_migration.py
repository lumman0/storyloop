"""Remembered package defaults migrate without masking user configuration errors."""
import importlib
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest

from storyloop_platform.config import load_settings
from storyloop_platform.portal.local_config import LocalPreferences


@pytest.fixture(params=["portal_api", "portal_play"])
def launch(request, tmp_path, monkeypatch):
    command = importlib.import_module("storyloop_platform.cli." + request.param)
    default = Path(command.__file__).resolve().parents[1] / "defaults/local.json"
    preferences = LocalPreferences(tmp_path / "preferences")
    catalog, database = tmp_path / "catalog.json", tmp_path / "remembered.sqlite3"
    # A successful startup must not rewrite or remove the independent credentials file.
    preferences.directory.mkdir()
    credentials = preferences.directory / "credentials.dpapi"
    credentials.write_bytes(b"existing session and model credentials")
    starts = []
    creations = []

    def create_portal(selected_catalog, selected_config, selected_db):
        config = load_settings(selected_config)
        creations.append((str(selected_catalog), str(selected_config), str(selected_db)))
        return SimpleNamespace(config=config, db_path=selected_db)

    monkeypatch.setattr(command, "LocalPreferences", lambda: preferences)
    monkeypatch.setattr(command, "PlayerPortal", create_portal)
    monkeypatch.setenv("STORY_MODEL_API_KEY", "offline-test")
    monkeypatch.setattr(command, "sys", SimpleNamespace(
        stdout=SimpleNamespace(reconfigure=lambda **_: None),
        stdin=SimpleNamespace(isatty=lambda: False)))
    if request.param == "portal_api":
        monkeypatch.setattr(command, "serve", lambda *args: starts.append(args))
    else:
        async def play(*args):
            starts.append(args)
        monkeypatch.setattr(command, "play", play)

    def run(saved_config, explicit=None):
        preferences.save_settings(catalog, saved_config, database)
        original = (preferences.directory / "settings.json").read_bytes()
        monkeypatch.setattr(sys, "argv", [request.param] + (
            ["--config", str(explicit)] if explicit is not None else []))
        return original, command.main

    return SimpleNamespace(run=run, default=default, preferences=preferences,
                           old=tmp_path / "old-install/story_harness/defaults/local.json",
                           catalog=catalog, database=database, credentials=credentials,
                           starts=starts, creations=creations, command=command)


@pytest.mark.parametrize("selection", ["missing_old", "explicit", "existing_old", "existing_custom"])
def test_startup_selects_config_and_preserves_other_preferences(launch, tmp_path, selection):
    saved = launch.old
    expected = launch.default
    explicit = None
    if selection in {"explicit", "existing_custom"}:
        expected = tmp_path / "custom.json"
        shutil.copy(launch.default, expected)
        if selection == "explicit":
            explicit = expected
        else:
            saved = expected
    elif selection == "existing_old":
        launch.old.parent.mkdir(parents=True)
        shutil.copy(launch.default, launch.old)
        expected = launch.old
    _, main = launch.run(saved, explicit)
    main()
    assert launch.creations == [(str(launch.catalog), str(expected), str(launch.database))]
    assert len(launch.starts) == 1
    assert launch.preferences.load_settings() == {
        "catalog": str(launch.catalog), "config": str(expected), "db": str(launch.database)}
    assert launch.credentials.read_bytes() == b"existing session and model credentials"


@pytest.mark.parametrize("selection", ["missing_custom", "explicit_missing_old", "wrong_profile"])
def test_missing_user_config_still_errors_without_rewriting_preferences(launch, tmp_path, selection):
    saved = (tmp_path / "missing-custom.json" if selection == "missing_custom" else
             launch.old.with_name("online.json") if selection == "wrong_profile" else launch.old)
    explicit = launch.old if selection == "explicit_missing_old" else None
    original, main = launch.run(saved, explicit)
    with pytest.raises(FileNotFoundError):
        main()
    assert not launch.creations
    assert not launch.starts
    assert (launch.preferences.directory / "settings.json").read_bytes() == original


def test_failed_portal_initialization_does_not_persist_migrated_default(launch, monkeypatch):
    def fail(*args):
        raise RuntimeError("portal initialization failed")
    monkeypatch.setattr(launch.command, "PlayerPortal", fail)
    original, main = launch.run(launch.old)
    with pytest.raises(RuntimeError, match="portal initialization failed"):
        main()
    assert (launch.preferences.directory / "settings.json").read_bytes() == original
