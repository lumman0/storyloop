"""Player-controlled profile memory and batched extraction inputs.

Revision ID: 0006_player_memory
Revises: 0005_user_scenarios
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0006_player_memory"
down_revision = "0005_user_scenarios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_memory_settings",
        sa.Column("player_id", sa.Text, primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("last_generated_at", sa.BigInteger, nullable=False),
    )
    op.create_table(
        "player_memory_inputs",
        sa.Column("game_id", sa.Text, primary_key=True),
        sa.Column("request_id", sa.Text, primary_key=True),
        sa.Column("player_id", sa.Text, nullable=False),
        sa.Column("input_text", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False),
        sa.Column("available_at", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.BigInteger, nullable=False),
    )
    op.create_index("player_memory_inputs_ready", "player_memory_inputs",
                    ["player_id", "status", "available_at", "created_at"])


def downgrade() -> None:
    op.drop_index("player_memory_inputs_ready", table_name="player_memory_inputs")
    op.drop_table("player_memory_inputs")
    op.drop_table("player_memory_settings")
