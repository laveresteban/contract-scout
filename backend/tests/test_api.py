import pytest
import pytest_asyncio

from app.models import Job as JobORM
from app.scraped import Job


@pytest_asyncio.fixture
async def sample_job(db):
    orm = JobORM(
        id="indeed-1",
        site="indeed",
        title="Python Contractor",
        company="Acme",
        location="Remote",
        job_url="https://indeed.com/job/1",
        description="Contract role.",
        job_type="contract",
        employment_type="1099",
        interval="yearly",
        min_amount=100000,
        max_amount=120000,
        currency="USD",
        is_remote=True,
        is_us=True,
    )
    db.add(orm)
    await db.commit()
    return orm


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_list_sources(client):
    response = await client.get("/api/v1/sources")
    assert response.status_code == 200
    sources = response.json()
    ids = {s["id"] for s in sources}
    assert "indeed" in ids
    assert "linkedin" in ids
    assert "glassdoor" in ids
    assert "careerjet" in ids
    assert "greenhouse" in ids
    assert "hackernews" in ids
    assert "apify" in ids
    assert all("configured" in source for source in sources)


async def test_search_rejects_unknown_source(client):
    response = await client.post("/api/v1/search", json={"query": "python", "sources": ["unknown"]})
    assert response.status_code == 400
    assert "Unknown job source" in response.json()["detail"]


async def test_get_job_stats(client, sample_job):
    response = await client.get("/api/v1/jobs/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["count"] == 1
    assert stats["last_scraped"] is not None


async def test_list_jobs(client, sample_job):
    response = await client.get("/api/v1/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Python Contractor"


async def test_list_jobs_with_source_filter(client, sample_job):
    response = await client.get("/api/v1/jobs?source=linkedin")
    assert response.status_code == 200
    assert len(response.json()) == 0

    response = await client.get("/api/v1/jobs?source=indeed")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_get_job(client, sample_job):
    response = await client.get(f"/api/v1/jobs/{sample_job.id}")
    assert response.status_code == 200
    assert response.json()["id"] == sample_job.id


async def test_get_job_not_found(client):
    response = await client.get("/api/v1/jobs/missing-id")
    assert response.status_code == 404


async def test_filter_jobs(client, sample_job):
    response = await client.post("/api/v1/jobs/filter", json={"employment_type": "1099"})
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = await client.post("/api/v1/jobs/filter", json={"employment_type": "w2"})
    assert response.status_code == 200
    assert len(response.json()) == 0


async def test_search_jobs(client, monkeypatch):
    from app.services import boards

    def fake_major(*args, **kwargs):
        return [
            Job(
                id="indeed-1",
                site="indeed",
                title="Python Contractor",
                company="Acme",
                location="Remote",
                job_url="https://indeed.com/job/1",
                description="Contract role.",
                job_type="contract",
                employment_type="1099",
                is_remote=True,
                is_us=True,
            )
        ]

    async def fake_builtin(source, *args, **kwargs):
        assert source == "remoteok"
        return [
            Job(
                id="remoteok-1",
                site="remoteok",
                title="Remote Python Dev",
                company="Beta",
                location="Remote",
                job_url="https://remoteok.com/job/1",
                description="Contractor.",
                job_type="contract",
                is_remote=True,
                is_us=True,
            )
        ]

    # run_scrape resolves these off the boards module at call time.
    monkeypatch.setattr(boards, "scrape_major_boards", fake_major)
    monkeypatch.setattr(boards, "scrape_builtin_source", fake_builtin)

    response = await client.post(
        "/api/v1/search",
        json={
            "query": "python",
            "location": "United States",
            "is_remote": True,
            "job_type": "contract",
            "results_wanted": 5,
            "sources": ["indeed", "remoteok"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["scraped"] == 2
    assert data["saved"] == 2

    health = (await client.get("/api/v1/scrape/health")).json()
    health_sources = {source["source"]: source for source in health["sources"]}
    assert {"indeed", "remoteok"}.issubset(health_sources)
    assert health_sources["indeed"]["stored_jobs"] == 1
    assert "pay_coverage" in health_sources["indeed"]

    response = await client.get("/api/v1/jobs?source=remoteok")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1
    assert jobs[0]["site"] == "remoteok"


async def test_list_jobs_sort_by_pay(client, db):
    jobs = [
        JobORM(id="low-pay", site="indeed", title="Low Pay", company="Acme", is_remote=True,
               is_us=True, job_type="contract", min_amount=50000, max_amount=60000),
        JobORM(id="high-pay", site="indeed", title="High Pay", company="Beta", is_remote=True,
               is_us=True, job_type="contract", min_amount=150000, max_amount=200000),
        JobORM(id="mid-pay", site="indeed", title="Mid Pay", company="Gamma", is_remote=True,
               is_us=True, job_type="contract", min_amount=100000, max_amount=120000),
    ]
    for job in jobs:
        db.add(job)
    await db.commit()

    data = (await client.get("/api/v1/jobs?sort_by=max_pay&sort_order=desc")).json()
    assert [job["title"] for job in data] == ["High Pay", "Mid Pay", "Low Pay"]

    data = (await client.get("/api/v1/jobs?sort_by=min_pay&sort_order=asc")).json()
    assert [job["title"] for job in data] == ["Low Pay", "Mid Pay", "High Pay"]


async def test_list_jobs_sort_by_relevance(client, db):
    jobs = [
        JobORM(id="title-match", site="indeed", title="Python Contractor", company="A",
               description="Contract role.", is_remote=True, is_us=True, job_type="contract"),
        JobORM(id="company-match", site="indeed", title="Other Role", company="Python Staffing",
               description="Contract role.", is_remote=True, is_us=True, job_type="contract"),
        JobORM(id="description-match", site="indeed", title="Other Role", company="B",
               description="Looking for python experience.", is_remote=True, is_us=True, job_type="contract"),
    ]
    for job in jobs:
        db.add(job)
    await db.commit()

    data = (await client.get("/api/v1/jobs?q=python&sort_by=relevance&sort_order=desc")).json()
    assert data[0]["title"] == "Python Contractor"
    assert data[1]["company"] == "Python Staffing"
    assert data[2]["description"] == "Looking for python experience."


async def test_list_jobs_negative_keywords(client, db):
    jobs = [
        JobORM(id="senior-python", site="indeed", title="Senior Python Contractor", company="Acme",
               description="Need senior Python help.", is_remote=True, is_us=True, job_type="contract"),
        JobORM(id="junior-python", site="indeed", title="Junior Python Contractor", company="Beta",
               description="Need junior Python help.", is_remote=True, is_us=True, job_type="contract"),
    ]
    for job in jobs:
        db.add(job)
    await db.commit()

    data = (await client.get("/api/v1/jobs?q=python -senior")).json()
    assert len(data) == 1
    assert data[0]["id"] == "junior-python"
