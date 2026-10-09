"""Install release artifacts outside the checkout and exercise the product boundary."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def test_platform_wheels_run_without_checkout_or_old_distribution():
    # UV_OFFLINE/UV_CACHE_DIR may be supplied by an offline verification runner.
    env = {key: value for key, value in os.environ.items()
           if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}}
    env.update(PYTHONIOENCODING="utf-8", STORY_BAILIAN_API_KEY="offline-test",
               LANGFUSE_PUBLIC_KEY="", LANGFUSE_SECRET_KEY="")
    with tempfile.TemporaryDirectory(prefix="storyloop-wheel-") as directory:
        work = Path(directory)
        assert not work.is_relative_to(ROOT)

        def run(*command):
            result = subprocess.run(command, cwd=work, env=env, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=300)
            assert result.returncode == 0, result.stdout + result.stderr
            return result.stdout

        wheels = work / "wheels"
        for name in ("harness", "platform"):
            source = work / "sources" / name
            shutil.copytree(ROOT / "packages" / name, source, ignore=shutil.ignore_patterns(
                "build", "dist", "*.egg-info", "__pycache__", "node_modules", "web", "deploy"))
            run("uv", "build", "--no-sources", "--wheel", str(source),
                "--out-dir", str(wheels))
        run("uv", "venv", "--python", "3.12", str(work / "venv"))
        python = work / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        harness = next(wheels.glob("storyloop_harness-*.whl"))
        platform = next(wheels.glob("storyloop_platform-*.whl"))
        run("uv", "pip", "install", "--python", str(python), str(harness),
            str(platform) + "[portal]")
        shutil.copytree(ROOT / "examples/freeform", work / "scenario")
        shutil.copy(ROOT / "tests/wheel_smoke.py", work / "smoke.py")
        shutil.copy(ROOT / "alembic.ini", work / "alembic.ini")
        assert "offline player turn passed" in run(str(python), "-I", "smoke.py")
        run(str(python), "-I", "-m", "alembic", "-c", "alembic.ini", "heads")
        for command in ("portal_api", "portal_play", "bootstrap_admin", "signup_invite",
                        "package_cleanup", "prepare_prologue", "scenario_demo"):
            run(str(python), "-I", "-m", "storyloop_platform.cli." + command, "--help")
