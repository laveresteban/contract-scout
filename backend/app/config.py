import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'jobs.db'}")

# Default scrape settings
DEFAULT_RESULTS_PER_BOARD = int(os.getenv("RESULTS_PER_BOARD", "25"))
MAX_RESULTS_PER_BOARD = int(os.getenv("MAX_RESULTS_PER_BOARD", "100"))
SCRAPER_HOURS_OLD = int(os.getenv("SCRAPER_HOURS_OLD", "168"))  # 7 days

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
# Secret used to sign our own JWT session tokens and the OAuth state session.
JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 30)))  # 30 days

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

# --- Scheduled scraping -----------------------------------------------------
# Minutes between automatic scrape runs. 0 disables the scheduler.
SCRAPE_INTERVAL_MINUTES = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "0"))
# Comma-separated default queries scraped on each scheduled run when there are
# no alert-enabled saved searches to drive scraping.
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
            import json

            rates.update({k.upper(): float(v) for k, v in json.loads(raw).items()})
        except (ValueError, TypeError):
            pass
    return rates


FX_RATES = _load_fx_rates()

# Assumed working hours per year / months per year for interval normalization.
HOURS_PER_YEAR = int(os.getenv("HOURS_PER_YEAR", "2080"))
MONTHS_PER_YEAR = 12
