"""Keep the player's chosen flow separate from the authored package mode.

Revision ID: 0011_save_play_mode
Revises: 0010_save_generation_settings
"""

import sqlalchemy as sa
from alembic import op


revision = "0011_save_play_mode"
down_revision = "0010_save_generation_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL preserves the original catalog mode for every existing save.
    op.add_column("player_saves", sa.Column("play_mode", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("player_saves", "play_mode")
