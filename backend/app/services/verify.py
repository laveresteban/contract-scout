"""Re-fetch a job's original posting and decide whether it's still live.

This is the one check the frontend can't do: the scrape fields (`is_remote`,
`date_posted`) rot immediately, so we go back to the source URL and persist a
verdict everyone benefits from. Key rule: a transient failure is *inconclusive*
(`unreachable`), never `expired` — we must not bury a live job on a timeout.
"""

import re
from datetime import datetime, timedelta, timezone

import httpx

from ..config import get_settings
from ..models import Job, VerifyStatus
from . import salary as salary_service

_settings = get_settings()

# HTTP-200-but-closed: boards keep the URL alive and swap in a "closed" notice.
_DEAD_MARKERS = re.compile(
    r"(no longer (accepting|available|open)"
    r"|this (job|position|posting) (has|is)\s+(closed|expired|been filled|no longer)"
    r"|position (has been )?filled"
    r"|posting (has )?(expired|closed)"
    r"|applications? (are )?(closed|no longer)"
    r"|job (not found|has expired)"
    r"|404 error"
    r"|we('|’)re sorry, this job)",
    re.I,
)

# On-site / hybrid signals, to re-confirm the remote claim against live copy.
_ONSITE = re.compile(
    r"\b(on-?site|in-office|in[-\s]person|hybrid|must relocate|report to .{0,20}office)\b",
    re.I,
)

_MAX_BODY = 200_000  # cap; some boards ship enormous pages

# Strip tags/scripts so the salary parser reads copy, not markup.
_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.I | re.S)


def _visible_text(html: str) -> str:
    return _TAG.sub(" ", html)


def _maybe_scrape_salary(job: Job, body: str, force: bool) -> None:
    """Fill in pay from the live posting when we're missing it (or on a forced
    re-check). Never clobbers a range the original scrape already captured
    unless the user explicitly asked to re-check."""
    has_pay = job.min_amount is not None or job.max_amount is not None
    if has_pay and not force:
        return
    found = salary_service.parse_salary(_visible_text(body))
    if not found:
        return
    for field, value in found.items():
        setattr(job, field, value)


def _cache_fresh(job: Job) -> bool:
    if not job.verify_checked_at or job.verify_status == VerifyStatus.unverified.value:
        return False
    checked = job.verify_checked_at
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - checked
    return age < timedelta(hours=_settings.verify_cache_hours)


def _persist(job: Job, status: VerifyStatus, detail: str, http_status: int | None) -> dict:
    job.verify_status = status.value
    job.verify_detail = detail
    job.verify_http_status = http_status
    job.verify_checked_at = datetime.now(timezone.utc)
    return _result(job, cached=False)


def _result(job: Job, *, cached: bool) -> dict:
    return {
        "status": job.verify_status,
        "detail": job.verify_detail,
        "http_status": job.verify_http_status,
        "checked_at": job.verify_checked_at,
        "cached": cached,
        # Pay may have just been scraped off the live page; echo it back so the
        # UI can update the card without a second round-trip.
        "min_amount": job.min_amount,
        "max_amount": job.max_amount,
        "currency": job.currency,
        "interval": job.interval,
        "normalized_min_yearly": job.normalized_min_yearly,
        "normalized_max_yearly": job.normalized_max_yearly,
    }


async def verify_job(job: Job, *, force: bool = False, client: httpx.AsyncClient | None = None) -> dict:
    """Verify one job, mutating its verify_* fields. Caller commits the session."""
    if not force and _cache_fresh(job):
        return _result(job, cached=True)

    url = job.job_url_direct or job.job_url
    if not url:
        return _persist(job, VerifyStatus.unreachable, "No source URL on record.", None)

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(_settings.verify_timeout_seconds, connect=4.0),
            follow_redirects=True,
            headers={"User-Agent": _settings.verify_user_agent},
        )
    try:
        resp = await client.get(url)
    except httpx.HTTPError as exc:
        return _persist(job, VerifyStatus.unreachable, f"Fetch failed: {type(exc).__name__}.", None)
    finally:
        if owns_client:
            await client.aclose()

    if resp.status_code in (404, 410):
        return _persist(job, VerifyStatus.expired, f"Source returned {resp.status_code}.", resp.status_code)
    if resp.status_code >= 400:
        return _persist(
            job, VerifyStatus.unreachable, f"Source returned {resp.status_code}.", resp.status_code
        )

    body = resp.text[:_MAX_BODY]
    if _DEAD_MARKERS.search(body):
        return _persist(job, VerifyStatus.expired, "Posting reports it's closed or filled.", resp.status_code)

    # Live page — mine the pay out of it while we have the body in hand.
    _maybe_scrape_salary(job, body, force)

    detail = "Posting reachable and appears open."
    if job.is_remote and _ONSITE.search(body):
        detail = "Live — but the page mentions on-site/hybrid, so remote is unverified."
    return _persist(job, VerifyStatus.live, detail, resp.status_code)


def new_client() -> httpx.AsyncClient:
    """Shared client for batch verification (one connection pool for the fan-out)."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(_settings.verify_timeout_seconds, connect=4.0),
        follow_redirects=True,
        headers={"User-Agent": _settings.verify_user_agent},
    )
