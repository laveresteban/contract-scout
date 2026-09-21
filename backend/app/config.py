"""Application configuration.

Two layers live here, intentionally:

* ``Settings`` (pydantic-settings, ``CS_`` prefix) — the async core's tunables:
  database URL, verification, the saved-search scan, and now the scraping /
  auth / scheduler knobs the full backend needs. New code reads these via
  ``get_settings()``.
* Module-level constants (``os.getenv``) — the historical settings the ported
  scraper, providers, auth and alerts modules import by name. Kept so those
  large modules port with import-path changes only, not a settings rewrite.
  Where the two overlap they read the same environment variable.
"""

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Async core settings (CS_ prefix)
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CS_", env_file=".env", extra="ignore")

    # Async SQLAlchemy URL. Defaults to a local SQLite file so the service runs
    # with zero setup; point this at Postgres (postgresql+asyncpg://…) in prod.
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'jobs.db'}"

    # Verification tuning.
    verify_cache_hours: float = 12.0        # don't re-fetch a job more often than this
    verify_timeout_seconds: float = 8.0
    verify_batch_max: int = 25              # ids accepted per batch call
    verify_batch_concurrency: int = 5       # simultaneous outbound fetches
    verify_user_agent: str = "ContractScoutBot/1.0 (+https://contractscout.example/bot)"

    # --- Background re-verification ----------------------------------------
    # A per-instance loop re-checks active jobs whose verdict is stale/missing so
    # the UI trends toward ground truth without a user clicking "Re-check".
    verify_background_enabled: bool = True
    verify_background_interval_minutes: int = 30   # how often the loop wakes
    verify_background_batch: int = 20              # jobs re-checked per tick
    verify_background_stale_hours: float = 24.0    # re-check once a verdict is older

    # Rate limit (per identity): `rate_limit_times` requests per window.
    rate_limit_times: int = 30
    rate_limit_window_seconds: float = 60.0
    # Optional Redis URL (e.g. redis://localhost:6379/0). When set, rate limiting
    # uses a shared Redis store so the limit is enforced across all workers;
    # otherwise it falls back to the in-process limiter (per-worker).
    redis_url: str | None = None

    # --- Saved-search background scan --------------------------------------
    scan_enabled: bool = True                # start the background loop at all
    scan_interval_minutes: int = 60          # how often a due search is re-run
    scan_weekdays_only: bool = True          # skip Sat/Sun ("during the week")
    scan_timezone: str = "UTC"               # tz used to decide the weekday
    scan_max_results: int = 200              # cap results ingested per scan
    scan_concurrency: int = 3                # searches scraped in parallel
    saved_search_max: int = 50               # saved searches kept per identity

    # Create tables on startup (dev convenience). Use Alembic in production.
    auto_create_tables: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ---------------------------------------------------------------------------
# Legacy module-level constants (imported by the ported scraper / providers /
# auth / alerts / scheduler). Read straight from the environment.
# ---------------------------------------------------------------------------

# Sync SQLAlchemy URL is no longer used (the whole DB layer is async now), but a
# couple of ported helpers still reference DATABASE_URL indirectly via settings.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'jobs.db'}")

# Default scrape settings
DEFAULT_RESULTS_PER_BOARD = int(os.getenv("RESULTS_PER_BOARD", "25"))
MAX_RESULTS_PER_BOARD = int(os.getenv("MAX_RESULTS_PER_BOARD", "100"))
SCRAPER_HOURS_OLD = int(os.getenv("SCRAPER_HOURS_OLD", "168"))  # 7 days
JOB_STALE_DAYS = int(os.getenv("JOB_STALE_DAYS", "30"))

# Apify integration (optional)
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
APIFY_ACTOR_ID = os.getenv("APIFY_ACTOR_ID", "hyperbach/remote-jobs-feed")

DEFAULT_SCRAPE_SOURCES = [
    source.strip()
    for source in os.getenv(
        "DEFAULT_SCRAPE_SOURCES",
        "indeed,linkedin,remoteok,weworkremotely,jobicy,remotive,dice,himalayas,apify",
    ).split(",")
    if source.strip()
]
CAREERJET_API_KEY = os.getenv("CAREERJET_API_KEY")
CAREERJET_API_URL = os.getenv("CAREERJET_API_URL", "https://search.api.careerjet.net/v4/query")
WORKABLE_FEED_URL = os.getenv("WORKABLE_FEED_URL", "https://www.workable.com/boards/workable.xml")
GREENHOUSE_BOARDS = os.getenv("GREENHOUSE_BOARDS", "")
LEVER_BOARDS = os.getenv("LEVER_BOARDS", "")
ASHBY_BOARDS = os.getenv("ASHBY_BOARDS", "")
SMARTRECRUITERS_BOARDS = os.getenv("SMARTRECRUITERS_BOARDS", "")
RECRUITEE_BOARDS = os.getenv("RECRUITEE_BOARDS", "")
JOOBLE_API_KEY = os.getenv("JOOBLE_API_KEY")
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")
ADZUNA_COUNTRY = os.getenv("ADZUNA_COUNTRY", "us")
USAJOBS_API_KEY = os.getenv("USAJOBS_API_KEY")
USAJOBS_EMAIL = os.getenv("USAJOBS_EMAIL")
UPWORK_API_TOKEN = os.getenv("UPWORK_API_TOKEN")
UPWORK_GRAPHQL_URL = os.getenv("UPWORK_GRAPHQL_URL", "https://api.upwork.com/graphql")

# CORS origins for local dev
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:5175",
).split(",")

# Frontend URL used for OAuth redirects back into the SPA.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Base URL of this backend, used to build OAuth callback URLs.
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8001")

# --- Authentication (OAuth) -------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 30)))  # 30 days

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

# --- Scheduled scraping -----------------------------------------------------
# Minutes between automatic scrape runs. 0 disables the scrape scheduler (the
# saved-search scan loop is controlled separately via CS_SCAN_* settings).
SCRAPE_INTERVAL_MINUTES = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "0"))
SCHEDULED_QUERIES = [
    q.strip() for q in os.getenv("SCHEDULED_QUERIES", "software engineer").split(",") if q.strip()
]

# --- Email alerts (SMTP) ----------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "contract-scout@localhost")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

# --- Pay normalization ------------------------------------------------------
# Approximate exchange rates to USD. Override via FX_RATES env as JSON, e.g.
# FX_RATES='{"EUR": 1.08, "GBP": 1.27}'. Rates are "1 unit of X = N USD".
_DEFAULT_FX_RATES = {
    "USD": 1.0,
    "CAD": 0.73,
    "EUR": 1.08,
    "GBP": 1.27,
    "AUD": 0.66,
    "INR": 0.012,
    "MXN": 0.055,
    "BRL": 0.18,
}


def _load_fx_rates() -> dict:
    raw = os.getenv("FX_RATES")
    rates = dict(_DEFAULT_FX_RATES)
    if raw:
        try:
            rates.update({k.upper(): float(v) for k, v in json.loads(raw).items()})
        except (ValueError, TypeError):
            pass
    return rates


FX_RATES = _load_fx_rates()

# Assumed working hours per year / months per year for interval normalization.
HOURS_PER_YEAR = int(os.getenv("HOURS_PER_YEAR", "2080"))
MONTHS_PER_YEAR = 12
