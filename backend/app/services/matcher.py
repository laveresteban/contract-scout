"""Decide whether a scraped posting satisfies a saved search's filters.

The real scraper is expected to apply the filters server-side, but we re-check
here defensively so a loose scraper can't leak off-target roles into a user's
"new matches" — trust/quality is the product's whole point. Filter keys mirror
`frontend/src/utils/filters.js`; unknown keys are ignored.
"""

from __future__ import annotations

# Eligibility values we treat as US-eligible (see the frontend quality engine).
_US_ELIGIBLE = {"explicit_us", "remote_us_assumed"}


def _text(job: dict, *keys: str) -> str:
    return " ".join(str(job.get(k) or "") for k in keys).lower()


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def matches(job: dict, filters: dict) -> bool:
    """True if `job` satisfies every constraint present in `filters`.

    A missing/blank filter is not a constraint. Missing job data fails only the
    filters that actually require that field.
    """
    filters = filters or {}

    query = (filters.get("query") or "").strip().lower()
    if query and query not in _text(job, "title", "description", "company"):
        return False

    job_type = (filters.get("job_type") or "").strip().lower()
    if job_type and job_type != str(job.get("job_type") or "").lower():
        return False

    employment_type = (filters.get("employment_type") or "").strip().lower()
    if employment_type and employment_type != str(job.get("employment_type") or "").lower():
        return False

    company = (filters.get("company") or "").strip().lower()
    if company and company not in str(job.get("company") or "").lower():
        return False

    source = (filters.get("source") or "").strip().lower()
    if source and source != str(job.get("site") or "").lower():
        return False

    # Contract Scout targets remote + US-eligible roles. The frontend always
    # sends is_remote truthy; honor it when present.
    if filters.get("is_remote") and not job.get("is_remote"):
        return False
    if filters.get("us_eligible") and str(job.get("eligibility") or "") not in _US_ELIGIBLE:
        return False

    # Pay is compared on the normalized yearly-USD scale both sides share.
    min_yearly = _num(filters.get("min_yearly"))
    if min_yearly is not None:
        # A job with no pay data can't be proven to clear the floor, but we don't
        # want to bury it silently — the frontend flags unknown pay separately.
        # Only exclude when the job *has* a max below the requested minimum.
        job_max = _num(job.get("normalized_max_yearly"))
        if job_max is not None and job_max < min_yearly:
            return False

    max_yearly = _num(filters.get("max_yearly"))
    if max_yearly is not None:
        job_min = _num(job.get("normalized_min_yearly"))
        if job_min is not None and job_min > max_yearly:
            return False

    return True


def filter_jobs(jobs: list[dict], filters: dict) -> list[dict]:
    return [job for job in jobs if matches(job, filters)]
