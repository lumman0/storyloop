import ast
from pathlib import Path


def test_no_platform_imports():
    root = Path(__file__).parents[1] / 'src/storyloop_harness'
    assert root.is_dir(), 'independent harness source missing'
    forbidden = ('story_harness', 'storyloop_platform', 'sqlalchemy', 'fastapi', 'mem0', 'langfuse')
    for path in root.rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            names = ([node.module or ''] if isinstance(node, ast.ImportFrom) else
                     [item.name for item in node.names] if isinstance(node, ast.Import) else [])
            for name in names:
                assert not any(name == prefix or name.startswith(prefix + '.') for prefix in forbidden), (path, name)
                if 'runtime' in path.parts:
                    assert not any(part.startswith('sql_') for part in name.split('.')), (path, name)


def test_runtime_imports_exclude_platform():
    import subprocess
    import sys
    script = """
import sys
import storyloop_harness
import storyloop_harness.models.agentscope
for name in sys.modules:
    assert not name.startswith(('story_harness', 'storyloop_platform', 'sqlalchemy', 'fastapi', 'mem0', 'langfuse')), name
"""
    subprocess.run([sys.executable, '-I', '-c', script], check=True, capture_output=True)
