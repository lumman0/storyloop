"""Shared deployment selection and preflight before constructing portal resources."""
from __future__ import annotations

import getpass
import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from storyloop_platform.config import (
    ModelFactory,
    PlatformResources,
    PlatformSettings,
    default_settings,
    load_settings,
)
from storyloop_platform.portal.local_config import LocalPreferences

if TYPE_CHECKING:
    from storyloop_platform.portal.service import PlayerPortal


def load_profile_settings(config: str | Path | None, profile: str) -> PlatformSettings:
    settings = load_settings(config) if config is not None else default_settings(profile)
    if settings.environment != profile:
        raise ValueError("--profile and config environment disagree")
    return settings


def credential_providers(settings: PlatformSettings, *, tasks: Iterable[str] | None = None,
                         include_memory: bool = True) -> tuple[str, ...]:
    profiles = set()
    for task in settings.routes if tasks is None else tasks:
        settings.model_for(task)
        profiles.add(settings.routes[task])
    if include_memory and settings.player_memory.driver == "mem0":
        profiles.update((settings.player_memory.extraction_profile,
                         settings.player_memory.embedding_profile))
    return tuple(sorted({settings.models[name].provider for name in profiles}))


def prepare_credentials(settings: PlatformSettings, preferences: LocalPreferences | None = None,
                        *, tasks: Iterable[str] | None = None, include_memory: bool = True,
                        prompt: bool = False, require: bool = False) -> tuple[str, ...]:
    """Activate each used env reference once; never persist during preparation."""
    providers = credential_providers(settings, tasks=tasks, include_memory=include_memory)
    names = tuple(sorted({settings.providers[name].api_key_env for name in providers}))
    for name in names:
        if preferences is not None:
            preferences.activate_model_key(name, prompt=prompt, persist=False)
        elif prompt and not os.environ.get(name, "").strip():
            entered = getpass.getpass(f"{name} API Key（输入不回显）: ").strip()
            if entered:
                os.environ[name] = entered
    factory = ModelFactory(settings)
    for provider in providers:
        factory.base_url(provider)
        if require and not factory.api_key(provider):
            raise ValueError(f"set {settings.providers[provider].api_key_env} before model use")
    return names


def persist_credentials(preferences: LocalPreferences, names: Iterable[str]) -> None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value and value != preferences.model_key(name):
            preferences.save_model_key(name, value)


def launch_portal(*, profile: str, config: str | None, catalog: str | None,
                  db: str | None, preferences: LocalPreferences | None,
                  prompt: bool = False,
                  portal_factory: Callable[..., PlayerPortal] | None = None) -> PlayerPortal:
    """Catalog priority: --catalog, STORY_CATALOG, remembered local catalog.

    Explicit config starts a new launch; otherwise restore the local bundle.
    Default settings are represented by absence of a custom config in preferences.
    """
    saved = preferences.load_settings() if preferences is not None and config is None else {}
    selected_config = config if config is not None else saved.get("config")
    selected_catalog = catalog or os.environ.get("STORY_CATALOG") or saved.get("catalog")
    selected_db = db if db is not None else saved.get("db")
    if not selected_catalog:
        raise ValueError("--catalog or STORY_CATALOG is required on first launch or with --config")
    if not Path(selected_catalog).is_file():
        raise ValueError("scenario catalog file does not exist")
    settings = load_profile_settings(selected_config, profile)
    if profile == "online" and selected_db is not None:
        raise ValueError("--db is only available in local mode")
    names = prepare_credentials(settings, preferences, prompt=prompt,
                                require=profile == "online")
    resources = PlatformResources(settings)
    resources.database_url(selected_db)
    resources.allowed_hosts()
    resources.allowed_origins()
    resources.player_memory_enabled()
    if settings.player_memory.driver == "mem0":
        # Disabled collection still constructs clients for read/delete access.
        factory = ModelFactory(settings)
        for provider in credential_providers(settings, tasks=()):
            if not factory.api_key(provider):
                raise ValueError(f"set {settings.providers[provider].api_key_env} before player memory use")
        resources.player_memory_path()
    if profile == "online" and not os.environ.get("STORY_UPLOAD_DIR", "").strip():
        raise ValueError("STORY_UPLOAD_DIR is required in online mode")
    if portal_factory is None:
        from storyloop_platform.bootstrap import build_portal
        portal_factory = build_portal
    portal = portal_factory(selected_catalog, settings, selected_db)
    try:
        if preferences is not None:
            persist_credentials(preferences, names)
            preferences.save_settings(selected_catalog, selected_config, portal.db_path)
    except Exception:
        portal.close()
        raise
    return portal
