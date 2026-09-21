"""Cross-source / cross-path de-duplication.

Covers the shared key (``app.dedup``), the scan path collapsing duplicates and
pointing matches at the survivor, parity between the ``/search`` (persist) and
scan paths, and the backfill script.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.backfill_dedup import backfill_session
from app.dedup import dedup_key
from app.models import Job, SavedSearch, SavedSearchMatch
from app.scraped import Job as ScrapedJob
from app.services import persist
from app.services import scan as scan_service


# --- shared key ------------------------------------------------------------
def test_key_collapses_source_noise():
    a = dedup_key(company="Acme, Inc.", title="Senior Java Developer (Remote)", location="Remote")
    b = dedup_key(company="Acme LLC", title="Senior Java Developer - Contract", location="United States")
    assert a == b


def test_key_keeps_distinct_roles_apart():
    a = dedup_key(company="Acme", title="Java Developer")
    b = dedup_key(company="Acme", title="Python Developer")
    c = dedup_key(company="Globex", title="Java Developer")
    assert len({a, b, c}) == 3


def test_key_real_location_distinguishes():
    remote = dedup_key(company="Acme", title="Java Developer", location="Remote")
    austin = dedup_key(company="Acme", title="Java Developer", location="Austin, TX")
    assert remote != austin


def test_key_falls_back_to_url_then_id():
    # No company/title → canonical URL identity (tracking params stripped).
    a = dedup_key(company=None, title=None, url="https://b.co/1?utm_source=x", job_id="1")
    b = dedup_key(company=None, title=None, url="https://b.co/1", job_id="2")
    assert a == b


# --- scan path -------------------------------------------------------------
def _hit(**over):
    base = dict(
        id="s1", title="Senior Python Engineer", company="Acme",
        description="Fully remote contract", site="linkedin", is_remote=True,
        job_url="https://src/s1",
    )
    base.update(over)
    return base


async def _search(db):
    s = SavedSearch(
        id="search-1", user_id="ip:unknown", name="Py",
        filters={"query": "python", "is_remote": True}, alert_enabled=True,
    )
    db.add(s)
    await db.commit()
    return s


async def _count(db, model, *where):
    return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


async def _scraper(jobs):
    async def _s(_filters):
        return jobs
    return _s


async def test_scan_collapses_cross_source_duplicates(db):
    s = await _search(db)
    # Same role, two boards, two ids.
    res = await scan_service.scan_one(
        db, s,
        await _scraper([
            _hit(id="li-1", site="linkedin", title="Senior Python Engineer (Remote)"),
            _hit(id="in-9", site="indeed", title="Senior Python Engineer - Contract"),
        ]),
    )
    await db.commit()

    assert res.matched == 2
    # One stored row and exactly one match, both pointing at the survivor.
    assert await _count(db, Job) == 1
    assert await _count(db, SavedSearchMatch) == 1
    assert res.new == 1


async def test_scan_merges_onto_persist_row(db):
    # A job already stored via the /search path...
    await persist.save_jobs(
        [ScrapedJob(id="search-42", title="Senior Python Engineer", company="Acme",
                    site="google", is_remote=True, job_url="https://g.co/42")],
        db,
    )
    s = await _search(db)
    # ...is re-found by a scan under a different source id and must not duplicate.
    await scan_service.scan_one(
        db, s, await _scraper([_hit(id="li-77", title="Senior Python Engineer (Remote)")])
    )
    await db.commit()

    assert await _count(db, Job) == 1
    row = (await db.execute(select(Job))).scalar_one()
    assert row.id == "search-42"  # survivor keeps the original id
    match = (await db.execute(select(SavedSearchMatch))).scalar_one()
    assert match.job_id == "search-42"


# --- backfill --------------------------------------------------------------
async def test_backfill_deactivates_duplicates(db):
    # Two raw rows for the same role with NULL dedup_key (legacy scan inserts).
    db.add(Job(id="a", title="Senior Python Engineer", company="Acme, Inc.",
               is_active=True, last_seen=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    db.add(Job(id="b", title="Senior Python Engineer (Remote)", company="Acme LLC",
               is_active=True, last_seen=datetime(2026, 2, 1, tzinfo=timezone.utc)))
    await db.commit()

    keyed, deactivated = await backfill_session(db)
    assert keyed == 2
    assert deactivated == 1

    active = (await db.execute(select(Job).where(Job.is_active.is_(True)))).scalars().all()
    assert [j.id for j in active] == ["b"]  # freshest survives


# --- seed fixture parity (data the Selenium E2E relies on) ------------------
def test_seed_duplicates_collapse_onto_live_job():
    from app.seed import DUPLICATE_JOBS, SAMPLE_JOBS

    live = next(j for j in SAMPLE_JOBS if j.id == "seed-live-1")
    live_key = dedup_key(company=live.company, title=live.title, location=live.location)
    for dup in DUPLICATE_JOBS:
        assert dedup_key(company=dup.company, title=dup.title, location=dup.location) == live_key
