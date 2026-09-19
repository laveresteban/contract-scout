"""Run saved searches against the scraper and record newly-found postings.

Flow for one search:
  1. call the injected scraper with the search's stored `filters`,
  2. defensively re-filter the results (see `matcher`),
  3. upsert each posting into the `jobs` table (never clobbering verify data),
  4. record a `SavedSearchMatch` for any job not already matched to this search,
     flagged `is_new` so the frontend can badge it,
  5. stamp `last_scanned_at`.

Load-bearing rule, mirroring the verify service: a *failed* scrape is
inconclusive — we leave the search's existing matches untouched and do NOT mark
it scanned, so it's retried next tick. We never delete a match on a bad fetch.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import Job, SavedSearch, SavedSearchMatch
from . import matcher
from .scraper import Scraper, get_scraper

logger = logging.getLogger(__name__)
_settings = get_settings()

# Job columns we let a scrape populate. `id` is handled separately and the
# verify_* columns are owned by the verification feature, never by ingest.
_JOB_COLUMNS = {
    c.name
    for c in Job.__table__.columns
    if c.name != "id" and not c.name.startswith("verify_")
}
_DATETIME_COLUMNS = {"date_posted", "date_scraped"}


@dataclass
class ScanResult:
    saved_search_id: str
    scraped: int = 0
    matched: int = 0
    new: int = 0
    ok: bool = True
    error: str | None = None


@dataclass
class ScanSummary:
    ran: int = 0
    skipped_not_due: int = 0
    results: list[ScanResult] = field(default_factory=list)

    @property
    def total_new(self) -> int:
        return sum(r.new for r in self.results)


def _coerce_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _ingest_job(session: AsyncSession, existing: Job | None, data: dict) -> Job:
    """Insert a new Job or update an existing one with the scraped fields.

    Only keys the scrape provided are written, so we never null out columns the
    posting didn't include (and never touch verify_* data on a re-scrape).
    """
    job = existing or Job(id=str(data["id"]))
    for key, value in data.items():
        if key not in _JOB_COLUMNS:
            continue
        if key in _DATETIME_COLUMNS:
            value = _coerce_dt(value)
        setattr(job, key, value)
    if existing is None:
        session.add(job)
    return job


async def scan_one(
    session: AsyncSession,
    search: SavedSearch,
    scraper: Scraper,
    *,
    now: datetime | None = None,
) -> ScanResult:
    """Scrape and ingest one saved search. Caller commits the session."""
    now = now or datetime.now(timezone.utc)
    result = ScanResult(saved_search_id=search.id)

    try:
        raw = await scraper(dict(search.filters or {}))
    except Exception as exc:  # scraper failure is inconclusive — retry next tick
        logger.warning("scan of saved search %s failed: %s", search.id, exc)
        result.ok = False
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    jobs = [j for j in (raw or []) if j.get("id") is not None][: _settings.scan_max_results]
    result.scraped = len(jobs)
    hits = matcher.filter_jobs(jobs, dict(search.filters or {}))
    result.matched = len(hits)

    if hits:
        ids = [str(j["id"]) for j in hits]
        existing_jobs = {
            j.id: j
            for j in (await session.execute(select(Job).where(Job.id.in_(ids)))).scalars()
        }
        already = set(
            (
                await session.execute(
                    select(SavedSearchMatch.job_id).where(
                        SavedSearchMatch.saved_search_id == search.id,
                        SavedSearchMatch.job_id.in_(ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        for data in hits:
            jid = str(data["id"])
            self_data = {**data, "id": jid}
            _ingest_job(session, existing_jobs.get(jid), self_data)
            if jid not in already:
                session.add(
                    SavedSearchMatch(
                        saved_search_id=search.id, job_id=jid, first_seen_at=now, is_new=True
                    )
                )
                already.add(jid)
                result.new += 1

    search.last_scanned_at = now
    return result


def _is_due(search: SavedSearch, now: datetime, interval: timedelta) -> bool:
    last = search.last_scanned_at
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    # Small slack so a slightly-early loop tick still fires on schedule.
    return (now - last) >= (interval - timedelta(seconds=30))


async def run_due_scans(
    session: AsyncSession,
    scraper: Scraper | None = None,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> ScanSummary:
    """Scan every enabled saved search that's due. Commits the session itself.

    Scrapes are fanned out concurrently (bounded); DB writes are applied
    sequentially since the AsyncSession isn't safe for concurrent use.
    """
    scraper = scraper or get_scraper()
    now = now or datetime.now(timezone.utc)
    interval = timedelta(minutes=_settings.scan_interval_minutes)
    summary = ScanSummary()

    searches = (
        (await session.execute(select(SavedSearch).where(SavedSearch.alert_enabled.is_(True))))
        .scalars()
        .all()
    )
    due = [s for s in searches if force or _is_due(s, now, interval)]
    summary.skipped_not_due = len(searches) - len(due)
    if not due:
        return summary

    # Fan out the (slow, I/O-bound) scrapes; ingest results one at a time.
    semaphore = asyncio.Semaphore(_settings.scan_concurrency)

    async def _scrape(filters: dict):
        async with semaphore:
            return await scraper(filters)

    scraped = await asyncio.gather(
        *(_scrape(dict(s.filters or {})) for s in due), return_exceptions=True
    )

    for search, raw in zip(due, scraped):
        if isinstance(raw, Exception):
            logger.warning("scan of saved search %s failed: %s", search.id, raw)
            summary.results.append(
                ScanResult(saved_search_id=search.id, ok=False, error=str(raw))
            )
            continue
        # Reuse scan_one's ingest path with the already-fetched results.
        result = await _ingest_prefetched(session, search, raw or [], now)
        summary.results.append(result)
        summary.ran += 1

    await session.commit()
    return summary


async def _ingest_prefetched(
    session: AsyncSession, search: SavedSearch, raw: list[dict], now: datetime
) -> ScanResult:
    """The ingest half of scan_one, given results already fetched by the fan-out."""

    async def _prefetched(_filters: dict) -> list[dict]:
        return raw

    return await scan_one(session, search, _prefetched, now=now)
