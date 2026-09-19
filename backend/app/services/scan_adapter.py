"""Adapter connecting the saved-search scan to the real board scraper.

The scan depends on an injectable ``async (filters: dict) -> list[dict]``
(`services.scraper.Scraper`). Here we implement it against the ported scraping
stack: map a saved search's stored filters onto scrape parameters, run the
sources, and return job dicts (including the computed normalized-pay and
eligibility fields the matcher/ingest rely on). Wired in at app startup via
``scraper.set_scraper(scan_scraper)``.
"""

from __future__ import annotations

from ..config import get_settings
from . import scrape_run

_settings = get_settings()


async def scan_scraper(filters: dict) -> list[dict]:
    filters = filters or {}
    jobs = await scrape_run.scrape_only(
        query=str(filters.get("query") or ""),
        location=str(filters.get("location") or "United States"),
        is_remote=bool(filters.get("is_remote", True)),
        job_type=filters.get("job_type") or "contract",
        employment_type=filters.get("employment_type"),
        results_wanted=int(filters.get("results_wanted") or 25),
        sources=filters.get("sources"),
    )
    # `model_dump(mode="json")` includes the computed normalized_* / eligibility
    # fields the matcher filters on and the scan ingest stores.
    return [job.model_dump(mode="json") for job in jobs][: _settings.scan_max_results]
