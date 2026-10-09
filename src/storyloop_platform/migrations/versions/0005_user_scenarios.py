"""Author-owned scenario uploads and immutable published versions.

Revision ID: 0005_user_scenarios
Revises: 0004_signup_invites
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0005_user_scenarios"
down_revision = "0004_signup_invites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_scenarios",
        sa.Column("scenario_id", sa.Text, primary_key=True),
        sa.Column("owner_id", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("mode", sa.Text, nullable=False),
        sa.Column("visibility", sa.Text, nullable=False),
        sa.Column("published_version_id", sa.Text),
        sa.Column("created_at", sa.BigInteger, nullable=False),
    )
    op.create_index("user_scenarios_owner", "user_scenarios", ["owner_id", "created_at"])
    op.create_table(
        "user_scenario_versions",
        sa.Column("version_id", sa.Text, primary_key=True),
        sa.Column("scenario_id", sa.Text, nullable=False),
        sa.Column("package_id", sa.Text, nullable=False),
        sa.Column("package_version", sa.Text, nullable=False),
        sa.Column("package_hash", sa.Text, nullable=False),
        sa.Column("package_ref", sa.Text, nullable=False, unique=True),
        sa.Column("published_at", sa.BigInteger),
        sa.Column("created_at", sa.BigInteger, nullable=False),
    )
    op.create_index("user_scenario_versions_scenario", "user_scenario_versions",
                    ["scenario_id", "created_at"])


def downgrade() -> None:
    op.drop_index("user_scenario_versions_scenario", table_name="user_scenario_versions")
    op.drop_table("user_scenario_versions")
    op.drop_index("user_scenarios_owner", table_name="user_scenarios")
    op.drop_table("user_scenarios")
