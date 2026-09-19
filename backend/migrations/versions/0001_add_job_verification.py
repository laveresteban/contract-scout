"""add job verification columns

Adds the verification fields to the existing `jobs` table. Additive and
backfilled to 'unverified', so it's safe to apply before the endpoint ships.

Revision ID: 0001_add_job_verification
Revises: 0000_create_jobs
Create Date: 2026-09-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_add_job_verification"
down_revision: Union[str, None] = "0000_create_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(
            sa.Column(
                "verify_status",
                sa.String(),
                nullable=False,
                server_default="unverified",
            )
        )
        batch.add_column(sa.Column("verify_checked_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("verify_http_status", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("verify_detail", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("verify_detail")
        batch.drop_column("verify_http_status")
        batch.drop_column("verify_checked_at")
        batch.drop_column("verify_status")
