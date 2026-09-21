import re
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import VerifyStatus


def _as_utc(value: datetime | None) -> datetime | None:
    # SQLite loses tzinfo, so naive datetimes come back from the DB unmarked.
    # Assume UTC (that's what we store) so they serialize with a 'Z'/offset and
    # the frontend doesn't misread them as local time.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class JobOut(BaseModel):
    """Read model — mirrors the fields the frontend renders."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    site: str | None = None
    job_url: str | None = None
    job_url_direct: str | None = None
    is_remote: bool | None = None
    eligibility: str | None = None
    job_type: str | None = None
    employment_type: str | None = None
    date_posted: datetime | None = None
    date_scraped: datetime | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str | None = None
    interval: str | None = None
    normalized_min_yearly: float | None = None
    normalized_max_yearly: float | None = None
    verify_status: str | None = None
    verify_checked_at: datetime | None = None
    verify_http_status: int | None = None
    verify_detail: str | None = None

    _utc = field_validator("date_posted", "date_scraped", "verify_checked_at")(_as_utc)


class VerifyResult(BaseModel):
    """Response for a single job verification."""

    job_id: str
    status: VerifyStatus
    detail: str | None = None
    http_status: int | None = None
    checked_at: datetime | None = None
    cached: bool = False

    # Pay scraped from the live page during this check (may be unchanged).
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str | None = None
    interval: str | None = None
    normalized_min_yearly: float | None = None
    normalized_max_yearly: float | None = None

    _utc = field_validator("checked_at")(_as_utc)


class VerifyBatchIn(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=100)


class VerifyBatchOut(BaseModel):
    results: dict[str, VerifyResult]


# --- Saved searches ---------------------------------------------------------
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value: str | None) -> str | None:
    """Normalize a delivery address: blank → None; otherwise basic format check."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _EMAIL_RE.match(value):
        raise ValueError("alert_email is not a valid email address")
    return value


class SavedSearchIn(BaseModel):
    """Create payload — matches what the frontend `savedSearchApi.create` sends."""

    name: str = Field(min_length=1, max_length=200)
    filters: dict = Field(default_factory=dict)
    alert_enabled: bool = False
    alert_frequency: str = "daily"
    alert_email: str | None = None

    _norm_email = field_validator("alert_email")(_validate_email)


class SavedSearchPatch(BaseModel):
    """Partial update — every field optional (`savedSearchApi.update`)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    filters: dict | None = None
    alert_enabled: bool | None = None
    alert_frequency: str | None = None
    alert_email: str | None = None

    _norm_email = field_validator("alert_email")(_validate_email)


class SavedSearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    filters: dict = Field(default_factory=dict)
    alert_enabled: bool
    alert_frequency: str
    alert_email: str | None = None
    last_alerted_at: datetime | None = None
    last_scanned_at: datetime | None = None
    created_at: datetime | None = None
    # How many matches are still flagged new (filled by the router).
    new_count: int = 0

    _utc = field_validator("last_alerted_at", "last_scanned_at", "created_at")(_as_utc)


class SavedSearchMatchOut(BaseModel):
    """A matched job plus its match metadata."""

    model_config = ConfigDict(from_attributes=True)

    job: JobOut
    first_seen_at: datetime | None = None
    is_new: bool = False

    _utc = field_validator("first_seen_at")(_as_utc)


class ScanRunOut(BaseModel):
    """Result of a manual scan trigger."""

    saved_search_id: str
    scraped: int
    matched: int
    new: int
    ok: bool
    detail: str | None = None
