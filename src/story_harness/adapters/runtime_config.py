"""Versioned harness configuration with optional local model credentials."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from agentscope.model import OpenAIChatModel

from story_harness.adapters.model_config import NpcModelConfig
from sqlalchemy import Engine

from story_harness.adapters.sql_database import open_database, sqlite_url, upgrade_database
from story_harness.adapters.sql_store import SQLGameStore
from story_harness.adapters.store import GameStore
from story_harness.adapters.telemetry import Telemetry


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value.strip()


def _positive_int(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _local_model_key(source: Path, models: dict, profile: str) -> str | None:
    filename = models.get("api_key_file")
    if filename is None:
        return None
    if profile != "local":
        raise ValueError("models.api_key_file is available only in local mode")
    target = Path(_string(filename, "models.api_key_file"))
    if not target.is_absolute():
        target = source.parent / target
    if not target.is_file():
        return None
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("local model key file requires schema_version 1")
    credentials = payload.get("models")
    if not isinstance(credentials, dict) or not isinstance(credentials.get("api_key"), str):
        raise ValueError("local model key file requires models.api_key")
    return credentials["api_key"].strip() or None


@dataclass(frozen=True)
class RuntimeSettings:
    max_steps: int
    main_max_iters: int
    npc_max_iters: int
    max_npc_replies: int = 3


@dataclass(frozen=True)
class StorageSettings:
    driver: str
    path: str | None
    url_env: str | None = None


@dataclass(frozen=True)
class HarnessConfig:
    base_url: str
    api_key_env: str
    task_models: Mapping[str, str] = field(repr=False)
    runtime: RuntimeSettings = field(repr=True)
    storage: StorageSettings = field(repr=True)
    memory_driver: str = "in_memory"
    tool_choice_policy: str = "native"
    profile: str = "local"
    allowed_hosts_env: str | None = None
    allowed_origins_env: str | None = None
    local_api_key: str | None = field(default=None, repr=False)

    @classmethod
    def load(cls, path: str | Path) -> HarnessConfig:
        source = Path(path).resolve()
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("unsupported harness config schema_version")
        models = data.get("models")
        runtime = data.get("runtime")
        storage = data.get("storage")
        memory = data.get("memory")
        if not all(isinstance(item, dict) for item in (models, runtime, storage, memory)):
            raise ValueError("models, runtime, storage and memory must be objects")
        if models.get("provider") != "openai_compatible":
            raise ValueError("unsupported model provider")
        tool_choice_policy = models.get("tool_choice_policy", "native")
        if tool_choice_policy not in ("native", "auto_only"):
            raise ValueError("models.tool_choice_policy must be native or auto_only")
        routes = models.get("tasks")
        if not isinstance(routes, dict) or not routes:
            raise ValueError("models.tasks must be a nonempty object")
        task_models = {
            _string(task, "task name"): _string(name, f"model for {task}")
            for task, name in routes.items()
        }
        for required in ("main_react", "npc_reply", "npc_selection", "work_selection", "narration"):
            if required not in task_models:
                raise ValueError(f"models.tasks requires {required}")
        runtime_settings = RuntimeSettings(
            _positive_int(runtime.get("max_steps"), "max_steps"),
            _positive_int(runtime.get("main_max_iters"), "main_max_iters"),
            _positive_int(runtime.get("npc_max_iters"), "npc_max_iters"),
            _positive_int(runtime.get("max_npc_replies", 3), "max_npc_replies"),
        )
        profile = data.get("environment", "local")
        if profile not in {"local", "online"}:
            raise ValueError("environment must be local or online")
        local_api_key = _local_model_key(source, models, profile)
        driver = _string(storage.get("driver"), "storage.driver")
        raw_path = storage.get("path")
        path_base = storage.get("path_base", "config")
        if path_base not in {"config", "cwd"}:
            raise ValueError("storage.path_base must be config or cwd")
        base = source.parent if path_base == "config" else Path.cwd()
        resolved_path = str((base / raw_path).resolve()) if isinstance(raw_path, str) and raw_path else None
        if driver == "sqlite" and resolved_path is None:
            raise ValueError("SQLite storage requires path")
        if profile == "local" and driver != "sqlite":
            raise ValueError("local environment requires SQLite storage")
        url_env = storage.get("url_env")
        if profile == "online" and driver != "postgresql":
            raise ValueError("online environment requires PostgreSQL storage")
        if driver == "postgresql":
            url_env = _string(url_env, "storage.url_env")
        http = data.get("http", {})
        if not isinstance(http, dict):
            raise ValueError("http must be an object")
        hosts_env = http.get("allowed_hosts_env")
        origins_env = http.get("allowed_origins_env")
        if profile == "online":
            hosts_env = _string(hosts_env, "http.allowed_hosts_env")
            origins_env = _string(origins_env, "http.allowed_origins_env")
        memory_driver = _string(memory.get("driver"), "memory.driver")
        if memory_driver != "in_memory":
            raise ValueError(f"memory driver {memory_driver!r} is not installed")
        return cls(
            base_url=_string(models.get("base_url"), "models.base_url"),
            api_key_env=_string(models.get("api_key_env"), "models.api_key_env"),
            task_models=task_models,
            runtime=runtime_settings,
            storage=StorageSettings(driver, resolved_path, url_env),
            memory_driver=memory_driver,
            tool_choice_policy=tool_choice_policy,
            profile=profile,
            allowed_hosts_env=hosts_env,
            allowed_origins_env=origins_env,
            local_api_key=local_api_key,
        )

    def model_api_key(self, env: Mapping[str, str] | None = None) -> str:
        values = os.environ if env is None else env
        return values.get(self.api_key_env, "").strip() or self.local_api_key or ""

    def model_name(self, task: str) -> str:
        try:
            return self.task_models[task]
        except KeyError as error:
            raise ValueError(f"unconfigured model task: {task}") from error

    def create_model(
        self, task: str, env: Mapping[str, str] | None = None,
        telemetry: Telemetry | None = None,
    ) -> OpenAIChatModel:
        api_key = self.model_api_key(env)
        if not api_key:
            raise ValueError(f"set {self.api_key_env} or configure a local model key file before model use")
        return NpcModelConfig(
            self.model_name(task), api_key, self.base_url,
            self.tool_choice_policy,
            telemetry,
            task,
        ).create_model()

    def database_url(self, path_override: str | None = None,
                     env: Mapping[str, str] | None = None) -> str:
        if self.storage.driver == "sqlite":
            return sqlite_url(path_override or self.storage.path or "")
        if path_override:
            raise ValueError("--db is only available in local mode")
        values = os.environ if env is None else env
        name = self.storage.url_env or "DATABASE_URL"
        url = values.get(name, "")
        if not url:
            raise ValueError(f"set {name} for online PostgreSQL storage")
        if not url.startswith("postgresql+psycopg://"):
            raise ValueError(f"{name} must use postgresql+psycopg://")
        return url

    def create_database(self, path_override: str | None = None,
                        env: Mapping[str, str] | None = None) -> Engine:
        url = self.database_url(path_override, env)
        upgrade_database(url)
        return open_database(url)

    def create_store(self, path_override: str | None = None,
                     engine: Engine | None = None) -> GameStore:
        return SQLGameStore(engine or self.create_database(path_override))

    def allowed_hosts(self, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
        if self.profile == "local":
            return ("127.0.0.1", "localhost")
        values = os.environ if env is None else env
        hosts = tuple(item.strip().lower() for item in
                      values.get(self.allowed_hosts_env or "", "").split(",") if item.strip())
        if not hosts or "*" in hosts:
            raise ValueError(f"set {self.allowed_hosts_env} to explicit online hostnames")
        return hosts

    def allowed_origins(self, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
        if self.profile == "local":
            return ()
        values = os.environ if env is None else env
        return tuple(item.strip() for item in
                     values.get(self.allowed_origins_env or "", "").split(",") if item.strip())
