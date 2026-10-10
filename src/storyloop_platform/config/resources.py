"""Resolve deployment environment and assemble platform resources."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from storyloop_platform.adapters.store import GameStore
    from storyloop_platform.portal.billing import BillingPolicy
from .schema import PlatformSettings


class PlatformResources:
    def __init__(
        self, settings: PlatformSettings, *, env: Mapping[str, str] | None = None
    ) -> None:
        self.settings = settings
        self._env = os.environ if env is None else env

    @property
    def billing_policy(self) -> BillingPolicy | None:
        from storyloop_platform.portal.billing import BillingPolicy, ModelRate

        credits = self.settings.credits
        if credits is None:
            return None
        rates = {
            profile.model: ModelRate(
                input_rmb_per_million=profile.rate.input_rmb_per_million,
                output_rmb_per_million=profile.rate.output_rmb_per_million,
                cached_input_rmb_per_million=profile.rate.cached_input_rmb_per_million,
                multiplier=profile.rate.multiplier,
            )
            for profile in self.settings.models.values()
            if profile.rate is not None
        }
        versions = sorted(
            {
                profile.rate.pricing_version
                for profile in self.settings.models.values()
                if profile.rate
            }
        )
        return BillingPolicy(
            welcome_points=credits.welcome_points,
            points_per_rmb=credits.points_per_rmb,
            pricing_version=";".join(versions),
            rates=rates,
        )

    def database_url(self, path_override: str | None = None) -> str:
        from storyloop_platform.adapters.sql_database import sqlite_url

        storage = self.settings.storage
        if storage.driver == "sqlite":
            return sqlite_url(path_override or storage.path or "")
        if path_override:
            raise ValueError("--db is only available in local mode")
        url = self._env.get(storage.url_env, "")
        if not url:
            raise ValueError(f"set {storage.url_env} for online PostgreSQL storage")
        if not url.startswith("postgresql+psycopg://"):
            raise ValueError(f"{storage.url_env} must use postgresql+psycopg://")
        return url

    def create_database(self, path_override: str | None = None) -> Engine:
        from storyloop_platform.adapters.sql_database import (
            open_database,
            upgrade_database,
        )

        url = self.database_url(path_override)
        upgrade_database(url)
        return open_database(url)

    def create_store(self, *, engine: Engine) -> GameStore:
        from storyloop_platform.adapters.sql_store import SQLGameStore

        return SQLGameStore(engine)

    def allowed_hosts(self) -> tuple[str, ...]:
        if self.settings.environment == "local":
            return ("127.0.0.1", "localhost")
        name = self.settings.http.allowed_hosts_env
        hosts = tuple(
            item.strip().lower()
            for item in self._env.get(name, "").split(",")
            if item.strip()
        )
        if not hosts or "*" in hosts:
            raise ValueError(f"set {name} to explicit online hostnames")
        return hosts

    def allowed_origins(self) -> tuple[str, ...]:
        if self.settings.environment == "local":
            return ()
        return tuple(
            item.strip()
            for item in self._env.get(self.settings.http.allowed_origins_env, "").split(
                ","
            )
            if item.strip()
        )

    def player_memory_enabled(self) -> bool:
        memory = self.settings.player_memory
        if memory.driver == "none":
            return False
        if memory.enabled_env is None:
            return True
        raw = self._env.get(memory.enabled_env, "0").strip().lower()
        if raw not in {"0", "1", "false", "true"}:
            raise ValueError(f"{memory.enabled_env} must be 0 or 1")
        return raw in {"1", "true"}

    def player_memory_path(self) -> Path:
        memory = self.settings.player_memory
        if memory.path_env:
            raw = self._env.get(memory.path_env, "").strip()
            if not raw:
                raise ValueError(f"set {memory.path_env} for player memory storage")
            return Path(raw).resolve()
        if self.settings.storage.path is None:
            raise ValueError("player memory storage path is not configured")
        return Path(self.settings.storage.path).resolve().parent / "player-memory"
