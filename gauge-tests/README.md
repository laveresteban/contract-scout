# Contract Scout — Gauge acceptance tests

Two specs, both asserting the cross-source de-duplication fix:

| Spec | Layer | What it proves |
| --- | --- | --- |
| `specs/job_results.spec` | HTTP (`urllib`) | `GET /jobs` returns unique postings and `X-Total-Count` matches the rows returned. |
| `specs/ui_dedup.spec` | Browser (Selenium + headless Chrome) | The same role scraped by several boards renders as a single card in the real React UI. |

The posting-identity key used by both specs lives in `tests/dedup_key.py` and
mirrors the backend's `app/dedup.py` and the frontend's `utils/jobs.js`, so a
spec fails only when the app actually leaks a duplicate.

## Prerequisites

- [Gauge](https://gauge.org) is provided via the `@getgauge/cli` dev dependency
  (`npm install` in this folder). Chrome must be installed; Selenium Manager
  fetches the matching driver automatically.
- `run-gauge.js` creates `.venv/` and installs `getgauge` + `selenium` on first
  run.

## Bring up the app against a disposable, seeded database

The UI spec needs the stack running with deterministic data. Use a throwaway
SQLite DB so your dev data is untouched, seed the cross-source duplicates, and
collapse them with the backfill:

```bash
# from repo root
export CS_DATABASE_URL="sqlite+aiosqlite:///$PWD/e2e.db"   # throwaway DB

# backend (port 8001)
cd backend
python -m app.seed --with-duplicates    # 3 sample jobs + 2 duplicate sources of one role
python -m app.backfill_dedup            # deactivates the 2 duplicates
uvicorn app.main:app --port 8001 --host 127.0.0.1 &

# frontend (port 5173, proxies /api → 8001)
cd ../frontend
npm install
npm run dev &
```

## Run the specs

```bash
cd gauge-tests
API_BASE=http://127.0.0.1:8001 APP_URL=http://localhost:5173 node run-gauge.js
```

`API_BASE` (default `http://127.0.0.1:8001`) targets the backend for the HTTP
spec; `APP_URL` (default `http://localhost:5173`) targets the frontend for the
Selenium spec. The HTML report is written to `reports/html-report/index.html`.
