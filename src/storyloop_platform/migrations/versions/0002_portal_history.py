"""Persist playable transcript data.

Revision ID: 0002_portal_history
Revises: 0001_initial
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_portal_history"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("portal_turns")}
    if "input_text" not in columns:
        op.add_column("portal_turns", sa.Column("input_text", sa.Text))
    if "portal_intros" not in sa.inspect(bind).get_table_names():
        op.create_table("portal_intros", sa.Column("game_id", sa.Text, primary_key=True),
                        sa.Column("response_json", sa.Text, nullable=False))


def downgrade() -> None:
    op.drop_table("portal_intros")
    op.drop_column("portal_turns", "input_text")
