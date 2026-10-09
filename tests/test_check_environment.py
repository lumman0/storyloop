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
        env = dict(os.environ, PYTHONPATH=str(import_root or ROOT / "packages/platform/src"))
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--config", str(config)],
            cwd=ROOT, env=env, text=True, capture_output=True, check=False,
        )

    def test_reports_baseline_without_config_or_environment_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"storage": {"driver": "postgresql",
                "url": "postgresql://name:secret-password@host/db"},
                "models": {"api_key": "secret-model-key"}}), encoding="utf-8")
            result = self.run_check(config)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"python: {Path(sys.executable).resolve()}", result.stdout)
        self.assertIn(f"storyloop_platform: {(ROOT / 'packages/platform/src/storyloop_platform/__init__.py').resolve()}", result.stdout)
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
        self.assertIn("cannot read storage driver", result.stderr)
        self.assertNotIn("secret-password", result.stdout + result.stderr)

    def test_missing_config_is_nonzero(self):
        result = self.run_check(ROOT / "config/not-present.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot read storage driver", result.stderr)
