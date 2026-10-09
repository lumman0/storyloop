"""Prepare one official scenario package before adding it to a catalog."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from storyloop_platform.adapters.runtime_config import HarnessConfig
from storyloop_platform.adapters.telemetry import configured_telemetry
from storyloop_platform.generators.prologue_generator import ModelPrologueGenerator
from storyloop_platform.runtime.campaign import CampaignProgram
from storyloop_harness.advanced import save_prologue
from storyloop_harness import ScenarioPackage


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a missing prologue once for an official package")
    parser.add_argument("package", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--summary", default="")
    args = parser.parse_args()
    package = ScenarioPackage.load(args.package)
    if package.authored_prologue:
        print("Prologue already saved; model call skipped.")
        return
    path = args.package / "campaign.json"
    program = CampaignProgram.load(path) if path.exists() else None
    config = HarnessConfig.load(args.config)
    task = "prologue" if "prologue" in config.task_models else "narration"
    telemetry = configured_telemetry()
    try:
        model = config.create_model(task, dict(os.environ), telemetry)
        prose = asyncio.run(ModelPrologueGenerator(model, telemetry).generate(
            package, program, args.title, args.summary,
        ))
        save_prologue(args.package, prose)
    finally:
        telemetry.flush()
    print("Prologue generated and saved to manifest.json.")


if __name__ == "__main__":
    main()
