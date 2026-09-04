"""Shared scraping orchestration used by the API and the scheduler.

Wraps the individual scrapers so that every run records timing, counts, and
errors in the `scrape_runs` table for source-health reporting.
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app import config, scraper
from app.models import ScrapeRunORM
from app.providers import PROVIDERS, ProviderRequest

logger = logging.getLogger(__name__)


def _positive_terms(query: str | None) -> str:
    if not query:
        return ""
    return " ".join(p for p in query.split() if not p.startswith("-"))


def _record_run(db: Session, source, trigger, status, found, saved, started, error=None):
    now = datetime.utcnow()
    run = ScrapeRunORM(
        source=source,
        trigger=trigger,
        status=status,
        jobs_found=found,
        jobs_saved=saved,
        duration_ms=int((now - started).total_seconds() * 1000),
        error=(str(error)[:1000] if error else None),
        started_at=started,
        finished_at=now,
    )
    db.add(run)
    db.commit()


async def run_scrape(
    db: Session,
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
    invalid = [source for source in selected if source not in scraper.ALL_SOURCES]
    if invalid:
        raise ValueError(f"Unknown job source(s): {', '.join(invalid)}")

    scraped = 0
    saved = 0
    for source in selected:
        started = datetime.utcnow()
        try:
            if source in scraper.MAJOR_SOURCES:
                jobs = await asyncio.to_thread(
                    scraper.scrape_major_boards,
                    search_term=term,
                    location=location or "United States",
                    is_remote=is_remote,
                    job_type=job_type or "contract",
                    employment_type=employment_type,
                    results_wanted=results_wanted,
                    sources=[source],
                )
            elif source in scraper.BUILTIN_ASYNC_SOURCES:
                jobs = await scraper.scrape_builtin_source(
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
            source_saved = scraper.save_jobs(jobs, db)
            scraped += len(jobs)
            saved += source_saved
            _record_run(db, source, trigger, "success", len(jobs), source_saved, started)
        except Exception as exc:
            logger.warning("%s scrape failed: %s", source, exc)
            _record_run(db, source, trigger, "error", 0, 0, started, error=exc)

    return {"scraped": scraped, "saved": saved}
