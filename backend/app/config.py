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

# CORS origins for local dev
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:5175",
).split(",")
