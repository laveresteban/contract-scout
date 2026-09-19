"""expand jobs + add users, prefs, and scrape-run tables

Reconciles the standalone verification package's narrow schema with the full
Contract Scout backend: adds the pay-classification / dedup / freshness columns
to ``jobs`` and creates the ``users``, ``saved_jobs``, ``hidden_jobs``,
``viewed_jobs`` and ``scrape_runs`` tables that back auth, server-side prefs and
source-health reporting.

Revision ID: 0003_full_backend
Revises: 0002_add_saved_searches
Create Date: 2026-09-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_full_backend"
down_revision: Union[str, None] = "0002_add_saved_searches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_JOB_COLUMNS = [
    sa.Column("classification_source", sa.String(), nullable=True),
    sa.Column("classification_confidence", sa.String(), nullable=True),
    sa.Column("normalized_min_hourly", sa.Float(), nullable=True),
    sa.Column("normalized_max_hourly", sa.Float(), nullable=True),
    sa.Column("pay_source", sa.String(), nullable=True),
    sa.Column("pay_confidence", sa.String(), nullable=True),
    sa.Column("pay_raw_text", sa.Text(), nullable=True),
    sa.Column("is_us", sa.Boolean(), nullable=True, server_default=sa.text("0")),
    sa.Column("quality_version", sa.Integer(), nullable=True, server_default=sa.text("2")),
    sa.Column("source_urls", sa.Text(), nullable=True),
    sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("1")),
    sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
    sa.Column("dedup_key", sa.String(), nullable=True),
    sa.Column("raw_data", sa.Text(), nullable=True),
]


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        for column in _NEW_JOB_COLUMNS:
            batch.add_column(column)
    op.create_index("ix_jobs_normalized_min_hourly", "jobs", ["normalized_min_hourly"])
    op.create_index("ix_jobs_normalized_max_hourly", "jobs", ["normalized_max_hourly"])
    op.create_index("ix_jobs_is_us", "jobs", ["is_us"])
    op.create_index("ix_jobs_is_active", "jobs", ["is_active"])
    op.create_index("ix_jobs_dedup_key", "jobs", ["dedup_key"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("provider_id", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("avatar_url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_provider", "users", ["provider"])
    op.create_index("ix_users_provider_id", "users", ["provider_id"])
    op.create_index("ix_users_email", "users", ["email"])

    for table in ("saved_jobs", "hidden_jobs"):
        op.create_table(
            table,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("job_id", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
        op.create_index(f"ix_{table}_job_id", table, ["job_id"])

    op.create_table(
        "viewed_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_viewed_jobs_user_id", "viewed_jobs", ["user_id"])
    op.create_index("ix_viewed_jobs_job_id", "viewed_jobs", ["job_id"])

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("trigger", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("jobs_found", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("jobs_saved", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("jobs_with_pay", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("hourly_jobs", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("contract_jobs", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_scrape_runs_source", "scrape_runs", ["source"])
    op.create_index("ix_scrape_runs_status", "scrape_runs", ["status"])


def downgrade() -> None:
    op.drop_table("scrape_runs")
    op.drop_table("viewed_jobs")
    op.drop_table("hidden_jobs")
    op.drop_table("saved_jobs")
    op.drop_table("users")
    for index in (
        "ix_jobs_dedup_key", "ix_jobs_is_active", "ix_jobs_is_us",
        "ix_jobs_normalized_max_hourly", "ix_jobs_normalized_min_hourly",
    ):
        op.drop_index(index, table_name="jobs")
    with op.batch_alter_table("jobs") as batch:
        for column in reversed(_NEW_JOB_COLUMNS):
            batch.drop_column(column.name)
