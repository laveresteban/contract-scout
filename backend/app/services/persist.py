"""Async persistence for scraped jobs: upsert, cross-source dedup, staleness.

Ported from the old sync ``scraper.save_jobs`` onto ``AsyncSession``. The
scraping modules build ``scraped.Job`` (Pydantic, with pay/classification
inference); this layer merges exact-id and cross-source duplicates into the
``Job`` ORM row and stores the normalized pay + eligibility columns the SQL
filters sort on. The verify_* columns are never touched here.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import JOB_STALE_DAYS
from ..dedup import dedup_key as compute_dedup_key
from ..models import Job as JobORM
from ..scraped import Job

# Computed/derived Pydantic fields that must not be passed straight to the ORM.
_COMPUTED_FIELDS = {
    "normalized_min_yearly",
    "normalized_max_yearly",
    "normalized_min_hourly",
    "normalized_max_hourly",
    "normalized_currency",
    "eligibility",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dedup_key(job: Job) -> str:
    """Cross-source identity, shared with the scan path via ``app.dedup``."""
    return compute_dedup_key(
        company=job.company,
        title=job.title,
        location=job.location,
        url=job.job_url_direct or job.job_url,
        job_id=job.id,
    )


def _source_urls(existing: str | None, job: Job) -> str:
    try:
        values = json.loads(existing or "[]")
    except (json.JSONDecodeError, TypeError):
        values = []
    entry = {"site": job.site, "url": job.job_url or job.job_url_direct}
    if entry not in values:
        values.append(entry)
    return json.dumps(values)


def _merge_job(existing: JobORM, job: Job) -> None:
    existing.last_seen = _utcnow()
    existing.date_scraped = job.date_scraped or _utcnow()
    existing.is_active = True
    existing.quality_version = 2
    existing.source_urls = _source_urls(existing.source_urls, job)
    if len(job.description or "") > len(existing.description or ""):
        existing.description = job.description
    for name in ("job_url", "job_url_direct", "location", "date_posted"):
        if getattr(existing, name) is None and getattr(job, name) is not None:
            setattr(existing, name, getattr(job, name))
    rank = {None: 0, "low": 1, "medium": 2, "high": 3}
    existing_pay_count = int(existing.min_amount is not None) + int(existing.max_amount is not None)
    incoming_pay_count = int(job.min_amount is not None) + int(job.max_amount is not None)
    if incoming_pay_count and (
        not existing_pay_count
        or rank.get(job.pay_confidence, 0) >= rank.get(existing.pay_confidence, 0)
        or incoming_pay_count > existing_pay_count
    ):
        for name in (
            "min_amount", "max_amount", "currency", "interval",
            "pay_source", "pay_confidence", "pay_raw_text",
        ):
            value = getattr(job, name)
            if value is not None:
                setattr(existing, name, value)
        existing.normalized_min_yearly = job.normalized_min_yearly
        existing.normalized_max_yearly = job.normalized_max_yearly
        existing.normalized_min_hourly = job.normalized_min_hourly
        existing.normalized_max_hourly = job.normalized_max_hourly
    if rank.get(job.classification_confidence, 0) >= rank.get(existing.classification_confidence, 0):
        for name in ("job_type", "employment_type", "classification_source", "classification_confidence"):
            value = getattr(job, name)
            if value is not None:
                setattr(existing, name, value)
    existing.is_remote = existing.is_remote or job.is_remote
    existing.is_us = existing.is_us or job.is_us
    existing.eligibility = job.eligibility
    existing.raw_data = json.dumps(job.model_dump(mode="json"))


def _new_orm(job: Job, key: str) -> JobORM:
    payload = job.model_dump(
        exclude_none=True, exclude={"date_posted", "source_urls", *_COMPUTED_FIELDS}
    )
    orm = JobORM(**payload)
    orm.date_posted = job.date_posted
    orm.normalized_min_yearly = job.normalized_min_yearly
    orm.normalized_max_yearly = job.normalized_max_yearly
    orm.normalized_min_hourly = job.normalized_min_hourly
    orm.normalized_max_hourly = job.normalized_max_hourly
    orm.eligibility = job.eligibility
    orm.dedup_key = key
    orm.source_urls = _source_urls(None, job)
    orm.last_seen = job.date_scraped or _utcnow()
    orm.is_active = True
    orm.raw_data = json.dumps(job.model_dump(mode="json"))
    return orm


async def save_jobs(jobs: list[Job], db: AsyncSession) -> int:
    """Persist jobs, merging exact-id and cross-source duplicates. Commits."""
    count = 0
    batch: dict[str, JobORM] = {}
    for job in jobs:
        key = _dedup_key(job)
        existing = batch.get(key)
        if existing is None:
            existing = (
                await db.execute(
                    select(JobORM).where(JobORM.dedup_key == key, JobORM.is_active.is_(True))
                )
            ).scalars().first()
        if existing is None:
            existing = await db.get(JobORM, job.id)
        if existing is not None:
            existing.dedup_key = key
            _merge_job(existing, job)
            batch[key] = existing
            continue
        orm = _new_orm(job, key)
        db.add(orm)
        batch[key] = orm
        count += 1
    await db.commit()
    return count


async def mark_stale_jobs(db: AsyncSession) -> int:
    """Deactivate jobs not seen within JOB_STALE_DAYS. Commits."""
    cutoff = _utcnow() - timedelta(days=JOB_STALE_DAYS)
    result = await db.execute(
        update(JobORM)
        .where(JobORM.is_active.is_(True), JobORM.last_seen < cutoff)
        .values(is_active=False)
    )
    await db.commit()
    return result.rowcount or 0
