"""Run the player portal JSON API in local or online mode."""

from __future__ import annotations

import argparse
import sys

from storyloop_platform.cli.startup import launch_portal
from storyloop_platform.portal.http_api import serve
from storyloop_platform.portal.local_config import LocalPreferences
from storyloop_platform.bootstrap import build_portal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", help="scenario catalog; remembered after first launch")
    parser.add_argument("--profile", choices=("local", "online"), default="local")
    parser.add_argument("--config", help="deployment settings; remembered after successful local launch")
    parser.add_argument("--db", help="SQLite database path (local mode only)")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    preferences = LocalPreferences() if args.profile == "local" else None
    try:
        portal = launch_portal(profile=args.profile, config=args.config, catalog=args.catalog,
                               db=args.db, preferences=preferences, prompt=sys.stdin.isatty(),
                               portal_factory=build_portal)
    except FileNotFoundError:
        parser.error("selected settings or catalog file does not exist")
    except ValueError as error:
        parser.error(str(error))
    serve(portal, args.host or ("0.0.0.0" if args.profile == "online" else "127.0.0.1"), args.port)


if __name__ == "__main__":
    main()
