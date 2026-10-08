from __future__ import annotations

from story_harness.adapters.sql_database import open_database, sqlite_url, upgrade_database
from story_harness.adapters.sql_store import SQLGameStore

from story_harness.core.store_port import GameStore


class SQLiteGameStore(SQLGameStore):
    """Compatibility entry point backed by the shared SQL repository."""

    def __init__(self, path: str) -> None:
        self.path = path
        url = sqlite_url(path)
        upgrade_database(url)
        super().__init__(open_database(url))
