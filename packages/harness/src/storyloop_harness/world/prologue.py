"""Store a fixed prologue in a scenario package before fingerprinting it."""

from __future__ import annotations

import json
from pathlib import Path

from storyloop_harness.world.scenario import ScenarioPackage


def save_prologue(directory: str | Path, prose: str) -> ScenarioPackage:
    text = prose.strip().replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    if not text:
        raise ValueError("prologue generation returned empty text")
    root = Path(directory)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("authored_prologue"):
        raise ValueError("scenario already has a prologue")
    manifest["authored_prologue"] = text
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return ScenarioPackage.load(root)
