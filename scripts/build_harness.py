"""Build harness from the exact Git revision declared by this platform."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import tomllib


def harness_requirement(metadata: dict) -> str:
    source = metadata.get("tool", {}).get("uv", {}).get("sources", {}).get("storyloop-harness", {})
    git, rev = source.get("git", ""), source.get("rev", "")
    if not git.startswith("https://") or not re.fullmatch(r"[0-9a-f]{40}", rev):
        raise ValueError("Set the harness HTTPS Git URL and immutable 40-character rev in pyproject.toml before building")
    return f"git+{git}@{rev}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    requirement = harness_requirement(tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")))
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir",
                    str(args.out_dir), requirement], check=True)


if __name__ == "__main__":
    main()
