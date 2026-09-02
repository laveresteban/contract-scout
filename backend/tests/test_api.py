import pytest

from app.models import Job, JobORM


@pytest.fixture
def sample_job(db):
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
    db.commit()
    return orm


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_sources(client):
    response = client.get("/api/v1/sources")
    assert response.status_code == 200
    sources = response.json()
    ids = {s["id"] for s in sources}
    assert "indeed" in ids
    assert "linkedin" in ids
    assert "apify" in ids


def test_list_jobs(client, sample_job):
    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Python Contractor"


def test_list_jobs_with_source_filter(client, sample_job):
    response = client.get("/api/v1/jobs?source=linkedin")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 0

    response = client.get("/api/v1/jobs?source=indeed")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1


def test_get_job(client, sample_job):
    response = client.get(f"/api/v1/jobs/{sample_job.id}")
    assert response.status_code == 200
    assert response.json()["id"] == sample_job.id


def test_get_job_not_found(client):
    response = client.get("/api/v1/jobs/missing-id")
    assert response.status_code == 404


def test_filter_jobs(client, sample_job):
    response = client.post("/api/v1/jobs/filter", json={"employment_type": "1099"})
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1

    response = client.post("/api/v1/jobs/filter", json={"employment_type": "w2"})
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 0


def test_search_jobs(client, monkeypatch):
    from app import api as api_module
    from app import scraper

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

    async def fake_remote(*args, **kwargs):
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

    monkeypatch.setattr(api_module, "scrape_major_boards", fake_major)
    monkeypatch.setattr(api_module, "scrape_remote_boards", fake_remote)
    # Patch the scraper module too, in case other code paths reference it.
    monkeypatch.setattr(scraper, "scrape_major_boards", fake_major)
    monkeypatch.setattr(scraper, "scrape_remote_boards", fake_remote)

    response = client.post(
        "/api/v1/search",
        json={
            "query": "python",
            "location": "United States",
            "is_remote": True,
            "job_type": "contract",
            "results_wanted": 5,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["scraped"] == 2
    assert data["saved"] == 2

    response = client.get("/api/v1/jobs?source=remoteok")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1
    assert jobs[0]["site"] == "remoteok"
