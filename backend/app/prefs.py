"""Server-backed user preferences: saved / hidden / viewed jobs and saved searches.

All endpoints require an authenticated user. The SPA falls back to
`localStorage` for anonymous visitors.
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    HiddenJobORM,
    SavedJobORM,
    SavedSearch,
    SavedSearchCreate,
    SavedSearchORM,
    SavedSearchUpdate,
    UserORM,
    ViewedJobORM,
)

router = APIRouter()


def _ids(db: Session, model, user_id: int) -> list[str]:
    rows = db.query(model.job_id).filter(model.user_id == user_id).all()
    return [r[0] for r in rows]


def _toggle_collection(db: Session, model, user_id: int, job_id: str, add: bool):
    existing = (
        db.query(model)
        .filter(model.user_id == user_id, model.job_id == job_id)
        .first()
    )
    if add and not existing:
        db.add(model(user_id=user_id, job_id=job_id))
        db.commit()
    elif not add and existing:
        db.delete(existing)
        db.commit()


# --- Saved jobs -------------------------------------------------------------
@router.get("/saved-jobs")
def list_saved_jobs(user: UserORM = Depends(get_current_user), db: Session = Depends(get_db)):
    return _ids(db, SavedJobORM, user.id)


@router.put("/saved-jobs/{job_id}")
def add_saved_job(job_id: str, user: UserORM = Depends(get_current_user), db: Session = Depends(get_db)):
    _toggle_collection(db, SavedJobORM, user.id, job_id, add=True)
    return {"job_id": job_id, "saved": True}


@router.delete("/saved-jobs/{job_id}")
def remove_saved_job(job_id: str, user: UserORM = Depends(get_current_user), db: Session = Depends(get_db)):
    _toggle_collection(db, SavedJobORM, user.id, job_id, add=False)
    return {"job_id": job_id, "saved": False}


# --- Hidden jobs ------------------------------------------------------------
@router.get("/hidden-jobs")
def list_hidden_jobs(user: UserORM = Depends(get_current_user), db: Session = Depends(get_db)):
    return _ids(db, HiddenJobORM, user.id)


@router.put("/hidden-jobs/{job_id}")
def add_hidden_job(job_id: str, user: UserORM = Depends(get_current_user), db: Session = Depends(get_db)):
    _toggle_collection(db, HiddenJobORM, user.id, job_id, add=True)
    return {"job_id": job_id, "hidden": True}


@router.delete("/hidden-jobs/{job_id}")
def remove_hidden_job(job_id: str, user: UserORM = Depends(get_current_user), db: Session = Depends(get_db)):
    _toggle_collection(db, HiddenJobORM, user.id, job_id, add=False)
    return {"job_id": job_id, "hidden": False}


@router.delete("/hidden-jobs")
def clear_hidden_jobs(user: UserORM = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(HiddenJobORM).filter(HiddenJobORM.user_id == user.id).delete()
    db.commit()
    return {"cleared": True}


# --- Viewed jobs ------------------------------------------------------------
@router.get("/viewed-jobs")
def list_viewed_jobs(user: UserORM = Depends(get_current_user), db: Session = Depends(get_db)):
    return _ids(db, ViewedJobORM, user.id)


@router.put("/viewed-jobs/{job_id}")
def mark_viewed(job_id: str, user: UserORM = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = (
        db.query(ViewedJobORM)
        .filter(ViewedJobORM.user_id == user.id, ViewedJobORM.job_id == job_id)
        .first()
    )
    if existing:
        existing.viewed_at = datetime.utcnow()
    else:
        db.add(ViewedJobORM(user_id=user.id, job_id=job_id))
    db.commit()
    return {"job_id": job_id, "viewed": True}


# --- Saved searches ---------------------------------------------------------
def _to_schema(row: SavedSearchORM) -> SavedSearch:
    try:
        filters = json.loads(row.filters) if row.filters else {}
    except (ValueError, TypeError):
        filters = {}
    return SavedSearch(
        id=row.id,
        name=row.name,
        filters=filters,
        alert_enabled=bool(row.alert_enabled),
        alert_frequency=row.alert_frequency or "daily",
        last_alerted_at=row.last_alerted_at,
        created_at=row.created_at,
    )


@router.get("/saved-searches", response_model=list[SavedSearch])
def list_saved_searches(user: UserORM = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(SavedSearchORM)
        .filter(SavedSearchORM.user_id == user.id)
        .order_by(SavedSearchORM.created_at.desc())
        .all()
    )
    return [_to_schema(r) for r in rows]


@router.post("/saved-searches", response_model=SavedSearch)
def create_saved_search(
    payload: SavedSearchCreate,
    user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = SavedSearchORM(
        user_id=user.id,
        name=payload.name,
        filters=json.dumps(payload.filters),
        alert_enabled=payload.alert_enabled,
        alert_frequency=payload.alert_frequency,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_schema(row)


def _get_owned(db: Session, search_id: int, user_id: int) -> SavedSearchORM:
    row = (
        db.query(SavedSearchORM)
        .filter(SavedSearchORM.id == search_id, SavedSearchORM.user_id == user_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return row


@router.patch("/saved-searches/{search_id}", response_model=SavedSearch)
def update_saved_search(
    search_id: int,
    payload: SavedSearchUpdate,
    user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_owned(db, search_id, user.id)
    if payload.name is not None:
        row.name = payload.name
    if payload.filters is not None:
        row.filters = json.dumps(payload.filters)
    if payload.alert_enabled is not None:
        row.alert_enabled = payload.alert_enabled
    if payload.alert_frequency is not None:
        row.alert_frequency = payload.alert_frequency
    db.commit()
    db.refresh(row)
    return _to_schema(row)


@router.delete("/saved-searches/{search_id}")
def delete_saved_search(
    search_id: int,
    user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_owned(db, search_id, user.id)
    db.delete(row)
    db.commit()
    return {"deleted": True}
