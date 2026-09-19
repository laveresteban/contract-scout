"""Shared scraping orchestration used by the API and the scheduler.

Wraps the individual scrapers so that every run records timing, counts, and
errors in the `scrape_runs` table for source-health reporting. Ported onto the
async session: scrapes fan out with the same major/builtin/provider dispatch,
and persistence goes through the async `persist` module.
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from .. import config
from ..models import ScrapeRunORM
from . import boards, persist
from .providers import PROVIDERS, ProviderRequest

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _positive_terms(query: str | None) -> str:
    if not query:
        return ""
    return " ".join(p for p in query.split() if not p.startswith("-"))


async def _record_run(db: AsyncSession, source, trigger, status, found, saved, started, error=None, jobs=None):
    now = _utcnow()
    run = ScrapeRunORM(
        source=source,
        trigger=trigger,
        status=status,
        jobs_found=found,
        jobs_saved=saved,
        jobs_with_pay=sum(1 for job in jobs or [] if job.min_amount is not None or job.max_amount is not None),
        hourly_jobs=sum(1 for job in jobs or [] if job.interval == "hourly"),
        contract_jobs=sum(1 for job in jobs or [] if "contract" in (job.job_type or "").lower()),
        duration_ms=int((now - started).total_seconds() * 1000),
        error=(str(error)[:1000] if error else None),
        started_at=started,
        finished_at=now,
    )
    db.add(run)
    await db.commit()


async def scrape_source(
    source: str,
    *,
    term: str,
    location: str,
    is_remote: bool,
    job_type: str | None,
    employment_type: str | None,
    results_wanted: int,
    user_ip: str | None = None,
    user_agent: str | None = None,
    referer: str | None = None,
) -> list:
    """Scrape a single source and return `scraped.Job` objects (no DB writes)."""
    if source in boards.MAJOR_SOURCES:
        return await asyncio.to_thread(
            boards.scrape_major_boards,
            search_term=term,
            location=location or "United States",
            is_remote=is_remote,
            job_type=job_type or "contract",
            employment_type=employment_type,
            results_wanted=results_wanted,
            sources=[source],
        )
    if source in boards.BUILTIN_ASYNC_SOURCES:
        return await boards.scrape_builtin_source(
            source,
            search_term=term,
            job_type=job_type or "contract",
            employment_type=employment_type,
            results_wanted=results_wanted,
            is_remote=is_remote,
        )
    request = ProviderRequest(
        query=term,
        location=location,
        is_remote=is_remote,
        job_type=job_type,
        employment_type=employment_type,
        results_wanted=results_wanted,
        user_ip=user_ip,
        user_agent=user_agent,
        referer=referer,
    )
    return await PROVIDERS[source](request)


async def scrape_only(
    *,
    query: str,
    location: str = "United States",
    is_remote: bool = True,
    job_type: str | None = "contract",
    employment_type: str | None = None,
    results_wanted: int = 25,
    sources: list[str] | None = None,
) -> list:
    """Scrape the requested sources and return combined `scraped.Job` objects.

    Persistence-free — used by the saved-search scan, which does its own ingest
    and match bookkeeping.
    """
    term = _positive_terms(query) or query
    selected = [s for s in dict.fromkeys(sources or config.DEFAULT_SCRAPE_SOURCES) if s in boards.ALL_SOURCES]
    jobs: list = []
    for source in selected:
        try:
            jobs.extend(
                await scrape_source(
                    source,
                    term=term,
                    location=location,
                    is_remote=is_remote,
                    job_type=job_type,
                    employment_type=employment_type,
                    results_wanted=results_wanted,
                )
            )
        except Exception as exc:
            logger.warning("%s scrape failed during scan: %s", source, exc)
    return jobs


async def run_scrape(
    db: AsyncSession,
    *,
    query: str,
    location: str = "United States",
    is_remote: bool = True,
    job_type: str | None = "contract",
    employment_type: str | None = None,
    results_wanted: int = 25,
    sources: list[str] | None = None,
    trigger: str = "manual",
    user_ip: str | None = None,
    user_agent: str | None = None,
    referer: str | None = None,
) -> dict:
    """Run requested sources, persist jobs, and record per-source health."""
    positive = _positive_terms(query)
    term = positive or query
    selected = list(dict.fromkeys(sources or config.DEFAULT_SCRAPE_SOURCES))
    invalid = [source for source in selected if source not in boards.ALL_SOURCES]
    if invalid:
        raise ValueError(f"Unknown job source(s): {', '.join(invalid)}")

    scraped = 0
    saved = 0
    for source in selected:
        started = _utcnow()
        try:
            if source in boards.MAJOR_SOURCES:
                jobs = await asyncio.to_thread(
                    boards.scrape_major_boards,
                    search_term=term,
                    location=location or "United States",
                    is_remote=is_remote,
                    job_type=job_type or "contract",
                    employment_type=employment_type,
                    results_wanted=results_wanted,
                    sources=[source],
                )
            elif source in boards.BUILTIN_ASYNC_SOURCES:
                jobs = await boards.scrape_builtin_source(
                    source,
                    search_term=term,
                    job_type=job_type or "contract",
                    employment_type=employment_type,
                    results_wanted=results_wanted,
                    is_remote=is_remote,
                )
            else:
                request = ProviderRequest(
                    query=term,
                    location=location,
                    is_remote=is_remote,
                    job_type=job_type,
                    employment_type=employment_type,
                    results_wanted=results_wanted,
                    user_ip=user_ip,
                    user_agent=user_agent,
                    referer=referer,
                )
                jobs = await PROVIDERS[source](request)
            source_saved = await persist.save_jobs(jobs, db)
            scraped += len(jobs)
            saved += source_saved
            await _record_run(db, source, trigger, "success", len(jobs), source_saved, started, jobs=jobs)
        except Exception as exc:
            logger.warning("%s scrape failed: %s", source, exc)
            await _record_run(db, source, trigger, "error", 0, 0, started, error=exc)

    stale = await persist.mark_stale_jobs(db)
    return {"scraped": scraped, "saved": saved, "marked_inactive": stale}
