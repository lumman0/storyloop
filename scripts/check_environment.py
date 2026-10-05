"""Report the selected checkout without loading models, databases or credentials."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=root / "config/local.json")
    args = parser.parse_args(argv)
    config = args.config.resolve()
    print(f"python: {Path(sys.executable).resolve()}")
    print(f"config: {config}")

    try:
        package = importlib.import_module("story_harness")
        location = Path(package.__file__).resolve()
    except (ImportError, TypeError, AttributeError):
        print("error: story_harness is not importable", file=sys.stderr)
        return 1
    print(f"story_harness: {location}")
    if location != (root / "src/story_harness/__init__.py").resolve():
        print("error: import root does not match this checkout", file=sys.stderr)
        return 1

    try:
        git = subprocess.run(
            ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root),
             "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        sha = git.stdout.strip()
        if len(sha) != 40 or any(char not in "0123456789abcdef" for char in sha):
            raise ValueError("invalid SHA")
    except (OSError, subprocess.SubprocessError, ValueError):
        print("error: cannot determine Git SHA", file=sys.stderr)
        return 1
    print(f"git_sha: {sha}")

    try:
        payload = json.loads(config.read_text(encoding="utf-8"))
        driver = payload["storage"]["driver"]
        if driver not in ("sqlite", "postgresql"):
            raise ValueError("unsupported driver")
    except (OSError, ValueError, KeyError, TypeError):
        # Config values and exception text can contain keys or database passwords.
        print("error: cannot read storage driver from config", file=sys.stderr)
        return 1
    print(f"storage_driver: {driver}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
