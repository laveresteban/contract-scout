"""In-process background loops: saved-search scan + scheduled scraping.

Two independent asyncio loops, started/stopped from the app lifespan:

* the **scan loop** re-runs due saved searches to surface newly-posted roles
  (controlled by ``CS_SCAN_*``);
* the **scrape loop** periodically scrapes the queries behind alert-enabled
  saved searches (plus ``SCHEDULED_QUERIES``) and sends due email alerts,
  enabled only when ``SCRAPE_INTERVAL_MINUTES > 0``.

Both are deliberately simple and per-instance (like the rate limiter and verify
cache). For multi-worker production, replace with a real scheduler/queue so N
workers don't each run — see README.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .. import config
from ..config import get_settings
from ..db import SessionLocal
from ..models import SavedSearch
from . import alerts as alert_service
from . import scan as scan_service
from . import scraper as scraper_module
from . import scrape_run
from . import verify as verify_service

logger = logging.getLogger(__name__)
_settings = get_settings()

_scan_task: asyncio.Task | None = None
_scrape_task: asyncio.Task | None = None
_reverify_task: asyncio.Task | None = None
_next_scrape_at: datetime | None = None


# ---------------------------------------------------------------------------
# Saved-search scan loop
# ---------------------------------------------------------------------------
def _tz() -> timezone | ZoneInfo:
    try:
        return ZoneInfo(_settings.scan_timezone)
    except Exception:
        logger.warning("unknown CS_SCAN_TIMEZONE %r; falling back to UTC", _settings.scan_timezone)
        return timezone.utc


def _is_weekday(now_utc: datetime) -> bool:
    """Mon–Fri in the configured timezone ('during the week')."""
    return now_utc.astimezone(_tz()).weekday() < 5


async def _scan_once() -> None:
    now = datetime.now(timezone.utc)
    if _settings.scan_weekdays_only and not _is_weekday(now):
        logger.debug("saved-search scan skipped: weekend")
        return
    async with SessionLocal() as session:
        summary = await scan_service.run_due_scans(session, now=now)
    if summary.ran:
        logger.info(
            "saved-search scan: ran %d, skipped %d not-due, %d new matches",
            summary.ran, summary.skipped_not_due, summary.total_new,
        )


async def _scan_loop() -> None:
    interval_seconds = max(60, _settings.scan_interval_minutes * 60)
    logger.info(
        "saved-search scan loop started (every %d min, weekdays_only=%s, tz=%s)",
        _settings.scan_interval_minutes, _settings.scan_weekdays_only, _settings.scan_timezone,
    )
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await _scan_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # never let one bad tick kill the loop
            logger.exception("saved-search scan tick failed")


# ---------------------------------------------------------------------------
# Scheduled scrape loop
# ---------------------------------------------------------------------------
async def _collect_queries(session) -> list[str]:
    """Queries to scrape: those behind alert-enabled saved searches, plus defaults."""
    queries: list[str] = []
    seen: set[str] = set()
    rows = (
        await session.execute(select(SavedSearch).where(SavedSearch.alert_enabled.is_(True)))
    ).scalars().all()
    for row in rows:
        q = str((row.filters or {}).get("query") or "").strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            queries.append(q)
    for q in config.SCHEDULED_QUERIES:
        if q.lower() not in seen:
            seen.add(q.lower())
            queries.append(q)
    return queries


async def _run_scheduled_scrape() -> None:
    logger.info("Scheduled scrape starting")
    async with SessionLocal() as session:
        for query in await _collect_queries(session):
            try:
                result = await scrape_run.run_scrape(session, query=query, trigger="scheduled")
                logger.info("Scheduled scrape for %r: %s", query, result)
            except Exception as exc:  # pragma: no cover
                logger.warning("Scheduled scrape for %r failed: %s", query, exc)
        sent = await alert_service.evaluate_alerts(session)
        logger.info("Scheduled scrape complete; %d alert email(s) sent", sent)


async def _scrape_loop() -> None:
    global _next_scrape_at
    interval_seconds = config.SCRAPE_INTERVAL_MINUTES * 60
    logger.info("Scheduled scrape loop started; every %d minutes", config.SCRAPE_INTERVAL_MINUTES)
    while True:
        try:
            _next_scrape_at = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
            await asyncio.sleep(interval_seconds)
            await _run_scheduled_scrape()
        except asyncio.CancelledError:
            raise
        except Exception:  # never let one bad tick kill the loop
            logger.exception("scheduled scrape tick failed")


def next_run_at() -> datetime | None:
    """Next scheduled scrape time, or None when the scrape loop is disabled."""
    return _next_scrape_at


# ---------------------------------------------------------------------------
# Background re-verification loop
# ---------------------------------------------------------------------------
async def _reverify_once() -> None:
    async with SessionLocal() as session:
        checked = await verify_service.reverify_stale(
            session,
            limit=_settings.verify_background_batch,
            stale_hours=_settings.verify_background_stale_hours,
        )
    if checked:
        logger.info("background re-verification: re-checked %d job(s)", checked)


async def _reverify_loop() -> None:
    interval_seconds = max(60, _settings.verify_background_interval_minutes * 60)
    logger.info(
        "background re-verification loop started (every %d min, batch %d, stale > %sh)",
        _settings.verify_background_interval_minutes,
        _settings.verify_background_batch,
        _settings.verify_background_stale_hours,
    )
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await _reverify_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # never let one bad tick kill the loop
            logger.exception("background re-verification tick failed")


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def start() -> None:
    global _scan_task, _scrape_task
    if _settings.scan_enabled:
        if not scraper_module.is_configured():
            logger.warning(
                "saved-search scan loop starting without a configured scraper; "
                "scans will find nothing until scraper.set_scraper(...) is called."
            )
        if _scan_task is None or _scan_task.done():
            _scan_task = asyncio.create_task(_scan_loop())
    else:
        logger.info("saved-search scan disabled (CS_SCAN_ENABLED=false)")

    if config.SCRAPE_INTERVAL_MINUTES > 0:
        if _scrape_task is None or _scrape_task.done():
            _scrape_task = asyncio.create_task(_scrape_loop())
    else:
        logger.info("Scheduled scraping disabled (SCRAPE_INTERVAL_MINUTES=0).")

    global _reverify_task
    if _settings.verify_background_enabled:
        if _reverify_task is None or _reverify_task.done():
            _reverify_task = asyncio.create_task(_reverify_loop())
    else:
        logger.info("Background re-verification disabled (CS_VERIFY_BACKGROUND_ENABLED=false).")


async def _cancel(task: asyncio.Task | None) -> None:
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def stop() -> None:
    global _scan_task, _scrape_task, _reverify_task, _next_scrape_at
    await _cancel(_scan_task)
    await _cancel(_scrape_task)
    await _cancel(_reverify_task)
    _scan_task = None
    _scrape_task = None
    _reverify_task = None
    _next_scrape_at = None
