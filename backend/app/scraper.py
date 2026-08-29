import json
import logging
import re
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.config import DEFAULT_RESULTS_PER_BOARD, SCRAPER_HOURS_OLD
from app.models import Job, JobORM

logger = logging.getLogger(__name__)


# Try to import jobspy; it is an optional dependency for major boards.
try:
    from jobspy import scrape_jobs

    JOBSPI_AVAILABLE = True
except ImportError:
    scrape_jobs = None
    JOBSPI_AVAILABLE = False
    logger.warning("python-jobspy is not installed. Major board scraping disabled.")


# Try to import playwright for remote-first boards.
try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    async_playwright = None
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright is not installed. Playwright scraping disabled.")


US_TERMS = ["united states", "usa", "u.s.", " us", " us ", "remote", "remote us", "remote usa"]
NON_US_TERMS = ["india", "china", "europe", "uk", "canada", "mexico", "brazil", "argentina"]


def _normalize_location(location: str | None) -> tuple[bool, bool]:
    """Return (is_remote, is_us) from a location string."""
    if not location:
        return False, False
    loc = location.lower()
    is_remote = "remote" in loc
    # For remote jobs without explicit country, assume US for now.
    is_us = any(term.strip() in loc for term in US_TERMS) and not any(term in loc for term in NON_US_TERMS)
    return is_remote, is_us


def _detect_employment_type(description: str | None, title: str | None) -> str | None:
    """Infer employment type from text: w2, 1099, c2c, contract."""
    text = " ".join([description or "", title or ""]).lower()

    if re.search(r"\bc2c\b|corp[- ]to[- ]corp", text):
        return "c2c"
    if re.search(r"\b1099\b|independent contractor|1099 contractor", text):
        return "1099"
    if re.search(r"\bw2\b|w-2|full[- ]time employee|employee position", text):
        return "w2"
    if re.search(r"\bcontract\b|contractor|contract role|contract position", text):
        return "contract"
    return None


def _parse_amount(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return float(value)
    except (ValueError, TypeError):
        return None


def _row_to_job(row: pd.Series) -> Job:
    location = str(row.get("location")) if pd.notna(row.get("location")) else None
    is_remote, is_us = _normalize_location(location)

    description = str(row.get("description")) if pd.notna(row.get("description")) else None
    title = str(row.get("title")) if pd.notna(row.get("title")) else None
    employment_type = _detect_employment_type(description, title)

    date_posted = row.get("date_posted")
    if date_posted is not None and not pd.isna(date_posted):
        if isinstance(date_posted, str):
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
        job_id = f"{row.get('site', 'unknown')}-{hash(str(row.get('title')) + str(row.get('company')) + str(row.get('job_url')))}"

    return Job(
        id=job_id,
        site=str(row.get("site")) if pd.notna(row.get("site")) else "unknown",
        title=title or "Untitled",
        company=str(row.get("company")) if pd.notna(row.get("company")) else "Unknown",
        location=location,
        job_url=str(row.get("job_url")) if pd.notna(row.get("job_url")) else None,
        job_url_direct=str(row.get("job_url_direct")) if pd.notna(row.get("job_url_direct")) else None,
        description=description,
        job_type=str(row.get("job_type")) if pd.notna(row.get("job_type")) else None,
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
    results_wanted: int = DEFAULT_RESULTS_PER_BOARD,
    sources: list[str] | None = None,
) -> list[Job]:
    """Scrape major job boards using JobSpy."""
    if not JOBSPI_AVAILABLE:
        logger.error("python-jobspy not installed; cannot scrape major boards.")
        return []

    default_sources = ["indeed", "linkedin", "zip_recruiter", "google"]
    sources = sources or default_sources

    try:
        df: pd.DataFrame = scrape_jobs(
            site_name=sources,
            search_term=search_term,
            location=location,
            is_remote=is_remote,
            job_type=job_type,
            results_wanted=results_wanted,
            hours_old=SCRAPER_HOURS_OLD,
            country_indeed="USA",
        )
    except Exception as exc:
        logger.exception("JobSpy scrape failed: %s", exc)
        return []

    if df is None or df.empty:
        return []

    jobs = []
    for _, row in df.iterrows():
        try:
            job = _row_to_job(row)
            # Keep only remote, US-ish roles.
            if job.is_remote and (job.is_us or "remote" in (job.location or "").lower()):
                jobs.append(job)
        except Exception as exc:
            logger.warning("Failed to parse job row: %s", exc)

    return jobs


async def scrape_remote_boards(
    search_term: str,
    results_wanted: int = DEFAULT_RESULTS_PER_BOARD,
) -> list[Job]:
    """Scrape remote-first job boards using Playwright."""
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("playwright not installed; cannot scrape remote boards.")
        return []

    jobs = []
    keyword = search_term.lower()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # RemoteOK
        try:
            await page.goto("https://remoteok.com/remote-" + keyword.replace(" ", "-") + "-jobs", timeout=30000)
            await page.wait_for_selector(".job", timeout=10000)
            rows = await page.query_selector_all(".job")
            for row in rows[:results_wanted]:
                try:
                    title_el = await row.query_selector("h2 a, h3 a, .position a")
                    company_el = await row.query_selector(".companyLink, .company, h3")
                    if not title_el:
                        continue
                    title = await title_el.inner_text()
                    company = await company_el.inner_text() if company_el else "Unknown"
                    href = await title_el.get_attribute("href")
                    job_url = "https://remoteok.com" + href if href and not href.startswith("http") else href
                    jobs.append(
                        Job(
                            id=f"remoteok-{hash(job_url or title)}",
                            site="remoteok",
                            title=title.strip(),
                            company=company.strip(),
                            location="Remote",
                            job_url=job_url,
                            description="",
                            job_type="contract",
                            employment_type="contract",
                            is_remote=True,
                            is_us=True,
                            date_scraped=datetime.utcnow(),
                        )
                    )
                except Exception as exc:
                    logger.debug("RemoteOK row parse failed: %s", exc)
        except Exception as exc:
            logger.warning("RemoteOK scrape failed: %s", exc)

        # We Work Remotely
        try:
            await page.goto("https://weworkremotely.com/remote-jobs/search?utf8=%E2%9C%93&term=" + keyword.replace(" ", "+") + "&button=", timeout=30000)
            await page.wait_for_timeout(3000)
            rows = await page.query_selector_all(".feature, .job")
            for row in rows[:results_wanted]:
                try:
                    title_el = await row.query_selector(".title, h4 a, .position a")
                    if not title_el:
                        continue
                    title = await title_el.inner_text()
                    href = await title_el.get_attribute("href")
                    job_url = "https://weworkremotely.com" + href if href and not href.startswith("http") else href
                    jobs.append(
                        Job(
                            id=f"weworkremotely-{hash(job_url or title)}",
                            site="weworkremotely",
                            title=title.strip(),
                            company="Unknown",
                            location="Remote",
                            job_url=job_url,
                            description="",
                            job_type="contract",
                            employment_type="contract",
                            is_remote=True,
                            is_us=True,
                            date_scraped=datetime.utcnow(),
                        )
                    )
                except Exception as exc:
                    logger.debug("WWR row parse failed: %s", exc)
        except Exception as exc:
            logger.warning("WeWorkRemotely scrape failed: %s", exc)

        await browser.close()

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
