"""Persist per-save, per-agent context compression checkpoints.

Revision ID: 0009_agent_contexts
Revises: 0008_admin_invitations
"""

import sqlalchemy as sa
from alembic import op


revision = "0009_agent_contexts"
down_revision = "0008_admin_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("events_game_version", "events", ["game_id", "state_version"])
    op.create_index("observations_game_recipient", "observations", ["game_id", "recipient_id"])
    op.create_table(
        "agent_contexts",
        sa.Column("game_id", sa.Text, primary_key=True),
        sa.Column("actor_id", sa.Text, primary_key=True),
        sa.Column("through_version", sa.Integer, nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agent_contexts")
    op.drop_index("observations_game_recipient", table_name="observations")
    op.drop_index("events_game_version", table_name="events")
