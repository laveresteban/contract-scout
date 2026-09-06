import json
import os
import re
from urllib.request import urlopen

from getgauge.python import step

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8001")
jobs = []
reported_total = 0


def normalize(value):
    text = re.sub(r"[^a-z0-9 ]+", " ", (value or "").lower())
    text = re.sub(r"\b(inc|llc|ltd|corp|co|group|technologies|technology|solutions|remote)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def duplicate_groups(values, key_for):
    groups = {}
    for value in values:
        groups.setdefault(key_for(value), []).append(value)
    return {key: matches for key, matches in groups.items() if len(matches) > 1}


@step("Fetch all active job results")
def fetch_all_active_job_results():
    global jobs, reported_total
    with urlopen(f"{API_BASE}/api/v1/jobs?limit=200&offset=0") as response:
        assert response.status == 200
        reported_total = int(response.headers["X-Total-Count"])
        jobs = json.load(response)
    assert jobs, "Expected at least one active job result"


@step("Every result has a unique id")
def assert_unique_ids():
    duplicates = duplicate_groups(jobs, lambda job: job["id"])
    assert not duplicates, f"Duplicate ids: {', '.join(duplicates)}"


@step("No results share a normalized company and title")
def assert_unique_company_titles():
    duplicates = duplicate_groups(jobs, lambda job: f"{normalize(job['company'])}|{normalize(job['title'])}")
    details = "\n".join(
        f"{key}: {', '.join('{}/{}'.format(job['site'], job['id']) for job in matches)}"
        for key, matches in duplicates.items()
    )
    assert not duplicates, f"Duplicate jobs:\n{details}"


@step("API total count matches the returned results")
def assert_total_count():
    assert reported_total == len(jobs)
