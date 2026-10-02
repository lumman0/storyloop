"""Issue one-time registration invitations for the online portal."""

from __future__ import annotations

import argparse
from pathlib import Path

from story_harness.adapters.runtime_config import HarnessConfig
from story_harness.portal.sql_repository import SQLPlayerRepository


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1]
                                                / "defaults" / "online.json"))
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--valid-days", type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.count <= 100:
        parser.error("--count must be between 1 and 100")
    config = HarnessConfig.load(args.config)
    if config.profile != "online":
        parser.error("invites must be issued against an online database")
    engine = config.create_database()
    try:
        repository = SQLPlayerRepository(engine)
        for _ in range(args.count):
            print(repository.issue_signup_invite(args.valid_days))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
