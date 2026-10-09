"""Keep current code and tests independent of the removed compatibility package."""
import ast
from pathlib import Path


def test_old_namespace_and_beta_commands_are_absent():
    root = Path(__file__).resolve().parents[1]
    assert not (root / "src/story_harness").exists()
    cli = root / "packages/platform/src/storyloop_platform/cli"
    for name in ("react_play", "live_play", "campaign_play", "demo_check", "interaction_demo"):
        assert not (cli / f"{name}.py").exists()
    for folder in (root / "tests", root / "scripts", root / "packages/platform/src", root / "packages/harness/src"):
        for path in folder.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                modules = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                           else [name.name for name in node.names] if isinstance(node, ast.Import) else [])
                assert not any(name.startswith("story_harness") for name in modules), path
