import asyncio
import hashlib
import html
import json
import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.config import APIFY_ACTOR_ID, APIFY_API_TOKEN, DEFAULT_RESULTS_PER_BOARD, JOB_STALE_DAYS, SCRAPER_HOURS_OLD
from app.extraction import contract_role_signal, employment_type_signal, extract_compensation, normalize_interval, parse_compensation_text
from app.models import Job, JobORM

logger = logging.getLogger(__name__)


MAJOR_SOURCES = ["indeed", "linkedin", "glassdoor", "zip_recruiter", "google"]
REMOTE_SOURCES = ["remoteok", "weworkremotely", "jobicy", "remotive", "himalayas"]
DICE_SOURCE = "dice"
APIFY_SOURCE = "apify"
PROVIDER_SOURCES = [
    "careerjet",
    "workable",
    "greenhouse",
    "lever",
    "ashby",
    "smartrecruiters",
    "recruitee",
    "jooble",
    "adzuna",
    "hackernews",
    "usajobs",
    "upwork",
]
BUILTIN_ASYNC_SOURCES = REMOTE_SOURCES + [DICE_SOURCE, APIFY_SOURCE]
ALL_SOURCES = MAJOR_SOURCES + BUILTIN_ASYNC_SOURCES + PROVIDER_SOURCES


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

from app.browser_scraper import fetch_rendered


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

# Explicit "W2 only" signals. These also cover phrasing that rules out other
# arrangements ("no C2C", "no 1099"), which in practice means a W2 engagement.
W2_ONLY_PATTERNS = [
    re.compile(r"\bw-?2\s+(?:only|candidates?|contract(?:ors?)?|position|role|employees?|basis|hourly)\b"),
    re.compile(r"\bonly\s+w-?2\b"),
    re.compile(r"\bmust\s+be\s+(?:on\s+|able\s+to\s+work\s+on\s+)?w-?2\b"),
    re.compile(r"\bno\s+c2c\b"),
    re.compile(r"\bno\s+corp[- ]to[- ]corp\b"),
    re.compile(r"\bno\s+1099\b"),
    re.compile(r"\bw-?2\s+(?:candidates?\s+)?only\b"),
]

# Strong full-time / employee role indicators.
EMPLOYEE_ROLE_PATTERNS = [
    re.compile(r"\bfull[- ]?time\s+(?:employee|associate|staff|role|position)\b"),
    re.compile(r"\bemployee\s+(?:position|role)\b"),
    re.compile(r"\bpermanent\s+(?:employee|associate|staff|role|position)\b"),
    re.compile(r"\bdirect[- ]hire\b"),
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
    return contract_role_signal(text)


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
    employment_type, _, _ = employment_type_signal(description, title)
    return employment_type


def _parse_amount(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_pay_from_text(text: str | None) -> tuple[float | None, float | None, str | None]:
    """Extract a pay range and interval from free-text job descriptions."""
    pay = parse_compensation_text(text)
    return pay.minimum, pay.maximum, pay.interval


def _matches_job_request(
    job: Job,
    job_type: str | None,
    employment_type: str | None,
) -> bool:
    """Check whether a scraped job matches the requested type filters."""
    if not job_type and not employment_type:
        return True

    jt = (job.job_type or "").lower()
    et = (job.employment_type or "").lower()
    if job_type:
        requested_job_type = job_type.lower()
        type_matches = requested_job_type in jt or requested_job_type in et
        if requested_job_type == "contract" and _text_indicates_contract_role(
            f"{job.title or ''} {job.description or ''}"
        ):
            type_matches = True
        if requested_job_type == "contingent" and ("contingent" in jt or "contingent" in et):
            type_matches = True
        if not type_matches:
            return False

    if employment_type and employment_type.lower() != "any":
        requested_employment = employment_type.lower()
        if requested_employment not in et and requested_employment not in jt:
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
    employment_type, classification_source, classification_confidence = employment_type_signal(description, title)
    pay = extract_compensation(
        description,
        minimum=row.get("min_amount"),
        maximum=row.get("max_amount"),
        currency=str(row.get("currency")) if pd.notna(row.get("currency")) else None,
        interval=str(row.get("interval")) if pd.notna(row.get("interval")) else None,
    )

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
        interval=pay.interval,
        min_amount=pay.minimum,
        max_amount=pay.maximum,
        currency=pay.currency,
        pay_source=pay.source,
        pay_confidence=pay.confidence,
        pay_raw_text=pay.raw_text,
        classification_source=classification_source or ("structured" if inferred_job_type else None),
        classification_confidence=classification_confidence or ("high" if inferred_job_type else None),
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
        terms = [search_term] if has_contract_term else [f"{search_term} contract", f"contract {search_term}", f"{search_term} contract-to-hire"]
        et = (employment_type or "").lower()
        if et == "w2":
            # W2 contract roles use very specific phrasing; target it directly
            # and lead with it so it isn't crowded out by the per-term quota.
            terms.insert(0, f"{search_term} w2 contract")
            terms.append(f"w2 contract {search_term}")
        elif et == "1099":
            terms.insert(0, f"{search_term} 1099")
        elif et == "c2c":
            terms.insert(0, f"{search_term} c2c")
        else:
            # No specific engagement requested: cast a wide contract net.
            if "freelance" not in base and "contract" not in base:
                terms.append(f"freelance {search_term}")
            if "1099" not in base:
                terms.append(f"{search_term} 1099")
            if "c2c" not in base and "corp-to-corp" not in base:
                terms.append(f"{search_term} c2c")
        if not terms:
            terms.append(f"contract {search_term}")
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
    pay = extract_compensation(
        description,
        minimum=min_amount,
        maximum=max_amount,
        currency="USD" if min_amount is not None or max_amount is not None else None,
        interval=interval,
    )

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
        interval=pay.interval,
        min_amount=pay.minimum,
        max_amount=pay.maximum,
        currency=pay.currency,
        pay_source=pay.source,
        pay_confidence=pay.confidence,
        pay_raw_text=pay.raw_text,
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

    pay = extract_compensation(text)

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
        interval=pay.interval,
        min_amount=pay.minimum,
        max_amount=pay.maximum,
        currency=pay.currency,
        pay_source=pay.source,
        pay_confidence=pay.confidence,
        pay_raw_text=pay.raw_text,
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
    pay = extract_compensation(
        description,
        minimum=min_amount,
        maximum=max_amount,
        currency=item.get("salaryCurrency"),
        interval=interval,
    )

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
        interval=pay.interval,
        min_amount=pay.minimum,
        max_amount=pay.maximum,
        currency=pay.currency,
        pay_source=pay.source,
        pay_confidence=pay.confidence,
        pay_raw_text=pay.raw_text,
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
    pay = extract_compensation(
        " ".join(filter(None, (item.get("salary"), description))),
        minimum=min_amount,
        maximum=max_amount,
        currency="USD" if min_amount is not None or max_amount is not None else None,
        interval=interval,
    )

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
        interval=pay.interval,
        min_amount=pay.minimum,
        max_amount=pay.maximum,
        currency=pay.currency,
        pay_source=pay.source,
        pay_confidence=pay.confidence,
        pay_raw_text=pay.raw_text,
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


def _map_himalayas_employment_type(value: str | None) -> str | None:
    """Map Himalayas' employmentType label to our job_type vocabulary."""
    if not value:
        return None
    v = str(value).lower()
    if "contract" in v or "freelance" in v or "temporary" in v:
        return "contract"
    if "full" in v:
        return "fulltime"
    if "part" in v:
        return "parttime"
    if "intern" in v:
        return "internship"
    return None


def _himalayas_is_us(location_restrictions: list, description: str, title: str) -> tuple[bool, bool]:
    """Himalayas jobs are remote; decide US eligibility from its location list."""
    locations = [str(loc) for loc in (location_restrictions or [])]
    # No restriction listed means the role is open worldwide -> US-eligible.
    if not locations:
        return True, True
    joined = " ".join(locations).lower()
    has_us = any(p.search(joined) for p in US_PATTERNS) or "worldwide" in joined or "anywhere" in joined
    has_non_us = any(p.search(joined) for p in NON_US_PATTERNS)
    if has_us:
        return True, True
    if has_non_us:
        return True, False
    # An unrecognized restriction (e.g. a single non-listed country) is treated
    # as not US-eligible to avoid surfacing region-locked roles.
    return True, False


def _build_himalayas_job(
    item: dict,
    job_type: str | None = None,
    employment_type: str | None = None,
) -> Job | None:
    """Build a Job from a Himalayas public API record."""
    title = html.unescape((item.get("title") or "").strip())
    if not title:
        return None

    company = html.unescape((item.get("companyName") or "Unknown").strip())
    location_restrictions = item.get("locationRestrictions") or []
    is_remote, is_us = _himalayas_is_us(
        location_restrictions, str(item.get("description") or ""), title
    )
    location = ", ".join(str(loc) for loc in location_restrictions) or "Remote"

    description = str(item.get("description") or item.get("excerpt") or "")
    description = html.unescape(re.sub(r"<[^>]+>", " ", description))
    description = re.sub(r"\s+", " ", description).strip()

    text = f"{title} {description}".lower()

    inferred_job_type = _map_himalayas_employment_type(item.get("employmentType"))
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
            site="himalayas",
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

    min_amount = _parse_amount(item.get("minSalary"))
    max_amount = _parse_amount(item.get("maxSalary"))
    period = (item.get("salaryPeriod") or "").lower()
    if "hour" in period:
        interval = "hourly"
    elif "month" in period:
        interval = "monthly"
    elif period:
        interval = "yearly"  # "annual"
    elif min_amount is not None or max_amount is not None:
        interval = _infer_interval_from_amounts(min_amount, max_amount)
    else:
        interval = None
    pay = extract_compensation(
        description,
        minimum=min_amount,
        maximum=max_amount,
        currency=item.get("currency"),
        interval=interval,
    )

    job_url = item.get("applicationLink") or item.get("guid") or ""
    raw_id = item.get("guid") or job_url or title
    return Job(
        id=f"himalayas-{hashlib.md5(str(raw_id).encode()).hexdigest()[:16]}",
        site="himalayas",
        title=title,
        company=company,
        location=location,
        job_url=job_url,
        description=description,
        job_type=inferred_job_type,
        employment_type=inferred_employment_type,
        interval=pay.interval,
        min_amount=pay.minimum,
        max_amount=pay.maximum,
        currency=pay.currency,
        pay_source=pay.source,
        pay_confidence=pay.confidence,
        pay_raw_text=pay.raw_text,
        is_remote=is_remote,
        is_us=is_us,
        date_posted=_parse_iso_date(item.get("pubDate")),
        date_scraped=datetime.utcnow(),
    )


async def _scrape_himalayas(
    client: httpx.AsyncClient,
    search_term: str,
    job_type: str | None,
    employment_type: str | None,
    results_wanted: int,
) -> list[Job]:
    """Fetch remote jobs from the Himalayas public API.

    Himalayas has no server-side keyword search, so we page through its feed
    (newest first) with cursor pagination and filter by keyword locally, the
    same approach used for RemoteOK and We Work Remotely.
    """
    keyword = (search_term or "").lower()
    seen: set[str] = set()
    jobs: list[Job] = []
    cursor: str | None = None
    # Cap pages so a low-yield keyword can't page indefinitely. 100 jobs/page.
    max_pages = 5

    for _ in range(max_pages):
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        try:
            r = await client.get("https://himalayas.app/jobs/api", params=params)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            logger.warning("Himalayas feed failed: %s", exc)
            break

        items = data.get("jobs", [])
        if not items:
            break

        for item in items:
            text = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("companyName") or ""),
                    str(item.get("excerpt") or ""),
                    " ".join(str(c) for c in item.get("categories", [])),
                ]
            )
            if not _keyword_matches(text, keyword):
                continue
            job = _build_himalayas_job(item, job_type=job_type, employment_type=employment_type)
            if job and job.is_us and job.id not in seen:
                seen.add(job.id)
                jobs.append(job)
                if len(jobs) >= results_wanted:
                    break

        if len(jobs) >= results_wanted:
            break
        cursor = data.get("nextCursor")
        if not cursor:
            break

    logger.info("Himalayas returned %d matching jobs", len(jobs))
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
    pay = extract_compensation(
        description,
        minimum=min_amount,
        maximum=max_amount,
        currency=str(item.get("salary_currency")) if item.get("salary_currency") else None,
        interval=interval,
    )

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
        interval=pay.interval,
        min_amount=pay.minimum,
        max_amount=pay.maximum,
        currency=pay.currency,
        pay_source=pay.source,
        pay_confidence=pay.confidence,
        pay_raw_text=pay.raw_text,
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


_DICE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Dice's employmentType facet values, keyed by our job_type / employment_type.
DICE_EMPLOYMENT_FILTER = {
    "contract": "CONTRACTS",
    "fulltime": "FULLTIME",
    "full-time": "FULLTIME",
    "parttime": "PARTTIME",
    "part-time": "PARTTIME",
}


def _find_dice_joblist(node: Any) -> list[dict] | None:
    """Recursively locate the ``jobList.data`` array in a decoded RSC node."""
    if isinstance(node, dict):
        jl = node.get("jobList")
        if isinstance(jl, dict) and isinstance(jl.get("data"), list):
            return jl["data"]
        for value in node.values():
            found = _find_dice_joblist(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_dice_joblist(value)
            if found is not None:
                return found
    return None


def _extract_dice_joblist(html: str) -> list[dict]:
    """Extract job records embedded in Dice's Next.js RSC (``__next_f``) chunks.

    Dice's search page ships the results as escaped JSON inside
    ``self.__next_f.push([1,"..."])`` script chunks rather than a REST API.
    """
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.DOTALL)
    for chunk in chunks:
        if "jobList" not in chunk:
            continue
        try:
            decoded = json.loads('"' + chunk + '"')
        except json.JSONDecodeError:
            continue
        # Chunks are prefixed with a hex id like '12:' before the JSON payload.
        m = re.match(r"^[0-9a-fA-F]+:", decoded)
        body = decoded[m.end():] if m else decoded
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        job_list = _find_dice_joblist(data)
        if job_list:
            return job_list
    return []


def _map_dice_job_type(value: str | None) -> str | None:
    if not value:
        return None
    v = value.lower()
    if "contract" in v or "third party" in v or "3rd party" in v:
        return "contract"
    if "full" in v:
        return "fulltime"
    if "part" in v:
        return "parttime"
    if "intern" in v:
        return "internship"
    return None


def _build_dice_job(
    item: dict,
    job_type: str | None = None,
    employment_type: str | None = None,
) -> Job | None:
    """Build a Job from a Dice search result record."""
    title = (item.get("title") or "").strip()
    if not title:
        return None

    company = (item.get("companyName") or "Unknown").strip()
    is_remote = bool(item.get("isRemote"))
    workplace = ", ".join(str(w) for w in (item.get("workplaceTypes") or []) if w)
    location = workplace or ("Remote" if is_remote else "United States")
    # Dice is a US tech board; treat postings as US-eligible.
    is_us = True

    description = re.sub(r"<[^>]+>", " ", str(item.get("summary") or ""))
    description = re.sub(r"\s+", " ", description).strip()
    text = f"{title} {description}".lower()

    inferred_job_type = _map_dice_job_type(item.get("employmentType"))
    if not inferred_job_type and _text_indicates_contract_role(text):
        inferred_job_type = "contract"

    inferred_employment_type, classification_source, classification_confidence = employment_type_signal(description, title)
    if not inferred_employment_type:
        if str(item.get("employmentType") or "").lower().startswith("third"):
            inferred_employment_type = "c2c"
            classification_source = "structured"
            classification_confidence = "high"
        elif inferred_job_type == "contract":
            inferred_employment_type = "contract"
            classification_source = "structured"
            classification_confidence = "high"
    pay_text = " ".join(str(item.get(key) or "") for key in ("salary", "compensation", "payRate", "summary"))
    pay = extract_compensation(
        pay_text,
        minimum=item.get("salaryMin") or item.get("minSalary"),
        maximum=item.get("salaryMax") or item.get("maxSalary"),
        currency=item.get("salaryCurrency") or item.get("currency"),
        interval=item.get("salaryUnit") or item.get("salaryPeriod"),
    )

    if not _matches_job_request(
        Job(
            id="",
            site=DICE_SOURCE,
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

    job_url = item.get("detailsPageUrl") or ""
    raw_id = str(item.get("id") or item.get("guid") or job_url or title)
    return Job(
        id=f"{DICE_SOURCE}-{hashlib.md5(raw_id.encode()).hexdigest()[:16]}",
        site=DICE_SOURCE,
        title=title,
        company=company,
        location=location,
        job_url=job_url,
        description=description,
        job_type=inferred_job_type,
        employment_type=inferred_employment_type,
        interval=pay.interval,
        min_amount=pay.minimum,
        max_amount=pay.maximum,
        currency=pay.currency,
        pay_source=pay.source,
        pay_confidence=pay.confidence,
        pay_raw_text=pay.raw_text,
        classification_source=classification_source or ("structured" if inferred_job_type else None),
        classification_confidence=classification_confidence or ("high" if inferred_job_type else None),
        is_remote=is_remote,
        is_us=is_us,
        date_posted=_parse_iso_date(item.get("postedDate")),
        date_scraped=datetime.utcnow(),
    )


def _dice_detail(html_text: str) -> tuple[str | None, Any, Any, str | None, str | None]:
    for match in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_text, re.I | re.S):
        try:
            payload = json.loads(html.unescape(match.group(1)).strip())
        except (json.JSONDecodeError, TypeError):
            continue
        nodes = payload if isinstance(payload, list) else payload.get("@graph", [payload]) if isinstance(payload, dict) else []
        for node in nodes:
            if not isinstance(node, dict) or "JobPosting" not in str(node.get("@type", "")):
                continue
            description = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(str(node.get("description") or "")))).strip() or None
            salary = node.get("baseSalary") or node.get("estimatedSalary") or {}
            salary = salary[0] if isinstance(salary, list) and salary else salary
            value = salary.get("value", {}) if isinstance(salary, dict) else {}
            if not isinstance(value, dict):
                value = {"value": value}
            minimum = value.get("minValue", value.get("value"))
            maximum = value.get("maxValue", value.get("value"))
            currency = salary.get("currency") if isinstance(salary, dict) else None
            interval = value.get("unitText")
            return description, minimum, maximum, currency, interval
    return None, None, None, None, None


async def _enrich_dice_job(client: httpx.AsyncClient, job: Job, semaphore: asyncio.Semaphore) -> Job:
    if not job.job_url:
        return job
    try:
        async with semaphore:
            response = await client.get(job.job_url, headers={"User-Agent": _DICE_UA, "Accept": "text/html"})
            response.raise_for_status()
        description, minimum, maximum, currency, interval = _dice_detail(response.text)
        text = description or response.text
        pay = extract_compensation(text, minimum=minimum, maximum=maximum, currency=currency, interval=interval)
        if description and len(description) > len(job.description or ""):
            job.description = description
            employment_type, source, confidence = employment_type_signal(description, job.title)
            if employment_type:
                job.employment_type = employment_type
                job.classification_source = source
                job.classification_confidence = confidence
            if contract_role_signal(f"{job.title} {description}"):
                job.job_type = "contract"
        if pay.minimum is not None or pay.maximum is not None:
            job.min_amount = pay.minimum
            job.max_amount = pay.maximum
            job.currency = pay.currency
            job.interval = pay.interval
            job.pay_source = pay.source
            job.pay_confidence = pay.confidence
            job.pay_raw_text = pay.raw_text
    except Exception as exc:
        logger.debug("Dice detail enrichment failed for %s: %s", job.job_url, type(exc).__name__)
    return job


async def _scrape_dice(
    client: httpx.AsyncClient,
    search_term: str,
    job_type: str | None,
    employment_type: str | None,
    results_wanted: int,
    is_remote: bool = True,
) -> list[Job]:
    """Scrape Dice.com contract/tech postings via its public search page.

    Dice is a US, contract-heavy tech board, so it is a strong source for
    W2 contract software-engineering roles that the general boards miss.
    """
    keyword = (search_term or "software engineer").strip()

    # Pick the tightest employmentType facet we can. A C2C request maps to
    # Dice's "Third Party" bucket; otherwise fall back to the job_type facet.
    filter_value = None
    if (employment_type or "").lower() == "c2c":
        filter_value = "THIRD_PARTY"
    elif job_type:
        filter_value = DICE_EMPLOYMENT_FILTER.get(job_type.lower())

    seen: set[str] = set()
    jobs: list[Job] = []
    max_pages = 5  # Dice serves 30 results/page.

    for page in range(1, max_pages + 1):
        params = {
            "q": keyword,
            "location": "United States",
            "page": page,
            "pageSize": 100,  # Dice caps this at 30, but the param is harmless.
        }
        if is_remote:
            params["filters.workplaceTypes"] = "Remote"
        if filter_value:
            params["filters.employmentType"] = filter_value
        url = "https://www.dice.com/jobs?" + urllib.parse.urlencode(params)

        html = None
        try:
            r = await client.get(url, headers={"User-Agent": _DICE_UA, "Accept": "text/html"})
            r.raise_for_status()
            html = r.text
        except Exception as exc:
            logger.warning("Dice fetch failed (page %d): %s", page, exc)

        items = _extract_dice_joblist(html) if html else []

        # Dice renders its results through a JS framework and intermittently
        # bot-blocks raw HTTP clients (empty shell, 403, or a challenge page).
        # When the httpx path yields nothing, fall back to rendering the page
        # in a real headless browser and re-parse the same embedded job data.
        if not items:
            rendered = await fetch_rendered(
                url, wait_selector='[data-testid="job-search-serp-card"]'
            )
            if rendered:
                items = _extract_dice_joblist(rendered)

        if not items:
            break

        for item in items:
            job = _build_dice_job(item, job_type=job_type, employment_type=employment_type)
            if not job or not job.is_us:
                continue
            if not _keyword_matches(f"{job.title} {job.company} {job.description or ''}", keyword):
                continue
            if job.id in seen:
                continue
            seen.add(job.id)
            jobs.append(job)
            if len(jobs) >= results_wanted:
                break

        if len(jobs) >= results_wanted or len(items) < 30:
            break

    if jobs:
        semaphore = asyncio.Semaphore(5)
        jobs = list(await asyncio.gather(*(_enrich_dice_job(client, job, semaphore) for job in jobs)))
    logger.info("Dice returned %d matching jobs", len(jobs))
    return jobs


async def _scrape_remoteok(
    client: httpx.AsyncClient,
    search_term: str,
    job_type: str | None,
    employment_type: str | None,
    results_wanted: int,
) -> list[Job]:
    jobs: list[Job] = []
    try:
        r = await client.get("https://remoteok.com/api")
        r.raise_for_status()
        for item in r.json()[1:]:
            if not isinstance(item, dict):
                continue
            title = (item.get("position") or "").strip()
            tags = " ".join(str(t) for t in item.get("tags", []))
            description = str(item.get("description") or "")
            if not _keyword_matches(f"{title} {tags} {description}", search_term):
                continue
            job = _build_remoteok_job(item, job_type=job_type, employment_type=employment_type)
            if job and job.is_us:
                jobs.append(job)
                if len(jobs) >= results_wanted:
                    break
    except Exception as exc:
        logger.warning("RemoteOK feed failed: %s", exc)
    return jobs


async def _scrape_weworkremotely(
    client: httpx.AsyncClient,
    search_term: str,
    job_type: str | None,
    employment_type: str | None,
    results_wanted: int,
) -> list[Job]:
    jobs: list[Job] = []
    try:
        r = await client.get("https://weworkremotely.com/remote-jobs.rss")
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for item in root.findall(".//item"):
            raw_title = (item.findtext("title") or "").strip()
            if ":" not in raw_title:
                continue
            _, title = _parse_wwr_title(raw_title)
            description = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", item.findtext("description") or "")).strip()
            if not _keyword_matches(f"{title} {description}", search_term):
                continue
            job = _build_weworkremotely_job(item, job_type=job_type, employment_type=employment_type)
            if job and job.is_us:
                jobs.append(job)
                if len(jobs) >= results_wanted:
                    break
    except Exception as exc:
        logger.warning("WWR feed failed: %s", exc)
    return jobs


async def scrape_builtin_source(
    source: str,
    search_term: str,
    job_type: str | None = None,
    employment_type: str | None = None,
    results_wanted: int = DEFAULT_RESULTS_PER_BOARD,
    is_remote: bool = True,
) -> list[Job]:
    if source == APIFY_SOURCE:
        return await _scrape_apify(search_term, job_type, employment_type, results_wanted)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        if source == "remoteok":
            return await _scrape_remoteok(client, search_term, job_type, employment_type, results_wanted)
        if source == "weworkremotely":
            return await _scrape_weworkremotely(client, search_term, job_type, employment_type, results_wanted)
        if source == "jobicy":
            return await _scrape_jobicy(client, search_term, job_type, employment_type, results_wanted)
        if source == "remotive":
            return await _scrape_remotive(client, search_term, job_type, employment_type, results_wanted)
        if source == "himalayas":
            return await _scrape_himalayas(client, search_term, job_type, employment_type, results_wanted)
        if source == DICE_SOURCE:
            return await _scrape_dice(client, search_term, job_type, employment_type, results_wanted, is_remote)
    raise ValueError(f"Unknown built-in source: {source}")


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
        dice_task = asyncio.create_task(
            _scrape_dice(client, search_term, job_type, employment_type, results_wanted)
        )
        himalayas_task = asyncio.create_task(
            _scrape_himalayas(client, search_term, job_type, employment_type, results_wanted)
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
        dice_jobs = await dice_task
        himalayas_jobs = await himalayas_task

    apify_jobs = await apify_task

    jobs = (
        jobicy_jobs
        + remotive_jobs
        + dice_jobs
        + himalayas_jobs
        + remoteok_jobs
        + wwr_jobs
        + apify_jobs
    )
    logger.info("Remote board scrape finished, found %d jobs", len(jobs))
    return jobs


_DEDUP_STRIP = re.compile(r"[^a-z0-9 ]+")
_DEDUP_WS = re.compile(r"\s+")


def _normalize_for_dedup(value: str | None) -> str:
    if not value:
        return ""
    text = value.lower()
    # Drop common company suffixes and seniority/location noise so the same
    # role posted on multiple boards collapses to one key.
    text = _DEDUP_STRIP.sub(" ", text)
    text = re.sub(r"\b(inc|llc|ltd|corp|co|group|technologies|technology|solutions|remote)\b", " ", text)
    return _DEDUP_WS.sub(" ", text).strip()


def _dedup_key(job: Job) -> str:
    """Build a cross-source semantic key from normalized company + title."""
    base = f"{_normalize_for_dedup(job.company)}|{_normalize_for_dedup(job.title)}"
    return hashlib.md5(base.encode()).hexdigest()[:20]


# Fields that are derived at read time (computed) and must not be passed to the ORM.
_COMPUTED_FIELDS = {
    "normalized_min_yearly",
    "normalized_max_yearly",
    "normalized_min_hourly",
    "normalized_max_hourly",
    "normalized_currency",
    "eligibility",
}


def _source_urls(existing: str | None, job: Job) -> str:
    try:
        values = json.loads(existing or "[]")
    except (json.JSONDecodeError, TypeError):
        values = []
    entry = {"site": job.site, "url": job.job_url or job.job_url_direct}
    if entry not in values:
        values.append(entry)
    return json.dumps(values)


def _merge_job(existing: JobORM, job: Job) -> None:
    existing.last_seen = datetime.utcnow()
    existing.date_scraped = job.date_scraped or datetime.utcnow()
    existing.is_active = True
    existing.quality_version = 2
    existing.source_urls = _source_urls(existing.source_urls, job)
    if len(job.description or "") > len(existing.description or ""):
        existing.description = job.description
    for name in ("job_url", "job_url_direct", "location", "date_posted"):
        if getattr(existing, name) is None and getattr(job, name) is not None:
            setattr(existing, name, getattr(job, name))
    rank = {None: 0, "low": 1, "medium": 2, "high": 3}
    existing_pay_count = int(existing.min_amount is not None) + int(existing.max_amount is not None)
    incoming_pay_count = int(job.min_amount is not None) + int(job.max_amount is not None)
    if incoming_pay_count and (not existing_pay_count or rank.get(job.pay_confidence, 0) >= rank.get(existing.pay_confidence, 0) or incoming_pay_count > existing_pay_count):
        for name in ("min_amount", "max_amount", "currency", "interval", "pay_source", "pay_confidence", "pay_raw_text"):
            value = getattr(job, name)
            if value is not None:
                setattr(existing, name, value)
        existing.normalized_min_yearly = job.normalized_min_yearly
        existing.normalized_max_yearly = job.normalized_max_yearly
        existing.normalized_min_hourly = job.normalized_min_hourly
        existing.normalized_max_hourly = job.normalized_max_hourly
    if rank.get(job.classification_confidence, 0) >= rank.get(existing.classification_confidence, 0):
        for name in ("job_type", "employment_type", "classification_source", "classification_confidence"):
            value = getattr(job, name)
            if value is not None:
                setattr(existing, name, value)
    existing.is_remote = existing.is_remote or job.is_remote
    existing.is_us = existing.is_us or job.is_us
    existing.raw_data = json.dumps(job.model_dump(mode="json"))


def save_jobs(jobs: list[Job], db: Session) -> int:
    """Persist jobs to SQLite, merging exact-id and cross-source duplicates."""
    count = 0
    batch: dict[str, JobORM] = {}
    for job in jobs:
        key = _dedup_key(job)
        existing = batch.get(key) or db.query(JobORM).filter(
            JobORM.dedup_key == key,
            JobORM.is_active.is_(True),
        ).first()
        if not existing:
            existing = db.query(JobORM).filter(JobORM.id == job.id).first()
        if existing:
            existing.dedup_key = key
            _merge_job(existing, job)
            continue
        payload = job.model_dump(exclude_none=True, exclude={"date_posted", "source_urls", *_COMPUTED_FIELDS})
        orm = JobORM(**payload)
        orm.date_posted = job.date_posted
        orm.normalized_min_yearly = job.normalized_min_yearly
        orm.normalized_max_yearly = job.normalized_max_yearly
        orm.normalized_min_hourly = job.normalized_min_hourly
        orm.normalized_max_hourly = job.normalized_max_hourly
        orm.dedup_key = key
        orm.source_urls = _source_urls(None, job)
        orm.last_seen = job.date_scraped or datetime.utcnow()
        orm.is_active = True
        orm.raw_data = json.dumps(job.model_dump(mode="json"))
        db.add(orm)
        batch[key] = orm
        count += 1
    db.commit()
    return count


def mark_stale_jobs(db: Session) -> int:
    cutoff = datetime.utcnow() - timedelta(days=JOB_STALE_DAYS)
    count = db.query(JobORM).filter(JobORM.is_active.is_(True), JobORM.last_seen < cutoff).update(
        {JobORM.is_active: False}, synchronize_session=False
    )
    db.commit()
    return count
