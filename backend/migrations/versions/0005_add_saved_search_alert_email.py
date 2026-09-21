"""add saved_searches.alert_email

Optional explicit delivery address for a saved search's email alerts. Lets an
anonymous (ip:) search be emailed, and overrides the account email for an
authenticated one. Additive and nullable, so safe to apply anytime.

Revision ID: 0005_add_saved_search_alert_email
Revises: 0004_backfill_dedup_keys
Create Date: 2026-09-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_add_saved_search_alert_email"
down_revision: Union[str, None] = "0004_backfill_dedup_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("saved_searches") as batch:
        batch.add_column(sa.Column("alert_email", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("saved_searches") as batch:
        batch.drop_column("alert_email")
