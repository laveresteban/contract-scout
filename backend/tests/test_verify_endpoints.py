import httpx
import respx


async def _seed(db, make_job, **overrides):
    job = make_job(**overrides)
    db.add(job)
    await db.commit()
    return job


@respx.mock
async def test_verify_single_live(client, db, make_job):
    await _seed(db, make_job, id="j1", job_url="https://src/1")
    respx.get("https://src/1").mock(return_value=httpx.Response(200, text="apply now"))

    resp = await client.post("/api/v1/jobs/j1/verify")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == "j1"
    assert body["status"] == "live"
    assert body["checked_at"] is not None


async def test_verify_single_404_job(client):
    resp = await client.post("/api/v1/jobs/does-not-exist/verify")
    assert resp.status_code == 404


@respx.mock
async def test_verify_batch(client, db, make_job):
    await _seed(db, make_job, id="a", job_url="https://src/a")
    await _seed(db, make_job, id="b", job_url="https://src/b")
    respx.get("https://src/a").mock(return_value=httpx.Response(200, text="open"))
    respx.get("https://src/b").mock(return_value=httpx.Response(404))

    resp = await client.post("/api/v1/jobs/verify", json={"ids": ["a", "b", "missing"]})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results["a"]["status"] == "live"
    assert results["b"]["status"] == "expired"
    assert "missing" not in results  # unknown ids are skipped


@respx.mock
async def test_list_jobs_sets_total_header(client, db, make_job):
    await _seed(db, make_job, id="a")
    await _seed(db, make_job, id="b")
    resp = await client.get("/api/v1/jobs?limit=1")
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "2"
    assert len(resp.json()) == 1
