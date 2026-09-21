"""API-level check for the manual background re-verification trigger."""

import json
import os
from urllib.request import Request, urlopen

from getgauge.python import step

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8001")
_state = {}


@step("Re-verify stale jobs with limit <limit> treating everything as stale")
def run_reverify(limit):
    # stale_hours=0 makes every active job eligible, so `checked` is exactly
    # min(limit, active jobs) regardless of what each source returns.
    url = f"{API_BASE}/api/v1/jobs/reverify-stale?limit={limit}&stale_hours=0"
    req = Request(url, data=b"", method="POST")
    with urlopen(req) as resp:
        assert resp.status == 200, resp.status
        _state["body"] = json.loads(resp.read())


@step("The re-verification checked <expected> jobs")
def assert_checked(expected):
    assert _state["body"].get("checked") == int(expected), _state["body"]
