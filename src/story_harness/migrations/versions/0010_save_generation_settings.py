"""Per-save model generation and agent context budgets.

Revision ID: 0010_save_generation_settings
Revises: 0009_agent_contexts
"""

import sqlalchemy as sa
from alembic import op


revision = "0010_save_generation_settings"
down_revision = "0009_agent_contexts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "save_generation_settings",
        sa.Column("game_id", sa.Text, sa.ForeignKey("player_saves.game_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("temperature", sa.Float, nullable=False),
        sa.Column("context_window_tokens", sa.Integer, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("save_generation_settings")
