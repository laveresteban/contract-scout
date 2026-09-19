"""create jobs table

Baseline for the standalone service. In the real Contract Scout database the
`jobs` table already exists from an earlier migration — there you would skip
this and apply only 0001_add_job_verification.

Revision ID: 0000_create_jobs
Revises:
Create Date: 2026-09-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0000_create_jobs"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("site", sa.String(), nullable=True),
        sa.Column("job_url", sa.String(), nullable=True),
        sa.Column("job_url_direct", sa.String(), nullable=True),
        sa.Column("is_remote", sa.Boolean(), nullable=True),
        sa.Column("eligibility", sa.String(), nullable=True),
        sa.Column("job_type", sa.String(), nullable=True),
        sa.Column("employment_type", sa.String(), nullable=True),
        sa.Column("date_posted", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_scraped", sa.DateTime(timezone=True), nullable=True),
        sa.Column("min_amount", sa.Float(), nullable=True),
        sa.Column("max_amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("interval", sa.String(), nullable=True),
        sa.Column("normalized_min_yearly", sa.Float(), nullable=True),
        sa.Column("normalized_max_yearly", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("jobs")
