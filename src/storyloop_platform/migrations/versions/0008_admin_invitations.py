"""Record invitation issuers and allow revocation without changing old codes.

Revision ID: 0008_admin_invitations
Revises: 0007_moderation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0008_admin_invitations"
down_revision = "0007_moderation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("signup_invites", sa.Column("issued_by", sa.Text))
    op.add_column("signup_invites", sa.Column("created_at", sa.BigInteger))
    op.add_column("signup_invites", sa.Column("revoked_at", sa.BigInteger))
    op.add_column("signup_invites", sa.Column("revoked_by", sa.Text))
    op.create_index("signup_invites_issuer", "signup_invites", ["issued_by", "created_at"])


def downgrade() -> None:
    op.drop_index("signup_invites_issuer", table_name="signup_invites")
    op.drop_column("signup_invites", "revoked_by")
    op.drop_column("signup_invites", "revoked_at")
    op.drop_column("signup_invites", "created_at")
    op.drop_column("signup_invites", "issued_by")
