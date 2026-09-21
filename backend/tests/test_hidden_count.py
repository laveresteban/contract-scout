"""The short-list guardrail: how many query matches are hidden solely by the
remote/US eligibility filters (so the UI can offer a one-click loosen)."""

import pytest_asyncio

from app.models import Job as JobORM


@pytest_asyncio.fixture
async def eligibility_mix(db):
    rows = [
        # Matches "engineer" and is remote + US → shown by default.
        JobORM(id="ok-1", title="Backend Engineer", company="Acme",
               description="x", is_remote=True, is_us=True),
        # Matches, remote but not US-eligible → hidden by the US filter.
        JobORM(id="eu-1", title="Backend Engineer", company="Globex",
               description="x", is_remote=True, is_us=False),
        # Matches, US but on-site → hidden by the remote filter.
        JobORM(id="onsite-1", title="Backend Engineer", company="Initech",
               description="x", is_remote=False, is_us=True),
        # Does NOT match the query → never counted.
        JobORM(id="other-1", title="Marketing Lead", company="Acme",
               description="x", is_remote=True, is_us=False),
    ]
    for r in rows:
        db.add(r)
    await db.commit()
    return rows


async def test_hidden_count_reports_eligibility_hidden(client, eligibility_mix):
    resp = await client.get("/api/v1/jobs/hidden-count", params={"q": "engineer"})
    assert resp.status_code == 200
    body = resp.json()
    # 1 shown (ok-1), 2 hidden by remote/US (eu-1, onsite-1); marketing excluded.
    assert body == {"shown": 1, "hidden": 2, "total_matching": 3}


async def test_hidden_count_zero_when_nothing_hidden(client, eligibility_mix):
    resp = await client.get(
        "/api/v1/jobs/hidden-count", params={"q": "engineer", "company": "Acme"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"shown": 1, "hidden": 0, "total_matching": 1}


async def test_list_include_ineligible_relaxes_filters(client, eligibility_mix):
    strict = await client.get("/api/v1/jobs", params={"q": "engineer"})
    assert strict.headers["X-Total-Count"] == "1"

    relaxed = await client.get(
        "/api/v1/jobs", params={"q": "engineer", "include_ineligible": "true"}
    )
    assert relaxed.headers["X-Total-Count"] == "3"  # + the non-US and on-site matches
