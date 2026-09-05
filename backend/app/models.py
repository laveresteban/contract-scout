from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, computed_field, model_validator
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, Boolean, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from app.config import DATABASE_URL
from app.extraction import employment_type_signal, extract_compensation, job_type_signal
from app.normalize import classify_eligibility, normalize_amount, normalize_hourly_amount

Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class JobORM(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    site = Column(String, index=True)
    title = Column(String, index=True)
    company = Column(String, index=True)
    location = Column(String, index=True)
    job_url = Column(String)
    job_url_direct = Column(String)
    description = Column(Text)
    job_type = Column(String, index=True)  # fulltime, parttime, contract, internship
    employment_type = Column(String, index=True)  # inferred: w2, 1099, c2c, etc.
    interval = Column(String)  # yearly, hourly, monthly
    min_amount = Column(Float)
    max_amount = Column(Float)
    currency = Column(String)
    # Pay normalized to approximate yearly USD so hourly contract rates and
    # yearly full-time salaries can be filtered and sorted on one scale.
    normalized_min_yearly = Column(Float, index=True)
    normalized_max_yearly = Column(Float, index=True)
    normalized_min_hourly = Column(Float, index=True)
    normalized_max_hourly = Column(Float, index=True)
    pay_source = Column(String)
    pay_confidence = Column(String)
    pay_raw_text = Column(Text)
    classification_source = Column(String)
    classification_confidence = Column(String)
    quality_version = Column(Integer, default=2)
    source_urls = Column(Text)
    is_active = Column(Boolean, index=True, default=True)
    last_seen = Column(DateTime, default=datetime.utcnow)
    is_remote = Column(Boolean, index=True, default=False)
    is_us = Column(Boolean, index=True, default=False)
    date_posted = Column(DateTime)
    date_scraped = Column(DateTime, default=datetime.utcnow)
    dedup_key = Column(String, index=True)  # cross-source semantic duplicate key
    raw_data = Column(Text)


class UserORM(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, index=True)  # google, github
    provider_id = Column(String, index=True)
    email = Column(String, index=True)
    name = Column(String)
    avatar_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class SavedJobORM(Base):
    __tablename__ = "saved_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    job_id = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class HiddenJobORM(Base):
    __tablename__ = "hidden_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    job_id = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ViewedJobORM(Base):
    __tablename__ = "viewed_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    job_id = Column(String, index=True)
    viewed_at = Column(DateTime, default=datetime.utcnow)


class SavedSearchORM(Base):
    __tablename__ = "saved_searches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String)
    filters = Column(Text)  # JSON blob of the filter payload
    alert_enabled = Column(Boolean, default=False)
    alert_frequency = Column(String, default="daily")  # daily, weekly, immediate
    last_alerted_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class ScrapeRunORM(Base):
    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, index=True)  # e.g. major_boards, remote_boards, scheduled
    trigger = Column(String)  # manual, scheduled
    status = Column(String, index=True)  # success, error
    jobs_found = Column(Integer, default=0)
    jobs_saved = Column(Integer, default=0)
    jobs_with_pay = Column(Integer, default=0)
    hourly_jobs = Column(Integer, default=0)
    contract_jobs = Column(Integer, default=0)
    duration_ms = Column(Integer)
    error = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)


class Job(BaseModel):
    id: str
    site: str
    title: str
    company: str
    location: Optional[str] = None
    job_url: Optional[str] = None
    job_url_direct: Optional[str] = None
    description: Optional[str] = None
    job_type: Optional[str] = None
    employment_type: Optional[str] = None
    interval: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    currency: Optional[str] = None
    pay_source: Optional[str] = None
    pay_confidence: Optional[str] = None
    pay_raw_text: Optional[str] = None
    classification_source: Optional[str] = None
    classification_confidence: Optional[str] = None
    quality_version: int = 2
    source_urls: Optional[str] = None
    is_active: bool = True
    last_seen: Optional[datetime] = None
    is_remote: bool = False
    is_us: bool = False
    date_posted: Optional[datetime] = None
    date_scraped: Optional[datetime] = None

    class Config:
        from_attributes = True

    @model_validator(mode="after")
    def infer_quality_fields(self):
        pay = extract_compensation(
            self.description,
            minimum=self.min_amount,
            maximum=self.max_amount,
            currency=self.currency,
            interval=self.interval,
        )
        if pay.minimum is not None or pay.maximum is not None:
            self.min_amount = pay.minimum
            self.max_amount = pay.maximum
            self.currency = pay.currency
            self.interval = pay.interval
            self.pay_source = self.pay_source or pay.source
            self.pay_confidence = self.pay_confidence or pay.confidence
            self.pay_raw_text = self.pay_raw_text or pay.raw_text
        employment_type, employment_source, employment_confidence = employment_type_signal(self.description, self.title)
        job_type, job_source, job_confidence = job_type_signal(self.description, self.title)
        if employment_type and (not self.employment_type or employment_confidence == "high"):
            self.employment_type = employment_type
        if job_type and (not self.job_type or job_confidence == "high"):
            self.job_type = job_type
        if job_type == "fulltime" and job_confidence == "high" and not employment_type:
            self.employment_type = "w2"
            employment_source = job_source
            employment_confidence = job_confidence
        if employment_confidence == "high" or job_confidence == "high":
            self.classification_source = employment_source or job_source
            self.classification_confidence = employment_confidence or job_confidence
        else:
            self.classification_source = self.classification_source or employment_source or job_source
            self.classification_confidence = self.classification_confidence or employment_confidence or job_confidence
        return self

    @computed_field
    @property
    def normalized_min_yearly(self) -> Optional[float]:
        return normalize_amount(self.min_amount, self.interval, self.currency)

    @computed_field
    @property
    def normalized_max_yearly(self) -> Optional[float]:
        return normalize_amount(self.max_amount, self.interval, self.currency)

    @computed_field
    @property
    def normalized_min_hourly(self) -> Optional[float]:
        return normalize_hourly_amount(self.min_amount, self.interval, self.currency)

    @computed_field
    @property
    def normalized_max_hourly(self) -> Optional[float]:
        return normalize_hourly_amount(self.max_amount, self.interval, self.currency)

    @computed_field
    @property
    def normalized_currency(self) -> str:
        return "USD"

    @computed_field
    @property
    def eligibility(self) -> str:
        return classify_eligibility(self.location, self.is_remote, self.is_us)


class JobSearchRequest(BaseModel):
    query: str = Field(default="software engineer")
    location: Optional[str] = Field(default="United States")
    is_remote: bool = Field(default=True)
    job_type: Optional[str] = Field(default="contract")
    min_pay: Optional[float] = None
    max_pay: Optional[float] = None
    pay_interval: Optional[str] = Field(default=None, description="hourly, yearly, monthly")
    employment_type: Optional[str] = Field(default=None, description="w2, 1099, c2c, any")
    sources: Optional[list[str]] = Field(default=None)
    results_wanted: int = Field(default=25, ge=1, le=100)


class JobFilterRequest(BaseModel):
    query: Optional[str] = None
    is_remote: Optional[bool] = None
    is_us: Optional[bool] = None
    job_type: Optional[str] = None
    employment_type: Optional[str] = None
    min_pay: Optional[float] = None
    max_pay: Optional[float] = None
    # Pay filters expressed as yearly-USD equivalents. These compare against the
    # normalized columns, so a $100/hr contract and a $200k/yr salary are ranked
    # on the same scale.
    min_yearly: Optional[float] = None
    max_yearly: Optional[float] = None
    pay_interval: Optional[str] = None
    source: Optional[str] = None
    company: Optional[str] = None
    sort_by: Optional[str] = Field(default="date_posted")
    sort_order: Optional[str] = Field(default="desc")


class JobStats(BaseModel):
    last_scraped: Optional[datetime] = None
    count: int
    by_source: dict[str, int] = Field(default_factory=dict)
    by_employment_type: dict[str, int] = Field(default_factory=dict)
    remote_count: int = 0
    us_count: int = 0


class User(BaseModel):
    id: int
    provider: str
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


class SavedSearch(BaseModel):
    id: int
    name: str
    filters: dict[str, Any] = Field(default_factory=dict)
    alert_enabled: bool = False
    alert_frequency: str = "daily"
    last_alerted_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SavedSearchCreate(BaseModel):
    name: str
    filters: dict[str, Any] = Field(default_factory=dict)
    alert_enabled: bool = False
    alert_frequency: str = "daily"


class SavedSearchUpdate(BaseModel):
    name: Optional[str] = None
    filters: Optional[dict[str, Any]] = None
    alert_enabled: Optional[bool] = None
    alert_frequency: Optional[str] = None


class ScrapeRun(BaseModel):
    id: int
    source: str
    trigger: Optional[str] = None
    status: str
    jobs_found: int = 0
    jobs_saved: int = 0
    jobs_with_pay: int = 0
    hourly_jobs: int = 0
    contract_jobs: int = 0
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SourceHealth(BaseModel):
    source: str
    last_status: Optional[str] = None
    last_run_at: Optional[datetime] = None
    last_duration_ms: Optional[int] = None
    last_jobs_found: int = 0
    last_error: Optional[str] = None
    stored_jobs: int = 0
    contract_jobs: int = 0
    jobs_with_pay: int = 0
    hourly_jobs: int = 0
    pay_coverage: float = 0
    hourly_coverage: float = 0


class ScrapeHealth(BaseModel):
    scheduler_enabled: bool = False
    interval_minutes: int = 0
    next_run_at: Optional[datetime] = None
    sources: list[SourceHealth] = Field(default_factory=list)
    recent_runs: list[ScrapeRun] = Field(default_factory=list)
