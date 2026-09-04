"""Shared query building for stored jobs (search, filter, sort).

Extracted from the API layer so the alert engine can reuse the exact same
filtering semantics that users see in the UI.
"""
from sqlalchemy import case, or_

from app.models import JobFilterRequest, JobORM


def parse_query(query):
    """Split a query into (positive terms string, list of negative terms)."""
    if not query:
        return "", []
    parts = query.split()
    positive = [p for p in parts if not p.startswith("-")]
    negative = [p[1:] for p in parts if p.startswith("-") and len(p) > 1]
    return " ".join(positive), negative


def apply_filters(query, filters: JobFilterRequest):
    positive, negative = parse_query(filters.query)
    if positive:
        like = f"%{positive}%"
        query = query.filter(
            or_(
                JobORM.title.ilike(like),
                JobORM.company.ilike(like),
                JobORM.description.ilike(like),
            )
        )
    for term in negative:
        neg_like = f"%{term}%"
        query = query.filter(
            ~or_(
                JobORM.title.ilike(neg_like),
                JobORM.company.ilike(neg_like),
                JobORM.description.ilike(neg_like),
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
    # Yearly-USD-normalized pay filters. A job qualifies for a floor when the top
    # of its range clears it, and for a ceiling when the bottom is under it.
    if filters.min_yearly is not None:
        query = query.filter(JobORM.normalized_max_yearly >= filters.min_yearly)
    if filters.max_yearly is not None:
        query = query.filter(JobORM.normalized_min_yearly <= filters.max_yearly)
    if filters.pay_interval:
        query = query.filter(JobORM.interval.ilike(f"%{filters.pay_interval}%"))
    if filters.source:
        query = query.filter(JobORM.site.ilike(f"%{filters.source}%"))
    if filters.company:
        query = query.filter(JobORM.company.ilike(f"%{filters.company}%"))
    return query


def apply_sort(query, filters: JobFilterRequest):
    sort_by = (filters.sort_by or "date_posted").lower()
    sort_order = (filters.sort_order or "desc").lower()
    positive, _ = parse_query(filters.query)
    if sort_by == "relevance" and positive:
        like = f"%{positive}%"
        score = (
            case((JobORM.title.ilike(like), 3), else_=0)
            + case((JobORM.company.ilike(like), 2), else_=0)
            + case((JobORM.description.ilike(like), 1), else_=0)
        ).label("relevance")
        return query.order_by(score.desc(), JobORM.date_posted.desc().nullslast())

    column = {
        "date_posted": JobORM.date_posted,
        "min_pay": JobORM.min_amount,
        "max_pay": JobORM.max_amount,
        # Yearly-equivalent sorts put hourly and salaried roles on one scale.
        "annual_min": JobORM.normalized_min_yearly,
        "annual_max": JobORM.normalized_max_yearly,
    }.get(sort_by, JobORM.date_posted)

    if sort_order == "asc":
        return query.order_by(column.asc().nullslast())
    return query.order_by(column.desc().nullslast())
