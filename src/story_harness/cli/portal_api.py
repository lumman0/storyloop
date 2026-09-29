"""Run the local player portal JSON API."""

from __future__ import annotations

import argparse

from story_harness.cli.react_play import DEFAULT_CONFIG
from story_harness.portal.http_api import serve
from story_harness.portal.service import PlayerPortal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--db", help="SQLite database shared by accounts and games")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(PlayerPortal(args.catalog, args.config, args.db), args.host, args.port)


if __name__ == "__main__":
    main()
