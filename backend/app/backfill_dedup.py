"""Backfill ``dedup_key`` and collapse cross-source duplicates in-place.

The async twin of migration ``0004_backfill_dedup_keys`` for dev/prod databases
created via ``db.create_all`` (which never runs Alembic). Idempotent: re-running
only re-groups and re-deactivates, so it's safe to run repeatedly.

    python -m app.backfill_dedup
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import SessionLocal
from .dedup import dedup_key as compute_dedup_key
from .models import Job


def _survivor_rank(job: Job):
    verified = 1 if (job.verify_status and job.verify_status != "unverified") else 0
    stamp = job.last_seen or job.date_scraped
    return (verified, stamp is not None, str(stamp or ""))


async def backfill_session(session: AsyncSession) -> tuple[int, int]:
    """Re-key every job and deactivate duplicate losers. Commits. Idempotent."""
    keyed = 0
    deactivated = 0
    jobs = (await session.execute(select(Job))).scalars().all()
    groups: dict[str, list[Job]] = {}
    for job in jobs:
        key = compute_dedup_key(
            company=job.company,
            title=job.title,
            location=job.location,
            url=job.job_url_direct or job.job_url,
            job_id=job.id,
        )
        job.dedup_key = key
        keyed += 1
        groups.setdefault(key, []).append(job)

    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=_survivor_rank, reverse=True)
        for loser in members[1:]:
            if loser.is_active:
                loser.is_active = False
                deactivated += 1

    await session.commit()
    return keyed, deactivated


async def backfill() -> tuple[int, int]:
    """Return (rows_keyed, rows_deactivated) for the configured database."""
    async with SessionLocal() as session:
        return await backfill_session(session)


def main() -> None:
    keyed, deactivated = asyncio.run(backfill())
    print(f"dedup backfill: keyed {keyed} rows, deactivated {deactivated} duplicates")


if __name__ == "__main__":
    main()
