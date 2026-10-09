"""Platform ownership and distribution boundaries."""
import ast
import importlib
from pathlib import Path
import tomllib

import pytest


@pytest.mark.parametrize("new,symbol", [
    ("portal.service", "PlayerPortal"),
    ("adapters.sql_store", "SQLGameStore"),
    ("adapters.runtime_config", "HarnessConfig"),
])
def test_canonical_platform_objects_are_owned_by_platform(new, symbol):
    canonical = importlib.import_module(f"storyloop_platform.{new}")
    assert getattr(canonical, symbol).__module__ == f"storyloop_platform.{new}"


def test_platform_has_no_dependency_on_old_compatibility_package():
    root = Path(__file__).resolve().parents[1] / "src/storyloop_platform"
    sources = list(root.rglob("*.py"))
    assert sources, f"No platform sources found in {root}"
    for source in sources:
        # Historical path data is allowed for upgrading remembered settings;
        # importing the removed namespace still violates the package boundary.
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            modules = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                       else [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
            assert not any(name.startswith("story_harness") for name in modules), source


def test_platform_declares_versioned_harness_dependency():
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["name"] == "storyloop-platform"
    assert metadata["project"]["requires-python"] == ">=3.12"
    assert "storyloop-harness>=0.2,<0.3" in metadata["project"]["dependencies"]
