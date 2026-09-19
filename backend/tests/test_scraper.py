import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime

import pandas as pd
import pytest

import app.services.boards as scraper_module
from app.services.boards import (
    ALL_SOURCES,
    _build_apify_job,
    _build_dice_job,
    _build_himalayas_job,
    _build_jobicy_job,
    _build_remoteok_job,
    _build_remotive_job,
    _build_weworkremotely_job,
    _detect_employment_type,
    _dice_detail,
    _extract_dice_joblist,
    _infer_interval_from_amounts,
    _map_dice_job_type,
    _map_himalayas_employment_type,
    _matches_job_request,
    _normalize_location,
    _parse_amount,
    _parse_iso_date,
    _parse_k_amount,
    _parse_pay_from_text,
    _parse_remotive_salary,
    _row_to_job,
    _scrape_dice,
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

    def test_detect_employment_type_w2_contract(self):
        assert _detect_employment_type("This is a remote W2 contract opportunity", "") == "w2"

    def test_detect_employment_type_w2_only_no_c2c(self):
        # "No C2C" phrasing implies a W2 engagement and must not be read as C2C.
        assert _detect_employment_type("W2 only, no C2C or 1099", "") == "w2"

    def test_detect_employment_type_c2c_still_wins_when_offered(self):
        assert _detect_employment_type("Open to C2C candidates", "") == "c2c"

    def test_text_indicates_contract_role(self):
        assert _text_indicates_contract_role("Freelance software engineer contract")
        assert not _text_indicates_contract_role("Full-time employee with benefits")

    @pytest.mark.parametrize(
        "text",
        [
            "6 month contract",
            "12-month assignment",
            "contract-to-hire opportunity",
            "temporary role",
            "consulting engagement",
        ],
    )
    def test_text_indicates_fixed_term_contract_role(self, text):
        assert _text_indicates_contract_role(text)

    @pytest.mark.parametrize(
        "text",
        [
            "Full-time employee supporting a federal contract",
            "Position contingent upon contract award with full employee benefits",
            "Implement Comply-to-Connect (C2C) network controls",
        ],
    )
    def test_text_does_not_treat_customer_contract_context_as_contract_role(self, text):
        assert not _text_indicates_contract_role(text)

    def test_detect_employment_type_negated_corp_to_corp_and_1099(self):
        text = "Direct-hire W-2 position. No Corp-2-Corp or 1099 contractors."
        assert _detect_employment_type(text, "AI Engineer") == "w2"

    def test_detect_employment_type_trailing_negation(self):
        text = "We ask Corp-to-Corp or 1099 candidates to refrain from applying."
        assert _detect_employment_type(text, "Engineer") == "w2"

    def test_regular_role_does_not_treat_compliance_c2c_as_engagement(self):
        from app.scraped import Job

        job = Job(
            id="regular",
            site="indeed",
            title="Systems Architect",
            company="Acme",
            description="Requisition Type:**Regular**. Implement Comply\\-to\\-Connect (C2C) controls.",
            job_type="contract",
            employment_type="c2c",
        )
        assert job.job_type == "fulltime"
        assert job.employment_type == "w2"

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

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Pay rate: $85-$105/hr", (85, 105, "hourly")),
            ("Rate: 85 to 105 per hour", (85, 105, "hourly")),
            ("Compensation: $85.50 - $105.75 hourly", (85.5, 105.75, "hourly")),
            ("up to $110/hr", (None, 110, "hourly")),
            ("from $75/hour", (75, None, "hourly")),
            ("$80-100 an hour", (80, 100, "hourly")),
            ("Rate: \\$60 \\- \\$65 per hour", (60, 65, "hourly")),
        ],
    )
    def test_parse_pay_from_text_real_world_hourly_formats(self, text, expected):
        assert _parse_pay_from_text(text) == expected

    def test_parse_pay_ignores_unqualified_dollar_value(self):
        assert _parse_pay_from_text("Includes a $1,000 equipment allowance") == (None, None, None)

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
        from app.scraped import Job

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
        assert _matches_job_request(job, "contract", "1099")
        assert not _matches_job_request(job, "contract", "w2")
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
        terms = []

        def fake_scrape_jobs(**kwargs):
            terms.append(kwargs["search_term"])
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

        import app.services.boards as scraper

        monkeypatch.setattr(scraper, "scrape_jobs", fake_scrape_jobs)
        jobs = scrape_major_boards("python", job_type="contract", results_wanted=5)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Contractor"
        assert jobs[0].site == "indeed"
        assert any("contract" in term.lower() for term in terms)


class TestDice:
    def _dice_item(self, **overrides):
        item = {
            "id": "abc123",
            "guid": "guid-1",
            "detailsPageUrl": "https://www.dice.com/job-detail/guid-1",
            "companyName": "Dexian DISYS",
            "employmentType": "Contract",
            "employerType": "Recruiter",
            "postedDate": "2026-09-02T16:10:22Z",
            "title": "Senior Mainframe Software Engineer",
            "summary": "This is a remote W2 contract opportunity with potential for extension.",
            "isRemote": True,
            "workplaceTypes": ["Remote"],
        }
        item.update(overrides)
        return item

    def test_map_dice_job_type(self):
        assert _map_dice_job_type("Contract") == "contract"
        assert _map_dice_job_type("Full-time") == "fulltime"
        assert _map_dice_job_type("Third Party") == "contract"
        assert _map_dice_job_type(None) is None

    def test_build_dice_job_w2_contract(self):
        job = _build_dice_job(self._dice_item(), job_type="contract")
        assert job
        assert job.site == "dice"
        assert job.title == "Senior Mainframe Software Engineer"
        assert job.company == "Dexian DISYS"
        assert job.job_type == "contract"
        assert job.employment_type == "w2"  # detected from "W2 contract"
        assert job.is_remote
        assert job.is_us
        assert job.id.startswith("dice-")
        assert job.job_url == "https://www.dice.com/job-detail/guid-1"

    def test_build_dice_job_third_party_is_c2c(self):
        item = self._dice_item(employmentType="Third Party", summary="Great opportunity for an engineer.")
        job = _build_dice_job(item, job_type="contract")
        assert job
        assert job.employment_type == "c2c"

    def test_build_dice_job_filters_by_employment_type(self):
        # A full-time posting should be dropped when contract is requested.
        item = self._dice_item(
            employmentType="Full-time",
            summary="Permanent full-time employee role with benefits.",
        )
        assert _build_dice_job(item, job_type="contract") is None

    def test_extract_dice_joblist_from_rsc_chunk(self):
        import json

        payload = ["$", "$L32", None, {"jobList": {"data": [self._dice_item()]}}]
        chunk = "12:" + json.dumps(payload)
        # Re-escape as it appears inside self.__next_f.push([1,"..."]).
        escaped = json.dumps(chunk)[1:-1]
        html = f'<script>self.__next_f.push([1,"{escaped}"])</script>'
        items = _extract_dice_joblist(html)
        assert len(items) == 1
        assert items[0]["title"] == "Senior Mainframe Software Engineer"

    def test_extract_dice_joblist_missing_returns_empty(self):
        assert _extract_dice_joblist("<html>no data here</html>") == []

    def test_extract_dice_detail_compensation(self):
        html = '''
        <script type="application/ld+json">
        {"@type":"JobPosting","description":"<p>Six month W2 contract.</p>","baseSalary":{"@type":"MonetaryAmount","currency":"USD","value":{"minValue":85,"maxValue":105,"unitText":"HOUR"}}}
        </script>
        '''
        description, minimum, maximum, currency, interval = _dice_detail(html)
        assert description == "Six month W2 contract."
        assert (minimum, maximum, currency, interval) == (85, 105, "USD", "HOUR")


class TestHimalayas:
    def _item(self, **overrides):
        item = {
            "title": "Senior Backend Engineer (Contract)",
            "companyName": "Acme Labs",
            "employmentType": "Contract",
            "minSalary": 90,
            "maxSalary": 130,
            "salaryPeriod": "hourly",
            "currency": "USD",
            "locationRestrictions": ["United States"],
            "categories": ["Backend", "Python"],
            "description": "<p>Independent contractor role. 1099 engagement.</p>",
            "excerpt": "Contract backend role.",
            "pubDate": 1788523038,
            "applicationLink": "https://himalayas.app/companies/acme/jobs/senior-backend-engineer",
            "guid": "https://himalayas.app/companies/acme/jobs/senior-backend-engineer",
        }
        item.update(overrides)
        return item

    def test_map_himalayas_employment_type(self):
        assert _map_himalayas_employment_type("Contract") == "contract"
        assert _map_himalayas_employment_type("Freelance") == "contract"
        assert _map_himalayas_employment_type("Full Time") == "fulltime"
        assert _map_himalayas_employment_type("Part Time") == "parttime"
        assert _map_himalayas_employment_type("Internship") == "internship"
        assert _map_himalayas_employment_type(None) is None

    def test_build_himalayas_contract_job(self):
        job = _build_himalayas_job(self._item(), job_type="contract")
        assert job
        assert job.site == "himalayas"
        assert job.title == "Senior Backend Engineer (Contract)"
        assert job.company == "Acme Labs"
        assert job.job_type == "contract"
        assert job.employment_type == "1099"  # detected from description text
        assert job.is_remote
        assert job.is_us
        assert job.interval == "hourly"
        assert job.min_amount == 90
        assert job.max_amount == 130
        assert job.id.startswith("himalayas-")
        assert job.job_url.endswith("/senior-backend-engineer")

    def test_build_himalayas_annual_interval(self):
        job = _build_himalayas_job(
            self._item(salaryPeriod="annual", minSalary=120000, maxSalary=160000)
        )
        assert job
        assert job.interval == "yearly"

    def test_build_himalayas_worldwide_is_us_eligible(self):
        job = _build_himalayas_job(self._item(locationRestrictions=[]))
        assert job
        assert job.is_us

    def test_build_himalayas_europe_only_not_us(self):
        job = _build_himalayas_job(self._item(locationRestrictions=["Europe"]))
        assert job
        assert job.is_remote
        assert not job.is_us

    def test_build_himalayas_fulltime_dropped_when_contract_requested(self):
        item = self._item(
            title="Staff Engineer",
            employmentType="Full Time",
            description="<p>Permanent full-time employee role with 401(k) and benefits.</p>",
            excerpt="Full-time staff role.",
        )
        assert _build_himalayas_job(item, job_type="contract") is None


class TestDiceBrowserFallback:
    def _dice_html(self):
        import json

        item = {
            "id": "abc123",
            "detailsPageUrl": "https://www.dice.com/job-detail/guid-1",
            "companyName": "Dexian",
            "employmentType": "Contract",
            "postedDate": "2026-09-02T16:10:22Z",
            "title": "Remote Contract Software Engineer",
            "summary": "Remote W2 contract role for a software engineer.",
            "isRemote": True,
            "workplaceTypes": ["Remote"],
        }
        payload = ["$", "$L32", None, {"jobList": {"data": [item]}}]
        chunk = "12:" + json.dumps(payload)
        escaped = json.dumps(chunk)[1:-1]
        return f'<script>self.__next_f.push([1,"{escaped}"])</script>'

    class _EmptyClient:
        """httpx-like client that always returns a page with no job data."""

        async def get(self, url, **kwargs):
            class _Resp:
                text = "<html>blocked</html>"

                def raise_for_status(self):
                    return None

            return _Resp()

    @pytest.mark.asyncio
    async def test_dice_falls_back_to_browser_render(self, monkeypatch):
        rendered = self._dice_html()

        async def fake_fetch_rendered(url, **kwargs):
            return rendered

        monkeypatch.setattr(scraper_module, "fetch_rendered", fake_fetch_rendered)

        jobs = await _scrape_dice(
            self._EmptyClient(),
            "software engineer",
            job_type="contract",
            employment_type=None,
            results_wanted=5,
        )
        assert len(jobs) == 1
        assert jobs[0].site == "dice"
        assert jobs[0].title == "Remote Contract Software Engineer"

    @pytest.mark.asyncio
    async def test_dice_no_browser_when_unavailable(self, monkeypatch):
        async def fake_fetch_rendered(url, **kwargs):
            return None  # Playwright unavailable / render failed.

        monkeypatch.setattr(scraper_module, "fetch_rendered", fake_fetch_rendered)

        jobs = await _scrape_dice(
            self._EmptyClient(),
            "software engineer",
            job_type="contract",
            employment_type=None,
            results_wanted=5,
        )
        assert jobs == []


class TestSources:
    def test_all_sources_includes_apify(self):
        assert "apify" in ALL_SOURCES

    def test_all_sources_includes_dice(self):
        assert "dice" in ALL_SOURCES

    def test_all_sources_includes_himalayas(self):
        assert "himalayas" in ALL_SOURCES
