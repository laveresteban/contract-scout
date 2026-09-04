from sqlalchemy import inspect, text

from app.models import Base, SessionLocal, engine
from app.normalize import normalize_amount


def _ensure_columns():
    """Add columns introduced after a database was first created.

    SQLite has no automatic migrations here, so we add any missing columns to
    existing tables by hand. This keeps older `jobs.db` files working.
    """
    inspector = inspect(engine)
    if "jobs" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("jobs")}
    if "dedup_key" not in existing:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN dedup_key VARCHAR"))
    added_normalized = False
    if "normalized_min_yearly" not in existing:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN normalized_min_yearly FLOAT"))
        added_normalized = True
    if "normalized_max_yearly" not in existing:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN normalized_max_yearly FLOAT"))
        added_normalized = True
    if added_normalized:
        _backfill_normalized_pay()


def _backfill_normalized_pay():
    """Populate the normalized yearly-USD columns for rows created before they existed."""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id, min_amount, max_amount, interval, currency FROM jobs "
                "WHERE normalized_min_yearly IS NULL AND normalized_max_yearly IS NULL"
            )
        ).all()
        for row in rows:
            nmin = normalize_amount(row.min_amount, row.interval, row.currency)
            nmax = normalize_amount(row.max_amount, row.interval, row.currency)
            if nmin is None and nmax is None:
                continue
            conn.execute(
                text(
                    "UPDATE jobs SET normalized_min_yearly = :nmin, normalized_max_yearly = :nmax "
                    "WHERE id = :id"
                ),
                {"nmin": nmin, "nmax": nmax, "id": row.id},
            )


def init_db():
    _ensure_columns()
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
