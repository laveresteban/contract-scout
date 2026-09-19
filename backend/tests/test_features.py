from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import Job as JobORM
from app.models import UserORM
from app.normalize import classify_eligibility, normalize_amount
from app.routers.auth import create_access_token
from app.scraped import Job
from app.services.persist import _dedup_key, mark_stale_jobs, save_jobs


@pytest_asyncio.fixture
async def user(db):
    u = UserORM(provider="github", provider_id="123", email="dev@example.com", name="Dev")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.fixture
def auth_headers(user):
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


# --- Pay normalization ------------------------------------------------------
def test_normalize_amount_hourly_usd():
    assert normalize_amount(100, "hourly", "USD") == 100 * 2080


def test_normalize_amount_currency_conversion():
    assert normalize_amount(100000, "yearly", "EUR") == 108000.0


def test_normalize_amount_unknown_interval():
    assert normalize_amount(100, None, "USD") is None


async def test_job_exposes_normalized_fields(client, db):
    db.add(
        JobORM(
            id="norm-1",
            site="indeed",
            title="Contractor",
            company="Acme",
            interval="hourly",
            min_amount=50,
            max_amount=100,
            currency="USD",
            is_remote=True,
            is_us=True,
        )
    )
    await db.commit()
    resp = await client.get("/api/v1/jobs/norm-1")
    data = resp.json()
    assert data["normalized_min_yearly"] == 50 * 2080
    assert data["normalized_max_yearly"] == 100 * 2080
    assert data["normalized_currency"] == "USD"
    assert "eligibility" in data


# --- Normalized (yearly-USD) pay filtering ----------------------------------
async def _make_pay_jobs(db):
    """A $100/hr contract (~$208k/yr) and a $150k/yr full-time salary."""
    jobs = [
        Job(id="hr-100", site="dice", title="Contract Engineer", company="Acme",
            interval="hourly", min_amount=100, max_amount=100, currency="USD",
            job_type="contract", is_remote=True, is_us=True),
        Job(id="ft-150k", site="indeed", title="Staff Engineer", company="Globex",
            interval="yearly", min_amount=150000, max_amount=150000, currency="USD",
            job_type="fulltime", is_remote=True, is_us=True),
    ]
    await save_jobs(jobs, db)


async def test_save_jobs_persists_normalized_pay(db):
    await _make_pay_jobs(db)
    hourly = (await db.execute(select(JobORM).where(JobORM.id == "hr-100"))).scalar_one()
    assert hourly.normalized_min_yearly == 100 * 2080  # 208,000


async def test_min_yearly_filter_excludes_lower_salary(client, db):
    await _make_pay_jobs(db)
    # $100/hr floor -> 208k/yr. The 150k/yr full-time role must not appear.
    resp = await client.get("/api/v1/jobs?min_yearly=208000")
    ids = {j["id"] for j in resp.json()}
    assert ids == {"hr-100"}


async def test_annual_sort_ranks_hourly_above_lower_salary(client, db):
    await _make_pay_jobs(db)
    resp = await client.get("/api/v1/jobs?sort_by=annual_max&sort_order=desc")
    ids = [j["id"] for j in resp.json()]
    assert ids.index("hr-100") < ids.index("ft-150k")


async def test_min_yearly_filter_includes_single_ended_rate(client, db):
    await save_jobs(
        [
            Job(
                id="hourly-from",
                site="dice",
                title="Contract Engineer",
                company="Acme",
                interval="hourly",
                min_amount=100,
                currency="USD",
                job_type="contract",
                is_remote=True,
                is_us=True,
            )
        ],
        db,
    )
    resp = await client.get("/api/v1/jobs?min_yearly=208000")
    ids = {job["id"] for job in resp.json()}
    assert ids == {"hourly-from"}


# --- Eligibility ------------------------------------------------------------
def test_classify_eligibility():
    assert classify_eligibility("Remote, United States", True, True) == "explicit_us"
    assert classify_eligibility("Remote", True, True) == "remote_us_assumed"
    assert classify_eligibility("Remote, India", True, False) == "non_us"


# --- Dedup ------------------------------------------------------------------
def test_dedup_key_collapses_across_sources():
    a = Job(id="indeed-1", site="indeed", title="Senior Python Engineer", company="Acme Inc")
    b = Job(id="linkedin-9", site="linkedin", title="Senior Python Engineer", company="Acme")
    assert _dedup_key(a) == _dedup_key(b)


async def test_save_jobs_skips_cross_source_duplicates(db):
    jobs = [
        Job(id="indeed-1", site="indeed", title="Python Dev", company="Acme", is_remote=True, is_us=True),
        Job(id="linkedin-1", site="linkedin", title="Python Dev", company="Acme", is_remote=True, is_us=True),
    ]
    saved = await save_jobs(jobs, db)
    assert saved == 1


async def test_save_jobs_merges_richer_duplicate(db):
    await save_jobs(
        [Job(id="dice-1", site="dice", title="Python Dev", company="Acme", description="Short summary", is_remote=True, is_us=True)],
        db,
    )
    changed = await save_jobs(
        [
            Job(
                id="indeed-1",
                site="indeed",
                title="Python Dev",
                company="Acme Inc",
                description="Longer contract description with compensation details",
                job_url="https://example.com/job",
                interval="hourly",
                min_amount=85,
                max_amount=105,
                currency="USD",
                pay_source="structured",
                pay_confidence="high",
                pay_raw_text="$85-$105/hr",
                is_remote=True,
                is_us=True,
            )
        ],
        db,
    )
    merged = (await db.execute(select(JobORM))).scalars().one()
    assert changed == 0
    assert merged.min_amount == 85
    assert merged.max_amount == 105
    assert merged.interval == "hourly"
    assert merged.description.startswith("Longer")
    assert merged.pay_source == "structured"
    assert "indeed" in merged.source_urls


async def test_mark_stale_jobs_hides_expired_results(client, db):
    db.add(
        JobORM(
            id="stale",
            site="indeed",
            title="Old Contract",
            company="Acme",
            is_remote=True,
            is_us=True,
            is_active=True,
            last_seen=datetime.now(timezone.utc) - timedelta(days=31),
        )
    )
    await db.commit()
    assert await mark_stale_jobs(db) == 1
    resp = await client.get("/api/v1/jobs")
    assert resp.json() == []


# --- Stats / count ----------------------------------------------------------
async def test_stats_aggregates(client, db):
    db.add(JobORM(id="s1", site="indeed", title="A", company="X", employment_type="1099", is_remote=True, is_us=True))
    db.add(JobORM(id="s2", site="linkedin", title="B", company="Y", employment_type="w2", is_remote=True, is_us=False))
    await db.commit()
    stats = (await client.get("/api/v1/jobs/stats")).json()
    assert stats["count"] == 2
    assert stats["by_source"].get("indeed") == 1
    assert stats["remote_count"] == 2
    assert stats["us_count"] == 1


async def test_jobs_total_count_header(client, db):
    for i in range(3):
        db.add(JobORM(id=f"c{i}", site="indeed", title="A", company="X", is_remote=True, is_us=True))
    await db.commit()
    resp = await client.get("/api/v1/jobs?limit=1")
    assert resp.headers["X-Total-Count"] == "3"
    assert len(resp.json()) == 1


async def test_jobs_count_endpoint(client, db):
    db.add(JobORM(id="cc1", site="indeed", title="A", company="X", is_remote=True, is_us=True))
    await db.commit()
    resp = await client.get("/api/v1/jobs/count")
    assert resp.json()["count"] == 1


# --- Auth -------------------------------------------------------------------
async def test_providers_empty_without_config(client):
    assert (await client.get("/api/v1/auth/providers")).json() == []


async def test_me_requires_auth(client):
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_me_with_token(client, auth_headers):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "dev@example.com"


# --- Prefs ------------------------------------------------------------------
async def test_saved_jobs_requires_auth(client):
    assert (await client.get("/api/v1/prefs/saved-jobs")).status_code == 401


async def test_saved_jobs_roundtrip(client, auth_headers):
    await client.put("/api/v1/prefs/saved-jobs/job-1", headers=auth_headers)
    assert (await client.get("/api/v1/prefs/saved-jobs", headers=auth_headers)).json() == ["job-1"]
    await client.delete("/api/v1/prefs/saved-jobs/job-1", headers=auth_headers)
    assert (await client.get("/api/v1/prefs/saved-jobs", headers=auth_headers)).json() == []


async def test_saved_search_crud(client, auth_headers):
    created = (await client.post(
        "/api/v1/prefs/saved-searches",
        headers=auth_headers,
        json={"name": "Py", "filters": {"query": "python"}, "alert_enabled": True},
    )).json()
    sid = created["id"]
    assert created["name"] == "Py"
    assert created["filters"]["query"] == "python"

    updated = (await client.patch(
        f"/api/v1/prefs/saved-searches/{sid}",
        headers=auth_headers,
        json={"alert_frequency": "weekly"},
    )).json()
    assert updated["alert_frequency"] == "weekly"

    assert len((await client.get("/api/v1/prefs/saved-searches", headers=auth_headers)).json()) == 1
    await client.delete(f"/api/v1/prefs/saved-searches/{sid}", headers=auth_headers)
    assert (await client.get("/api/v1/prefs/saved-searches", headers=auth_headers)).json() == []


# --- Scrape health / alerts -------------------------------------------------
async def test_scrape_health(client):
    data = (await client.get("/api/v1/scrape/health")).json()
    assert "sources" in data
    assert "scheduler_enabled" in data


async def test_alerts_run(client, auth_headers, db):
    await client.post(
        "/api/v1/prefs/saved-searches",
        headers=auth_headers,
        json={"name": "Py", "filters": {"query": "python"}, "alert_enabled": True},
    )
    db.add(
        JobORM(id="a1", site="indeed", title="Python Dev", company="Acme", is_remote=True, is_us=True)
    )
    await db.commit()
    # SMTP unconfigured -> log-only send still counts as sent.
    resp = await client.post("/api/v1/alerts/run")
    assert resp.status_code == 200
    assert resp.json()["sent"] >= 1
