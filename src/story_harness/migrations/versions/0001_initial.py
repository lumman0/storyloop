"""Baseline relational schema, including upgrades for legacy SQLite saves.

Revision ID: 0001_initial
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if "games" not in existing:
        op.create_table("games", sa.Column("game_id", sa.Text, primary_key=True),
                        sa.Column("version", sa.Integer, nullable=False),
                        sa.Column("tick", sa.Integer, nullable=False),
                        sa.Column("data", sa.Text, nullable=False))
    if "events" not in existing:
        op.create_table("events", sa.Column("game_id", sa.Text, primary_key=True),
                        sa.Column("event_id", sa.Text, primary_key=True),
                        sa.Column("kind", sa.Text, nullable=False), sa.Column("actor_id", sa.Text),
                        sa.Column("cause_id", sa.Text), sa.Column("tick", sa.Integer, nullable=False),
                        sa.Column("effects", sa.Text, nullable=False),
                        sa.Column("details", sa.Text, nullable=False),
                        sa.Column("state_version", sa.Integer, nullable=False))
    if "observations" not in existing:
        op.create_table("observations", sa.Column("game_id", sa.Text, primary_key=True),
                        sa.Column("observation_id", sa.Text, primary_key=True),
                        sa.Column("event_id", sa.Text, nullable=False),
                        sa.Column("recipient_id", sa.Text, nullable=False),
                        sa.Column("channel", sa.Text, nullable=False),
                        sa.Column("content", sa.Text, nullable=False),
                        sa.Column("tick", sa.Integer, nullable=False),
                        sa.Column("created_order", sa.BigInteger))
    elif "created_order" not in {c["name"] for c in sa.inspect(bind).get_columns("observations")}:
        op.add_column("observations", sa.Column("created_order", sa.BigInteger))
    if "pending_work" not in existing:
        op.create_table("pending_work", sa.Column("game_id", sa.Text, primary_key=True),
                        sa.Column("work_id", sa.Text, primary_key=True),
                        sa.Column("kind", sa.Text, nullable=False),
                        sa.Column("due_tick", sa.Integer, nullable=False),
                        sa.Column("priority", sa.Integer, nullable=False),
                        sa.Column("cause_id", sa.Text), sa.Column("payload", sa.Text, nullable=False),
                        sa.Column("mandatory", sa.Integer, nullable=False),
                        sa.Column("status", sa.Text, nullable=False))
    if "player_accounts" not in existing:
        op.create_table("player_accounts", sa.Column("player_id", sa.Text, primary_key=True),
                        sa.Column("username", sa.Text, nullable=False, unique=True),
                        sa.Column("password_salt", sa.LargeBinary, nullable=False),
                        sa.Column("password_hash", sa.LargeBinary, nullable=False),
                        sa.Column("created_at", sa.Integer, nullable=False))
    if "player_sessions" not in existing:
        op.create_table("player_sessions", sa.Column("token_hash", sa.LargeBinary, primary_key=True),
                        sa.Column("player_id", sa.Text, nullable=False),
                        sa.Column("expires_at", sa.Integer, nullable=False))
    if "player_saves" not in existing:
        op.create_table("player_saves", sa.Column("game_id", sa.Text, primary_key=True),
                        sa.Column("player_id", sa.Text, nullable=False),
                        sa.Column("catalog_id", sa.Text, nullable=False),
                        sa.Column("package_id", sa.Text, nullable=False),
                        sa.Column("package_version", sa.Text, nullable=False),
                        sa.Column("package_hash", sa.Text, nullable=False),
                        sa.Column("created_at", sa.Integer, nullable=False))
        op.create_index("player_saves_owner", "player_saves", ["player_id", "created_at"])
    if "portal_turns" not in existing:
        op.create_table("portal_turns", sa.Column("game_id", sa.Text, primary_key=True),
                        sa.Column("request_id", sa.Text, primary_key=True),
                        sa.Column("input_hash", sa.LargeBinary, nullable=False),
                        sa.Column("response_json", sa.Text, nullable=False),
                        sa.Column("created_order", sa.BigInteger))
    elif "created_order" not in {c["name"] for c in sa.inspect(bind).get_columns("portal_turns")}:
        op.add_column("portal_turns", sa.Column("created_order", sa.BigInteger))
    if bind.dialect.name == "sqlite":
        bind.execute(sa.text("UPDATE observations SET created_order = rowid WHERE created_order IS NULL"))
        bind.execute(sa.text("UPDATE portal_turns SET created_order = rowid WHERE created_order IS NULL"))


def downgrade() -> None:
    raise RuntimeError("The baseline migration preserves player data and cannot be downgraded")
