"""The platform may only import the documented harness surfaces."""
import ast
from pathlib import Path


def test_platform_imports_only_public_harness_modules():
    allowed = {'storyloop_harness', 'storyloop_harness.contracts', 'storyloop_harness.ports',
               'storyloop_harness.advanced', 'storyloop_harness.generation',
               'storyloop_harness.telemetry', 'storyloop_harness.usage'}
    root = Path(__file__).parents[1] / 'packages/platform/src/storyloop_platform'
    violations = []
    for path in root.rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) else
                       [item.name for item in node.names] if isinstance(node, ast.Import) else [])
            if isinstance(node, ast.ImportFrom) and node.module == 'storyloop_harness':
                for alias in node.names:
                    if alias.name in {'core', 'runtime', 'world', 'agents', 'models', 'adapters'}:
                        violations.append(f'{path.relative_to(root)}:{node.lineno}: {alias.name}')
            for module in modules:
                if module and module.startswith('storyloop_harness') and module not in allowed:
                    violations.append(f'{path.relative_to(root)}:{node.lineno}: {module}')
    assert not violations, '\n'.join(violations)
