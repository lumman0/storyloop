"""One-time invitations for paid online registration.

Revision ID: 0004_signup_invites
Revises: 0003_credits
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0004_signup_invites"
down_revision = "0003_credits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signup_invites",
        sa.Column("code_hash", sa.LargeBinary, primary_key=True),
        sa.Column("expires_at", sa.BigInteger, nullable=False),
        sa.Column("used_by", sa.Text),
        sa.Column("used_at", sa.BigInteger),
    )


def downgrade() -> None:
    op.drop_table("signup_invites")
