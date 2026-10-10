import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_environment.py"


class EnvironmentCheckTests(unittest.TestCase):
    def run_check(self, config, import_root=None):
        env = dict(os.environ, PYTHONPATH=str(import_root or ROOT / "src"))
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--config", str(config)],
            cwd=ROOT, env=env, text=True, capture_output=True, check=False,
        )

    def test_reports_baseline_without_config_or_environment_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"environment": "online",
                "storage": {"driver": "postgresql", "url_env": "CHECK_DATABASE_URL"}}), encoding="utf-8")
            result = self.run_check(config)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"python: {Path(sys.executable).resolve()}", result.stdout)
        self.assertIn(f"storyloop_platform: {(ROOT / 'src/storyloop_platform/__init__.py').resolve()}", result.stdout)
        self.assertRegex(result.stdout, r"git_sha: [0-9a-f]{40}")
        self.assertIn(f"config: {config.resolve()}", result.stdout)
        self.assertIn("storage_driver: postgresql", result.stdout)
        self.assertNotIn("secret-", result.stdout + result.stderr)
        self.assertNotIn("postgresql://", result.stdout + result.stderr)

    def test_rejects_import_from_another_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "storyloop_platform"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            result = self.run_check(ROOT / "config/local.json", Path(directory))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("import root does not match", result.stderr)

    def test_rejects_untrusted_driver_without_echoing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"storage": {"driver": "secret-password"}}), encoding="utf-8")
            result = self.run_check(config)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot load settings", result.stderr)
        self.assertNotIn("secret-password", result.stdout + result.stderr)

    def test_missing_config_is_nonzero(self):
        result = self.run_check(ROOT / "config/not-present.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot load settings", result.stderr)

    def test_rejects_invalid_settings_without_echoing_payload(self):
        payloads = [
            '{"storage":{"driver":"sqlite"},"runtime":{"max_step":"secret-model-key"}}',
            '{"storage":{"driver":"sqlite"},"models":{"secret-model-key":{"kind":"secret-password"}}}',
            '{"storage":{"driver":"sqlite","url":"postgresql://name:secret-password@host/db"}}',
            '{"storage":{"driver":"sqlite"},"runtime": "secret-model-key"}',
            '{"secret-model-key":',
            '["secret-model-key"]',
        ]
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            for payload in payloads:
                with self.subTest(payload=payload):
                    config.write_text(payload, encoding="utf-8")
                    result = self.run_check(config)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("cannot load settings", result.stderr)
                    self.assertNotIn("secret-", result.stdout + result.stderr)
                    self.assertNotIn("postgresql://", result.stdout + result.stderr)

    def test_checker_has_no_runtime_imports_or_environment_reads(self):
        code = '''
import builtins, os, runpy, sys
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.split(".")[0] in {"agentscope", "openai", "mem0", "sqlalchemy", "win32crypt"}:
        raise AssertionError("runtime import: " + name)
    return original_import(name, *args, **kwargs)
class NoEnvironment(dict):
    def get(self, *args, **kwargs):
        if args[0].startswith(("STORY_", "LANGFUSE_", "DATABASE_", "CHECK_")):
            raise AssertionError("credential/environment read")
        return super().get(*args, **kwargs)
builtins.__import__ = guarded_import
os.environ = NoEnvironment(os.environ)
sys.argv = [sys.argv[1]]
runpy.run_path(sys.argv[0], run_name="__main__")
'''
        result = subprocess.run(
            [sys.executable, "-c", code, str(SCRIPT)], cwd=ROOT,
            env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("storage_driver: sqlite", result.stdout)
