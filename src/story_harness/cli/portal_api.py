"""Run the local player portal JSON API."""

from __future__ import annotations

import argparse
import sys

from story_harness.cli.react_play import DEFAULT_CONFIG
from story_harness.portal.http_api import serve
from story_harness.portal.local_config import LocalPreferences
from story_harness.portal.service import PlayerPortal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", help="scenario catalog; remembered after first launch")
    parser.add_argument("--config", help="model config; remembered after first launch")
    parser.add_argument("--db", help="SQLite database shared by accounts and games")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    preferences = LocalPreferences()
    saved = preferences.load_settings()
    catalog = args.catalog or saved.get("catalog")
    if not catalog:
        parser.error("--catalog is required on first launch")
    config = args.config or saved.get("config") or str(DEFAULT_CONFIG)
    portal = PlayerPortal(catalog, config, args.db or saved.get("db"))
    preferences.save_settings(catalog, config, portal.db_path)
    preferences.activate_model_key(portal.config.api_key_env, prompt=sys.stdin.isatty())
    serve(portal, args.host, args.port)


if __name__ == "__main__":
    main()
