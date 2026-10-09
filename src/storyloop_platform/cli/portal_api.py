"""Run the player portal JSON API in local or online mode."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from storyloop_platform.adapters.runtime_config import HarnessConfig
from storyloop_platform.cli.config_paths import select_config
from storyloop_platform.portal.http_api import serve
from storyloop_platform.portal.local_config import LocalPreferences
from storyloop_platform.portal.service import PlayerPortal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", help="scenario catalog; remembered after first launch")
    parser.add_argument("--profile", choices=("local", "online"), default="local")
    parser.add_argument("--config", help="model config; remembered after first launch")
    parser.add_argument("--db", help="SQLite database path (local mode only)")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    preferences = LocalPreferences() if args.profile == "local" else None
    saved = preferences.load_settings() if preferences else {}
    catalog = args.catalog or saved.get("catalog") or os.environ.get("STORY_CATALOG")
    if not catalog:
        parser.error("--catalog is required on first launch")
    default_config = Path(__file__).resolve().parents[1] / "defaults" / f"{args.profile}.json"
    config = select_config(args.config, saved.get("config"), default_config)
    if HarnessConfig.load(config).profile != args.profile:
        parser.error("--profile and config environment disagree")
    portal = PlayerPortal(catalog, config, args.db or saved.get("db"))
    if preferences:
        preferences.save_settings(catalog, config, portal.db_path)
        if not portal.config.model_api_key():
            preferences.activate_model_key(portal.config.api_key_env, prompt=sys.stdin.isatty())
    serve(portal, args.host or ("0.0.0.0" if args.profile == "online" else "127.0.0.1"), args.port)


if __name__ == "__main__":
    main()
