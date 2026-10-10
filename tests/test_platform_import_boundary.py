"""The platform may only import the documented harness surfaces."""
from pathlib import Path

import pytest

from harness_import_guard import harness_import_violations, platform_import_violations


def test_platform_imports_only_public_harness_modules():
    root = Path(__file__).parents[1]
    violations = platform_import_violations(root)
    assert not violations, '\n'.join(f'{path}:{line}: {target}' for path, line, target in violations)


@pytest.mark.parametrize('source', [
    'import storyloop_harness.runtime.single_call',
    'from storyloop_harness.agents.scene_turn import SingleSceneGenerator',
    'from storyloop_harness import core as hidden',
    'import storyloop_harness as h; h.runtime.single_call.SingleCallGameSession',
    'from storyloop_harness import testing; testing.memory.InMemoryGameStore',
    'import importlib as il; il.import_module("storyloop_harness.world.scenario")',
    'from importlib import import_module as load; load("storyloop_harness.agents.scene_turn")',
    '__import__("storyloop_harness.models.agentscope")',
    'from unittest.mock import patch as change; change("storyloop_harness.agents.scene_turn.SingleSceneGenerator.generate")',
    'import unittest.mock as m; m.patch("storyloop_harness.runtime.single_call.SingleCallGameSession.run_turn")',
])
def test_guard_rejects_executable_private_access(source):
    assert harness_import_violations(source)


@pytest.mark.parametrize('source', [
    'from storyloop_harness import ScenarioPackage, TurnEngine',
    'from storyloop_harness.advanced import Snapshot',
    'from storyloop_harness.testing import project_scene_request',
    'from importlib import import_module; import_module("storyloop_harness.testing")',
    'from unittest.mock import patch; patch("storyloop_harness.TurnEngine.run_turn")',
    'source = "from storyloop_harness.runtime.single_call import SingleCallGameSession"',
    'source = "storyloop_harness.agents.scene_turn.SingleSceneGenerator.generate"',
])
def test_guard_allows_public_seams_and_scanner_fixture_strings(source):
    assert not harness_import_violations(source)


def test_boundary_includes_non_test_helper_files(tmp_path):
    (tmp_path / 'tests').mkdir()
    helper = tmp_path / 'tests/wheel_smoke.py'
    helper.write_text('from storyloop_harness.world.scenario import ScenarioPackage', encoding='utf-8')
    assert platform_import_violations(tmp_path) == [
        (Path('tests/wheel_smoke.py'), 1, 'storyloop_harness.world.scenario')]
