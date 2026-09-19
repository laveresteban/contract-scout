"""Jobs API: scraping, filtered listing, stats, source health, and verification.

Ported from the old sync ``api.py`` onto async SQLAlchemy, merged with the
async verification endpoints. List/detail return the rich ``scraped.Job`` shape
the frontend renders (pay normalized to yearly/hourly USD, eligibility, verify
status); verification re-fetches the source and persists a shared verdict.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import config
from ..config import get_settings
from ..db import get_db
from ..deps import rate_limit
from ..jobquery import apply_filters, apply_sort
from ..models import Job
from ..scraped import (
    Job as JobSchema,
    JobFilterRequest,
    JobSearchRequest,
    JobStats,
    ScrapeHealth,
    ScrapeRun,
    SourceHealth,
)
from ..schemas import VerifyBatchIn, VerifyBatchOut, VerifyResult
from ..services import alerts as alert_service
from ..services import boards
from ..services import scrape_run
from ..services import scheduler as scheduler_service
from ..services import verify as verify_service
from ..models import ScrapeRunORM

router = APIRouter(prefix="/api/v1", tags=["jobs"])
_settings = get_settings()

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


# --- Scraping ---------------------------------------------------------------
@router.post("/search")
async def search_jobs(payload: JobSearchRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Scrape and store jobs based on search criteria."""
    try:
        return await scrape_run.run_scrape(
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


# --- Read / filter ----------------------------------------------------------
@router.get("/jobs", response_model=list[JobSchema])
async def list_jobs(
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
    sort_by: str = Query("date_posted"),
    sort_order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    filters = JobFilterRequest(
        query=q, is_remote=is_remote, is_us=is_us, job_type=job_type,
        employment_type=employment_type, min_pay=min_pay, max_pay=max_pay,
        min_yearly=min_yearly, max_yearly=max_yearly, pay_interval=pay_interval,
        source=source, company=company, sort_by=sort_by, sort_order=sort_order,
    )
    base = apply_filters(select(Job), filters)
    total = (
        await db.execute(select(func.count()).select_from(base.order_by(None).subquery()))
    ).scalar_one()
    response.headers["X-Total-Count"] = str(total)
    stmt = apply_sort(base, filters).offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [JobSchema.model_validate(j) for j in rows]


@router.get("/jobs/count")
async def count_jobs(
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
    db: AsyncSession = Depends(get_db),
):
    filters = JobFilterRequest(
        query=q, is_remote=is_remote, is_us=is_us, job_type=job_type,
        employment_type=employment_type, min_pay=min_pay, max_pay=max_pay,
        min_yearly=min_yearly, max_yearly=max_yearly, pay_interval=pay_interval,
        source=source, company=company,
    )
    base = apply_filters(select(Job), filters)
    total = (
        await db.execute(select(func.count()).select_from(base.order_by(None).subquery()))
    ).scalar_one()
    return {"count": total}


@router.post("/jobs/filter", response_model=list[JobSchema])
async def filter_jobs(payload: JobFilterRequest, db: AsyncSession = Depends(get_db)):
    stmt = apply_sort(apply_filters(select(Job), payload), payload).limit(200)
    rows = (await db.execute(stmt)).scalars().all()
    return [JobSchema.model_validate(j) for j in rows]


@router.get("/jobs/stats", response_model=JobStats)
async def get_job_stats(db: AsyncSession = Depends(get_db)):
    """Return aggregate stats for the stored job dataset."""
    last_scraped, count = (
        await db.execute(select(func.max(Job.date_scraped), func.count(Job.id)))
    ).one()

    by_source = {
        (site or "unknown"): n
        for site, n in (
            await db.execute(select(Job.site, func.count(Job.id)).group_by(Job.site))
        ).all()
    }
    by_employment_type = {
        (et or "unknown"): n
        for et, n in (
            await db.execute(
                select(Job.employment_type, func.count(Job.id)).group_by(Job.employment_type)
            )
        ).all()
    }
    remote_count = (
        await db.execute(select(func.count(Job.id)).where(Job.is_remote.is_(True)))
    ).scalar() or 0
    us_count = (
        await db.execute(select(func.count(Job.id)).where(Job.is_us.is_(True)))
    ).scalar() or 0

    return JobStats(
        last_scraped=last_scraped,
        count=count,
        by_source=by_source,
        by_employment_type=by_employment_type,
        remote_count=remote_count,
        us_count=us_count,
    )


@router.get("/sources")
async def list_sources():
    """Return the available job sources and their display labels."""
    return [
        {"id": s, "label": SOURCE_LABELS.get(s, s), "configured": _source_configured(s)}
        for s in boards.ALL_SOURCES
    ]


@router.get("/scrape/health", response_model=ScrapeHealth)
async def scrape_health(db: AsyncSession = Depends(get_db)):
    """Report source health, recent scrape runs, and the next scheduled run."""
    recent = (
        await db.execute(
            select(ScrapeRunORM).order_by(ScrapeRunORM.started_at.desc()).limit(20)
        )
    ).scalars().all()

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

    quality = (
        await db.execute(
            select(
                Job.site,
                func.count(Job.id),
                func.sum(case((Job.job_type.ilike("%contract%"), 1), else_=0)),
                func.sum(case((Job.min_amount.isnot(None) | Job.max_amount.isnot(None), 1), else_=0)),
                func.sum(case((Job.interval == "hourly", 1), else_=0)),
            ).group_by(Job.site)
        )
    ).all()
    for site, stored, contracts, with_pay, hourly in quality:
        health = sources.setdefault(site or "unknown", SourceHealth(source=site or "unknown"))
        health.stored_jobs = stored or 0
        health.contract_jobs = contracts or 0
        health.jobs_with_pay = with_pay or 0
        health.hourly_jobs = hourly or 0
        health.pay_coverage = round(100 * health.jobs_with_pay / health.stored_jobs, 1) if health.stored_jobs else 0
        health.hourly_coverage = round(100 * health.hourly_jobs / health.stored_jobs, 1) if health.stored_jobs else 0

    next_run = scheduler_service.next_run_at()
    return ScrapeHealth(
        scheduler_enabled=next_run is not None,
        interval_minutes=config.SCRAPE_INTERVAL_MINUTES,
        next_run_at=next_run,
        sources=list(sources.values()),
        recent_runs=[ScrapeRun.model_validate(r) for r in recent],
    )


@router.post("/alerts/run")
async def run_alerts(db: AsyncSession = Depends(get_db)):
    """Manually trigger evaluation and sending of due saved-search alerts."""
    sent = await alert_service.evaluate_alerts(db)
    return {"sent": sent}


@router.delete("/jobs")
async def clear_jobs(db: AsyncSession = Depends(get_db)):
    await db.execute(Job.__table__.delete())
    await db.commit()
    return {"cleared": True}


@router.get("/jobs/{job_id}", response_model=JobSchema)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobSchema.model_validate(job)


# --- Verification -----------------------------------------------------------
@router.post("/jobs/{job_id}/verify", response_model=VerifyResult)
async def verify_single(
    job_id: str,
    force: bool = Query(default=False, description="Bypass the freshness cache."),
    db: AsyncSession = Depends(get_db),
    _identity: str = Depends(rate_limit),
) -> VerifyResult:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    result = await verify_service.verify_job(job, force=force)
    await db.commit()
    return VerifyResult(job_id=job_id, **result)


@router.post("/jobs/verify", response_model=VerifyBatchOut)
async def verify_batch(
    payload: VerifyBatchIn,
    db: AsyncSession = Depends(get_db),
    _identity: str = Depends(rate_limit),
) -> VerifyBatchOut:
    ids = list(dict.fromkeys(payload.ids))[: _settings.verify_batch_max]  # de-dupe, cap
    if not ids:
        return VerifyBatchOut(results={})

    rows = (await db.execute(select(Job).where(Job.id.in_(ids)))).scalars().all()
    semaphore = asyncio.Semaphore(_settings.verify_batch_concurrency)

    async with verify_service.new_client() as client:
        async def run(job: Job) -> tuple[str, dict]:
            async with semaphore:
                return job.id, await verify_service.verify_job(job, client=client)

        pairs = await asyncio.gather(*(run(job) for job in rows))

    await db.commit()
    results = {jid: VerifyResult(job_id=jid, **res) for jid, res in pairs}
    return VerifyBatchOut(results=results)
