"""Email alerts, including delivery for anonymous (ip:) saved searches that
carry an explicit alert_email."""

from datetime import datetime, timezone

import pytest

from app.models import Job as JobORM
from app.models import SavedSearch, UserORM
from app.services import alerts


async def _add_job(db, **over):
    base = dict(
        id="j1", title="Backend Engineer", company="Acme", description="x",
        is_remote=True, is_us=True, date_scraped=datetime.now(timezone.utc),
    )
    base.update(over)
    db.add(JobORM(**base))
    await db.commit()


# --- _email_for precedence -------------------------------------------------
async def test_email_for_uses_explicit_alert_email_for_ip_search(db):
    s = SavedSearch(id="s1", user_id="ip:1.2.3.4", name="n", filters={},
                    alert_email="anon@example.com")
    assert await alerts._email_for(db, s) == "anon@example.com"


async def test_email_for_prefers_explicit_over_account_email(db):
    db.add(UserORM(id=7, email="account@example.com"))
    await db.commit()
    s = SavedSearch(id="s2", user_id="user:7", name="n", filters={},
                    alert_email="override@example.com")
    assert await alerts._email_for(db, s) == "override@example.com"


async def test_email_for_falls_back_to_account_email(db):
    db.add(UserORM(id=8, email="account@example.com"))
    await db.commit()
    s = SavedSearch(id="s3", user_id="user:8", name="n", filters={})
    assert await alerts._email_for(db, s) == "account@example.com"


async def test_email_for_none_for_anonymous_without_address(db):
    s = SavedSearch(id="s4", user_id="ip:9.9.9.9", name="n", filters={})
    assert await alerts._email_for(db, s) is None


# --- evaluate_alerts end to end -------------------------------------------
async def test_evaluate_alerts_emails_anonymous_search_with_alert_email(db, monkeypatch):
    await _add_job(db)
    db.add(SavedSearch(
        id="s5", user_id="ip:1.2.3.4", name="Backend", filters={"query": "backend"},
        alert_enabled=True, alert_email="anon@example.com",
    ))
    await db.commit()

    captured = []

    async def _fake_send(to, subject, body):
        captured.append((to, subject))
        return True

    monkeypatch.setattr(alerts, "send_email", _fake_send)

    sent = await alerts.evaluate_alerts(db)
    assert sent == 1
    assert captured and captured[0][0] == "anon@example.com"
