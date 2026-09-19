# Contract Scout — backend

A FastAPI service (async SQLAlchemy 2.0 + SQLite/aiosqlite by default, Postgres
via `CS_DATABASE_URL`) that aggregates **remote, US-eligible contract roles**
from ~24 job sources, scores/normalizes them, and **re-fetches postings to
confirm they're still live**. This is the full product backend behind
`frontend/`: scraping, filtering, stats, source health, OAuth, server-side
prefs, saved-search scans, and verification.

> History: this package began as a standalone *verification slice* and was
> reconciled with the older full backend onto this async architecture. The
> scraping stack (`python-jobspy` major boards, the httpx board scrapers, and
> the JSON/RSS providers) was ported over; persistence, queries, auth, prefs,
> alerts and the scheduler were rewritten onto `AsyncSession`.

## Layout

```
app/
  main.py            # app, CORS, SessionMiddleware, lifespan (create tables, wire scraper, start loops)
  config.py          # Settings (CS_ prefix) + legacy module constants the scrapers import
  db.py              # async engine / SessionLocal / Base / create_all
  models.py          # ORM: Job, User/SavedJob/HiddenJob/ViewedJob/ScrapeRun, SavedSearch(+Match)
  scraped.py         # Pydantic Job (pay + classification inference) and request/response DTOs
  jobquery.py        # shared select() filter/sort builder (jobs router + alerts)
  extraction.py      # compensation / employment-type parsing (pure)
  normalize.py       # yearly/hourly-USD normalization + eligibility (pure)
  deps.py            # current_identity (JWT→user:<id> | ip:<addr>), user deps, rate limit
  routers/
    jobs.py          # /search, /jobs(+filters), /jobs/stats, /sources, /scrape/health, /alerts/run, verify
    auth.py          # OAuth (Google/GitHub) + JWT sessions
    prefs.py         # saved/hidden/viewed jobs + saved-searches + scan matches
  services/
    boards.py        # ported multi-board scraper (jobspy majors + httpx boards)
    providers.py     # JSON/RSS providers (careerjet, greenhouse, lever, adzuna, …)
    browser_scraper.py  # optional Playwright render fallback
    persist.py       # async save_jobs (dedup/merge) + mark_stale_jobs
    scrape_run.py    # run_scrape (persist + ScrapeRun health) + scrape_only (scan)
    scan.py / matcher.py / scan_adapter.py  # saved-search scan pipeline
    scheduler.py     # asyncio loops: saved-search scan + scheduled scrape/alerts
    verify.py / salary.py / ratelimit.py    # verification + pay mining + limiter
    alerts.py        # SMTP email alerts for due saved searches
```

## Endpoints (prefix `/api/v1`)

- `POST /search` — scrape + persist (`JobSearchRequest`); records per-source health
- `GET  /jobs` — filter (`q`, `is_remote`, `is_us`, `job_type`, `employment_type`,
  `min_pay/max_pay`, `min_yearly/max_yearly`, `pay_interval`, `source`, `company`),
  sort (`date_posted|min_pay|max_pay|annual_min|annual_max|relevance`), paginate;
  sets `X-Total-Count`. Defaults to remote + US-eligible.
- `GET  /jobs/count`, `POST /jobs/filter`, `GET /jobs/stats`, `GET /jobs/{id}`, `DELETE /jobs`
- `GET  /sources` — available sources + display label + whether configured
- `GET  /scrape/health` — per-source health + recent runs + next scheduled run
- `POST /jobs/{id}/verify?force=`, `POST /jobs/verify` (batch) — re-fetch + verdict
- `POST /alerts/run` — evaluate/send due saved-search email alerts
- `GET  /auth/providers`, `GET /auth/me`, `GET /auth/{provider}/login|callback`
- `/prefs/saved-jobs`, `/prefs/hidden-jobs`, `/prefs/viewed-jobs` (auth required),
  `/prefs/saved-searches` (+`/matches`, `/matches/seen`, `/scan`)
- `GET  /health`

Verification and manual scans are rate-limited per identity
(`rate_limit_times` per `rate_limit_window_seconds`, default 30/min) → HTTP 429.

## Load-bearing rules (don't weaken)

- **Inconclusive ≠ dead.** A transient fetch failure is `unreachable`, never
  `expired`; a failed scrape leaves existing matches intact and isn't marked
  scanned. Mirrors `frontend/src/utils/quality.js`.
- **One pay scale.** Pay is normalized to yearly (and hourly) USD so a $100/hr
  contract and a $200k/yr salary sort/filter together (`normalize.py`).
- **UTC everywhere.** Datetimes are stored/served UTC; naive values from SQLite
  are stamped UTC on serialization (`schemas._as_utc`).

## Identity

`deps.current_identity` decodes a Bearer JWT to `user:<id>` (authenticated) or
falls back to `ip:<addr>`. Saved searches, scans and rate limiting key on this
string; `/prefs/*-jobs` and `/auth/me` require a real user (401 otherwise). The
SPA mirrors prefs to `localStorage` when anonymous.

## Run it (local dev)

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate           # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt

# Migrations (mirrors prod) …
python -m alembic upgrade head
# … or rely on auto-create (default; set CS_AUTO_CREATE_TABLES=false to disable)

python -m app.seed               # optional sample data
uvicorn app.main:app --port 8001 --reload
python -m pytest
```

Run on **8001** — the Vite dev server proxies `/api` there.

Heavy scrapers are optional at runtime and degrade gracefully: `python-jobspy`
(major boards), `playwright` (Dice render fallback), and `apify-client` each
disable their source with a log line if unavailable. Provider sources activate
only when their API keys/board slugs are set (see `/sources` `configured`).

## Config

Env-overridable with the `CS_` prefix for the async core
(`CS_DATABASE_URL=postgresql+asyncpg://…`, `CS_VERIFY_CACHE_HOURS`,
`CS_SCAN_INTERVAL_MINUTES`, `CS_RATE_LIMIT_TIMES`, …). The scraping/auth/SMTP
knobs read plain env vars (`APIFY_API_TOKEN`, `GREENHOUSE_BOARDS`,
`GOOGLE_CLIENT_ID`, `JWT_SECRET`, `SMTP_HOST`, `SCRAPE_INTERVAL_MINUTES`, `FX_RATES`,
…) — see `app/config.py` and `.env.example`.

## Background loops (per-instance)

`scheduler.start()` runs two asyncio loops in the app lifespan:
- **saved-search scan** — re-runs enabled saved searches to surface new matches
  (`CS_SCAN_*`; default hourly, weekdays only);
- **scheduled scrape** — when `SCRAPE_INTERVAL_MINUTES > 0`, scrapes the queries
  behind alert-enabled saved searches (+ `SCHEDULED_QUERIES`) and sends due alerts.

Both are per-instance (like the sliding-window limiter). For multiple workers,
run them in exactly one leader or move to a real scheduler/queue (arq / Celery
beat) so searches aren't scanned/scraped N times.
