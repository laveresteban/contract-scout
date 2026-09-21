"""Seed a few sample jobs for local development.

Run:  python -m app.seed

The URLs are chosen so `verify` returns deterministic verdicts you can see in
the UI: a live page, a 404 (expired), and one that reads remote but isn't.
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone

from .db import SessionLocal, create_all
from .models import Job


def _days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


SAMPLE_JOBS = [
    Job(
        id="seed-live-1",
        title="Senior Backend Engineer (Contract)",
        company="Northwind Labs",
        location="Remote",
        site="linkedin",
        job_url="https://example.com/",
        is_remote=True,
        is_us=True,
        eligibility="explicit_us",
        job_type="contract",
        employment_type="c2c",
        date_posted=_days_ago(4),
        date_scraped=_days_ago(1),
        min_amount=95,
        max_amount=120,
        currency="USD",
        interval="hourly",
        normalized_min_yearly=197600,
        normalized_max_yearly=249600,
        description="<p>We're hiring a fully remote senior backend engineer to build "
        "our billing platform.</p><ul><li>Python, FastAPI, Postgres</li>"
        "<li>Event-driven systems</li><li>US-based, W2 or C2C</li></ul>",
    ),
    Job(
        id="seed-expired-1",
        title="Platform Engineer",
        company="Acme Corp",
        location="United States",
        site="indeed",
        job_url="https://httpbin.org/status/404",
        is_remote=True,
        is_us=True,
        eligibility="remote_us_assumed",
        job_type="contract",
        date_posted=_days_ago(72),
        date_scraped=_days_ago(2),
        description="<p>Remote platform engineering contract working on Kubernetes "
        "and Terraform. Long-term engagement with a great team.</p>",
    ),
    Job(
        id="seed-fakeremote-1",
        title="Data Engineer (Remote)",
        company="Globex, Inc.",
        location="Austin, TX",
        site="ziprecruiter",
        job_url="https://example.com/",
        is_remote=True,
        is_us=True,
        eligibility="remote_us_assumed",
        job_type="contract",
        date_posted=_days_ago(9),
        date_scraped=_days_ago(1),
        description="<p>Join our data team. This is a hybrid position; you must be "
        "on-site three days a week in our Austin office. Relocation is available.</p>",
    ),
    # Matches an "engineer" search but is NOT US-eligible, so the default
    # remote+US filters hide it — this is what the short-list guardrail surfaces
    # ("N more hidden") and can reveal on request.
    Job(
        id="seed-noneligible-1",
        title="Backend Engineer",
        company="Zenith EU",
        location="Berlin, Germany",
        site="linkedin",
        job_url="https://example.com/eu/1",
        is_remote=True,
        is_us=False,
        eligibility="non_us",
        job_type="contract",
        date_posted=_days_ago(6),
        date_scraped=_days_ago(1),
        description="<p>Remote backend engineering contract, EU-based applicants only.</p>",
    ),
]


# Cross-source duplicates of `seed-live-1`: the SAME role scraped by two other
# boards under different ids and lightly-varied title/company/location. They are
# inserted raw (no dedup) so the E2E suite can prove the backfill + dedup collapse
# them to a single active card. Opt-in via `--with-duplicates`.
DUPLICATE_JOBS = [
    Job(
        id="seed-live-1-dup-indeed",
        title="Senior Backend Engineer - C2C",
        company="Northwind Labs LLC",
        location="United States",
        site="indeed",
        job_url="https://example.com/indeed/1",
        is_remote=True,
        is_us=True,
        eligibility="explicit_us",
        job_type="contract",
        employment_type="c2c",
        date_posted=_days_ago(4),
        date_scraped=_days_ago(1),
        description="<p>Remote senior backend engineer, long-term contract.</p>",
    ),
    Job(
        id="seed-live-1-dup-zip",
        title="(Remote) Senior Backend Engineer",
        company="Northwind Labs",
        location="Remote, US",
        site="ziprecruiter",
        job_url="https://example.com/zip/1",
        is_remote=True,
        is_us=True,
        eligibility="explicit_us",
        job_type="contract",
        date_posted=_days_ago(3),
        date_scraped=_days_ago(1),
        description="<p>Backend engineering contract, fully remote.</p>",
    ),
]


async def seed(with_duplicates: bool = False) -> None:
    await create_all()
    rows = SAMPLE_JOBS + (DUPLICATE_JOBS if with_duplicates else [])
    async with SessionLocal() as session:
        for job in rows:
            await session.merge(job)  # idempotent upsert by primary key
        await session.commit()
    print(f"Seeded {len(rows)} jobs.")


if __name__ == "__main__":
    asyncio.run(seed(with_duplicates="--with-duplicates" in sys.argv))
