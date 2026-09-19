"""Seed a few sample jobs for local development.

Run:  python -m app.seed

The URLs are chosen so `verify` returns deterministic verdicts you can see in
the UI: a live page, a 404 (expired), and one that reads remote but isn't.
"""

import asyncio
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
        eligibility="remote_us_assumed",
        job_type="contract",
        date_posted=_days_ago(9),
        date_scraped=_days_ago(1),
        description="<p>Join our data team. This is a hybrid position; you must be "
        "on-site three days a week in our Austin office. Relocation is available.</p>",
    ),
]


async def seed() -> None:
    await create_all()
    async with SessionLocal() as session:
        for job in SAMPLE_JOBS:
            await session.merge(job)  # idempotent upsert by primary key
        await session.commit()
    print(f"Seeded {len(SAMPLE_JOBS)} jobs.")


if __name__ == "__main__":
    asyncio.run(seed())
