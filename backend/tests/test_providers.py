import pytest

from app import config
from app.services.providers import PROVIDERS, ProviderRequest, _job, _wanted, adzuna, jooble, upwork


def test_provider_registry_contains_all_new_sources():
    assert set(PROVIDERS) == {
        "careerjet",
        "workable",
        "greenhouse",
        "lever",
        "ashby",
        "smartrecruiters",
        "recruitee",
        "jooble",
        "adzuna",
        "hackernews",
        "usajobs",
        "upwork",
    }


def test_provider_job_normalization():
    job = _job(
        "example",
        {"salary_min": 70, "salary_max": 90, "salary_currency": "usd", "salaryInterval": "hour"},
        title="Python Contractor",
        company="Acme",
        location="Remote, United States",
        url="https://example.com/jobs/1",
        description="Remote 1099 contract role",
        external_id="1",
    )
    assert job.id == "example-1"
    assert job.job_type == "contract"
    assert job.employment_type == "1099"
    assert job.is_remote
    assert job.is_us
    assert job.min_amount == 70
    assert job.max_amount == 90
    assert job.interval == "hourly"
    assert job.currency == "USD"


def test_provider_request_filtering():
    job = _job(
        "example",
        {},
        title="Python Contractor",
        company="Acme",
        location="Remote",
        description="Freelance Python work",
        external_id="1",
    )
    assert _wanted(job, ProviderRequest(query="python", job_type="contract"))
    assert not _wanted(job, ProviderRequest(query="java", job_type="contract"))
    assert not _wanted(job, ProviderRequest(query="python", employment_type="w2"))


@pytest.mark.asyncio
async def test_keyed_providers_skip_when_unconfigured(monkeypatch):
    monkeypatch.setattr(config, "JOOBLE_API_KEY", None)
    monkeypatch.setattr(config, "ADZUNA_APP_ID", None)
    monkeypatch.setattr(config, "ADZUNA_APP_KEY", None)
    monkeypatch.setattr(config, "UPWORK_API_TOKEN", None)
    request = ProviderRequest(query="python")
    assert await jooble(request) == []
    assert await adzuna(request) == []
    assert await upwork(request) == []
