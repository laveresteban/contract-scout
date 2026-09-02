import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime

import pandas as pd
import pytest

from app.scraper import (
    ALL_SOURCES,
    _build_apify_job,
    _build_jobicy_job,
    _build_remoteok_job,
    _build_remotive_job,
    _build_weworkremotely_job,
    _detect_employment_type,
    _infer_interval_from_amounts,
    _matches_job_request,
    _normalize_location,
    _parse_amount,
    _parse_iso_date,
    _parse_k_amount,
    _parse_pay_from_text,
    _parse_remotive_salary,
    _row_to_job,
    _text_indicates_contract_role,
    scrape_major_boards,
)


class TestHelpers:
    def test_normalize_location_us_remote(self):
        is_remote, is_us = _normalize_location("United States, Remote")
        assert is_remote
        assert is_us

    def test_normalize_location_worldwide(self):
        is_remote, is_us = _normalize_location("Worldwide")
        assert is_remote
        assert is_us

    def test_normalize_location_europe_not_us(self):
        is_remote, is_us = _normalize_location("Europe")
        assert not is_us

    def test_normalize_location_india(self):
        is_remote, is_us = _normalize_location("Remote, India")
        assert is_remote
        assert not is_us

    def test_detect_employment_type_c2c(self):
        assert _detect_employment_type("Corp-to-corp opportunity", "") == "c2c"

    def test_detect_employment_type_1099(self):
        assert _detect_employment_type("We need a 1099 contractor", "") == "1099"

    def test_detect_employment_type_w2(self):
        assert _detect_employment_type("Full-time employee W2 position", "") == "w2"

    def test_text_indicates_contract_role(self):
        assert _text_indicates_contract_role("Freelance software engineer contract")
        assert not _text_indicates_contract_role("Full-time employee with benefits")

    def test_parse_pay_from_text_yearly(self):
        lo, hi, interval = _parse_pay_from_text("Salary $120,000 - $150,000 per year")
        assert lo == 120000
        assert hi == 150000
        assert interval == "yearly"

    def test_parse_pay_from_text_hourly(self):
        lo, hi, interval = _parse_pay_from_text("$75 - $95 per hour")
        assert lo == 75
        assert hi == 95
        assert interval == "hourly"

    def test_parse_remotive_salary_k_range(self):
        lo, hi, interval = _parse_remotive_salary("$120k - $230k")
        assert lo == 120000
        assert hi == 230000
        assert interval == "yearly"

    def test_parse_remotive_salary_hourly(self):
        lo, hi, interval = _parse_remotive_salary("$14/hour")
        assert lo == 14
        assert hi == 14
        assert interval == "hourly"

    def test_parse_k_amount(self):
        assert _parse_k_amount("120k") == 120000
        assert _parse_k_amount("85,000") == 85000

    def test_infer_interval_from_amounts(self):
        assert _infer_interval_from_amounts(50, 80) == "hourly"
        assert _infer_interval_from_amounts(5000, 8000) == "monthly"
        assert _infer_interval_from_amounts(100000, 150000) == "yearly"

    def test_parse_amount(self):
        assert _parse_amount(123.0) == 123.0
        assert _parse_amount(None) is None

    def test_parse_iso_date(self):
        parsed = _parse_iso_date("2026-08-01T12:00:00Z")
        assert parsed
        assert (parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute) == (2026, 8, 1, 12, 0)

    def test_matches_job_request(self):
        from app.models import Job

        job = Job(
            id="x",
            site="remoteok",
            title="Contract Python Engineer",
            company="Acme",
            job_type="contract",
            employment_type="1099",
            is_remote=True,
            is_us=True,
        )
        assert _matches_job_request(job, "contract", None)
        assert _matches_job_request(job, None, "1099")
        assert not _matches_job_request(job, "fulltime", None)


class TestJobBuilders:
    def test_build_remoteok_job(self):
        item = {
            "id": 12345,
            "position": "Senior Backend Engineer",
            "company": "Stripe",
            "location": "Remote, US",
            "description": "<p>We are looking for a contractor.</p>",
            "tags": ["full time", "backend"],
            "salary_min": 100000,
            "salary_max": 150000,
            "date": "2026-08-01",
            "url": "https://remoteok.com/job/12345",
        }
        job = _build_remoteok_job(item)
        assert job
        assert job.title == "Senior Backend Engineer"
        assert job.company == "Stripe"
        assert job.is_remote
        assert job.is_us
        assert job.job_type == "fulltime"

    def test_build_weworkremotely_job(self):
        xml = """
        <item>
            <title>Example Co : Software Engineer</title>
            <description><![CDATA[Contract role.]]></description>
            <link>https://weworkremotely.com/job/1</link>
            <pubDate>Mon, 01 Aug 2026 12:00:00 GMT</pubDate>
            <country>United States</country>
        </item>
        """
        item = ET.fromstring(xml)
        job = _build_weworkremotely_job(item)
        assert job
        assert job.title == "Software Engineer"
        assert job.company == "Example Co"
        assert job.is_remote
        assert job.is_us
        assert job.job_type == "contract"

    def test_build_jobicy_job(self):
        item = {
            "id": "abc",
            "jobTitle": "Data Engineer",
            "companyName": "Data Co",
            "jobGeo": "Worldwide",
            "jobDescription": "<p>Freelance data engineering project.</p>",
            "jobType": ["contract"],
            "salaryMin": 50,
            "salaryMax": 80,
            "salaryPeriod": "hourly",
            "salaryCurrency": "USD",
            "url": "https://jobicy.com/job/abc",
        }
        job = _build_jobicy_job(item)
        assert job
        assert job.title == "Data Engineer"
        assert job.job_type == "contract"
        assert job.employment_type == "contract"
        assert job.interval == "hourly"

    def test_build_remotive_job(self):
        item = {
            "id": 123,
            "title": "Frontend Developer",
            "company_name": "Remotive Inc",
            "candidate_required_location": "Worldwide",
            "description": "<p>Full-time employee.</p>",
            "job_type": "full_time",
            "salary": "$80k - $120k /year",
            "publication_date": "2026-08-01T12:00:00Z",
            "url": "https://remotive.com/job/123",
        }
        job = _build_remotive_job(item)
        assert job
        assert job.title == "Frontend Developer"
        assert job.job_type == "fulltime"
        assert job.employment_type == "w2"

    def test_build_apify_job(self):
        item = {
            "title": "Cloud Architect",
            "company": "Cloud Co",
            "location_restriction": "United States",
            "description": "<p>Contractor needed for 6 months.</p>",
            "employment_type": "Contractor",
            "salary_min": 150000,
            "salary_max": 180000,
            "salary_currency": "USD",
            "salary_unit": "YEAR",
            "posted_at": "2026-08-01 12:00:00+00",
            "url": "https://example.com/job/cloud",
        }
        job = _build_apify_job(item)
        assert job
        assert job.title == "Cloud Architect"
        assert job.job_type == "contract"
        assert job.employment_type == "contract"
        assert job.is_remote
        assert job.is_us
        assert job.interval == "yearly"


class TestRowToJob:
    def test_row_to_job_stable_id(self):
        row = pd.Series(
            {
                "id": "indeed-abc",
                "site": "indeed",
                "title": "Backend Engineer",
                "company": "Acme",
                "location": "United States, Remote",
                "job_url": "https://indeed.com/job/1",
                "description": "Contractor role.",
                "job_type": "contract",
                "interval": "yearly",
                "min_amount": 100000,
                "max_amount": 120000,
                "currency": "USD",
                "is_remote": True,
                "date_posted": "2026-08-01",
            }
        )
        job = _row_to_job(row)
        assert job.id == "indeed-abc"
        assert job.job_type == "contract"
        assert job.is_remote
        assert job.is_us

    def test_row_to_job_fallback_id_is_stable(self):
        row = pd.Series(
            {
                "site": "indeed",
                "title": "Backend Engineer",
                "company": "Acme",
                "location": "Remote",
                "job_url": "https://indeed.com/job/1",
                "description": "Contractor role.",
                "job_type": "fulltime",
                "is_remote": True,
                "date_posted": None,
            }
        )
        job = _row_to_job(row)
        expected = hashlib.md5(
            f"{row['title']}{row['company']}{row['job_url']}".encode()
        ).hexdigest()[:16]
        assert job.id == f"indeed-{expected}"


class TestScrapeMajorBoards:
    def test_scrape_major_boards_with_mock(self, monkeypatch):
        def fake_scrape_jobs(**kwargs):
            return pd.DataFrame(
                [
                    {
                        "id": "indeed-1",
                        "site": "indeed",
                        "title": "Python Contractor",
                        "company": "Acme",
                        "location": "Remote",
                        "job_url": "https://indeed.com/job/1",
                        "description": "Contract role.",
                        "job_type": "contract",
                        "interval": "yearly",
                        "min_amount": 100000,
                        "max_amount": 120000,
                        "currency": "USD",
                        "is_remote": True,
                        "date_posted": "2026-08-01",
                    }
                ]
            )

        import app.scraper as scraper

        monkeypatch.setattr(scraper, "scrape_jobs", fake_scrape_jobs)
        jobs = scrape_major_boards("python", job_type="contract", results_wanted=5)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Contractor"
        assert jobs[0].site == "indeed"


class TestSources:
    def test_all_sources_includes_apify(self):
        assert "apify" in ALL_SOURCES
