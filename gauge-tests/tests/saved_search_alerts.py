"""API-level checks for the saved-search alert_email field (no browser)."""

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from getgauge.python import step

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8001")
_state = {}


def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(
        f"{API_BASE}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req) as resp:
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else None)


@step("Create a saved search with alert email <email>")
def create_with_email(email):
    status, body = _req("POST", "/api/v1/prefs/saved-searches", {
        "name": "Gauge alert test",
        "filters": {"query": "engineer"},
        "alert_enabled": True,
        "alert_email": email,
    })
    assert status == 201, f"create failed: {status}"
    _state["id"] = body["id"]
    _state["created"] = body


@step("The saved search stores alert email <email>")
def assert_stored(email):
    assert _state["created"]["alert_email"] == email, _state["created"]


@step("Clearing the alert email removes it")
def clear_email():
    status, body = _req("PATCH", f"/api/v1/prefs/saved-searches/{_state['id']}",
                        {"alert_email": "  "})
    assert status == 200, f"patch failed: {status}"
    assert body["alert_email"] is None, body


@step("A malformed alert email is rejected")
def reject_malformed():
    try:
        _req("POST", "/api/v1/prefs/saved-searches", {
            "name": "bad", "filters": {}, "alert_email": "not-an-email",
        })
    except HTTPError as exc:
        assert exc.code == 422, f"expected 422, got {exc.code}"
    else:
        raise AssertionError("malformed alert_email was not rejected")


@step("Delete the saved search")
def cleanup():
    _req("DELETE", f"/api/v1/prefs/saved-searches/{_state['id']}")
