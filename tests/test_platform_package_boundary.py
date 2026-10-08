"""Platform ownership and temporary import compatibility during extraction."""
import ast
import importlib
import json
from pathlib import Path
import tomllib

import pytest


@pytest.mark.parametrize("old,new,symbol", [
    ("portal.service", "portal.service", "PlayerPortal"),
    ("adapters.sql_store", "adapters.sql_store", "SQLGameStore"),
    ("adapters.runtime_config", "adapters.runtime_config", "HarnessConfig"),
    ("runtime.npc_work", "legacy.npc_work", "make_npc_reply_handler"),
])
def test_canonical_platform_objects_and_old_imports_are_identical(old, new, symbol):
    canonical = importlib.import_module(f"storyloop_platform.{new}")
    compatibility = importlib.import_module(f"story_harness.{old}")
    assert compatibility is canonical
    assert getattr(canonical, symbol).__module__ == f"storyloop_platform.{new}"


def test_harness_has_no_reverse_platform_imports():
    root = Path(__file__).resolve().parents[1] / "packages/harness/src/storyloop_harness"
    for source in root.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            modules = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                       else [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
            assert not any(name.startswith(("storyloop_platform", "story_harness")) for name in modules), source


def test_platform_has_no_dependency_on_old_compatibility_package():
    import storyloop_platform
    for source in Path(storyloop_platform.__file__).parent.rglob("*.py"):
        assert "story_harness" not in source.read_text(encoding="utf-8"), source


def test_internal_harness_imports_match_task_6_inventory():
    import storyloop_platform
    root = Path(storyloop_platform.__file__).parent
    actual = {}
    for source in sorted(root.rglob("*.py")):
        imports = []
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("storyloop_harness."):
                imports.append(node.module + ": " + ", ".join(alias.name for alias in node.names))
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names
                               if alias.name.startswith("storyloop_harness."))
        if imports:
            actual[source.relative_to(root).as_posix()] = sorted(set(imports))
    inventory = Path(__file__).resolve().parents[1] / "docs/superpowers/specs/task-6-platform-harness-imports.json"
    assert actual == json.loads(inventory.read_text(encoding="utf-8"))


def test_platform_declares_versioned_harness_dependency():
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "packages/platform/pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["name"] == "storyloop-platform"
    assert metadata["project"]["requires-python"] == ">=3.12"
    assert "storyloop-harness>=0.1,<0.2" in metadata["project"]["dependencies"]
