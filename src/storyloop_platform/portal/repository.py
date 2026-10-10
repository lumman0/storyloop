"""SQL-owned SQLite convenience constructor."""

from __future__ import annotations

from storyloop_platform.adapters.sql_database import open_database, sqlite_url, upgrade_database
from storyloop_platform.portal.sql_repository import SQLPlayerRepository


class SQLitePlayerRepository(SQLPlayerRepository):
    """Owns a SQLite Engine for offline scripts and focused repository tests."""

    def __init__(self, path: str) -> None:
        self.path = path
        url = sqlite_url(path)
        upgrade_database(url)
        super().__init__(open_database(url))
