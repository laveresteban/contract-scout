from __future__ import annotations

import hashlib
import html
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Awaitable, Callable
from urllib.parse import quote, urljoin

import httpx

from .. import config
from ..extraction import Compensation, contract_role_signal, employment_type_signal, extract_compensation
from ..scraped import Job

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProviderRequest:
    query: str = "software engineer"
    location: str | None = "United States"
    is_remote: bool = True
    job_type: str | None = "contract"
    employment_type: str | None = None
    results_wanted: int = 25
    user_ip: str | None = None
    user_agent: str | None = None
    referer: str | None = None


def _cfg(*names: str, default: Any = None) -> Any:
    for name in names:
        value = getattr(config, name, None)
        if value is not None and value != "":
            return value
    return default


def _boards(*names: str) -> list[str]:
    value = _cfg(*names)
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        value = ", ".join(str(item) for item in value if item is not None)
    elif isinstance(value, dict):
        value = value.get("name") or value.get("text") or value.get("value")
    if value is None:
        return None
    result = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", str(value)))).strip()
    return result or None


def _date(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            stamp = float(value)
            if stamp > 10_000_000_000:
                stamp /= 1000
            return datetime.fromtimestamp(stamp, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    raw = str(value).strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            return parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None


def _pay(data: dict[str, Any], description: str | None = None) -> Compensation:
    compensation = data.get("compensation") or data.get("salary") or data.get("pay")
    merged = {**data, **compensation} if isinstance(compensation, dict) else data
    low = next((merged.get(key) for key in ("min_amount", "min", "minimum", "salaryMin", "salary_min", "minSalary") if merged.get(key) is not None), None)
    high = next((merged.get(key) for key in ("max_amount", "max", "maximum", "salaryMax", "salary_max", "maxSalary") if merged.get(key) is not None), None)
    currency = next((_text(merged.get(key)) for key in ("currency", "salaryCurrency", "salary_currency", "currencyCode") if merged.get(key)), None)
    interval = next((_text(merged.get(key)) for key in ("interval", "frequency", "period", "salaryInterval", "salaryPeriod") if merged.get(key)), None)
    text = " ".join(filter(None, (_text(compensation) if not isinstance(compensation, dict) else None, description)))
    return extract_compensation(text, minimum=low, maximum=high, currency=currency, interval=interval)


def _types(title: str, description: str | None, supplied: Any = None) -> tuple[str | None, str | None]:
    supplied_text = _text(supplied)
    raw = " ".join(filter(None, (title, description, supplied_text)))
    employment, _, _ = employment_type_signal(description, " ".join(filter(None, (title, supplied_text))))
    if re.search(r"\bintern(?:ship)?\b", supplied_text or title, re.I):
        job_type = "internship"
    elif re.search(r"\bpart[- ]?time\b", supplied_text or title, re.I):
        job_type = "parttime"
    elif re.search(r"\b(?:contract(?:or)?|freelance|temporary|temp)\b", supplied_text or "", re.I) or contract_role_signal(raw):
        job_type = "contract"
    elif re.search(r"\bfull[- ]?time\b|\bpermanent\b|\bdirect[- ]hire\b", raw, re.I):
        job_type = "fulltime"
    else:
        job_type = None
    return job_type, employment


def _location_flags(location: str | None, title: str, description: str | None, explicit_remote: Any = None) -> tuple[bool, bool]:
    loc = (location or "").lower()
    body = " ".join(filter(None, (title, description))).lower()
    if explicit_remote is not None:
        remote = explicit_remote if isinstance(explicit_remote, bool) else str(explicit_remote).lower() in ("1", "true", "yes", "remote")
    else:
        remote = bool(re.search(r"\bremote\b|work from home|anywhere|worldwide", f"{loc} {body}"))
    non_us = bool(re.search(r"\b(?:india|china|europe|united kingdom|uk|canada|mexico|brazil|australia|apac|emea|latam)\b", loc))
    is_us = bool(re.search(r"\bunited states\b|\busa\b|\bu\.s\.\b|\bremote[- ]?us\b", loc)) or (remote and not non_us)
    return remote, is_us


def _stable_id(source: str, external_id: Any, title: str, company: str, url: str | None) -> str:
    raw = str(external_id).strip() if external_id is not None else ""
    if not raw:
        raw = hashlib.sha256(f"{title}|{company}|{url or ''}".encode()).hexdigest()[:24]
    safe = re.sub(r"[^A-Za-z0-9._~-]+", "-", raw).strip("-")
    return f"{source}-{safe or hashlib.sha256(raw.encode()).hexdigest()[:24]}"


def _job(source: str, data: dict[str, Any], *, title: Any, company: Any, location: Any = None, url: Any = None, description: Any = None, external_id: Any = None, date_posted: Any = None, type_value: Any = None, explicit_remote: Any = None, pay_data: dict[str, Any] | None = None) -> Job:
    clean_title = _text(title) or "Untitled"
    clean_company = _text(company) or "Unknown"
    clean_location = _text(location)
    clean_url = _text(url)
    clean_description = _text(description)
    job_type, employment_type = _types(clean_title, clean_description, type_value)
    is_remote, is_us = _location_flags(clean_location, clean_title, clean_description, explicit_remote)
    pay = _pay(pay_data or data, clean_description)
    _, classification_source, classification_confidence = employment_type_signal(clean_description, clean_title)
    return Job(id=_stable_id(source, external_id, clean_title, clean_company, clean_url), site=source, title=clean_title, company=clean_company, location=clean_location, job_url=clean_url, job_url_direct=clean_url, description=clean_description, job_type=job_type, employment_type=employment_type, interval=pay.interval, min_amount=pay.minimum, max_amount=pay.maximum, currency=pay.currency, pay_source=pay.source, pay_confidence=pay.confidence, pay_raw_text=pay.raw_text, classification_source=classification_source or ("structured" if type_value else None), classification_confidence=classification_confidence or ("high" if type_value else None), is_remote=is_remote, is_us=is_us, date_posted=_date(date_posted), date_scraped=datetime.now(timezone.utc))


def _wanted(job: Job, request: ProviderRequest) -> bool:
    haystack = f"{job.title} {job.company} {job.description or ''}".lower()
    words = [word.lower() for word in re.findall(r"[\w+#.-]+", request.query) if len(word) > 1]
    if words and not any(word in haystack for word in words):
        return False
    if request.is_remote and not job.is_remote:
        return False
    requested_type = (request.job_type or "").lower()
    if requested_type and requested_type not in (job.job_type or "").lower() and requested_type not in (job.employment_type or "").lower():
        return False
    requested_employment = (request.employment_type or "").lower()
    if requested_employment and requested_employment != "any" and requested_employment not in (job.employment_type or "").lower():
        return False
    return True


def _append(records: list[Job], request: ProviderRequest, source: str, data: dict[str, Any], **fields: Any) -> None:
    try:
        job = _job(source, data, **fields)
        if _wanted(job, request) and all(existing.id != job.id for existing in records):
            records.append(job)
    except Exception as exc:
        logger.warning("%s record parse failed: %s", source, type(exc).__name__)


async def careerjet(request: ProviderRequest) -> list[Job]:
    key = _cfg("CAREERJET_API_KEY")
    if not key or not request.user_ip or not request.user_agent or not request.referer:
        return []
    params = {
        "locale_code": "en_US",
        "keywords": request.query,
        "location": request.location or "",
        "contract_type": "c" if request.job_type == "contract" else "",
        "page_size": min(request.results_wanted, 100),
        "user_ip": request.user_ip,
        "user_agent": request.user_agent,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                _cfg("CAREERJET_API_URL", default="https://search.api.careerjet.net/v4/query"),
                params=params,
                auth=(str(key), ""),
                headers={"Referer": request.referer},
            )
            response.raise_for_status()
            items = response.json().get("jobs", [])
    except Exception as exc:
        logger.warning("careerjet request failed: %s", type(exc).__name__)
        return []
    jobs: list[Job] = []
    for item in items:
        if isinstance(item, dict):
            _append(jobs, request, "careerjet", item, title=item.get("title"), company=item.get("company"), location=item.get("locations") or item.get("location"), url=item.get("url"), description=item.get("description"), external_id=item.get("id") or item.get("url"), date_posted=item.get("date"), type_value=item.get("contract_type") or item.get("contracttype") or item.get("contracttime"))
    return jobs[: request.results_wanted]


async def workable(request: ProviderRequest) -> list[Job]:
    url = _cfg("WORKABLE_FEED_URL", default="https://www.workable.com/boards/workable.xml")
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            response = await client.get(url, headers={"Accept": "application/xml, application/json"})
            response.raise_for_status()
        jobs: list[Job] = []
        try:
            payload = response.json()
            items = payload.get("jobs", payload.get("results", payload)) if isinstance(payload, dict) else payload
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict):
                    _append(jobs, request, "workable", item, title=item.get("title") or item.get("name"), company=item.get("company") or item.get("account"), location=item.get("location"), url=item.get("url") or item.get("application_url"), description=item.get("description"), external_id=item.get("id") or item.get("shortcode"), date_posted=item.get("published") or item.get("created_at"), type_value=item.get("employment_type") or item.get("type"), explicit_remote=item.get("remote"))
        except Exception:
            root = ET.fromstring(response.content)
            for node in root.findall(".//job") + root.findall(".//item"):
                values = {child.tag.rsplit("}", 1)[-1]: child.text for child in node}
                _append(jobs, request, "workable", values, title=values.get("title"), company=values.get("company") or values.get("account"), location=values.get("location"), url=values.get("url") or values.get("link"), description=values.get("description"), external_id=values.get("id") or values.get("shortcode") or values.get("guid"), date_posted=values.get("published") or values.get("pubDate"), type_value=values.get("employment_type") or values.get("type"))
        return jobs[: request.results_wanted]
    except Exception as exc:
        logger.warning("workable request failed: %s", type(exc).__name__)
        return []


async def greenhouse(request: ProviderRequest) -> list[Job]:
    boards = _boards("GREENHOUSE_BOARDS", "GREENHOUSE_BOARD_IDS")
    if not boards:
        return []
    jobs: list[Job] = []
    async with httpx.AsyncClient(timeout=20) as client:
        for board in boards:
            try:
                response = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{quote(board, safe='')}/jobs", params={"content": "true"})
                response.raise_for_status()
                for item in response.json().get("jobs", []):
                    offices = item.get("offices") or []
                    location = (item.get("location") or {}).get("name") or ", ".join(filter(None, (_text(value) for value in offices)))
                    _append(jobs, request, "greenhouse", item, title=item.get("title"), company=board, location=location, url=item.get("absolute_url"), description=item.get("content"), external_id=f"{board}-{item.get('id')}", date_posted=item.get("updated_at"), type_value=item.get("metadata"))
            except Exception as exc:
                logger.warning("greenhouse board request failed: %s", type(exc).__name__)
    return jobs[: request.results_wanted]


async def lever(request: ProviderRequest) -> list[Job]:
    boards = _boards("LEVER_BOARDS", "LEVER_BOARD_IDS")
    if not boards:
        return []
    jobs: list[Job] = []
    async with httpx.AsyncClient(timeout=20) as client:
        for board in boards:
            try:
                response = await client.get(f"https://api.lever.co/v0/postings/{quote(board, safe='')}", params={"mode": "json", "limit": request.results_wanted})
                response.raise_for_status()
                for item in response.json():
                    categories = item.get("categories") or {}
                    description = " ".join(filter(None, (_text(item.get("descriptionPlain")), _text(item.get("additionalPlain")))))
                    _append(jobs, request, "lever", item, title=item.get("text"), company=board, location=categories.get("location") or item.get("workplaceType"), url=item.get("hostedUrl") or item.get("applyUrl"), description=description, external_id=f"{board}-{item.get('id')}", date_posted=item.get("createdAt"), type_value=categories.get("commitment"), explicit_remote=item.get("workplaceType") == "remote")
            except Exception as exc:
                logger.warning("lever board request failed: %s", type(exc).__name__)
    return jobs[: request.results_wanted]


async def ashby(request: ProviderRequest) -> list[Job]:
    boards = _boards("ASHBY_BOARDS", "ASHBY_BOARD_IDS")
    if not boards:
        return []
    jobs: list[Job] = []
    async with httpx.AsyncClient(timeout=20) as client:
        for board in boards:
            try:
                response = await client.get(f"https://api.ashbyhq.com/posting-api/job-board/{quote(board, safe='')}", params={"includeCompensation": "true"})
                response.raise_for_status()
                for item in response.json().get("jobs", []):
                    _append(jobs, request, "ashby", item, title=item.get("title"), company=board, location=item.get("location"), url=item.get("jobUrl") or item.get("applyUrl"), description=item.get("descriptionPlain") or item.get("descriptionHtml"), external_id=f"{board}-{item.get('id') or item.get('jobUrl')}", date_posted=item.get("publishedAt"), type_value=item.get("employmentType") or item.get("team"), explicit_remote=item.get("isRemote"), pay_data=item.get("compensation") if isinstance(item.get("compensation"), dict) else item)
            except Exception as exc:
                logger.warning("ashby board request failed: %s", type(exc).__name__)
    return jobs[: request.results_wanted]


async def smartrecruiters(request: ProviderRequest) -> list[Job]:
    boards = _boards("SMARTRECRUITERS_BOARDS", "SMARTRECRUITERS_COMPANY_IDS")
    if not boards:
        return []
    jobs: list[Job] = []
    async with httpx.AsyncClient(timeout=20) as client:
        for board in boards:
            try:
                response = await client.get(f"https://api.smartrecruiters.com/v1/companies/{quote(board, safe='')}/postings", params={"limit": min(request.results_wanted, 100), "q": request.query})
                response.raise_for_status()
                for summary in response.json().get("content", []):
                    item = summary
                    try:
                        detail = await client.get(f"https://api.smartrecruiters.com/v1/companies/{quote(board, safe='')}/postings/{summary.get('id')}")
                        if detail.is_success:
                            item = detail.json()
                    except Exception:
                        pass
                    location_data = item.get("location") or {}
                    location = ", ".join(str(location_data.get(key)) for key in ("city", "region", "country") if location_data.get(key)) if isinstance(location_data, dict) else location_data
                    sections = item.get("jobAd", {}).get("sections", {}) if isinstance(item.get("jobAd"), dict) else {}
                    description = " ".join(_text(value) or "" for value in sections.values()) if isinstance(sections, dict) else None
                    _append(jobs, request, "smartrecruiters", item, title=item.get("name"), company=(item.get("company") or {}).get("name") if isinstance(item.get("company"), dict) else board, location=location, url=item.get("postingUrl") or item.get("applyUrl") or f"https://jobs.smartrecruiters.com/{board}/{item.get('id')}", description=description, external_id=f"{board}-{item.get('id')}", date_posted=item.get("releasedDate"), type_value=(item.get("typeOfEmployment") or {}).get("label") if isinstance(item.get("typeOfEmployment"), dict) else item.get("typeOfEmployment"), explicit_remote=item.get("remote"))
            except Exception as exc:
                logger.warning("smartrecruiters board request failed: %s", type(exc).__name__)
    return jobs[: request.results_wanted]


async def recruitee(request: ProviderRequest) -> list[Job]:
    boards = _boards("RECRUITEE_BOARDS", "RECRUITEE_COMPANY_IDS")
    if not boards:
        return []
    jobs: list[Job] = []
    async with httpx.AsyncClient(timeout=20) as client:
        for board in boards:
            try:
                response = await client.get(f"https://{board}.recruitee.com/api/offers/")
                response.raise_for_status()
                for item in response.json().get("offers", []):
                    locations = item.get("locations") or item.get("location")
                    _append(jobs, request, "recruitee", item, title=item.get("title"), company=board, location=locations, url=item.get("careers_url") or item.get("careers_apply_url"), description=item.get("description") or item.get("requirements"), external_id=f"{board}-{item.get('id') or item.get('slug')}", date_posted=item.get("published_at") or item.get("created_at"), type_value=item.get("employment_type_code") or item.get("employment_type"), explicit_remote=item.get("remote"))
            except Exception as exc:
                logger.warning("recruitee board request failed: %s", type(exc).__name__)
    return jobs[: request.results_wanted]


async def jooble(request: ProviderRequest) -> list[Job]:
    key = _cfg("JOOBLE_API_KEY")
    if not key:
        return []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"https://jooble.org/api/{quote(str(key), safe='')}", json={"keywords": request.query, "location": request.location or "", "page": 1})
            response.raise_for_status()
            items = response.json().get("jobs", [])
    except Exception as exc:
        logger.warning("jooble request failed: %s", type(exc).__name__)
        return []
    jobs: list[Job] = []
    for item in items:
        if isinstance(item, dict):
            _append(jobs, request, "jooble", item, title=item.get("title"), company=item.get("company"), location=item.get("location"), url=item.get("link"), description=item.get("snippet"), external_id=item.get("id") or item.get("link"), date_posted=item.get("updated"), type_value=item.get("type"), pay_data={**item, "salary": item.get("salary")})
    return jobs[: request.results_wanted]


async def adzuna(request: ProviderRequest) -> list[Job]:
    app_id = _cfg("ADZUNA_APP_ID", "ADZUNA_APPLICATION_ID")
    key = _cfg("ADZUNA_APP_KEY", "ADZUNA_API_KEY")
    if not app_id or not key:
        return []
    country = _cfg("ADZUNA_COUNTRY", default="us")
    params = {"app_id": app_id, "app_key": key, "what": request.query, "where": request.location or "", "results_per_page": min(request.results_wanted, 50), "content-type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1", params=params)
            response.raise_for_status()
            items = response.json().get("results", [])
    except Exception as exc:
        logger.warning("adzuna request failed: %s", type(exc).__name__)
        return []
    jobs: list[Job] = []
    for item in items:
        if isinstance(item, dict):
            category = (item.get("category") or {}).get("label") if isinstance(item.get("category"), dict) else item.get("category")
            location = (item.get("location") or {}).get("display_name") if isinstance(item.get("location"), dict) else item.get("location")
            company = (item.get("company") or {}).get("display_name") if isinstance(item.get("company"), dict) else item.get("company")
            pay = {**item, "min": item.get("salary_min"), "max": item.get("salary_max"), "currency": item.get("salary_currency") or "USD", "interval": "yearly"}
            _append(jobs, request, "adzuna", item, title=item.get("title"), company=company, location=location, url=item.get("redirect_url"), description=item.get("description"), external_id=item.get("id"), date_posted=item.get("created"), type_value=item.get("contract_type") or item.get("contract_time") or category, pay_data=pay)
    return jobs[: request.results_wanted]


async def hackernews(request: ProviderRequest) -> list[Job]:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            search = await client.get("https://hn.algolia.com/api/v1/search_by_date", params={"query": "Ask HN: Who is hiring?", "tags": "story", "hitsPerPage": 10})
            search.raise_for_status()
            hits = search.json().get("hits", [])
            story = next((hit for hit in hits if re.search(r"who is hiring\?", hit.get("title") or "", re.I)), None)
            if not story:
                return []
            response = await client.get(f"https://hn.algolia.com/api/v1/items/{story.get('objectID')}")
            response.raise_for_status()
            children = response.json().get("children", [])
    except Exception as exc:
        logger.warning("hackernews request failed: %s", type(exc).__name__)
        return []
    jobs: list[Job] = []
    for item in children:
        if not isinstance(item, dict):
            continue
        body = _text(item.get("text"))
        if not body or not re.search(r"\bremote\b|work from home", body, re.I) or not re.search(r"\bcontract(?:or)?\b|\bfreelance\b|\b1099\b|\bc2c\b", body, re.I):
            continue
        parts = [part.strip() for part in re.split(r"\s*\|\s*|\n", body) if part.strip()]
        company = parts[0][:150] if parts else "HN employer"
        title = next((part for part in parts[1:5] if re.search(r"engineer|developer|designer|manager|consultant|contract", part, re.I)), f"Contract role at {company}")
        link_match = re.search(r"https?://[^\s<]+", item.get("text") or "")
        url = html.unescape(link_match.group(0)).rstrip(".,)") if link_match else f"https://news.ycombinator.com/item?id={item.get('id')}"
        _append(jobs, request, "hackernews", item, title=title, company=company, location="Remote", url=url, description=body, external_id=item.get("id"), date_posted=item.get("created_at") or item.get("created_at_i"), type_value="contract", explicit_remote=True)
    return jobs[: request.results_wanted]


async def usajobs(request: ProviderRequest) -> list[Job]:
    key = _cfg("USAJOBS_API_KEY")
    email = _cfg("USAJOBS_EMAIL", "USAJOBS_USER_AGENT")
    if not key or not email:
        return []
    headers = {"Authorization-Key": str(key), "User-Agent": str(email), "Host": "data.usajobs.gov"}
    params = {"Keyword": request.query, "LocationName": request.location or "", "ResultsPerPage": min(request.results_wanted, 500)}
    if request.is_remote:
        params["RemoteIndicator"] = "True"
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.get("https://data.usajobs.gov/api/search", headers=headers, params=params)
            response.raise_for_status()
            items = response.json().get("SearchResult", {}).get("SearchResultItems", [])
    except Exception as exc:
        logger.warning("usajobs request failed: %s", type(exc).__name__)
        return []
    jobs: list[Job] = []
    for wrapper in items:
        if not isinstance(wrapper, dict):
            continue
        item = wrapper.get("MatchedObjectDescriptor") or {}
        details = item.get("UserArea", {}).get("Details", {})
        locations = item.get("PositionLocation") or []
        location = ", ".join(filter(None, ((_text(value.get("LocationName")) if isinstance(value, dict) else _text(value)) for value in locations)))
        remuneration = (item.get("PositionRemuneration") or [{}])[0]
        pay = {"min": remuneration.get("MinimumRange"), "max": remuneration.get("MaximumRange"), "currency": "USD", "interval": remuneration.get("RateIntervalCode") or remuneration.get("Description")}
        description = " ".join(filter(None, (_text(item.get("QualificationSummary")), _text(details.get("JobSummary")), _text(details.get("MajorDuties")))))
        _append(jobs, request, "usajobs", item, title=item.get("PositionTitle"), company=item.get("OrganizationName") or item.get("DepartmentName"), location=location, url=item.get("PositionURI"), description=description, external_id=item.get("PositionID"), date_posted=item.get("PublicationStartDate"), type_value=details.get("AppointmentExplanation") or details.get("ScheduleName"), explicit_remote=details.get("RemoteIndicator"), pay_data=pay)
    return jobs[: request.results_wanted]


def _upwork_nodes(payload: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        if any(key in payload for key in ("title", "jobTitle")):
            nodes.append(payload)
        for value in payload.values():
            nodes.extend(_upwork_nodes(value))
    elif isinstance(payload, list):
        for value in payload:
            nodes.extend(_upwork_nodes(value))
    return nodes


async def upwork(request: ProviderRequest) -> list[Job]:
    token = _cfg("UPWORK_API_TOKEN", "UPWORK_BEARER_TOKEN")
    endpoint = _cfg("UPWORK_GRAPHQL_URL", "UPWORK_GRAPHQL_ENDPOINT")
    if not token or not endpoint:
        return []
    query = "query ProviderJobs($searchTerm: String!) { marketplaceJobPostings(marketPlaceJobFilter: { searchExpression_eq: $searchTerm }, searchType: USER_JOBS_SEARCH, sortAttributes: { field: RECENCY }) { edges { node { id title description createdDateTime duration engagement skills { name } } } } }"
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(endpoint, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json={"query": query, "variables": {"searchTerm": request.query}})
            response.raise_for_status()
            payload = response.json()
            if payload.get("errors") and not payload.get("data"):
                return []
            items = _upwork_nodes(payload.get("data", {}))
    except Exception as exc:
        logger.warning("upwork request failed: %s", type(exc).__name__)
        return []
    jobs: list[Job] = []
    for item in items:
        client_data = item.get("client") or {}
        location_data = item.get("location") or {}
        budget = item.get("hourlyBudget") or item.get("budget") or item.get("fixedPriceAmount") or {}
        if "amount" in budget and "min" not in budget:
            budget = {**budget, "min": budget.get("amount"), "max": budget.get("amount"), "interval": "fixed"}
        else:
            budget = {**budget, "interval": "hourly"}
        location = ", ".join(str(location_data.get(key)) for key in ("city", "country") if location_data.get(key)) if isinstance(location_data, dict) else location_data
        _append(jobs, request, "upwork", item, title=item.get("title") or item.get("jobTitle"), company=client_data.get("companyName") or client_data.get("name") or "Upwork client", location=location or "Remote", url=item.get("url") or item.get("ciphertext"), description=item.get("description"), external_id=item.get("id") or item.get("ciphertext"), date_posted=item.get("createdDateTime") or item.get("createdAt"), type_value=item.get("jobType") or item.get("engagement") or "contract", explicit_remote=True, pay_data=budget)
    return jobs[: request.results_wanted]


Provider = Callable[[ProviderRequest], Awaitable[list[Job]]]

PROVIDERS: dict[str, Provider] = {
    "careerjet": careerjet,
    "workable": workable,
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "smartrecruiters": smartrecruiters,
    "recruitee": recruitee,
    "jooble": jooble,
    "adzuna": adzuna,
    "hackernews": hackernews,
    "usajobs": usajobs,
    "upwork": upwork,
}
