"""add saved searches and scan matches

Creates the `saved_searches` and `saved_search_matches` tables that back the
saved-search background scan. In the real backend you may already have a saved
searches table under `/prefs/*`; if so, reconcile the columns here
(`filters`, `alert_enabled`, `alert_frequency`, `last_alerted_at`,
`last_scanned_at`) rather than creating a duplicate, and keep the matches table.

Revision ID: 0002_add_saved_searches
Revises: 0001_add_job_verification
Create Date: 2026-09-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_saved_searches"
down_revision: Union[str, None] = "0001_add_job_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("alert_enabled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("alert_frequency", sa.String(), nullable=False, server_default="daily"),
        sa.Column("last_alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_saved_searches_user_id", "saved_searches", ["user_id"])

    op.create_table(
        "saved_search_matches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "saved_search_id",
            sa.String(),
            sa.ForeignKey("saved_searches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_new", sa.Boolean(), nullable=False, server_default="1"),
        sa.UniqueConstraint("saved_search_id", "job_id", name="uq_saved_search_job"),
    )
    op.create_index(
        "ix_saved_search_matches_saved_search_id",
        "saved_search_matches",
        ["saved_search_id"],
    )
    op.create_index("ix_saved_search_matches_job_id", "saved_search_matches", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_search_matches_job_id", table_name="saved_search_matches")
    op.drop_index(
        "ix_saved_search_matches_saved_search_id", table_name="saved_search_matches"
    )
    op.drop_table("saved_search_matches")
    op.drop_index("ix_saved_searches_user_id", table_name="saved_searches")
    op.drop_table("saved_searches")
