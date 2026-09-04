import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import config, scheduler
from app.alerts import evaluate_alerts
from app.database import get_db
from app.jobquery import apply_filters, apply_sort
from app.models import (
    Job,
    JobFilterRequest,
    JobORM,
    JobSearchRequest,
    JobStats,
    ScrapeHealth,
    ScrapeRun,
    ScrapeRunORM,
    SourceHealth,
)
from app.scrape_service import run_scrape
from app.scraper import ALL_SOURCES

SOURCE_LABELS = {
    "indeed": "Indeed",
    "linkedin": "LinkedIn",
    "glassdoor": "Glassdoor",
    "zip_recruiter": "ZipRecruiter",
    "google": "Google",
    "remoteok": "RemoteOK",
    "weworkremotely": "We Work Remotely",
    "jobicy": "Jobicy",
    "remotive": "Remotive",
    "himalayas": "Himalayas",
    "dice": "Dice",
    "apify": "Apify",
    "careerjet": "Careerjet",
    "workable": "Workable",
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "smartrecruiters": "SmartRecruiters",
    "recruitee": "Recruitee",
    "jooble": "Jooble",
    "adzuna": "Adzuna",
    "hackernews": "Hacker News",
    "usajobs": "USAJOBS",
    "upwork": "Upwork",
}


def _source_configured(source: str) -> bool:
    requirements = {
        "apify": bool(config.APIFY_API_TOKEN),
        "careerjet": bool(config.CAREERJET_API_KEY),
        "greenhouse": bool(config.GREENHOUSE_BOARDS),
        "lever": bool(config.LEVER_BOARDS),
        "ashby": bool(config.ASHBY_BOARDS),
        "smartrecruiters": bool(config.SMARTRECRUITERS_BOARDS),
        "recruitee": bool(config.RECRUITEE_BOARDS),
        "jooble": bool(config.JOOBLE_API_KEY),
        "adzuna": bool(config.ADZUNA_APP_ID and config.ADZUNA_APP_KEY),
        "usajobs": bool(config.USAJOBS_API_KEY and config.USAJOBS_EMAIL),
        "upwork": bool(config.UPWORK_API_TOKEN and config.UPWORK_GRAPHQL_URL),
    }
    return requirements.get(source, True)


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/search")
async def search_jobs(payload: JobSearchRequest, request: Request, db: Session = Depends(get_db)):
    """Scrape and store jobs based on search criteria."""
    try:
        return await run_scrape(
            db,
            query=payload.query,
            location=payload.location or "United States",
            is_remote=payload.is_remote,
            job_type=payload.job_type or "contract",
            employment_type=payload.employment_type,
            results_wanted=payload.results_wanted,
            sources=payload.sources,
            trigger="manual",
            user_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            referer=request.headers.get("referer") or config.FRONTEND_URL,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs", response_model=list[Job])
def list_jobs(
    response: Response,
    q: str = Query(None, description="Search term"),
    is_remote: bool = Query(True),
    is_us: bool = Query(True),
    job_type: str = Query(None),
    employment_type: str = Query(None),
    min_pay: float = Query(None),
    max_pay: float = Query(None),
    min_yearly: float = Query(None, description="Minimum yearly-USD-equivalent pay"),
    max_yearly: float = Query(None, description="Maximum yearly-USD-equivalent pay"),
    pay_interval: str = Query(None),
    source: str = Query(None),
    company: str = Query(None),
    sort_by: str = Query("date_posted", description="Sort field: date_posted, min_pay, max_pay, annual_min, annual_max, relevance"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
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
        min_yearly=min_yearly,
        max_yearly=max_yearly,
        pay_interval=pay_interval,
        source=source,
        company=company,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    base = apply_filters(db.query(JobORM), filters)
    # Server-side total count of the filtered result set (before pagination).
    total = base.order_by(None).count()
    response.headers["X-Total-Count"] = str(total)
    query = apply_sort(base, filters)
    jobs = query.offset(offset).limit(limit).all()
    return [Job.model_validate(j) for j in jobs]


@router.get("/jobs/count")
def count_jobs(
    q: str = Query(None),
    is_remote: bool = Query(True),
    is_us: bool = Query(True),
    job_type: str = Query(None),
    employment_type: str = Query(None),
    min_pay: float = Query(None),
    max_pay: float = Query(None),
    min_yearly: float = Query(None),
    max_yearly: float = Query(None),
    pay_interval: str = Query(None),
    source: str = Query(None),
    company: str = Query(None),
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
        min_yearly=min_yearly,
        max_yearly=max_yearly,
        pay_interval=pay_interval,
        source=source,
        company=company,
    )
    total = apply_filters(db.query(JobORM), filters).count()
    return {"count": total}


@router.post("/jobs/filter", response_model=list[Job])
def filter_jobs(payload: JobFilterRequest, db: Session = Depends(get_db)):
    query = apply_filters(db.query(JobORM), payload)
    query = apply_sort(query, payload)
    jobs = query.limit(200).all()
    return [Job.model_validate(j) for j in jobs]


@router.get("/jobs/stats", response_model=JobStats)
def get_job_stats(db: Session = Depends(get_db)):
    """Return aggregate stats for the stored job dataset."""
    last_scraped, count = db.query(func.max(JobORM.date_scraped), func.count(JobORM.id)).one()

    by_source = {
        site or "unknown": n
        for site, n in db.query(JobORM.site, func.count(JobORM.id)).group_by(JobORM.site).all()
    }
    by_employment_type = {
        (et or "unknown"): n
        for et, n in db.query(JobORM.employment_type, func.count(JobORM.id))
        .group_by(JobORM.employment_type)
        .all()
    }
    remote_count = db.query(func.count(JobORM.id)).filter(JobORM.is_remote.is_(True)).scalar() or 0
    us_count = db.query(func.count(JobORM.id)).filter(JobORM.is_us.is_(True)).scalar() or 0

    return JobStats(
        last_scraped=last_scraped,
        count=count,
        by_source=by_source,
        by_employment_type=by_employment_type,
        remote_count=remote_count,
        us_count=us_count,
    )


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(JobORM).filter(JobORM.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return Job.model_validate(job)


@router.get("/sources")
def list_sources():
    """Return the available job sources and their display labels."""
    return [
        {"id": source, "label": SOURCE_LABELS.get(source, source), "configured": _source_configured(source)}
        for source in ALL_SOURCES
    ]


@router.delete("/jobs")
def clear_jobs(db: Session = Depends(get_db)):
    db.query(JobORM).delete()
    db.commit()
    return {"cleared": True}


@router.get("/scrape/health", response_model=ScrapeHealth)
def scrape_health(db: Session = Depends(get_db)):
    """Report source health, recent scrape runs, and the next scheduled run."""
    recent = (
        db.query(ScrapeRunORM)
        .order_by(ScrapeRunORM.started_at.desc())
        .limit(20)
        .all()
    )
    # Latest run per source.
    sources: dict[str, SourceHealth] = {}
    for run in recent:
        if run.source not in sources:
            sources[run.source] = SourceHealth(
                source=run.source,
                last_status=run.status,
                last_run_at=run.started_at,
                last_duration_ms=run.duration_ms,
                last_jobs_found=run.jobs_found or 0,
                last_error=run.error,
            )
    next_run = scheduler.next_run_time()
    return ScrapeHealth(
        scheduler_enabled=next_run is not None,
        interval_minutes=config.SCRAPE_INTERVAL_MINUTES,
        next_run_at=next_run,
        sources=list(sources.values()),
        recent_runs=[ScrapeRun.model_validate(r) for r in recent],
    )


@router.post("/alerts/run")
def run_alerts(db: Session = Depends(get_db)):
    """Manually trigger evaluation and sending of due saved-search alerts."""
    sent = evaluate_alerts(db)
    return {"sent": sent}
