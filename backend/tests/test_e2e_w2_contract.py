import app.scraper as scraper_module


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _JobicyClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, **kwargs):
        return _Response(
            {
                "jobs": [
                    {
                        "id": "w2-over-90",
                        "jobTitle": "Python Platform Engineer",
                        "companyName": "Acme Staffing",
                        "jobGeo": "Remote, United States",
                        "jobDescription": "Six month W2 contract position. Pay rate: $92.50-$110/hr.",
                        "jobExcerpt": "Python W2 contract",
                        "jobIndustry": ["Python", "Software Engineering"],
                        "jobType": ["contract"],
                        "url": "https://example.com/jobs/w2-over-90",
                    },
                    {
                        "id": "w2-under-90",
                        "jobTitle": "Python Application Engineer",
                        "companyName": "Beta Staffing",
                        "jobGeo": "Remote, United States",
                        "jobDescription": "W2 contract role. Compensation: $70-$85 per hour.",
                        "jobExcerpt": "Python W2 contract",
                        "jobIndustry": ["Python"],
                        "jobType": ["contract"],
                        "url": "https://example.com/jobs/w2-under-90",
                    },
                    {
                        "id": "1099-over-90",
                        "jobTitle": "Python Data Engineer",
                        "companyName": "Gamma Consulting",
                        "jobGeo": "Remote, United States",
                        "jobDescription": "1099 contractor engagement paying $120/hour.",
                        "jobExcerpt": "Python 1099 contract",
                        "jobIndustry": ["Python"],
                        "jobType": ["contract"],
                        "url": "https://example.com/jobs/1099-over-90",
                    },
                ]
            }
        )


def test_w2_contract_search_returns_hourly_rate_at_or_above_90(client, monkeypatch):
    monkeypatch.setattr(scraper_module.httpx, "AsyncClient", _JobicyClient)

    scrape = client.post(
        "/api/v1/search",
        json={
            "query": "python engineer",
            "location": "United States",
            "is_remote": True,
            "job_type": "contract",
            "employment_type": "w2",
            "sources": ["jobicy"],
            "results_wanted": 25,
        },
    )
    assert scrape.status_code == 200
    assert scrape.json()["scraped"] == 2

    response = client.get(
        "/api/v1/jobs",
        params={
            "q": "python",
            "job_type": "contract",
            "employment_type": "w2",
            "pay_interval": "hourly",
            "min_pay": 90,
        },
    )
    assert response.status_code == 200
    jobs = response.json()
    assert jobs
    assert {job["id"] for job in jobs} == {"jobicy-w2-over-90"}
    for job in jobs:
        assert job["job_type"] == "contract"
        assert job["employment_type"] == "w2"
        assert job["interval"] == "hourly"
        rates = [rate for rate in (job["min_amount"], job["max_amount"]) if rate is not None]
        assert rates
        assert any(rate >= 90 for rate in rates)
