import json

from sqlalchemy import inspect, text

from app.models import Base, Job, JobORM, SessionLocal, engine
from app.normalize import normalize_amount, normalize_hourly_amount


def _ensure_columns():
    """Add columns introduced after a database was first created.

    SQLite has no automatic migrations here, so we add any missing columns to
    existing tables by hand. This keeps older `jobs.db` files working.
    """
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "jobs" in tables:
        existing = {col["name"] for col in inspector.get_columns("jobs")}
        columns = {
            "dedup_key": "VARCHAR",
            "normalized_min_yearly": "FLOAT",
            "normalized_max_yearly": "FLOAT",
            "normalized_min_hourly": "FLOAT",
            "normalized_max_hourly": "FLOAT",
            "pay_source": "VARCHAR",
            "pay_confidence": "VARCHAR",
            "pay_raw_text": "TEXT",
            "classification_source": "VARCHAR",
            "classification_confidence": "VARCHAR",
            "quality_version": "INTEGER DEFAULT 0",
            "source_urls": "TEXT",
            "is_active": "BOOLEAN DEFAULT 1",
            "last_seen": "DATETIME",
        }
        added_normalized = False
        with engine.begin() as conn:
            for name, data_type in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {data_type}"))
                    added_normalized = added_normalized or name.startswith("normalized_")
        with engine.begin() as conn:
            conn.execute(text("UPDATE jobs SET is_active = 1 WHERE is_active IS NULL"))
            conn.execute(text("UPDATE jobs SET last_seen = date_scraped WHERE last_seen IS NULL"))
        if added_normalized:
            _backfill_normalized_pay()
    if "scrape_runs" in tables:
        existing = {col["name"] for col in inspector.get_columns("scrape_runs")}
        with engine.begin() as conn:
            for name in ("jobs_with_pay", "hourly_jobs", "contract_jobs"):
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE scrape_runs ADD COLUMN {name} INTEGER DEFAULT 0"))


def _backfill_normalized_pay():
    """Populate the normalized yearly-USD columns for rows created before they existed."""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id, min_amount, max_amount, interval, currency FROM jobs WHERE "
                "normalized_min_yearly IS NULL OR normalized_max_yearly IS NULL OR "
                "normalized_min_hourly IS NULL OR normalized_max_hourly IS NULL"
            )
        ).all()
        for row in rows:
            nmin = normalize_amount(row.min_amount, row.interval, row.currency)
            nmax = normalize_amount(row.max_amount, row.interval, row.currency)
            hmin = normalize_hourly_amount(row.min_amount, row.interval, row.currency)
            hmax = normalize_hourly_amount(row.max_amount, row.interval, row.currency)
            if nmin is None and nmax is None:
                continue
            conn.execute(
                text(
                    "UPDATE jobs SET normalized_min_yearly = :nmin, normalized_max_yearly = :nmax, "
                    "normalized_min_hourly = :hmin, normalized_max_hourly = :hmax WHERE id = :id"
                ),
                {"nmin": nmin, "nmax": nmax, "hmin": hmin, "hmax": hmax, "id": row.id},
            )


def _backfill_quality_fields():
    db = SessionLocal()
    try:
        rows = db.query(JobORM).filter((JobORM.quality_version.is_(None)) | (JobORM.quality_version < 2)).all()
        for row in rows:
            job = Job.model_validate(row)
            for name in (
                "job_type",
                "employment_type",
                "interval",
                "min_amount",
                "max_amount",
                "currency",
                "pay_source",
                "pay_confidence",
                "pay_raw_text",
                "classification_source",
                "classification_confidence",
            ):
                setattr(row, name, getattr(job, name))
            row.normalized_min_yearly = job.normalized_min_yearly
            row.normalized_max_yearly = job.normalized_max_yearly
            row.normalized_min_hourly = job.normalized_min_hourly
            row.normalized_max_hourly = job.normalized_max_hourly
            row.source_urls = row.source_urls or json.dumps([{"site": row.site, "url": row.job_url or row.job_url_direct}])
            row.quality_version = 2
        db.commit()
    finally:
        db.close()


def _backfill_dedup_keys():
    from app.scraper import _dedup_key, _merge_job

    db = SessionLocal()
    try:
        groups = {}
        for row in db.query(JobORM).all():
            row.dedup_key = _dedup_key(Job.model_validate(row))
            if row.is_active is not False:
                groups.setdefault(row.dedup_key, []).append(row)
        for matches in groups.values():
            if len(matches) < 2:
                continue
            canonical = max(
                matches,
                key=lambda row: (
                    bool(row.description),
                    len(row.description or ""),
                    int(row.min_amount is not None) + int(row.max_amount is not None),
                ),
            )
            for duplicate in matches:
                if duplicate is canonical:
                    continue
                _merge_job(canonical, Job.model_validate(duplicate))
                duplicate.is_active = False
        db.commit()
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    _backfill_quality_fields()
    _backfill_dedup_keys()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
