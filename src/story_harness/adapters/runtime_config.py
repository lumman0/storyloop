"""Versioned harness configuration; secrets stay in the process environment."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from agentscope.model import OpenAIChatModel

from story_harness.adapters.model_config import NpcModelConfig
from story_harness.adapters.store import GameStore, SQLiteGameStore
from story_harness.adapters.telemetry import Telemetry


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value.strip()


def _positive_int(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be positive")
    return value


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


@dataclass(frozen=True)
class HarnessConfig:
    base_url: str
    api_key_env: str
    task_models: Mapping[str, str] = field(repr=False)
    runtime: RuntimeSettings = field(repr=True)
    storage: StorageSettings = field(repr=True)
    memory_driver: str = "in_memory"
    tool_choice_policy: str = "native"

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
        driver = _string(storage.get("driver"), "storage.driver")
        raw_path = storage.get("path")
        resolved_path = str((source.parent / raw_path).resolve()) if isinstance(raw_path, str) and raw_path else None
        if driver == "sqlite" and resolved_path is None:
            raise ValueError("SQLite storage requires path")
        memory_driver = _string(memory.get("driver"), "memory.driver")
        if memory_driver != "in_memory":
            raise ValueError(f"memory driver {memory_driver!r} is not installed")
        return cls(
            base_url=_string(models.get("base_url"), "models.base_url"),
            api_key_env=_string(models.get("api_key_env"), "models.api_key_env"),
            task_models=task_models,
            runtime=runtime_settings,
            storage=StorageSettings(driver, resolved_path),
            memory_driver=memory_driver,
            tool_choice_policy=tool_choice_policy,
        )

    def model_name(self, task: str) -> str:
        try:
            return self.task_models[task]
        except KeyError as error:
            raise ValueError(f"unconfigured model task: {task}") from error

    def create_model(
        self, task: str, env: Mapping[str, str] | None = None,
        telemetry: Telemetry | None = None,
    ) -> OpenAIChatModel:
        values = os.environ if env is None else env
        api_key = values.get(self.api_key_env, "")
        if not api_key:
            raise ValueError(f"set {self.api_key_env} before model use")
        return NpcModelConfig(
            self.model_name(task), api_key, self.base_url,
            self.tool_choice_policy,
            telemetry,
            task,
        ).create_model()

    def create_store(self, path_override: str | None = None) -> GameStore:
        if self.storage.driver == "sqlite":
            return SQLiteGameStore(path_override or self.storage.path)
        raise ValueError(f"storage driver {self.storage.driver!r} is not installed")
