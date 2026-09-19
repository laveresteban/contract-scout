# Scheduler — background job scraping

A tiny Alpine + cron container that re-scrapes your saved searches on a schedule
so new postings show up without you clicking **Search**.

## What it does

Every **30 minutes, 7:00am–10:00pm America/New_York, Monday–Saturday**, one pass:

1. `GET /prefs/saved-searches` — the searches you saved in the Contract Scout UI
   (each row's `filters` holds the exact query + options from the search form).
2. For each one, `POST /search` with those filters — the same call the UI's
   **Search** button makes — which pulls in newly posted jobs.

There is **nothing to hand-edit here** — the searches come from the app. Add,
rename, or remove a saved search in the UI and the next pass picks it up.

## Requirements

- The real scrape backend (serving `/search` and `/prefs/saved-searches`) must be
  reachable. This repo's `backend/` is only the verification slice and does **not**
  serve these endpoints — point the scheduler at wherever the full backend runs.
- A **bearer token** for a signed-in account. Only server-backed (signed-in)
  saved searches are visible headlessly; searches kept only in a browser's
  `localStorage` (unauthenticated) can't be reached. Grab the token from the
  browser after signing in: `localStorage["contract-scout:token"]`.

## Run it

From the repo root:

```bash
cp .env.example .env          # then set SCRAPE_AUTH_TOKEN and SCRAPE_API_BASE
docker compose up -d --build scheduler
docker compose logs -f scheduler
```

Verify config immediately (runs one pass on boot):

```bash
RUN_ON_START=true docker compose up --build scheduler
```

## Configuration (env)

| Var                 | Default                          | Purpose |
|---------------------|----------------------------------|---------|
| `SCRAPE_API_BASE`   | `http://backend:8000/api/v1`     | Backend base URL incl. `/api/v1`. Use `http://host.docker.internal:8001/api/v1` for a backend on your host. |
| `SCRAPE_AUTH_TOKEN` | *(required)*                     | Bearer token for the account whose saved searches to scrape. |
| `SCRAPE_TIMEOUT`    | `60`                             | Per-request timeout (seconds). |
| `ONLY_ALERTS`       | `false`                          | `true` = only run saved searches with alerts enabled. |
| `RUN_ON_START`      | `false`                          | `true` = run one pass immediately at startup. |
| `TZ`                | `America/New_York`               | Timezone the cron window is evaluated in. |

## Change the schedule

Edit [`crontab`](crontab) and rebuild. The window is two lines so the last run
lands exactly at 10:00pm:

```
0,30 7-21 * * 1-6 /app/scrape.sh > /proc/1/fd/1 2>/proc/1/fd/2
0 22    * * 1-6 /app/scrape.sh > /proc/1/fd/1 2>/proc/1/fd/2
```

## Notes

- A network error or timeout on a pass is logged as **inconclusive and retried
  next pass** — never treated as a failure that drops a search. This mirrors the
  app's load-bearing "transient failure is not a dead job" rule.
- Scraping is idempotent from the app's side: the backend dedupes/merges jobs, so
  re-running the same search just surfaces anything new.
