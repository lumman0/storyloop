"""Bound per-event observation lookups in actor context history joins."""

from alembic import op

revision = "0014_observation_join_index"
down_revision = "0013_package_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("observations_game_event_recipient", "observations",
                    ["game_id", "event_id", "recipient_id"])


def downgrade() -> None:
    op.drop_index("observations_game_event_recipient", table_name="observations")
