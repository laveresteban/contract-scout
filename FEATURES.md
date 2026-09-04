# Contract Scout Features

Contract Scout is a full-stack job aggregation and search application focused on remote, US-eligible contract work for software engineers and other technology professionals.

This document reflects the features currently implemented in the repository. Items under **Roadmap** are not yet implemented unless explicitly noted otherwise.

## Job discovery and aggregation

- Scrapes major job boards through JobSpy:
  - Indeed
  - LinkedIn
  - ZipRecruiter
  - Google Jobs
- Reads public feeds from remote-first job boards:
  - RemoteOK
  - We Work Remotely
  - Jobicy
  - Remotive
  - Himalayas (structured salary, employment type, and location-restriction data)
- Scrapes Dice for US contract tech roles, with an automatic Playwright headless-browser fallback when Dice bot-blocks plain HTTP requests.
- Supports the Apify `remote-jobs-feed` actor when an API token is configured.
- Queries remote sources concurrently where possible.
- Continues with available sources when an individual remote source fails.
- Degrades gracefully when optional dependencies (JobSpy, Apify client, Playwright and its browser binaries) are not installed.
- Limits results per request and avoids repeatedly hammering job boards.

## Job classification and data processing

- Detects remote and US-eligible listings from structured fields and job text.
- Distinguishes explicit onsite postings from remote-work listings.
- Infers employment arrangements from titles and descriptions:
  - W2
  - 1099
  - C2C / corp-to-corp
  - Contract / freelance
- Reconciles source-provided job types with contract and employee wording in the listing.
- Extracts hourly and yearly pay ranges from supported free-text salary formats.
- Parses source-specific salary formats and infers likely pay intervals when needed.
- Normalizes source records into one job schema.
- Generates stable fallback job IDs and skips duplicate records with an existing ID.
- Stores the original normalized record as JSON for later inspection.

## Search and filters

- Keyword search across job title, company, and description.
- Remote-only and US-only filtering in the API; the current UI applies both by default.
- Job type filtering:
  - Contract
  - Full-time
  - Part-time
  - Internship
- Employment type filtering by W2, 1099, C2C, or contract.
- Minimum and maximum pay filters expressed as a yearly-USD equivalent, so an hourly contract rate (e.g. $100/hr) and a full-time yearly salary are compared on one scale. An hourly/yearly toggle converts the entered figure.
- Sorting by yearly-equivalent pay (top of range or floor), putting hourly and salaried roles on the same axis.
- Source filtering.
- Company filtering with autocomplete based on loaded results.
- Sort options for:
  - Newest or oldest posting date
  - Minimum pay, ascending or descending
  - Maximum pay, ascending or descending
  - Relevance, weighted by title, company, and description matches
- Active filter chips with one-click removal.
- Reset action for restoring default filters.

## Results browsing

- Paginated API results using `limit` and `offset`.
- “Load more” pagination in batches of 25 jobs.
- Responsive job cards with:
  - Company and location
  - Source, remote, job type, and employment type badges
  - Pay and posting date
  - Expandable descriptions
  - Direct job links
- Job detail modal with the complete listing and apply link.
- Modal dismissal through its close button, overlay click, or Escape key.
- New-job badges based on the time of the previous browser visit.
- Skeleton loading cards.
- Empty, end-of-results, error, and retry states.
- Last-scraped timestamp in the results header.

## Saved and hidden jobs

- Save or unsave jobs in browser `localStorage`.
- Switch between all results and saved jobs.
- Hide individual jobs in browser `localStorage`.
- Restore all hidden jobs from the results header.

These preferences are browser-local and are not synchronized between devices or user accounts.

## Search persistence and sharing

- Synchronizes active search filters with the page URL.
- Restores URL filters when the application loads.
- Copies a shareable search URL to the clipboard, with a fallback for older browsers.
- Stores up to five recent searches in `localStorage`.
- Supports named saved searches in `localStorage`.
- Re-runs recent and saved searches with one click.
- Deletes saved searches locally.

## Pay insights and export

- Displays pay insights for the currently visible jobs:
  - Observed pay range
  - Average reported upper-bound pay
  - Most common pay interval
  - Five-bucket pay histogram
- Exports currently visible jobs as CSV.
- Exports currently visible jobs as formatted JSON.

Pay filtering and sorting use compensation normalized to an approximate yearly-USD equivalent (via configurable FX rates and an assumed hours-per-year). The pay-insights histogram still summarizes the raw reported figures.

## User experience and accessibility

- Light and dark themes persisted in `localStorage`.
- Responsive layouts for smaller screens.
- Toast confirmations for common actions.
- Application-level React error boundary with a reload fallback.
- Keyboard shortcuts to focus search:
  - `Ctrl+K` or `Cmd+K`
  - `/`
- Keyboard-operable job cards and company autocomplete.
- ARIA labels, live regions, dialog semantics, and loading indicators in key interactions.

## Data storage and API

- Persistent SQLite storage through SQLAlchemy.
- FastAPI REST API with configurable CORS support.
- Automatic database initialization during application startup.
- Interactive OpenAPI documentation provided by FastAPI.
- Health endpoint for service checks.

### Available endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check backend health. |
| `POST` | `/api/v1/search` | Scrape configured sources and save new jobs. |
| `GET` | `/api/v1/jobs` | List, filter, sort, and paginate stored jobs. |
| `POST` | `/api/v1/jobs/filter` | Apply a full filter payload to stored jobs. |
| `GET` | `/api/v1/jobs/stats` | Return stored job count and last-scraped time. |
| `GET` | `/api/v1/jobs/{job_id}` | Retrieve one job by ID. |
| `GET` | `/api/v1/sources` | List supported source identifiers and labels. |
| `DELETE` | `/api/v1/jobs` | Clear all stored jobs. This endpoint is not exposed in the current UI. |

## Deployment and operation

- Local development with FastAPI/Uvicorn and React/Vite.
- Docker Compose deployment with separate backend and frontend services.
- Production frontend build served by Nginx.
- Nginx proxying of `/api` requests to the backend container.
- Persistent Docker volume mapping for the SQLite database.
- Environment-based configuration for database location, CORS origins, scraper limits, listing age, and Apify credentials.
- Backend API and scraper test coverage with pytest.
- Frontend lint and production build scripts.

## Current limitations

- No user accounts or server-side synchronization of saved jobs and searches.
- No scheduled or background scraping; searches trigger scraping directly.
- No email or other job alerts.
- No server-side total count for filtered results; the UI reports the number currently loaded and visible.
- Source and location quality depends on third-party feeds and best-effort text classification.
- Deduplication is based on source job IDs or generated fallback IDs, not cross-source semantic matching.
- Apify is optional and requires both the client dependency and valid configuration.
- The backend supports clearing all jobs, but the frontend does not currently expose that operation.

## Roadmap

### High priority

- Add scheduled background scraping with APScheduler, Celery, or an equivalent worker.
- Add authentication and server-backed user preferences.
- Move saved jobs and saved searches from browser-only storage to user accounts.
- Add configurable alerts for newly matched jobs.

### Search and data quality

- Add negative keyword support.
- Add search-as-you-type with debounce and request cancellation.
- Improve cross-source duplicate detection.
- Add stronger location validation and explicit eligibility indicators.
- Track source health, scrape duration, failures, and the next scheduled run.

### Product and accessibility

- Add a dedicated saved-searches management page.
- Add viewed/seen state beyond the current new-job badge.
- Add server-side result counts and richer aggregate statistics.
- Complete focus trapping and focus restoration for the job detail modal.
- Expand automated frontend test coverage.
