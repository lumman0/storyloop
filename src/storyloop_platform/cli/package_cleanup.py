"""Inspect local upload consistency, optionally retry already queued deletions."""

import argparse
import json
import os
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from storyloop_platform.adapters.sql_database import open_database, sqlite_url
from storyloop_platform.portal.package_cleanup import PackageCleanup, inspect_local_packages
from storyloop_platform.portal.scenario_storage import LocalPublishedPackageStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Existing SQLite file; otherwise use DATABASE_URL")
    parser.add_argument("--uploads", required=True, type=Path, help="Existing local upload directory")
    parser.add_argument("--retry-queued", action="store_true",
                        help="Retry only metadata-deletion intents already stored in SQL")
    args = parser.parse_args(argv)
    if not args.uploads.is_dir():
        parser.error("upload directory does not exist")
    if args.db and not Path(args.db).is_file():
        parser.error("SQLite database must already exist")
    url = sqlite_url(args.db) if args.db else os.environ.get("DATABASE_URL")
    if not url:
        parser.error("provide --db or DATABASE_URL")
    engine = open_database(url)
    try:
        cleanup = PackageCleanup(engine, LocalPublishedPackageStore(args.uploads))
        result = {"retried": cleanup.retry() if args.retry_queued else [],
                  "pending": cleanup.pending(), **inspect_local_packages(engine, args.uploads)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except SQLAlchemyError:
        # SQL exception strings can contain connection parameters. Keep CLI
        # diagnostics bounded; schema migration is intentionally not automatic.
        print("Database unavailable or package-cleanup migration is missing.")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
