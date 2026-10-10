"""Packaged defaults and finite deployment overrides."""

from __future__ import annotations

import json
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from .schema import PlatformSettings


def _read(path: Path | Traversable) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise ValueError("settings must contain valid JSON") from None
    if not isinstance(data, dict):
        raise ValueError("settings must be an object")
    return data


def _overlay(base: dict, override: dict) -> dict:
    # Maps replace entirely; only fixed settings sections merge one level.
    merged = dict(base)
    for key, value in override.items():
        if key in {"runtime", "http", "player_memory", "credits"} and isinstance(
            value, dict
        ):
            merged[key] = {**(base.get(key) or {}), **value}
        elif (
            key == "storage"
            and isinstance(value, dict)
            and value.get("driver", base.get(key, {}).get("driver"))
            == base.get(key, {}).get("driver")
        ):
            merged[key] = {**base.get(key, {}), **value}
        else:
            merged[key] = value
    return merged


def _defaults(environment: str) -> dict:
    if not isinstance(environment, str) or environment not in {"local", "online"}:
        raise ValueError("environment must be local or online")
    root = files("storyloop_platform").joinpath("defaults")
    return _overlay(
        _read(root.joinpath("shared.json")), _read(root.joinpath(f"{environment}.json"))
    )


def _resolve(data: dict, base: Path) -> PlatformSettings:
    settings = PlatformSettings.model_validate(data)
    if settings.storage.path is not None:
        directory = Path.cwd() if settings.storage.path_base == "cwd" else base
        storage = settings.storage.model_copy(
            update={"path": str((directory / settings.storage.path).resolve())}
        )
        settings = settings.model_copy(update={"storage": storage})
    return settings


def default_settings(environment: str = "local") -> PlatformSettings:
    return _resolve(_defaults(environment), Path.cwd())


def load_settings(path: str | Path) -> PlatformSettings:
    source = Path(path).resolve()
    override = _read(source)
    environment = override.get("environment", "local")
    defaults = _defaults(environment)
    # External relative paths are relative to their deployment settings file.
    if isinstance(override.get("storage"), dict) and "path" in override["storage"]:
        override["storage"].setdefault("path_base", "config")
    return _resolve(_overlay(defaults, override), source.parent)
