from datetime import datetime, timedelta, timezone

import pytest

from app.models import Job, SavedSearch, SavedSearchMatch
from app.services import matcher
from app.services import scan as scan_service
from sqlalchemy import func, select


def _job(**over):
    base = dict(
        id="s1",
        title="Senior Python Engineer",
        company="Acme",
        description="Fully remote contract",
        job_type="contract",
        employment_type="c2c",
        site="linkedin",
        is_remote=True,
        eligibility="explicit_us",
        job_url="https://src/s1",
        normalized_min_yearly=150000,
        normalized_max_yearly=200000,
    )
    base.update(over)
    return base


# --- matcher ---------------------------------------------------------------
def test_matcher_query_and_remote():
    j = _job()
    assert matcher.matches(j, {"query": "python", "is_remote": True})
    assert not matcher.matches(j, {"query": "rust"})
    assert not matcher.matches(_job(is_remote=False), {"is_remote": True})


def test_matcher_min_pay_excludes_only_proven_below():
    assert not matcher.matches(_job(normalized_max_yearly=90000), {"min_yearly": 150000})
    # Unknown pay is not excluded (don't bury jobs on missing data).
    assert matcher.matches(_job(normalized_max_yearly=None), {"min_yearly": 150000})


def test_matcher_employment_type():
    assert matcher.matches(_job(employment_type="c2c"), {"employment_type": "c2c"})
    assert not matcher.matches(_job(employment_type="w2"), {"employment_type": "c2c"})


# --- scan_one --------------------------------------------------------------
def _make_scraper(jobs):
    async def _scrape(_filters):
        return jobs

    return _scrape


async def _search(db, **over):
    s = SavedSearch(
        id=over.pop("id", "search-1"),
        user_id="ip:unknown",
        name="Py contracts",
        filters={"query": "python", "is_remote": True},
        alert_enabled=True,
    )
    for k, v in over.items():
        setattr(s, k, v)
    db.add(s)
    await db.commit()
    return s


async def _count(db, model, *where):
    return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


async def test_scan_one_ingests_and_flags_new(db):
    s = await _search(db)
    res = await scan_service.scan_one(db, s, _make_scraper([_job(id="a"), _job(id="b")]))
    await db.commit()

    assert (res.scraped, res.matched, res.new, res.ok) == (2, 2, 2, True)
    assert await _count(db, Job) == 2
    assert await _count(db, SavedSearchMatch, SavedSearchMatch.is_new.is_(True)) == 2
    assert s.last_scanned_at is not None


async def test_scan_one_dedupes_existing_matches(db):
    s = await _search(db)
    await scan_service.scan_one(db, s, _make_scraper([_job(id="a")]))
    await db.commit()
    # Same job again + one new one.
    res = await scan_service.scan_one(db, s, _make_scraper([_job(id="a"), _job(id="c")]))
    await db.commit()

    assert res.new == 1
    assert await _count(db, SavedSearchMatch) == 2


async def test_scan_one_filters_offtarget(db):
    s = await _search(db)  # filters query=python, is_remote
    res = await scan_service.scan_one(
        db, s, _make_scraper([_job(id="a"), _job(id="x", title="Rust Dev", description="on site")])
    )
    await db.commit()
    assert res.scraped == 2
    assert res.matched == 1
    assert await _count(db, SavedSearchMatch) == 1


async def test_scan_one_scraper_failure_is_inconclusive(db):
    s = await _search(db)

    async def _boom(_filters):
        raise RuntimeError("network down")

    res = await scan_service.scan_one(db, s, _boom)
    await db.commit()

    assert res.ok is False
    assert res.error is not None
    # No matches recorded and NOT marked scanned, so it's retried next tick.
    assert await _count(db, SavedSearchMatch) == 0
    assert s.last_scanned_at is None


# --- run_due_scans ---------------------------------------------------------
async def test_run_due_scans_only_enabled_and_due(db):
    now = datetime.now(timezone.utc)
    await _search(db, id="enabled-due", alert_enabled=True, last_scanned_at=None)
    await _search(
        db, id="enabled-fresh", alert_enabled=True, last_scanned_at=now - timedelta(minutes=5)
    )
    await _search(db, id="disabled", alert_enabled=False)

    summary = await scan_service.run_due_scans(db, _make_scraper([_job(id="a")]), now=now)

    ran_ids = {r.saved_search_id for r in summary.results}
    assert ran_ids == {"enabled-due"}
    assert summary.skipped_not_due == 1  # enabled-fresh


async def test_run_due_scans_force_ignores_freshness(db):
    now = datetime.now(timezone.utc)
    await _search(db, id="fresh", alert_enabled=True, last_scanned_at=now - timedelta(minutes=1))
    summary = await scan_service.run_due_scans(db, _make_scraper([_job(id="a")]), now=now, force=True)
    assert summary.ran == 1
