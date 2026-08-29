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

# CORS origins for local dev
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
