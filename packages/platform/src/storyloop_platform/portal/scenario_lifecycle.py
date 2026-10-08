"""Database serialization shared by authoring and moderation commands."""

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping


def lock_scenario(db: Connection, scenario_id: str) -> RowMapping:
    """Hold the scenario lock until the caller's transaction ends.

    SQLite's legacy transaction mode does not start a transaction for SELECT.
    Acquire its write lock before reading lifecycle state; PostgreSQL can lock
    just the selected row. Call before any lifecycle read in this transaction.
    """
    if db.dialect.name == "sqlite":
        db.execute(text("""UPDATE user_scenarios SET scenario_id=scenario_id
            WHERE scenario_id=:id"""), {"id": scenario_id})
        suffix = ""
    else:
        suffix = " FOR UPDATE"
    row = db.execute(text("SELECT * FROM user_scenarios WHERE scenario_id=:id" + suffix),
                     {"id": scenario_id}).mappings().first()
    if row is None:
        raise KeyError("scenario not found")
    return row
