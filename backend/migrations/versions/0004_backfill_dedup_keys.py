"""backfill dedup_key and collapse cross-source duplicates

Historic rows -- everything ingested via the saved-search scan path, or before
``dedup_key`` was populated -- have ``dedup_key = NULL`` and never merge on the
next scrape, so the ``jobs`` table accumulates cross-source duplicates. This is a
pure *data* migration (the column already exists as of 0003): it computes the
shared ``app.dedup`` key for every row, then within each duplicate group keeps one
survivor active and deactivates the rest (``is_active = 0``) so listings and
``X-Total-Count`` reflect unique postings.

The survivor is the most-recently-seen row, preferring one that already carries a
verification verdict so we don't discard ground truth.

Revision ID: 0004_backfill_dedup_keys
Revises: 0003_full_backend
Create Date: 2026-09-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.dedup import dedup_key as compute_dedup_key

revision: str = "0004_backfill_dedup_keys"
down_revision: Union[str, None] = "0003_full_backend"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _sort_key(row):
    # Higher tuples win the survivor slot: verified rows first, then freshest.
    verified = 1 if (row.verify_status and row.verify_status != "unverified") else 0
    stamp = row.last_seen or row.date_scraped
    return (verified, stamp is not None, str(stamp or ""))


def upgrade() -> None:
    bind = op.get_bind()
    jobs = sa.table(
        "jobs",
        sa.column("id", sa.String),
        sa.column("company", sa.String),
        sa.column("title", sa.String),
        sa.column("location", sa.String),
        sa.column("job_url", sa.String),
        sa.column("job_url_direct", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("last_seen", sa.DateTime),
        sa.column("date_scraped", sa.DateTime),
        sa.column("dedup_key", sa.String),
        sa.column("verify_status", sa.String),
    )
    rows = bind.execute(sa.select(jobs)).fetchall()

    groups: dict[str, list] = {}
    for row in rows:
        key = compute_dedup_key(
            company=row.company,
            title=row.title,
            location=row.location,
            url=row.job_url_direct or row.job_url,
            job_id=row.id,
        )
        groups.setdefault(key, []).append(row)

    for key, members in groups.items():
        members.sort(key=_sort_key, reverse=True)
        survivor = members[0]
        for row in members:
            deactivate = row.id != survivor.id
            values = {"dedup_key": key}
            if deactivate:
                values["is_active"] = False
            bind.execute(sa.update(jobs).where(jobs.c.id == row.id).values(**values))


def downgrade() -> None:
    # Non-reversible: we can't tell which rows were deactivated by this pass.
    pass
