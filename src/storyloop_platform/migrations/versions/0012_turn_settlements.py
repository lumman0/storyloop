"""Persist completed turn metering before attempting wallet settlement."""

import sqlalchemy as sa
from alembic import op

revision = "0012_turn_settlements"
down_revision = "0011_save_play_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "turn_settlement_intents",
        sa.Column("game_id", sa.Text, primary_key=True),
        sa.Column("request_id", sa.Text, primary_key=True),
        sa.Column("input_hash", sa.Text, nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("response_json", sa.Text, nullable=False),
        sa.Column("usage_json", sa.Text, nullable=False),
        sa.Column("policy_json", sa.Text, nullable=False),
        sa.Column("created_order", sa.BigInteger, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("turn_settlement_intents")
