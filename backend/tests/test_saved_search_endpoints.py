import pytest

from app.services import scraper as scraper_module


@pytest.fixture
def use_scraper():
    """Temporarily wire a fake scraper, restore the null stub afterward."""

    def _install(jobs):
        async def _scrape(_filters):
            return jobs

        scraper_module.set_scraper(_scrape)

    yield _install
    scraper_module.set_scraper(scraper_module._null_scraper)


def _job(**over):
    base = dict(
        id="j1",
        title="Senior Python Engineer",
        description="Fully remote contract",
        job_type="contract",
        is_remote=True,
        eligibility="explicit_us",
        job_url="https://src/j1",
        normalized_min_yearly=150000,
        normalized_max_yearly=200000,
    )
    base.update(over)
    return base


async def _create(client, **over):
    payload = {
        "name": "Python contracts",
        "filters": {"query": "python", "is_remote": True},
        "alert_enabled": True,
        "alert_frequency": "daily",
    }
    payload.update(over)
    resp = await client.post("/api/v1/prefs/saved-searches", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_saved_search_crud(client):
    created = await _create(client)
    assert created["name"] == "Python contracts"
    assert created["alert_enabled"] is True
    assert created["new_count"] == 0

    listed = (await client.get("/api/v1/prefs/saved-searches")).json()
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]

    patched = await client.patch(
        f"/api/v1/prefs/saved-searches/{created['id']}", json={"alert_enabled": False}
    )
    assert patched.status_code == 200
    assert patched.json()["alert_enabled"] is False

    deleted = await client.delete(f"/api/v1/prefs/saved-searches/{created['id']}")
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/prefs/saved-searches")).json() == []


async def test_unknown_search_is_404(client):
    assert (await client.get("/api/v1/prefs/saved-searches/nope/matches")).status_code == 404
    assert (await client.post("/api/v1/prefs/saved-searches/nope/scan")).status_code == 404


async def test_scan_now_finds_and_lists_matches(client, use_scraper):
    use_scraper([_job(id="a"), _job(id="b"), _job(id="x", title="Rust Dev", is_remote=False)])
    created = await _create(client)

    scan = await client.post(f"/api/v1/prefs/saved-searches/{created['id']}/scan")
    assert scan.status_code == 200, scan.text
    body = scan.json()
    assert body["scraped"] == 3
    assert body["matched"] == 2  # rust/on-site filtered out
    assert body["new"] == 2
    assert body["ok"] is True

    matches = (
        await client.get(f"/api/v1/prefs/saved-searches/{created['id']}/matches")
    ).json()
    assert {m["job"]["id"] for m in matches} == {"a", "b"}
    assert all(m["is_new"] for m in matches)

    # new_count is reflected on the list.
    listed = (await client.get("/api/v1/prefs/saved-searches")).json()
    assert listed[0]["new_count"] == 2


async def test_scan_is_idempotent_then_marks_seen(client, use_scraper):
    use_scraper([_job(id="a")])
    created = await _create(client)

    first = (await client.post(f"/api/v1/prefs/saved-searches/{created['id']}/scan")).json()
    assert first["new"] == 1
    second = (await client.post(f"/api/v1/prefs/saved-searches/{created['id']}/scan")).json()
    assert second["new"] == 0  # already recorded

    seen = await client.post(f"/api/v1/prefs/saved-searches/{created['id']}/matches/seen")
    assert seen.status_code == 204
    new_only = (
        await client.get(
            f"/api/v1/prefs/saved-searches/{created['id']}/matches?new_only=true"
        )
    ).json()
    assert new_only == []


async def test_scan_with_no_scraper_finds_nothing(client):
    # Default null stub — the real scraper lives in another backend.
    created = await _create(client)
    scan = (await client.post(f"/api/v1/prefs/saved-searches/{created['id']}/scan")).json()
    assert scan == {
        "saved_search_id": created["id"],
        "scraped": 0,
        "matched": 0,
        "new": 0,
        "ok": True,
        "detail": None,
    }
