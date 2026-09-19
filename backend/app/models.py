from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VerifyStatus(str, Enum):
    live = "live"                # fetched OK, still looks like an open posting
    expired = "expired"          # 404/410 or "no longer accepting applications"
    unreachable = "unreachable"  # network/blocked/timeout — inconclusive
    unverified = "unverified"    # never checked


class Job(Base):
    __tablename__ = "jobs"

    # String ids because sources hand us their own opaque ids.
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # Core posting fields.
    site: Mapped[str | None] = mapped_column(String, index=True)
    title: Mapped[str | None] = mapped_column(String, index=True)
    company: Mapped[str | None] = mapped_column(String, index=True)
    location: Mapped[str | None] = mapped_column(String, index=True)
    job_url: Mapped[str | None] = mapped_column(String)
    job_url_direct: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)

    # Classification.
    job_type: Mapped[str | None] = mapped_column(String, index=True)        # fulltime/contract/…
    employment_type: Mapped[str | None] = mapped_column(String, index=True)  # w2/1099/c2c/…
    classification_source: Mapped[str | None] = mapped_column(String)
    classification_confidence: Mapped[str | None] = mapped_column(String)

    # Pay (raw + normalized to yearly/hourly USD for cross-source comparison).
    interval: Mapped[str | None] = mapped_column(String)
    min_amount: Mapped[float | None] = mapped_column(Float)
    max_amount: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String)
    normalized_min_yearly: Mapped[float | None] = mapped_column(Float, index=True)
    normalized_max_yearly: Mapped[float | None] = mapped_column(Float, index=True)
    normalized_min_hourly: Mapped[float | None] = mapped_column(Float, index=True)
    normalized_max_hourly: Mapped[float | None] = mapped_column(Float, index=True)
    pay_source: Mapped[str | None] = mapped_column(String)
    pay_confidence: Mapped[str | None] = mapped_column(String)
    pay_raw_text: Mapped[str | None] = mapped_column(Text)

    # Location / eligibility.
    is_remote: Mapped[bool | None] = mapped_column(Boolean, index=True, default=False)
    is_us: Mapped[bool | None] = mapped_column(Boolean, index=True, default=False)
    eligibility: Mapped[str | None] = mapped_column(String)

    # Freshness / dedup bookkeeping.
    quality_version: Mapped[int | None] = mapped_column(Integer, default=2)
    source_urls: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool | None] = mapped_column(Boolean, index=True, default=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=_utcnow)
    dedup_key: Mapped[str | None] = mapped_column(String, index=True)
    raw_data: Mapped[str | None] = mapped_column(Text)
    date_posted: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_scraped: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # --- Verification columns ------------------------------------------------
    verify_status: Mapped[str] = mapped_column(
        String, default=VerifyStatus.unverified.value, server_default=VerifyStatus.unverified.value
    )
    verify_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verify_http_status: Mapped[int | None] = mapped_column(Integer)
    verify_detail: Mapped[str | None] = mapped_column(String)


# ---------------------------------------------------------------------------
# Users + server-backed preferences
# ---------------------------------------------------------------------------
class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str | None] = mapped_column(String, index=True)      # google, github
    provider_id: Mapped[str | None] = mapped_column(String, index=True)
    email: Mapped[str | None] = mapped_column(String, index=True)
    name: Mapped[str | None] = mapped_column(String)
    avatar_url: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SavedJobORM(Base):
    __tablename__ = "saved_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    job_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class HiddenJobORM(Base):
    __tablename__ = "hidden_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    job_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ViewedJobORM(Base):
    __tablename__ = "viewed_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    job_id: Mapped[str] = mapped_column(String, index=True)
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ScrapeRunORM(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str | None] = mapped_column(String, index=True)  # major_boards, scheduled, …
    trigger: Mapped[str | None] = mapped_column(String)             # manual, scheduled
    status: Mapped[str | None] = mapped_column(String, index=True)  # success, error
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_saved: Mapped[int] = mapped_column(Integer, default=0)
    jobs_with_pay: Mapped[int] = mapped_column(Integer, default=0)
    hourly_jobs: Mapped[int] = mapped_column(Integer, default=0)
    contract_jobs: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# Saved searches + their background-scan results (async core feature)
# ---------------------------------------------------------------------------
class SavedSearch(Base):
    """A user's stored search plus its background-scan settings.

    Owner (`user_id`) comes from `current_identity`: the authenticated user id
    when a JWT is present, else the client IP, so anonymous callers still get a
    private, per-client set (the SPA also mirrors these to localStorage).
    """

    __tablename__ = "saved_searches"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    # The search params as sent by the frontend, stored as JSON so the scan can
    # replay them against the scraper.
    filters: Mapped[dict] = mapped_column(JSON, default=dict)

    # `alert_enabled` doubles as the background-scan switch for this search.
    alert_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    alert_frequency: Mapped[str] = mapped_column(String, default="daily", server_default="daily")
    last_alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # When the scheduler last ran this search (drives the "due" check).
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SavedSearchMatch(Base):
    """A job a scan matched to a saved search. `is_new` until the user sees it."""

    __tablename__ = "saved_search_matches"
    __table_args__ = (
        UniqueConstraint("saved_search_id", "job_id", name="uq_saved_search_job"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    saved_search_id: Mapped[str] = mapped_column(
        String, ForeignKey("saved_searches.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    is_new: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
