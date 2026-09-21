# Contract Scout

A web app for finding **high-quality remote US contract roles** aggregated from
many job boards, with a strong emphasis on **filtering out junk**: postings that
are tagged remote but aren't, roles that were filled weeks ago, "talent pipeline"
listings that aren't real openings, and non-US-eligible jobs. The differentiator
is trust: the app scores every posting and can re-fetch the original URL to
confirm a job is still live before the user wastes an application.

## Repository layout

```
contract-scout/
├── frontend/   # React 18 + Vite SPA — the full product UI
└── backend/    # FastAPI service — ONLY the "verification" slice (see below)
```

This directory is a git repository.

## Frontend and backend are now symmetrical

The **frontend is the complete application** and the **backend now implements
the full API surface it calls** (`frontend/src/api.js`): `/search` (scrape),
`/jobs` (+filters/stats/count), `/sources`, `/scrape/health`, `/auth/*` (OAuth),
`/prefs/*` (server-backed saved/hidden/viewed jobs and saved searches), and
job **verification**.

This backend was reconciled from two diverged servers onto a single **async**
architecture: the older full backend's ~24-source scraping stack (jobspy major
boards + httpx board scrapers + JSON/RSS providers), auth, prefs, alerts and
scheduler were ported onto async SQLAlchemy and merged with the async
verification + saved-search-scan package. There is no longer a separate "real"
backend — this is it. `backend/README.md` documents the full layout and
endpoints.

The frontend is still written defensively (prefs fall back to `localStorage`
when unauthenticated; OAuth fails open) — keep that resilience — but the
endpoints it calls now exist server-side.

## Backend (`backend/`)

FastAPI + async SQLAlchemy 2.0 + SQLite (aiosqlite) by default; Postgres
(asyncpg) in prod via `CS_DATABASE_URL`. Alembic for migrations. Tests use
pytest + respx (mocked httpx).

Key files:
- `app/main.py` — app + CORS + lifespan (auto-creates tables in dev).
- `app/config.py` — `Settings` (pydantic-settings), all env-overridable with the
  `CS_` prefix (e.g. `CS_VERIFY_CACHE_HOURS`, `CS_RATE_LIMIT_TIMES`).
- `app/models.py` — the `Job` model and `VerifyStatus` enum. Job `id` is a
  string (sources supply opaque ids). Verification adds four columns:
  `verify_status`, `verify_checked_at`, `verify_http_status`, `verify_detail`.
- `app/services/verify.py` — **the heart of the feature.** Re-fetches
  `job_url_direct || job_url` and classifies:
  - `live` — 2xx and no "closed/filled" marker.
  - `expired` — 404/410 or a dead-marker phrase in the body.
  - `unreachable` — timeout/network/5xx — **inconclusive, never treated as
    expired.** This rule is deliberate: never bury a live job on a transient
    failure. Preserve it.
  - `unverified` — never checked.
  Results cached for `verify_cache_hours` (default 12h); `?force=true` bypasses.
  If a remote-tagged job's live page mentions on-site/hybrid, the `live` detail
  says so.
- `app/services/ratelimit.py` — in-process `SlidingWindowLimiter` (per instance;
  swap for Redis to scale across workers).
- `app/deps.py` — `current_identity` decodes the Bearer JWT to `user:<id>`, or
  falls back to `ip:<addr>`; `require_user` gates the auth-only endpoints. Rate
  limiting keys on the identity, so authenticated callers are throttled per-user.
- `app/routers/jobs.py` — verify endpoints + scaffolding read endpoints. Batch
  verify de-dupes, caps at `verify_batch_max`, fans out with bounded concurrency.
- `app/schemas.py` — Pydantic read/response models. Note the `_as_utc` validator:
  SQLite loses tzinfo, so naive datetimes are stamped UTC before serializing.
- `app/seed.py` — seeds a live, an expired, and a fake-remote sample job.
- `migrations/versions/` — `0000_create_jobs` is a **baseline only for this
  standalone package**; `0001_add_job_verification` is the one to apply to the
  real jobs table.

Endpoints (prefix `/api/v1`): `POST /search`, `GET /jobs` (full filters + sort +
`X-Total-Count`), `GET /jobs/count`, `POST /jobs/filter`, `GET /jobs/stats`,
`GET /jobs/{id}`, `DELETE /jobs`, `GET /sources`, `GET /scrape/health`,
`POST /jobs/{id}/verify?force=`, `POST /jobs/verify` (batch), `POST /alerts/run`,
`GET /auth/{providers,me,{provider}/login,{provider}/callback}`,
`/prefs/{saved,hidden,viewed}-jobs` and `/prefs/saved-searches` (+`/matches`,
`/matches/seen`, `/scan`), plus `GET /health`. See `backend/README.md` for the
full module map.

### Run the backend (dev)
```bash
cd backend
python -m venv .venv && .venv/Scripts/activate   # Windows; source .venv/bin/activate elsewhere
pip install -r requirements.txt
python -m app.seed                # optional sample data
uvicorn app.main:app --port 8001 --reload
python -m pytest                  # test suite (verify service + endpoints)
```
Run on **port 8001** — the Vite dev server proxies `/api` there.

## Frontend (`frontend/`)

React 18 + Vite, plain JS/JSX (no TypeScript despite the `@types/*` devdeps), no
UI/state library — hooks + Context only. ESLint configured (`.eslintrc.cjs`).
Deployed as static files behind nginx (`Dockerfile`, `nginx.conf` — nginx proxies
`/api` to `backend:8000` in that setup).

Structure:
- `src/App.jsx` — the whole page: search → scrape → list → detail modal. Holds
  most state. Notable behaviors: **auto-verification** (debounced, best-effort
  background batch-verify of loaded jobs), pagination/infinite-load with a
  `fetchId` guard against races, URL-synced filters, CSV/JSON export, copy link.
- `src/api.js` — all HTTP calls; bearer token in `localStorage`
  (`contract-scout:token`); `X-Total-Count` header drives totals.
- `src/auth/AuthContext.jsx` — OAuth: captures `?token=` from the callback
  redirect, then `/auth/me`. Fails open (unauthenticated) if the backend has no
  auth.
- `src/hooks/usePrefs.js`, `useSavedSearches.js` — **dual-mode**: server-backed
  when authenticated, `localStorage` otherwise, with an identical public API so
  callers never branch. Keep this contract when extending.
- `src/utils/quality.js` — **the client-side quality/trust engine.** Scores each
  job 0–100 into tiers `trusted`/`review`/`risky`, producing warning flags
  (remote mismatch, likely expired, pipeline post, non-US, thin description,
  vague employer, no apply link). Crucially, a **backend verification result
  overrides the heuristic guesses** — a real `live`/`expired` verdict refunds or
  overrides the age-based freshness penalties. This file is where "is this job
  trustworthy?" logic lives; the backend `verify` feature is its ground-truth
  input.
- Other `src/utils/`: `format.js` (currency/pay/date formatting, `stripHtml`),
  `filters.js` (URL (de)serialization + recent searches), `export.js`,
  `jobs.js` (dedupe/merge), `prefs.js`/`savedSearches.js` (localStorage),
  `description.js`.
- `src/components/` — `SearchFilters`, `JobList`/`JobCard`, `JobDetail` (modal
  with focus trap + Esc, "Re-check posting" button), `JobDescription`,
  `PayInsights`, `SavedSearchesPanel`, `ScrapeHealthPanel`, `AuthBar`,
  `ThemeToggle` (light/dark via `data-theme`), `Toast`, `ErrorBoundary`.

### Run the frontend (dev)
```bash
cd frontend
npm install
npm run dev      # http://localhost:5173, proxies /api → 127.0.0.1:8001
npm run build    # production build to dist/
npm run lint
```

## Conventions & notes

- **Trust/quality is the product's core value.** New job fields or sources should
  feed `quality.js` and/or the verify service so the risk flags stay meaningful.
- The verification "inconclusive ≠ dead" rule (transient failure → `unreachable`,
  never `expired`) is a load-bearing invariant on both sides (backend
  `verify.py`, frontend `quality.js`). Don't weaken it.
- Datetimes are stored/served as UTC; the frontend renders relative/local. Keep
  the `_as_utc` normalization when touching schemas or the DB.
- Prefs/saved-search hooks must keep their server-or-localStorage dual-mode API.
- The app targets **remote + US-eligible contract** roles specifically; filters
  and eligibility logic assume that focus.

## Likely future work (given the current shape)

- ~~Redis-backed rate limiter + background/async verification for multi-worker
  prod.~~ **Done:** set `CS_REDIS_URL` to enforce the rate limit across workers
  via `services/ratelimit.RedisSlidingWindowLimiter` (`build_limiter` falls back
  in-process when unset). A background loop (`CS_VERIFY_BACKGROUND_*`) re-checks
  stale/unverified active jobs via `verify.reverify_stale`, also exposed at
  `POST /jobs/reverify-stale`.
- Move the in-process scan/scrape/re-verify scheduler loops to a real
  scheduler/queue (arq / Celery beat / single leader) so N workers don't each
  run them.
- ~~The dual Job-ingest paths could be unified so scan results also get
  cross-source dedup.~~ **Done:** both `services/persist.save_jobs` and
  `scan._ingest_job` now derive `dedup_key` from the shared `app/dedup.py`
  (mirrors the frontend's `utils/jobs.js` grouping), so a role scraped by either
  path collapses onto one row. Backfill existing rows with
  `python -m app.backfill_dedup` (or Alembic `0004_backfill_dedup_keys`).
- ~~Broaden email-alert delivery beyond authenticated `user:<id>` searches.~~
  **Partly done:** a saved search can now carry an explicit `alert_email`
  (`services/alerts._email_for` prefers it, so an `ip:<addr>` search is now
  deliverable and an authenticated one can override its account email; migration
  `0005_add_saved_search_alert_email`). Remaining: the SPA still keeps anonymous
  saved searches in `localStorage` only, so exposing this in the UI for
  unauthenticated users needs anonymous searches to be server-backed first.
