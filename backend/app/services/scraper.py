"""The scrape boundary for the saved-search scan.

Contract Scout's real scraping (`POST /search`) lives in a *separate* backend,
so this package can't call it directly. Instead the scan depends on a small
injectable interface: an async callable that takes a saved search's `filters`
and returns a list of job dicts. In production you wire `set_scraper(...)` to a
function that calls the real scraper; in this standalone package (and in tests)
it defaults to a no-op stub so the scheduler runs without exploding.

A returned job dict should carry at least an `id` plus the columns the `Job`
model renders (title, company, job_url, is_remote, date_posted, …). Unknown keys
are ignored on ingest.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# async (filters: dict) -> list[dict]
Scraper = Callable[[dict], Awaitable[list[dict]]]


async def _null_scraper(filters: dict) -> list[dict]:
    """Default when no real scraper is wired in — finds nothing, loudly once."""
    logger.warning(
        "saved-search scan ran with no scraper configured; call "
        "scraper.set_scraper(...) to connect the real /search backend. "
        "Returning no results."
    )
    return []


_scraper: Scraper = _null_scraper


def set_scraper(fn: Scraper) -> None:
    """Register the function the scan uses to fetch fresh postings.

    In the real backend, pass an adapter that calls the scraping service with
    the saved search's filters and returns job dicts.
    """
    global _scraper
    _scraper = fn


def get_scraper() -> Scraper:
    return _scraper


def is_configured() -> bool:
    """True once a real scraper has been wired in (not the null stub)."""
    return _scraper is not _null_scraper
