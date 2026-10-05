"""Retain draft-package cleanup work in the metadata deletion transaction."""

import sqlalchemy as sa
from alembic import op

revision = "0013_package_cleanup"
down_revision = "0012_turn_settlements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "package_cleanup_queue",
        sa.Column("package_ref", sa.Text, primary_key=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_order", sa.BigInteger, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("package_cleanup_queue")
