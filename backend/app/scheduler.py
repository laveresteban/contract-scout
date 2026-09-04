"""In-process scheduled scraping with APScheduler.

Enabled only when SCRAPE_INTERVAL_MINUTES > 0. Each run scrapes the queries
driven by alert-enabled saved searches (falling back to SCHEDULED_QUERIES),
then evaluates and sends any due email alerts.
"""
import logging

from app import config
from app.alerts import evaluate_alerts
from app.models import SessionLocal, SavedSearchORM
from app.scrape_service import run_scrape

logger = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    _APS_AVAILABLE = True
except ImportError:  # pragma: no cover
    AsyncIOScheduler = None
    _APS_AVAILABLE = False

_scheduler = None


def _collect_queries(db) -> list[str]:
    """Queries to scrape: those behind alert-enabled saved searches, plus defaults."""
    queries: list[str] = []
    seen = set()
    rows = db.query(SavedSearchORM).filter(SavedSearchORM.alert_enabled.is_(True)).all()
    for row in rows:
        try:
            import json

            q = (json.loads(row.filters or "{}").get("query") or "").strip()
        except (ValueError, TypeError):
            q = ""
        if q and q.lower() not in seen:
            seen.add(q.lower())
            queries.append(q)
    for q in config.SCHEDULED_QUERIES:
        if q.lower() not in seen:
            seen.add(q.lower())
            queries.append(q)
    return queries


async def run_scheduled_scrape():
    logger.info("Scheduled scrape starting")
    db = SessionLocal()
    try:
        for query in _collect_queries(db):
            try:
                result = await run_scrape(db, query=query, trigger="scheduled")
                logger.info("Scheduled scrape for %r: %s", query, result)
            except Exception as exc:  # pragma: no cover
                logger.warning("Scheduled scrape for %r failed: %s", query, exc)
        sent = evaluate_alerts(db)
        logger.info("Scheduled scrape complete; %d alert email(s) sent", sent)
    finally:
        db.close()


def start_scheduler():
    global _scheduler
    if not _APS_AVAILABLE:
        logger.warning("APScheduler not installed; scheduled scraping disabled.")
        return
    if config.SCRAPE_INTERVAL_MINUTES <= 0:
        logger.info("Scheduled scraping disabled (SCRAPE_INTERVAL_MINUTES=0).")
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        run_scheduled_scrape,
        "interval",
        minutes=config.SCRAPE_INTERVAL_MINUTES,
        id="scheduled_scrape",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started; every %d minutes", config.SCRAPE_INTERVAL_MINUTES)


def stop_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def next_run_time():
    if _scheduler is None:
        return None
    job = _scheduler.get_job("scheduled_scrape")
    return job.next_run_time if job else None
