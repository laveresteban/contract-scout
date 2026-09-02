import asyncio
import hashlib
import json
import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.config import APIFY_ACTOR_ID, APIFY_API_TOKEN, DEFAULT_RESULTS_PER_BOARD, SCRAPER_HOURS_OLD
from app.models import Job, JobORM

logger = logging.getLogger(__name__)


MAJOR_SOURCES = ["indeed", "linkedin", "zip_recruiter", "google"]
REMOTE_SOURCES = ["remoteok", "weworkremotely", "jobicy", "remotive"]
APIFY_SOURCE = "apify"
ALL_SOURCES = MAJOR_SOURCES + REMOTE_SOURCES + [APIFY_SOURCE]


# Try to import jobspy; it is an optional dependency for major boards.
try:
    from jobspy import scrape_jobs

    JOBSPI_AVAILABLE = True
except ImportError:
    scrape_jobs = None
    JOBSPI_AVAILABLE = False
    logger.warning("python-jobspy is not installed. Major board scraping disabled.")

# Try to import the Apify async client; it is an optional dependency.
try:
    from apify_client import ApifyClientAsync

    APIFY_CLIENT_AVAILABLE = True
except ImportError:
    ApifyClientAsync = None
    APIFY_CLIENT_AVAILABLE = False
    logger.warning("apify-client is not installed. Apify source disabled.")


import httpx


US_PATTERNS = [
    re.compile(r"\bunited states\b"),
    re.compile(r"\busa\b"),
    re.compile(r"\bus\b"),
    re.compile(r"\bu\.s\.a?\b"),
    re.compile(r"\bremote[- ]?(?:us|usa)\b"),
]
NON_US_PATTERNS = [
    re.compile(r"\bindia\b"),
    re.compile(r"\bchina\b"),
    re.compile(r"\beurope\b"),
    re.compile(r"\buk\b"),
    re.compile(r"\bcanada\b"),
    re.compile(r"\bmexico\b"),
    re.compile(r"\bbrazil\b"),
    re.compile(r"\bargentina\b"),
    re.compile(r"\bapac\b"),
    re.compile(r"\blatam\b"),
    re.compile(r"\baustralia\b"),
    re.compile(r"\basia\b"),
    re.compile(r"\bafrica\b"),
]
US_FAVORABLE_PATTERNS = [
    re.compile(r"\bworldwide\b"),
    re.compile(r"\banywhere\b"),
    re.compile(r"\bglobal\b"),
    re.compile(r"\bamericas\b"),
    re.compile(r"\bremote\b"),
]


# Strong contract / freelance role indicators.
CONTRACT_ROLE_PATTERNS = [
    re.compile(r"\bcontractor\b"),
    re.compile(r"\bcontract(?:ual)?\s+(?:role|position|opportunity|job|employment)\b"),
    re.compile(r"\bindependent\s+contract(?:or)?\b"),
    re.compile(r"\bfreelance(?:r)?\b"),
    re.compile(r"\bc2c\b"),
    re.compile(r"\bcorp[- ]to[- ]corp"),
    re.compile(r"\b1099\b"),
    re.compile(r"\bcontingent\b.{0,80}\b(?:contract\s+award|customer\s+funding)\b", re.DOTALL),
    re.compile(r"\bcontingent\s+upon\s+contract\s+award\b"),
    re.compile(r"\bposition\s+contingent\s+upon\s+contract\s+award\b"),
]

# Strong full-time / employee role indicators.
EMPLOYEE_ROLE_PATTERNS = [
    re.compile(r"\bfull[- ]?time\s+(?:employee|associate|staff|role|position)\b"),
    re.compile(r"\bemployee\s+(?:position|role)\b"),
    re.compile(r"\bpermanent\s+(?:employee|associate|staff|role|position)\b"),
    re.compile(r"\bemployee\s+(?:benefits|stock\s+purchase|assistance\s+program)\b"),
    re.compile(r"\b401\s*\(?k\)?\b"),
    re.compile(r"\b(?:medical|dental|vision)\s+(?:insurance|benefits)\b"),
    re.compile(r"\bpaid\s+(?:time\s+off|vacation|holidays)\b"),
    re.compile(r"\bbenefits\s+package\b"),
]

# Strong remote work indicators.
REMOTE_PATTERNS = [
    re.compile(r"\bremote\s+(?:role|position|job|opportunity|work(?:er)?)\b"),
    re.compile(r"\b(?:fully?|100%|completely)\s*remote\b"),
    re.compile(r"\bwork\s+from\s+home\b"),
    re.compile(r"\bwork\s+remotely\b"),
    re.compile(r"\bremote[- ]?first\b"),
    re.compile(r"\btelecommut(?:e|ing|er)?\b"),
    re.compile(r"\bvirtual\s+(?:position|role|job)\b"),
]

# Onsite indicators that should override remote detection.
ONSITE_PATTERNS = [
    re.compile(r"\(onsite\)"),
    re.compile(r"\bon[- ]?site\s+(?:role|position|job)\b"),
    re.compile(r"\bthis\s+position\s+is\s+an?\s+on[- ]?site\s+role\b"),
    re.compile(r"\bposition\s+role\s+type\s*:\s*on[- ]?site\b"),
]

# Generic "remote" contexts that are not actual remote-work signals.
REMOTE_FALSE_POSITIVE_PATTERNS = [
    re.compile(r"\bremote[- ]?us(?:a?)?\b"),
    re.compile(r"\bon[- ]?site,\s*hybrid,\s*(?:and\s*|or\s*)?remote\b"),
    re.compile(r"\bvirtual\s+(?:doctor|visit|environment|machine|account|team)\b"),
]


def _normalize_location(location: str | None) -> tuple[bool, bool]:
    """Return (is_remote, is_us) from a location string."""
    if not location:
        return False, False
    loc = location.lower()
    is_remote = bool(re.search(r"\bremote\b", loc))
    # Worldwide / anywhere / global postings are also remote.
    if not is_remote and any(
        p.search(loc) for p in [re.compile(r"\bworldwide\b"), re.compile(r"\banywhere\b"), re.compile(r"\bglobal\b")]
    ):
        is_remote = True
    has_us = any(p.search(loc) for p in US_PATTERNS)
    has_non_us = any(p.search(loc) for p in NON_US_PATTERNS)
    is_us_favorable = any(p.search(loc) for p in US_FAVORABLE_PATTERNS)
    # A role is US-eligible if it explicitly mentions the US, or if it is
    # remote/worldwide/anywhere and does not restrict to a non-US region.
    is_us = has_us or (is_us_favorable and not has_non_us)
    # For remote jobs without an explicit country, assume US unless a non-US
    # country is mentioned.
    if is_remote and not is_us and not has_non_us:
        is_us = True
    return is_remote, is_us


def _title_matches(title: str, keyword: str) -> bool:
    """Check whether the title contains any of the keyword words."""
    return _keyword_matches(title, keyword)


def _keyword_matches(text: str | None, keyword: str) -> bool:
    """Check whether any keyword word appears in the text.

    This is used for client-side keyword filtering across titles,
    descriptions, tags, and company names.
    """
    if not text or not keyword:
        return True
    text_l = re.sub(r"<[^>]+>", " ", text).lower()
    words = [w for w in keyword.lower().split() if len(w) > 2]
    if not words:
        return True
    return any(w in text_l for w in words)


def _text_indicates_contract_role(text: str | None) -> bool:
    """Detect genuine contract/freelance role wording."""
    if not text:
        return False
    text = text.lower()
    return any(p.search(text) for p in CONTRACT_ROLE_PATTERNS)


def _text_indicates_employee_role(text: str | None) -> bool:
    """Detect full-time/employee role wording."""
    if not text:
        return False
    text = text.lower()
    return any(p.search(text) for p in EMPLOYEE_ROLE_PATTERNS)


def _text_indicates_onsite(title: str | None, description: str | None) -> bool:
    """Detect explicit onsite/ not-remote wording."""
    text = " ".join([title or "", description or ""]).lower()
    return any(p.search(text) for p in ONSITE_PATTERNS)


def _text_indicates_remote(title: str | None, description: str | None) -> bool:
    """Detect genuine remote-work wording, ignoring salary/benefit disclaimers."""
    text = " ".join([title or "", description or ""]).lower()
    if any(p.search(text) for p in REMOTE_PATTERNS):
        return True
    if re.search(r"\bremote\b", text):
        if any(p.search(text) for p in REMOTE_FALSE_POSITIVE_PATTERNS):
            return False
        return True
    return False


def _detect_employment_type(description: str | None, title: str | None) -> str | None:
    """Infer employment type from text: w2, 1099, c2c, contract."""
    text = " ".join([description or "", title or ""]).lower()

    if re.search(r"\bc2c\b|corp[- ]to[- ]corp", text):
        return "c2c"
    if re.search(r"\b1099\b|independent contractor", text):
        return "1099"
    if re.search(r"\bw2\b|w-2|full[- ]time employee|employee position", text):
        return "w2"
    if _text_indicates_contract_role(text):
        return "contract"
    return None


def _parse_amount(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_pay_from_text(text: str | None) -> tuple[float | None, float | None, str | None]:
    """Extract a pay range and interval from free-text job descriptions."""
    if not text:
        return None, None, None

    patterns = [
        (r"salary\s*range\s*[:$]?\s*\$?([\d,]+)\s*(?:–|-|---)\s*\$?([\d,]+)\s*(?:per\s+year|annually|/year|a\s+year|yearly)?", "yearly"),
        (r"salary[^.]{0,60}ranges?\s+between\s+\$?([\d,]+)\s+and\s+\$?([\d,]+)\s*(?:per\s+year|annually|/year|a\s+year|yearly)?", "yearly"),
        (r"\$([\d,]+)\s*(?:–|-|---)\s*\$?([\d,]+)\s*(?:per\s+year|annually|/year|a\s+year|yearly)", "yearly"),
        (r"\$([\d,]+)\s*(?:–|-|---)\s*\$?([\d,]+)\s*(?:per\s+hour|hourly|/hour)", "hourly"),
        (r"\$([\d,]+)\s+(?:per\s+year|annually|/year|yearly)", "yearly"),
        (r"\$([\d,]+)\s+(?:per\s+hour|hourly|/hour)", "hourly"),
    ]

    for pattern, interval in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            lo = float(m.group(1).replace(",", ""))
            hi = float(m.group(2).replace(",", "")) if m.group(2) else None
            return lo, hi, interval

    return None, None, None


def _matches_job_request(
    job: Job,
    job_type: str | None,
    employment_type: str | None,
) -> bool:
    """Check whether a scraped job matches the requested type filters."""
    if not job_type and not employment_type:
        return True

    if job_type:
        jt = (job.job_type or "").lower()
        et = (job.employment_type or "").lower()
        if job_type.lower() in jt or job_type.lower() in et:
            return True
        # Strong contract wording in title/description can also qualify.
        if job_type.lower() == "contract" and _text_indicates_contract_role(
            f"{job.title or ''} {job.description or ''}"
        ):
            return True
        if job_type.lower() == "contingent" and (
            "contingent" in jt or "contingent" in et
        ):
            return True
        return False

    if employment_type:
        jt = (job.job_type or "").lower()
        et = (job.employment_type or "").lower()
        if employment_type.lower() in et or employment_type.lower() in jt:
            return True
        return False

    return True


def _row_to_job(row: pd.Series) -> Job:
    location = str(row.get("location")) if pd.notna(row.get("location")) else None
    is_remote, is_us = _normalize_location(location)

    # JobSpy sets an explicit is_remote column; trust it unless the text
    # explicitly says the role is onsite.
    raw_is_remote = row.get("is_remote")
    if raw_is_remote is not None and not pd.isna(raw_is_remote):
        is_remote = bool(raw_is_remote)

    description = str(row.get("description")) if pd.notna(row.get("description")) else None
    title = str(row.get("title")) if pd.notna(row.get("title")) else None
    employment_type = _detect_employment_type(description, title)

    # Some sources don't tag remote in the location, but mention it in the title/description.
    if _text_indicates_onsite(title, description):
        is_remote = False
    elif not is_remote:
        is_remote = _text_indicates_remote(title, description)

    # JobSpy's job_type column is sometimes inaccurate. Resolve it against the text.
    inferred_job_type = str(row.get("job_type")) if pd.notna(row.get("job_type")) else None
    text = " ".join([description or "", title or ""]).lower()
    contract_signal = _text_indicates_contract_role(text)
    employee_signal = _text_indicates_employee_role(text)

    if contract_signal and employee_signal:
        # Explicit contract/contingent wording takes precedence over benefits context.
        inferred_job_type = "contract"
        if not employment_type:
            employment_type = "contract"
    elif contract_signal and not employee_signal:
        inferred_job_type = "contract"
        if not employment_type:
            employment_type = "contract"
    elif employee_signal and not contract_signal:
        inferred_job_type = "fulltime"
        if not employment_type:
            employment_type = "w2"
    elif (
        inferred_job_type
        and "contract" in inferred_job_type.lower()
        and employee_signal
    ):
        # JobSpy called it contract, but the description points to a regular employee role.
        inferred_job_type = "fulltime"
        employment_type = "w2"
    elif (
        inferred_job_type
        and "full" in inferred_job_type.lower()
        and contract_signal
    ):
        # JobSpy called it full-time, but the description clearly describes a contract role.
        inferred_job_type = "contract"
        if not employment_type:
            employment_type = "contract"

    date_posted = row.get("date_posted")
    if pd.isna(date_posted):
        date_posted = None
    elif isinstance(date_posted, str):
        try:
            date_posted = datetime.fromisoformat(date_posted.replace("Z", "+00:00"))
        except ValueError:
            date_posted = None
    elif isinstance(date_posted, datetime):
        pass
    else:
        date_posted = None

    job_id = str(row.get("id")) if pd.notna(row.get("id")) else None
    if not job_id:
        digest = hashlib.md5(
            f"{row.get('title')}{row.get('company')}{row.get('job_url')}".encode()
        ).hexdigest()[:16]
        job_id = f"{row.get('site', 'unknown')}-{digest}"

    return Job(
        id=job_id,
        site=str(row.get("site")) if pd.notna(row.get("site")) else "unknown",
        title=title or "Untitled",
        company=str(row.get("company")) if pd.notna(row.get("company")) else "Unknown",
        location=location,
        job_url=str(row.get("job_url")) if pd.notna(row.get("job_url")) else None,
        job_url_direct=str(row.get("job_url_direct")) if pd.notna(row.get("job_url_direct")) else None,
        description=description,
        job_type=inferred_job_type,
        employment_type=employment_type,
        interval=str(row.get("interval")) if pd.notna(row.get("interval")) else None,
        min_amount=_parse_amount(row.get("min_amount")),
        max_amount=_parse_amount(row.get("max_amount")),
        currency=str(row.get("currency")) if pd.notna(row.get("currency")) else None,
        is_remote=is_remote,
        is_us=is_us,
        date_posted=date_posted,
        date_scraped=datetime.utcnow(),
    )


def scrape_major_boards(
    search_term: str,
    location: str = "United States",
    is_remote: bool = True,
    job_type: str = "contract",
    employment_type: str | None = None,
    results_wanted: int = DEFAULT_RESULTS_PER_BOARD,
    sources: list[str] | None = None,
) -> list[Job]:
    """Scrape major job boards using JobSpy."""
    if not JOBSPI_AVAILABLE:
        logger.error("python-jobspy not installed; cannot scrape major boards.")
        return []

    # Indeed and LinkedIn are the most reliable sources in this set.
    # ZipRecruiter frequently returns 403 and Google returns few results, so
    # they are left out of the default.
    default_sources = ["indeed", "linkedin"]
    sources = sources or default_sources

    is_contract_search = bool(job_type and "contract" in job_type.lower())
    base = search_term.lower()

    if is_contract_search:
        # JobSpy's job_type='contract' filter is unreliable, so we search for
        # contract-related phrasing directly and then filter the rows ourselves.
        # If the query already contains contract language, use it as-is.
        has_contract_term = any(
            word in base
            for word in ("contract", "freelance", "1099", "c2c", "corp-to-corp")
        )
        terms = [search_term] if has_contract_term else []
        if "freelance" not in base and "contract" not in base:
            terms.append(f"freelance {search_term}")
        if "1099" not in base:
            terms.append(f"{search_term} 1099")
        if "c2c" not in base and "corp-to-corp" not in base:
            terms.append(f"{search_term} c2c")
        # Remove duplicates while preserving order.
        seen_terms = set()
        terms = [t for t in terms if not (t.lower() in seen_terms or seen_terms.add(t.lower()))]
        jobspy_job_type = None
    else:
        terms = [search_term]
        jobspy_job_type = job_type

    # Don't hammer the boards; split the per-board quota across query terms.
    per_term = max(5, results_wanted // max(1, len(terms)))

    seen = set()
    jobs: list[Job] = []

    for term in terms:
        try:
            df: pd.DataFrame = scrape_jobs(
                site_name=sources,
                search_term=term,
                location=location,
                is_remote=is_remote,
                job_type=jobspy_job_type,
                results_wanted=per_term,
                hours_old=SCRAPER_HOURS_OLD,
                country_indeed="USA",
            )
        except Exception as exc:
            logger.exception("JobSpy scrape failed for term %r: %s", term, exc)
            continue

        if df is None or df.empty:
            continue

        for _, row in df.iterrows():
            try:
                job = _row_to_job(row)
                # Keep only remote, US-ish roles that also match the requested type.
                if job.is_remote and (job.is_us or "remote" in (job.location or "").lower()):
                    if not _keyword_matches(
                        f"{job.title} {job.description or ''} {job.company}",
                        search_term,
                    ):
                        continue
                    if _matches_job_request(job, job_type, employment_type):
                        if job.id not in seen:
                            seen.add(job.id)
                            jobs.append(job)
            except Exception as exc:
                logger.warning("Failed to parse job row: %s", exc)

        if len(jobs) >= results_wanted:
            break

    logger.info("Major board scrape finished, found %d jobs", len(jobs))
    return jobs[:results_wanted]


def _remoteok_location(item: dict) -> str:
    """Build a location string from a RemoteOK feed item."""
    loc = item.get("location") or "Remote"
    return loc if loc.strip() else "Remote"


def _wwr_location(item: ET.Element) -> str:
    """Build a location string from a WWR RSS item."""
    parts = [
        item.findtext("country", ""),
        item.findtext("state", ""),
        item.findtext("region", ""),
    ]
    loc = ", ".join(p for p in parts if p and p.strip())
    return loc if loc.strip() else "Remote"


def _parse_wwr_title(title: str) -> tuple[str, str]:
    """WWR titles are formatted 'Company : Role'. Split on first colon."""
    if ":" in title:
        company, role = title.split(":", 1)
        return company.strip(), role.strip()
    return "Unknown", title.strip()


def _parse_iso_date(value: Any) -> datetime | None:
    if not value or (isinstance(value, float) and value != value):  # NaN check
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_rss_date(value: str | None) -> datetime | None:
    if not value:
        return None
    # Common RSS date format: 'Mon, 02 Jan 2006 15:04:05 GMT' or with timezone
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _employment_type_from_text(text: str | None) -> str | None:
    """Infer w2 / 1099 / c2c / contract from job description/title."""
    return _detect_employment_type(text, "")


def _infer_job_type_from_tags(tags: list[str]) -> str | None:
    """Infer a structured job type from RemoteOK tags."""
    lowered = [t.lower() for t in tags]
    for tag in lowered:
        if tag in ("full time", "full-time"):
            return "fulltime"
        if tag in ("part time", "part-time"):
            return "parttime"
        if tag in ("contract", "freelance", "temporary"):
            return "contract"
        if tag == "intern":
            return "internship"
    return None


def _build_remoteok_job(
    item: dict,
    job_type: str | None = None,
    employment_type: str | None = None,
) -> Job | None:
    title = (item.get("position") or "").strip()
    if not title:
        return None
    location = _remoteok_location(item)
    is_remote, is_us = _normalize_location(location)
    is_remote = True  # RemoteOK is remote-only
    description = item.get("description") or ""
    text = f"{title} {description}".lower()

    inferred_job_type = _infer_job_type_from_tags(item.get("tags", []))
    if not inferred_job_type:
        if _text_indicates_contract_role(text):
            inferred_job_type = "contract"
        elif re.search(r"\bfull[- ]?time\b", text):
            inferred_job_type = "fulltime"
        elif re.search(r"\bpart[- ]?time\b", text):
            inferred_job_type = "parttime"

    inferred_employment_type = _employment_type_from_text(text)
    if inferred_job_type == "contract" and not inferred_employment_type:
        inferred_employment_type = "contract"

    if not _matches_job_request(
        Job(
            id="",
            site="remoteok",
            title=title,
            company=(item.get("company") or "Unknown").strip(),
            job_type=inferred_job_type,
            employment_type=inferred_employment_type,
            is_remote=is_remote,
            is_us=is_us,
        ),
        job_type,
        employment_type,
    ):
        return None

    job_url = item.get("url") or item.get("apply_url") or ""
    raw_id = str(item.get("id")) if item.get("id") else (job_url or title)

    min_amount = _parse_amount(item.get("salary_min"))
    max_amount = _parse_amount(item.get("salary_max"))
    interval = None
    if min_amount is not None and max_amount is not None and (min_amount > 0 or max_amount > 0):
        if max_amount < 1000:
            interval = "hourly"
        elif max_amount < 10000:
            interval = "monthly"
        else:
            interval = "yearly"
    else:
        min_amount = None
        max_amount = None

    return Job(
        id=f"remoteok-{hashlib.md5(raw_id.encode()).hexdigest()[:16]}",
        site="remoteok",
        title=title,
        company=(item.get("company") or "Unknown").strip(),
        location=location,
        job_url=job_url,
        description=description,
        job_type=inferred_job_type,
        employment_type=inferred_employment_type,
        interval=interval,
        min_amount=min_amount,
        max_amount=max_amount,
        currency="USD" if min_amount or max_amount else None,
        is_remote=is_remote,
        is_us=is_us,
        date_posted=_parse_iso_date(item.get("date")),
        date_scraped=datetime.utcnow(),
    )


def _build_weworkremotely_job(
    item: ET.Element,
    job_type: str | None = None,
    employment_type: str | None = None,
) -> Job | None:
    raw_title = (item.findtext("title") or "").strip()
    if not raw_title or ":" not in raw_title:
        return None
    company, title = _parse_wwr_title(raw_title)
    if not title:
        return None
    location = _wwr_location(item)
    is_remote, is_us = _normalize_location(location)
    is_remote = True  # WWR is remote-only
    description = item.findtext("description") or ""
    # Strip HTML tags from description.
    description = re.sub(r"<[^>]+>", " ", description)
    description = re.sub(r"\s+", " ", description).strip()
    text = f"{title} {description}".lower()

    is_toptal = company.lower().startswith("toptal")
    inferred_job_type = None
    inferred_employment_type = None

    if re.search(r"\b(?:status|type)\s*[:&]?\s*full[- ]?time", text, re.IGNORECASE):
        inferred_job_type = "fulltime"
        inferred_employment_type = "w2"
    elif _text_indicates_contract_role(text):
        inferred_job_type = "contract"
        inferred_employment_type = _employment_type_from_text(text) or "contract"
    elif is_toptal and not _text_indicates_employee_role(text):
        inferred_job_type = "contract"
        inferred_employment_type = "contract"

    if not _matches_job_request(
        Job(
            id="",
            site="weworkremotely",
            title=title,
            company=company,
            job_type=inferred_job_type,
            employment_type=inferred_employment_type,
            is_remote=is_remote,
            is_us=is_us,
        ),
        job_type,
        employment_type,
    ):
        return None

    min_amount, max_amount, interval = _parse_pay_from_text(text)

    job_url = item.findtext("link") or ""
    return Job(
        id=f"weworkremotely-{hashlib.md5(job_url.encode()).hexdigest()[:16]}",
        site="weworkremotely",
        title=title,
        company=company,
        location=location,
        job_url=job_url,
        description=description,
        job_type=inferred_job_type,
        employment_type=inferred_employment_type,
        interval=interval,
        min_amount=min_amount,
        max_amount=max_amount,
        currency="USD" if min_amount or max_amount else None,
        is_remote=is_remote,
        is_us=is_us,
        date_posted=_parse_rss_date(item.findtext("pubDate")),
        date_scraped=datetime.utcnow(),
    )


def _parse_k_amount(value: str | None) -> float | None:
    """Parse a salary string that may contain a 'k' suffix or commas."""
    if not value:
        return None
    s = re.sub(r"[\s$]", "", str(value))
    is_k = "k" in s.lower()
    s = re.sub(r"[kK]", "", s)

    # Decide whether a comma is a thousands separator or a decimal comma.
    m = re.search(r"(\d{1,3}),(\d{1,3})", s)
    if m:
        after = m.group(2)
        if len(after) <= 2:
            s = s.replace(",", ".", 1)
        else:
            s = s.replace(",", "", 1)

    try:
        val = float(s)
    except (ValueError, TypeError):
        return None

    return val * 1000 if is_k else val


def _interval_from_string(value: str | None) -> str | None:
    if not value:
        return None
    s = value.lower()
    if any(w in s for w in ("hour", "hr")):
        return "hourly"
    if any(w in s for w in ("month", "mo")):
        return "monthly"
    if any(w in s for w in ("year", "yr", "annum")):
        return "yearly"
    return None


def _infer_interval_from_amounts(min_amount: float, max_amount: float) -> str | None:
    if min_amount is None and max_amount is None:
        return None
    amount = max_amount if max_amount is not None else min_amount
    if amount is None:
        return None
    if amount < 1000:
        return "hourly"
    if amount < 10000:
        return "monthly"
    return "yearly"


def _parse_remotive_salary(salary: str | None) -> tuple[float | None, float | None, str | None]:
    """Extract a pay range and interval from Remotive's free-text salary field."""
    if not salary:
        return None, None, None

    salary = salary.replace(",", ",")  # normalize en/em dashes
    # Range with optional interval, e.g. "$120 - $170 /hour" or "$150k - $230k".
    m = re.search(
        r"\$?([\d\.,]+[kK]?)\s*[-–—]\s*\$?([\d\.,]+[kK]?)\s*(?:/|\s)?\s*(hour|hr|year|yr|month|mo|annum)?",
        salary,
        re.IGNORECASE,
    )
    if m:
        lo = _parse_k_amount(m.group(1))
        hi = _parse_k_amount(m.group(2))
        interval = _interval_from_string(m.group(3)) if m.group(3) else None
        if lo is not None and hi is not None and interval is None:
            interval = _infer_interval_from_amounts(lo, hi)
        return lo, hi, interval

    # Single amount with interval, e.g. "$14/hour".
    m = re.search(
        r"\$?([\d\.,]+[kK]?)\s*(?:/|\s)?\s*(hour|hr|year|yr|month|mo|annum)",
        salary,
        re.IGNORECASE,
    )
    if m:
        lo = _parse_k_amount(m.group(1))
        interval = _interval_from_string(m.group(2))
        return lo, lo, interval

    return None, None, None


def _build_jobicy_job(
    item: dict,
    job_type: str | None = None,
    employment_type: str | None = None,
) -> Job | None:
    """Build a Job from a Jobicy API item."""
    title = (item.get("jobTitle") or "").strip()
    if not title:
        return None

    company = (item.get("companyName") or "Unknown").strip()
    location = (item.get("jobGeo") or "Remote").strip()
    is_remote, is_us = _normalize_location(location)
    is_remote = True  # Jobicy is a remote-only board.

    description = (item.get("jobDescription") or "") or (item.get("jobExcerpt") or "")
    description = re.sub(r"<[^>]+>", " ", description)
    description = re.sub(r"\s+", " ", description).strip()

    text = f"{title} {description}".lower()

    job_type_tags = [str(t).lower() for t in item.get("jobType", [])]
    if "contract" in job_type_tags or "freelance" in job_type_tags:
        inferred_job_type = "contract"
    elif "full-time" in job_type_tags or "full time" in job_type_tags:
        inferred_job_type = "fulltime"
    elif "part-time" in job_type_tags or "part time" in job_type_tags:
        inferred_job_type = "parttime"
    elif "internship" in job_type_tags:
        inferred_job_type = "internship"
    else:
        inferred_job_type = None

    if _text_indicates_contract_role(text):
        if not inferred_job_type:
            inferred_job_type = "contract"
        inferred_employment_type = _detect_employment_type(description, title) or "contract"
    elif inferred_job_type == "contract":
        inferred_employment_type = _detect_employment_type(description, title) or "contract"
    else:
        inferred_employment_type = _detect_employment_type(description, title)

    min_amount = _parse_amount(item.get("salaryMin"))
    max_amount = _parse_amount(item.get("salaryMax"))
    interval = (item.get("salaryPeriod") or "").lower() if item.get("salaryPeriod") else None
    if min_amount is not None and max_amount is not None and not interval:
        interval = _infer_interval_from_amounts(min_amount, max_amount)

    return Job(
        id=f"jobicy-{item.get('id')}",
        site="jobicy",
        title=title,
        company=company,
        location=location,
        job_url=item.get("url") or "",
        description=description,
        job_type=inferred_job_type,
        employment_type=inferred_employment_type,
        interval=interval,
        min_amount=min_amount,
        max_amount=max_amount,
        currency=item.get("salaryCurrency") or ("USD" if min_amount or max_amount else None),
        is_remote=is_remote,
        is_us=is_us,
        date_posted=_parse_iso_date(item.get("pubDate")),
        date_scraped=datetime.utcnow(),
    )


async def _scrape_jobicy(
    client: httpx.AsyncClient,
    keyword: str,
    job_type: str | None,
    employment_type: str | None,
    results_wanted: int,
) -> list[Job]:
    """Fetch remote jobs from the Jobicy public API."""
    is_contract = bool(job_type and "contract" in job_type.lower())
    # When filtering for contract roles, search the contract tag and then
    # apply the user's keyword locally. Otherwise search by keyword directly.
    tag = "contract" if is_contract else keyword
    count = min(100, max(25, results_wanted * 3))
    url = f"https://jobicy.com/api/v2/remote-jobs?count={count}&tag={urllib.parse.quote(tag)}"
    jobs: list[Job] = []

    try:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        for item in data.get("jobs", []):
            if is_contract:
                text = " ".join(
                    [
                        str(item.get("jobTitle") or ""),
                        str(item.get("companyName") or ""),
                        str(item.get("jobExcerpt") or ""),
                        *item.get("jobIndustry", []),
                    ]
                )
                if not _keyword_matches(text, keyword):
                    continue

            job = _build_jobicy_job(item, job_type=job_type, employment_type=employment_type)
            if job and job.is_us and _matches_job_request(job, job_type, employment_type):
                jobs.append(job)
                if len(jobs) >= results_wanted:
                    break
    except Exception as exc:
        logger.warning("Jobicy feed failed: %s", exc)

    return jobs


def _build_remotive_job(
    item: dict,
    job_type: str | None = None,
    employment_type: str | None = None,
) -> Job | None:
    """Build a Job from a Remotive API item."""
    title = (item.get("title") or "").strip()
    if not title:
        return None

    company = (item.get("company_name") or "Unknown").strip()
    location = (item.get("candidate_required_location") or "Remote").strip()
    is_remote, is_us = _normalize_location(location)
    is_remote = True  # Remotive is a remote-only board.

    description = item.get("description") or ""
    description = re.sub(r"<[^>]+>", " ", description)
    description = re.sub(r"\s+", " ", description).strip()

    text = f"{title} {description}".lower()

    jt = (item.get("job_type") or "").lower()
    if jt == "full_time":
        inferred_job_type = "fulltime"
    elif jt == "part_time":
        inferred_job_type = "parttime"
    elif jt == "contract":
        inferred_job_type = "contract"
    elif jt == "internship":
        inferred_job_type = "internship"
    else:
        inferred_job_type = None

    if _text_indicates_contract_role(text):
        if not inferred_job_type:
            inferred_job_type = "contract"
        inferred_employment_type = _detect_employment_type(description, title) or "contract"
    elif inferred_job_type == "contract":
        inferred_employment_type = _detect_employment_type(description, title) or "contract"
    else:
        inferred_employment_type = _detect_employment_type(description, title)

    min_amount, max_amount, interval = _parse_remotive_salary(item.get("salary"))
    if min_amount is not None and max_amount is not None and not interval:
        interval = _infer_interval_from_amounts(min_amount, max_amount)

    tags = item.get("tags", [])
    return Job(
        id=f"remotive-{item.get('id')}",
        site="remotive",
        title=title,
        company=company,
        location=location,
        job_url=item.get("url") or "",
        description=description,
        job_type=inferred_job_type,
        employment_type=inferred_employment_type,
        interval=interval,
        min_amount=min_amount,
        max_amount=max_amount,
        currency="USD" if min_amount or max_amount else None,
        is_remote=is_remote,
        is_us=is_us,
        date_posted=_parse_iso_date(item.get("publication_date")),
        date_scraped=datetime.utcnow(),
    )


async def _scrape_remotive(
    client: httpx.AsyncClient,
    keyword: str,
    job_type: str | None,
    employment_type: str | None,
    results_wanted: int,
) -> list[Job]:
    """Fetch remote jobs from the Remotive public API."""
    is_contract = bool(job_type and "contract" in job_type.lower())
    search_terms = [keyword]
    if is_contract and "contract" not in keyword.lower():
        search_terms.append(f"{keyword} contract")
        search_terms.append(f"contract {keyword}")

    seen = set()
    jobs: list[Job] = []

    for term in search_terms:
        url = f"https://remotive.com/api/remote-jobs?search={urllib.parse.quote(term)}&limit={results_wanted}"
        try:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            for item in data.get("jobs", []):
                job = _build_remotive_job(item, job_type=job_type, employment_type=employment_type)
                if job and job.is_us:
                    if not _keyword_matches(
                        f"{job.title} {job.company} {' '.join(item.get('tags', []))}",
                        keyword,
                    ):
                        continue
                    if _matches_job_request(job, job_type, employment_type):
                        if job.id not in seen:
                            seen.add(job.id)
                            jobs.append(job)
                            if len(jobs) >= results_wanted:
                                break
        except Exception as exc:
            logger.warning("Remotive feed failed for term %r: %s", term, exc)

        if len(jobs) >= results_wanted:
            break

    return jobs


def _map_apify_employment_type(value: str | None) -> str | None:
    """Map Apify employment_type string to our job_type vocabulary."""
    if not value:
        return None
    v = str(value).lower()
    if "contract" in v or "contractor" in v or "freelance" in v:
        return "contract"
    if "full" in v:
        return "fulltime"
    if "part" in v:
        return "parttime"
    if "intern" in v:
        return "internship"
    return None


def _build_apify_job(
    item: dict,
    job_type: str | None = None,
    employment_type: str | None = None,
) -> Job | None:
    """Build a Job from an Apify remote-jobs-feed record."""
    title = (item.get("title") or "").strip()
    if not title:
        return None

    company = (item.get("company") or "Unknown").strip()
    location = (item.get("location_restriction") or "Remote").strip()
    is_remote, is_us = _normalize_location(location)
    is_remote = True  # Apify feed is remote-only.

    description = str(item.get("description") or "")
    description = re.sub(r"<[^>]+>", " ", description)
    description = re.sub(r"\s+", " ", description).strip()

    text = f"{title} {description}".lower()
    categories = " ".join(str(c) for c in item.get("categories", []))

    inferred_job_type = _map_apify_employment_type(item.get("employment_type"))
    if _text_indicates_contract_role(text):
        if not inferred_job_type:
            inferred_job_type = "contract"
        inferred_employment_type = _detect_employment_type(description, title) or "contract"
    elif inferred_job_type == "contract":
        inferred_employment_type = _detect_employment_type(description, title) or "contract"
    else:
        inferred_employment_type = _detect_employment_type(description, title)

    if not _matches_job_request(
        Job(
            id="",
            site=APIFY_SOURCE,
            title=title,
            company=company,
            job_type=inferred_job_type,
            employment_type=inferred_employment_type,
            is_remote=is_remote,
            is_us=is_us,
        ),
        job_type,
        employment_type,
    ):
        return None

    min_amount = _parse_amount(item.get("salary_min"))
    max_amount = _parse_amount(item.get("salary_max"))
    interval = _interval_from_string(str(item.get("salary_unit") or ""))
    if min_amount is not None and max_amount is not None and not interval:
        interval = _infer_interval_from_amounts(min_amount, max_amount)

    job_url = item.get("url") or item.get("apply_url") or ""
    raw_id = job_url or title
    return Job(
        id=f"{APIFY_SOURCE}-{hashlib.md5(raw_id.encode()).hexdigest()[:16]}",
        site=APIFY_SOURCE,
        title=title,
        company=company,
        location=location,
        job_url=job_url,
        description=description,
        job_type=inferred_job_type,
        employment_type=inferred_employment_type,
        interval=interval,
        min_amount=min_amount,
        max_amount=max_amount,
        currency=str(item.get("salary_currency")) if item.get("salary_currency") else None,
        is_remote=is_remote,
        is_us=is_us,
        date_posted=_parse_iso_date(item.get("posted_at")),
        date_scraped=datetime.utcnow(),
    )


async def _scrape_apify(
    search_term: str,
    job_type: str | None = None,
    employment_type: str | None = None,
    results_wanted: int = DEFAULT_RESULTS_PER_BOARD,
) -> list[Job]:
    """Fetch remote jobs from the Apify remote-jobs-feed actor (optional, token-gated)."""
    if not APIFY_CLIENT_AVAILABLE or not APIFY_API_TOKEN:
        logger.info("Apify not configured; skipping source.")
        return []

    keyword = search_term.lower()
    run_input: dict[str, Any] = {
        "keyword": keyword,
        "maxItems": min(results_wanted, 100),
        "status": "live",
    }

    if job_type:
        jt = job_type.lower()
        if "contract" in jt:
            run_input["employmentType"] = "CONTRACTOR"
        elif "full" in jt:
            run_input["employmentType"] = "FULL_TIME"
        elif "part" in jt:
            run_input["employmentType"] = "PART_TIME"
        elif "intern" in jt:
            run_input["employmentType"] = "INTERN"

    client = ApifyClientAsync(APIFY_API_TOKEN)
    try:
        run = await client.actor(APIFY_ACTOR_ID).call(
            run_input=run_input,
            timeout_secs=60,
        )
        if not run or not getattr(run, "default_dataset_id", None):
            return []
        dataset_client = client.dataset(run.default_dataset_id)
        result = await dataset_client.list_items()
        items = getattr(result, "items", []) if result else []
    except Exception as exc:
        logger.warning("Apify source failed: %s", exc)
        return []

    jobs: list[Job] = []
    for item in items:
        job = _build_apify_job(item, job_type=job_type, employment_type=employment_type)
        if job and job.is_us:
            cats = " ".join(str(c) for c in item.get("categories", []))
            if not _keyword_matches(f"{job.title} {job.company} {cats} {job.description}", keyword):
                continue
            if _matches_job_request(job, job_type, employment_type):
                jobs.append(job)
                if len(jobs) >= results_wanted:
                    break

    logger.info("Apify source returned %d matching jobs", len(jobs))
    return jobs


async def scrape_remote_boards(
    search_term: str,
    job_type: str | None = None,
    employment_type: str | None = None,
    results_wanted: int = DEFAULT_RESULTS_PER_BOARD,
) -> list[Job]:
    """Fetch remote-first job boards via their public JSON/RSS feeds."""
    keyword = search_term.lower()

    apify_task = asyncio.create_task(
        _scrape_apify(search_term, job_type, employment_type, results_wanted)
    )

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # Run the new JSON-based sources concurrently.
        jobicy_task = asyncio.create_task(
            _scrape_jobicy(client, keyword, job_type, employment_type, results_wanted)
        )
        remotive_task = asyncio.create_task(
            _scrape_remotive(client, keyword, job_type, employment_type, results_wanted)
        )

        # RemoteOK public JSON feed
        remoteok_jobs: list[Job] = []
        try:
            r = await client.get("https://remoteok.com/api")
            r.raise_for_status()
            data = r.json()
            # First item is a legal header, not a job.
            for item in data[1:]:
                if not isinstance(item, dict):
                    continue
                title = (item.get("position") or "").strip()
                tags = " ".join(str(t) for t in item.get("tags", []))
                description = str(item.get("description") or "")
                text = f"{title} {tags} {description}"
                if not _keyword_matches(text, keyword):
                    continue
                job = _build_remoteok_job(item, job_type=job_type, employment_type=employment_type)
                if job and job.is_us:
                    remoteok_jobs.append(job)
                    if len(remoteok_jobs) >= results_wanted:
                        break
            logger.info("RemoteOK feed returned %d matching jobs", len(remoteok_jobs))
        except Exception as exc:
            logger.warning("RemoteOK feed failed: %s", exc)

        # We Work Remotely public RSS feed
        wwr_jobs: list[Job] = []
        try:
            r = await client.get("https://weworkremotely.com/remote-jobs.rss")
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                raw_title = (item.findtext("title") or "").strip()
                if ":" not in raw_title:
                    continue
                _, title = _parse_wwr_title(raw_title)
                description = item.findtext("description") or ""
                description = re.sub(r"<[^>]+>", " ", description)
                description = re.sub(r"\s+", " ", description).strip()
                text = f"{title} {description}"
                if not _keyword_matches(text, keyword):
                    continue
                job = _build_weworkremotely_job(item, job_type=job_type, employment_type=employment_type)
                if job and job.is_us:
                    wwr_jobs.append(job)
                    if len(wwr_jobs) >= results_wanted:
                        break
            logger.info("WWR feed returned %d matching jobs", len(wwr_jobs))
        except Exception as exc:
            logger.warning("WWR feed failed: %s", exc)

        jobicy_jobs = await jobicy_task
        remotive_jobs = await remotive_task

    apify_jobs = await apify_task

    jobs = jobicy_jobs + remotive_jobs + remoteok_jobs + wwr_jobs + apify_jobs
    logger.info("Remote board scrape finished, found %d jobs", len(jobs))
    return jobs


def save_jobs(jobs: list[Job], db: Session) -> int:
    """Persist jobs to SQLite, skipping duplicates by id."""
    count = 0
    for job in jobs:
        existing = db.query(JobORM).filter(JobORM.id == job.id).first()
        if existing:
            continue
        orm = JobORM(**job.model_dump(exclude_none=True, exclude={"date_posted"}))
        orm.date_posted = job.date_posted
        orm.raw_data = json.dumps(job.model_dump(mode="json"))
        db.add(orm)
        count += 1
    db.commit()
    return count
