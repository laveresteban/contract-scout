"""API-level checks that the paginated jobs endpoint returns unique postings.

The identity comes from ``dedup_key`` (shared with the backend and the UI spec),
so this spec fails only when the server actually leaks a duplicate.
"""

import json
import os
import sys
from urllib.request import urlopen

from getgauge.python import step

sys.path.insert(0, os.path.dirname(__file__))  # make sibling modules importable
from dedup_key import dedup_key

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8001")
jobs = []
reported_total = 0


def _key(job):
    return dedup_key(
        title=job.get("title"),
        company=job.get("company"),
        location=job.get("location"),
        url=job.get("job_url_direct") or job.get("job_url"),
        job_id=job.get("id"),
    )


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
    duplicates = duplicate_groups(jobs, _key)
    details = "\n".join(
        f"{key}: {', '.join('{}/{}'.format(job['site'], job['id']) for job in matches)}"
        for key, matches in duplicates.items()
    )
    assert not duplicates, f"Duplicate jobs:\n{details}"


@step("API total count matches the returned results")
def assert_total_count():
    assert reported_total == len(jobs), (
        f"X-Total-Count {reported_total} != {len(jobs)} returned rows"
    )
