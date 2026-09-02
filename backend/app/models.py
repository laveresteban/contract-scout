from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, Boolean, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

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
    is_remote = Column(Boolean, index=True, default=False)
    is_us = Column(Boolean, index=True, default=False)
    date_posted = Column(DateTime)
    date_scraped = Column(DateTime, default=datetime.utcnow)
    raw_data = Column(Text)


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
    is_remote: bool = False
    is_us: bool = False
    date_posted: Optional[datetime] = None
    date_scraped: Optional[datetime] = None

    class Config:
        from_attributes = True


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
    pay_interval: Optional[str] = None
    source: Optional[str] = None
    company: Optional[str] = None
    sort_by: Optional[str] = Field(default="date_posted")
    sort_order: Optional[str] = Field(default="desc")
