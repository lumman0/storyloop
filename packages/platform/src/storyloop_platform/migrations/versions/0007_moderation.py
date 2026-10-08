"""Roles, immutable review requests, public releases, and audit history.

Revision ID: 0007_moderation
Revises: 0006_player_memory
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0007_moderation"
down_revision = "0006_player_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("player_accounts", sa.Column("status", sa.Text, nullable=False,
                                                server_default="active"))
    op.create_table("player_roles",
                    sa.Column("player_id", sa.Text, primary_key=True),
                    sa.Column("role", sa.Text, primary_key=True))
    op.create_table(
        "scenario_submissions",
        sa.Column("submission_id", sa.Text, primary_key=True),
        sa.Column("scenario_id", sa.Text, nullable=False),
        sa.Column("version_id", sa.Text, nullable=False, unique=True),
        sa.Column("author_id", sa.Text, nullable=False),
        sa.Column("package_hash", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("submitted_at", sa.BigInteger, nullable=False),
        sa.Column("decided_at", sa.BigInteger),
        sa.Column("reviewer_id", sa.Text),
        sa.Column("reason", sa.Text),
    )
    op.create_index("scenario_submissions_queue", "scenario_submissions",
                    ["status", "submitted_at"])
    op.create_index("scenario_submissions_author", "scenario_submissions",
                    ["author_id", "submitted_at"])
    op.create_table(
        "scenario_public_releases",
        sa.Column("scenario_id", sa.Text, primary_key=True),
        sa.Column("version_id", sa.Text, nullable=False),
        sa.Column("submission_id", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.Column("updated_by", sa.Text, nullable=False),
    )
    op.create_table(
        "review_preview_saves",
        sa.Column("game_id", sa.Text, primary_key=True),
        sa.Column("submission_id", sa.Text, nullable=False),
        sa.Column("reviewer_id", sa.Text, nullable=False),
        sa.Column("created_at", sa.BigInteger, nullable=False),
    )
    op.create_table(
        "management_audit",
        sa.Column("event_id", sa.Text, primary_key=True),
        sa.Column("actor_id", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("target_type", sa.Text, nullable=False),
        sa.Column("target_id", sa.Text, nullable=False),
        sa.Column("details_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.BigInteger, nullable=False),
    )
    op.create_index("management_audit_recent", "management_audit", ["created_at"])


def downgrade() -> None:
    op.drop_index("management_audit_recent", table_name="management_audit")
    op.drop_table("management_audit")
    op.drop_table("review_preview_saves")
    op.drop_table("scenario_public_releases")
    op.drop_index("scenario_submissions_author", table_name="scenario_submissions")
    op.drop_index("scenario_submissions_queue", table_name="scenario_submissions")
    op.drop_table("scenario_submissions")
    op.drop_table("player_roles")
    op.drop_column("player_accounts", "status")
