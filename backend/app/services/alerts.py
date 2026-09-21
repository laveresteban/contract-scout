"""Email alerts for saved searches.

`evaluate_alerts` finds alert-enabled saved searches that are due, matches new
jobs scraped since the last alert, and emails the owning user. When SMTP is not
configured the message is logged instead so the flow still works locally.

Saved searches are owned by a string identity (`current_identity`): an
authenticated search stores ``user:<id>`` and can be emailed; an anonymous
``ip:<addr>`` search has no address, so we advance its watermark but send
nothing.
"""
import asyncio
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import config
from ..jobquery import apply_filters, apply_sort
from ..models import Job as JobORM
from ..models import SavedSearch, UserORM
from ..scraped import JobFilterRequest

logger = logging.getLogger(__name__)

_FREQUENCY_DELTA = {
    "immediate": timedelta(0),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def smtp_configured() -> bool:
    return bool(config.SMTP_HOST)


def _send_sync(to: str, subject: str, body: str) -> bool:
    if not smtp_configured():
        logger.info("[email:log-only] To: %s | %s\n%s", to, subject, body)
        return True
    msg = EmailMessage()
    msg["From"] = config.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
            if config.SMTP_USE_TLS:
                server.starttls()
            if config.SMTP_USER:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD or "")
            server.send_message(msg)
        return True
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("Failed to send alert email to %s: %s", to, exc)
        return False


async def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email via SMTP (off-thread), or log it when SMTP is unconfigured."""
    if not to:
        return False
    return await asyncio.to_thread(_send_sync, to, subject, body)


def _due(search: SavedSearch, now: datetime) -> bool:
    if not search.alert_enabled:
        return False
    last = _aware(search.last_alerted_at)
    if last is None:
        return True
    delta = _FREQUENCY_DELTA.get(search.alert_frequency or "daily", timedelta(days=1))
    return now - last >= delta


def _format_jobs(jobs: list[JobORM]) -> str:
    lines = []
    for job in jobs:
        pay = ""
        if job.min_amount or job.max_amount:
            pay = f" | {job.min_amount or ''}-{job.max_amount or ''} {job.currency or ''} {job.interval or ''}".rstrip()
        url = job.job_url or job.job_url_direct or ""
        lines.append(f"- {job.title} @ {job.company}{pay}\n  {url}")
    return "\n".join(lines)


async def _email_for(db: AsyncSession, search: SavedSearch) -> str | None:
    """Resolve a saved search to a delivery address, if we have one.

    An explicit ``alert_email`` wins (and is the only way an anonymous ``ip:``
    search can be reached); otherwise an authenticated ``user:<id>`` search falls
    back to the account email.
    """
    if search.alert_email:
        return search.alert_email
    user_id = search.user_id
    if not user_id or not user_id.startswith("user:"):
        return None
    try:
        uid = int(user_id.split(":", 1)[1])
    except (ValueError, IndexError):
        return None
    user = await db.get(UserORM, uid)
    return user.email if user else None


async def evaluate_alerts(db: AsyncSession) -> int:
    """Send due alerts. Returns the number of emails sent."""
    now = _utcnow()
    searches = (
        (await db.execute(select(SavedSearch).where(SavedSearch.alert_enabled.is_(True))))
        .scalars()
        .all()
    )
    sent = 0
    for search in searches:
        if not _due(search, now):
            continue
        try:
            filters = JobFilterRequest.model_validate(dict(search.filters or {}))
        except Exception:
            filters = JobFilterRequest()
        since = _aware(search.last_alerted_at) or (now - timedelta(days=7))
        stmt = select(JobORM).where(JobORM.date_scraped > since)
        stmt = apply_filters(stmt, filters)
        stmt = apply_sort(stmt, filters).limit(50)
        jobs = (await db.execute(stmt)).scalars().all()

        email = await _email_for(db, search)
        if jobs and email:
            subject = f'Contract Scout: {len(jobs)} new match(es) for "{search.name}"'
            body = (
                f'New jobs matching your saved search "{search.name}":\n\n'
                f"{_format_jobs(jobs)}\n"
            )
            if await send_email(email, subject, body):
                sent += 1
        # Advance the watermark even with no matches so we don't re-scan forever.
        search.last_alerted_at = now
        await db.commit()
    return sent
