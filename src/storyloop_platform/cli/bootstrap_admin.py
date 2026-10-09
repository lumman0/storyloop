"""Grant the administrator role to an existing account from the server terminal."""

from __future__ import annotations

import argparse
from pathlib import Path

from storyloop_platform.adapters.runtime_config import HarnessConfig
from storyloop_platform.portal.access import AccessService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="existing account username")
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1]
                                                / "defaults" / "online.json"))
    args = parser.parse_args()
    config = HarnessConfig.load(args.config)
    engine = config.create_database()
    try:
        player_id = AccessService(engine).bootstrap_admin(args.username)
        print(f"administrator granted: {player_id}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
