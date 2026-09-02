import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Job, JobFilterRequest, JobORM, JobSearchRequest
from app.scraper import ALL_SOURCES, scrape_major_boards, scrape_remote_boards, save_jobs

SOURCE_LABELS = {
    "indeed": "Indeed",
    "linkedin": "LinkedIn",
    "zip_recruiter": "ZipRecruiter",
    "google": "Google",
    "remoteok": "RemoteOK",
    "weworkremotely": "We Work Remotely",
    "jobicy": "Jobicy",
    "remotive": "Remotive",
    "apify": "Apify",
}

logger = logging.getLogger(__name__)

router = APIRouter()


def _search_orm(query, filters: JobFilterRequest):
    if filters.query:
        like = f"%{filters.query}%"
        query = query.filter(
            or_(
                JobORM.title.ilike(like),
                JobORM.company.ilike(like),
                JobORM.description.ilike(like),
            )
        )
    if filters.is_remote is not None:
        query = query.filter(JobORM.is_remote == filters.is_remote)
    if filters.is_us is not None:
        query = query.filter(JobORM.is_us == filters.is_us)
    if filters.job_type:
        query = query.filter(JobORM.job_type.ilike(f"%{filters.job_type}%"))
    if filters.employment_type:
        query = query.filter(JobORM.employment_type.ilike(f"%{filters.employment_type}%"))
    if filters.min_pay is not None:
        query = query.filter(JobORM.max_amount >= filters.min_pay)
    if filters.max_pay is not None:
        query = query.filter(JobORM.min_amount <= filters.max_pay)
    if filters.pay_interval:
        query = query.filter(JobORM.interval.ilike(f"%{filters.pay_interval}%"))
    if filters.source:
        query = query.filter(JobORM.site.ilike(f"%{filters.source}%"))
    if filters.company:
        query = query.filter(JobORM.company.ilike(f"%{filters.company}%"))
    return query


@router.post("/search")
async def search_jobs(payload: JobSearchRequest, db: Session = Depends(get_db)):
    """Scrape and store jobs based on search criteria."""
    sources = payload.sources or ["indeed", "linkedin"]
    major_jobs = scrape_major_boards(
        search_term=payload.query,
        location=payload.location or "United States",
        is_remote=payload.is_remote,
        job_type=payload.job_type or "contract",
        employment_type=payload.employment_type,
        results_wanted=payload.results_wanted,
        sources=sources,
    )
    try:
        remote_jobs = await scrape_remote_boards(
            search_term=payload.query,
            job_type=payload.job_type or "contract",
            employment_type=payload.employment_type,
            results_wanted=payload.results_wanted,
        )
    except Exception as exc:
        logger.warning("Remote scraping failed during search, continuing with major boards: %s", exc)
        remote_jobs = []
    all_jobs = major_jobs + remote_jobs
    saved = save_jobs(all_jobs, db)
    return {"scraped": len(all_jobs), "saved": saved}


@router.get("/jobs", response_model=list[Job])
def list_jobs(
    q: str = Query(None, description="Search term"),
    is_remote: bool = Query(True),
    is_us: bool = Query(True),
    job_type: str = Query(None),
    employment_type: str = Query(None),
    min_pay: float = Query(None),
    max_pay: float = Query(None),
    pay_interval: str = Query(None),
    source: str = Query(None),
    company: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    filters = JobFilterRequest(
        query=q,
        is_remote=is_remote,
        is_us=is_us,
        job_type=job_type,
        employment_type=employment_type,
        min_pay=min_pay,
        max_pay=max_pay,
        pay_interval=pay_interval,
        source=source,
        company=company,
    )
    query = db.query(JobORM).order_by(JobORM.date_posted.desc().nullslast())
    query = _search_orm(query, filters)
    jobs = query.offset(offset).limit(limit).all()
    return [Job.model_validate(j) for j in jobs]


@router.post("/jobs/filter", response_model=list[Job])
def filter_jobs(payload: JobFilterRequest, db: Session = Depends(get_db)):
    query = db.query(JobORM).order_by(JobORM.date_posted.desc().nullslast())
    query = _search_orm(query, payload)
    jobs = query.limit(200).all()
    return [Job.model_validate(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(JobORM).filter(JobORM.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return Job.model_validate(job)


@router.get("/sources")
def list_sources():
    """Return the available job sources and their display labels."""
    return [{"id": s, "label": SOURCE_LABELS.get(s, s)} for s in ALL_SOURCES]


@router.delete("/jobs")
def clear_jobs(db: Session = Depends(get_db)):
    db.query(JobORM).delete()
    db.commit()
    return {"cleared": True}
