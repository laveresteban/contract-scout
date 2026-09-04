"""Email alerts for saved searches.

`evaluate_alerts` finds alert-enabled saved searches that are due, matches new
jobs scraped since the last alert, and emails the owning user. When SMTP is not
configured the message is logged instead so the flow still works locally.
"""
import logging
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app import config
from app.jobquery import apply_filters, apply_sort
from app.models import (
    JobFilterRequest,
    JobORM,
    SavedSearchORM,
    UserORM,
)

logger = logging.getLogger(__name__)

_FREQUENCY_DELTA = {
    "immediate": timedelta(0),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
}


def smtp_configured() -> bool:
    return bool(config.SMTP_HOST)


def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email via SMTP, or log it when SMTP is unconfigured."""
    if not to:
        return False
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


def _due(search: SavedSearchORM, now: datetime) -> bool:
    if not search.alert_enabled:
        return False
    if search.last_alerted_at is None:
        return True
    delta = _FREQUENCY_DELTA.get(search.alert_frequency or "daily", timedelta(days=1))
    return now - search.last_alerted_at >= delta


def _format_jobs(jobs: list[JobORM]) -> str:
    lines = []
    for job in jobs:
        pay = ""
        if job.min_amount or job.max_amount:
            pay = f" | {job.min_amount or ''}-{job.max_amount or ''} {job.currency or ''} {job.interval or ''}".rstrip()
        url = job.job_url or job.job_url_direct or ""
        lines.append(f"- {job.title} @ {job.company}{pay}\n  {url}")
    return "\n".join(lines)


def evaluate_alerts(db: Session) -> int:
    """Send due alerts. Returns the number of emails sent."""
    now = datetime.utcnow()
    searches = db.query(SavedSearchORM).filter(SavedSearchORM.alert_enabled.is_(True)).all()
    sent = 0
    for search in searches:
        if not _due(search, now):
            continue
        try:
            filters = JobFilterRequest.model_validate_json(search.filters or "{}")
        except Exception:
            filters = JobFilterRequest()
        since = search.last_alerted_at or (now - timedelta(days=7))
        query = db.query(JobORM).filter(JobORM.date_scraped > since)
        query = apply_filters(query, filters)
        query = apply_sort(query, filters)
        jobs = query.limit(50).all()

        user = db.query(UserORM).filter(UserORM.id == search.user_id).first()
        if jobs and user and user.email:
            subject = f"Contract Scout: {len(jobs)} new match(es) for \"{search.name}\""
            body = (
                f"New jobs matching your saved search \"{search.name}\":\n\n"
                f"{_format_jobs(jobs)}\n"
            )
            if send_email(user.email, subject, body):
                sent += 1
        # Advance the watermark even when there were no matches so we don't
        # re-scan the same window forever.
        search.last_alerted_at = now
        db.commit()
    return sent
