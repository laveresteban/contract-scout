"""Background re-verification: re-check active jobs whose verdict is stale or
missing, oldest first, bounded per tick."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Job, VerifyStatus
from app.services import verify as verify_service


def _job(jid, **over):
    base = dict(id=jid, title="Engineer", company="Acme", is_remote=True, is_us=True,
                is_active=True, job_url=f"https://example.com/{jid}")
    base.update(over)
    return Job(**base)


async def _seed(db, jobs):
    for j in jobs:
        db.add(j)
    await db.commit()


async def test_reverify_stale_selects_missing_and_old_only(db, monkeypatch):
    now = datetime.now(timezone.utc)
    await _seed(db, [
        _job("never", verify_status=VerifyStatus.unverified.value, verify_checked_at=None),
        _job("old", verify_status=VerifyStatus.live.value,
             verify_checked_at=now - timedelta(hours=48)),
        _job("fresh", verify_status=VerifyStatus.live.value,
             verify_checked_at=now - timedelta(hours=1)),
        _job("inactive", is_active=False, verify_status=VerifyStatus.unverified.value),
    ])

    checked = []

    async def _fake_verify(job, *, force=False, client=None):
        checked.append(job.id)
        job.verify_status = VerifyStatus.live.value
        job.verify_checked_at = datetime.now(timezone.utc)
        return {"status": VerifyStatus.live.value}

    monkeypatch.setattr(verify_service, "verify_job", _fake_verify)

    count = await verify_service.reverify_stale(db, limit=10, stale_hours=24)

    assert count == 2
    assert set(checked) == {"never", "old"}  # not fresh, not inactive


async def test_reverify_stale_respects_limit_oldest_first(db, monkeypatch):
    now = datetime.now(timezone.utc)
    await _seed(db, [
        _job("older", verify_status=VerifyStatus.live.value,
             verify_checked_at=now - timedelta(hours=72)),
        _job("newer-stale", verify_status=VerifyStatus.live.value,
             verify_checked_at=now - timedelta(hours=30)),
    ])

    checked = []

    async def _fake_verify(job, *, force=False, client=None):
        checked.append(job.id)
        job.verify_checked_at = datetime.now(timezone.utc)
        return {"status": VerifyStatus.live.value}

    monkeypatch.setattr(verify_service, "verify_job", _fake_verify)

    count = await verify_service.reverify_stale(db, limit=1, stale_hours=24)
    assert count == 1
    assert checked == ["older"]  # oldest verdict re-checked first
