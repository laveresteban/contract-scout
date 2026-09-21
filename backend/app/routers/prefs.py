"""Saved searches + their background-scan results.

These endpoints back the frontend's `savedSearchApi` / `useSavedSearches` hook
(`/api/v1/prefs/saved-searches`) and add the "new matches" surface the scan
produces. Everything is scoped to `current_identity` (a real token->user lookup
replaces the stub — then this is per-user for free, like verification).

Contract Scout's real backend owns the broader `/prefs/*` surface; this package
owns the saved-search *scan*. Mount these on the real prefs router when
integrating (see README).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_db
from ..deps import current_identity, rate_limit, require_user
from ..models import (
    HiddenJobORM,
    Job,
    SavedJobORM,
    SavedSearch,
    SavedSearchMatch,
    UserORM,
    ViewedJobORM,
)
from ..schemas import (
    SavedSearchIn,
    SavedSearchMatchOut,
    SavedSearchOut,
    SavedSearchPatch,
    ScanRunOut,
)
from ..services import scan as scan_service
from ..services.scraper import get_scraper

router = APIRouter(prefix="/api/v1/prefs", tags=["prefs"])
_settings = get_settings()


# ---------------------------------------------------------------------------
# Server-backed saved / hidden / viewed jobs.
# These require an authenticated user; the SPA falls back to localStorage when
# anonymous. Scoped by the numeric user id (not the `current_identity` string).
# ---------------------------------------------------------------------------
async def _job_ids(db: AsyncSession, model, user_id: int) -> list[str]:
    rows = (await db.execute(select(model.job_id).where(model.user_id == user_id))).scalars().all()
    return list(rows)


async def _toggle(db: AsyncSession, model, user_id: int, job_id: str, add: bool) -> None:
    existing = (
        await db.execute(
            select(model).where(model.user_id == user_id, model.job_id == job_id)
        )
    ).scalars().first()
    if add and existing is None:
        db.add(model(user_id=user_id, job_id=job_id))
        await db.commit()
    elif not add and existing is not None:
        await db.delete(existing)
        await db.commit()


# --- Saved jobs -------------------------------------------------------------
@router.get("/saved-jobs")
async def list_saved_jobs(user: UserORM = Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await _job_ids(db, SavedJobORM, user.id)


@router.put("/saved-jobs/{job_id}")
async def add_saved_job(job_id: str, user: UserORM = Depends(require_user), db: AsyncSession = Depends(get_db)):
    await _toggle(db, SavedJobORM, user.id, job_id, add=True)
    return {"job_id": job_id, "saved": True}


@router.delete("/saved-jobs/{job_id}")
async def remove_saved_job(job_id: str, user: UserORM = Depends(require_user), db: AsyncSession = Depends(get_db)):
    await _toggle(db, SavedJobORM, user.id, job_id, add=False)
    return {"job_id": job_id, "saved": False}


# --- Hidden jobs ------------------------------------------------------------
@router.get("/hidden-jobs")
async def list_hidden_jobs(user: UserORM = Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await _job_ids(db, HiddenJobORM, user.id)


@router.put("/hidden-jobs/{job_id}")
async def add_hidden_job(job_id: str, user: UserORM = Depends(require_user), db: AsyncSession = Depends(get_db)):
    await _toggle(db, HiddenJobORM, user.id, job_id, add=True)
    return {"job_id": job_id, "hidden": True}


@router.delete("/hidden-jobs/{job_id}")
async def remove_hidden_job(job_id: str, user: UserORM = Depends(require_user), db: AsyncSession = Depends(get_db)):
    await _toggle(db, HiddenJobORM, user.id, job_id, add=False)
    return {"job_id": job_id, "hidden": False}


@router.delete("/hidden-jobs")
async def clear_hidden_jobs(user: UserORM = Depends(require_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(HiddenJobORM).where(HiddenJobORM.user_id == user.id))
    await db.commit()
    return {"cleared": True}


# --- Viewed jobs ------------------------------------------------------------
@router.get("/viewed-jobs")
async def list_viewed_jobs(user: UserORM = Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await _job_ids(db, ViewedJobORM, user.id)


@router.put("/viewed-jobs/{job_id}")
async def mark_viewed(job_id: str, user: UserORM = Depends(require_user), db: AsyncSession = Depends(get_db)):
    existing = (
        await db.execute(
            select(ViewedJobORM).where(
                ViewedJobORM.user_id == user.id, ViewedJobORM.job_id == job_id
            )
        )
    ).scalars().first()
    if existing is not None:
        existing.viewed_at = datetime.now(timezone.utc)
    else:
        db.add(ViewedJobORM(user_id=user.id, job_id=job_id))
    await db.commit()
    return {"job_id": job_id, "viewed": True}


async def _owned(db: AsyncSession, search_id: str, identity: str) -> SavedSearch:
    search = await db.get(SavedSearch, search_id)
    if search is None or search.user_id != identity:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return search


async def _new_counts(db: AsyncSession, ids: list[str]) -> dict[str, int]:
    if not ids:
        return {}
    rows = await db.execute(
        select(SavedSearchMatch.saved_search_id, func.count())
        .where(SavedSearchMatch.saved_search_id.in_(ids), SavedSearchMatch.is_new.is_(True))
        .group_by(SavedSearchMatch.saved_search_id)
    )
    return {sid: n for sid, n in rows.all()}


def _out(search: SavedSearch, new_count: int = 0) -> SavedSearchOut:
    dto = SavedSearchOut.model_validate(search)
    dto.new_count = new_count
    return dto


@router.get("/saved-searches", response_model=list[SavedSearchOut])
async def list_saved_searches(
    db: AsyncSession = Depends(get_db),
    identity: str = Depends(current_identity),
) -> list[SavedSearchOut]:
    searches = (
        (
            await db.execute(
                select(SavedSearch)
                .where(SavedSearch.user_id == identity)
                .order_by(SavedSearch.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    counts = await _new_counts(db, [s.id for s in searches])
    return [_out(s, counts.get(s.id, 0)) for s in searches]


@router.post("/saved-searches", response_model=SavedSearchOut, status_code=201)
async def create_saved_search(
    payload: SavedSearchIn,
    db: AsyncSession = Depends(get_db),
    identity: str = Depends(current_identity),
) -> SavedSearchOut:
    count = (
        await db.execute(
            select(func.count()).select_from(SavedSearch).where(SavedSearch.user_id == identity)
        )
    ).scalar_one()
    if count >= _settings.saved_search_max:
        raise HTTPException(status_code=409, detail="Saved search limit reached.")

    search = SavedSearch(
        id=uuid.uuid4().hex,
        user_id=identity,
        name=payload.name,
        filters=payload.filters,
        alert_enabled=payload.alert_enabled,
        alert_frequency=payload.alert_frequency,
        alert_email=payload.alert_email,
    )
    db.add(search)
    await db.commit()
    await db.refresh(search)
    return _out(search)


@router.patch("/saved-searches/{search_id}", response_model=SavedSearchOut)
async def update_saved_search(
    search_id: str,
    patch: SavedSearchPatch,
    db: AsyncSession = Depends(get_db),
    identity: str = Depends(current_identity),
) -> SavedSearchOut:
    search = await _owned(db, search_id, identity)
    for field, value in patch.model_dump(exclude_unset=True).items():
        setattr(search, field, value)
    await db.commit()
    await db.refresh(search)
    counts = await _new_counts(db, [search.id])
    return _out(search, counts.get(search.id, 0))


@router.delete("/saved-searches/{search_id}", status_code=204)
async def delete_saved_search(
    search_id: str,
    db: AsyncSession = Depends(get_db),
    identity: str = Depends(current_identity),
) -> None:
    search = await _owned(db, search_id, identity)
    # Explicit child delete (SQLite doesn't enforce ON DELETE CASCADE by default).
    await db.execute(
        delete(SavedSearchMatch).where(SavedSearchMatch.saved_search_id == search.id)
    )
    await db.delete(search)
    await db.commit()


@router.get("/saved-searches/{search_id}/matches", response_model=list[SavedSearchMatchOut])
async def list_matches(
    search_id: str,
    new_only: bool = Query(default=False, description="Only matches not yet seen."),
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    identity: str = Depends(current_identity),
) -> list[SavedSearchMatchOut]:
    await _owned(db, search_id, identity)
    filters = [SavedSearchMatch.saved_search_id == search_id]
    if new_only:
        filters.append(SavedSearchMatch.is_new.is_(True))
    rows = (
        await db.execute(
            select(SavedSearchMatch, Job)
            .join(Job, Job.id == SavedSearchMatch.job_id)
            .where(*filters)
            .order_by(SavedSearchMatch.first_seen_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        SavedSearchMatchOut(job=job, first_seen_at=m.first_seen_at, is_new=m.is_new)
        for m, job in rows
    ]


@router.post("/saved-searches/{search_id}/matches/seen", status_code=204)
async def mark_matches_seen(
    search_id: str,
    db: AsyncSession = Depends(get_db),
    identity: str = Depends(current_identity),
) -> None:
    await _owned(db, search_id, identity)
    await db.execute(
        update(SavedSearchMatch)
        .where(SavedSearchMatch.saved_search_id == search_id, SavedSearchMatch.is_new.is_(True))
        .values(is_new=False)
    )
    await db.commit()


@router.post("/saved-searches/{search_id}/scan", response_model=ScanRunOut)
async def scan_now(
    search_id: str,
    db: AsyncSession = Depends(get_db),
    identity: str = Depends(rate_limit),
) -> ScanRunOut:
    """Run this saved search against the scraper right now.

    Handy for confirming the background scan is wired up without waiting for the
    next scheduled tick. Rate-limited like verification so it can't hammer the
    source. Returns counts; new matches show up via `GET .../matches`.
    """
    search = await _owned(db, search_id, identity)
    result = await scan_service.scan_one(db, search, get_scraper(), now=datetime.now(timezone.utc))
    await db.commit()
    return ScanRunOut(
        saved_search_id=search_id,
        scraped=result.scraped,
        matched=result.matched,
        new=result.new,
        ok=result.ok,
        detail=result.error,
    )
