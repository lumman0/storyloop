"""Add player credit balances and immutable billing entries.

Revision ID: 0003_credits
Revises: 0002_portal_history
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0003_credits"
down_revision = "0002_portal_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credit_wallets",
        sa.Column("player_id", sa.Text, primary_key=True),
        sa.Column("balance_milli_points", sa.BigInteger, nullable=False),
    )
    op.create_table(
        "credit_ledger",
        sa.Column("entry_id", sa.Text, primary_key=True),
        sa.Column("player_id", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("game_id", sa.Text),
        sa.Column("request_id", sa.Text),
        sa.Column("delta_milli_points", sa.BigInteger, nullable=False),
        sa.Column("usage_cost_milli_points", sa.BigInteger, nullable=False),
        sa.Column("balance_after_milli_points", sa.BigInteger, nullable=False),
        sa.Column("pricing_version", sa.Text, nullable=False),
        sa.Column("usage_json", sa.Text, nullable=False),
        sa.Column("created_order", sa.BigInteger, nullable=False),
    )
    op.create_index("credit_ledger_player", "credit_ledger", ["player_id", "created_order"])


def downgrade() -> None:
    op.drop_index("credit_ledger_player", table_name="credit_ledger")
    op.drop_table("credit_ledger")
    op.drop_table("credit_wallets")
