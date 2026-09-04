# Contract Scout

A web app that helps software engineers and tech professionals find **remote, US-based contract work**. It aggregates listings from major job boards and remote-first sites, then lets you search and filter by role, pay rate, and employment type (W2, 1099, C2C, etc.).

## Tech stack

- **Backend:** Python [FastAPI](https://fastapi.tiangolo.com/) + SQLAlchemy (SQLite)
- **Scraping:** [JobSpy](https://github.com/speedyapply/JobSpy) for major boards + public JSON/RSS feeds for remote-first boards, with a [Playwright](https://playwright.dev/python/) headless-browser fallback for JS-gated / bot-protected boards
- **Frontend:** [React](https://react.dev/) + [Vite](https://vitejs.dev/)

## Research: why JobSpy + public feeds?

Before building, I evaluated several MCP servers and scraping approaches. For a standalone web app, the most reliable approach is to use the underlying libraries directly rather than an MCP layer.

| Tool / Approach | Best for | Why included / not included |
| --- | --- | --- |
| **JobSpy (python-jobspy)** | Scraping LinkedIn, Indeed, ZipRecruiter, Google, Glassdoor concurrently | Has native `job_type='contract'`, `is_remote=True`, and `country_indeed='USA'` filters. Returns a clean DataFrame with salary, company, title, etc. |
| **Public JSON/RSS feeds** | Remote-first boards (RemoteOK, We Work Remotely, Jobicy, Remotive, Himalayas) | These boards all publish free, public feeds. Faster and more reliable than browser automation, and avoids the ToS/robots issues of scraping their HTML. |
| **Himalayas public API** | High-volume remote board with structured salary + location data | `https://himalayas.app/jobs/api` returns structured `employmentType`, `minSalary`/`maxSalary`, `salaryPeriod`, `currency`, and `locationRestrictions` fields, which map cleanly onto our schema and give strong US-eligibility signals. Paged with cursor pagination and filtered by keyword locally. |
| **Apify remote-jobs-feed** | Pre-aggregated remote feed | Excellent as an external data source, but costs Apify credits. Can be added later via the `apify-client` dependency. |
| **JobPilot / JobSpy MCP / LinkedIn-Job-Scraper-MCP** | Claude Desktop / MCP clients | These are MCP servers, not web app backends. They are useful for AI assistants, but we need a direct API for the web app. |
| **Playwright headless browser** | Fallback for JS-gated / bot-protected boards (e.g. Dice) | Boards like Dice render results through a JS framework and intermittently bot-block raw HTTP clients. When the fast httpx path returns nothing, `app/browser_scraper.py` renders the page in a real headless browser and the existing parser consumes the same embedded job data. Playwright is an **optional** dependency; if it (or its browser binaries) are absent, the fallback is a graceful no-op. |

The current implementation uses **JobSpy for major boards**, **public feeds for remote-first boards** (including Himalayas), and a **Playwright browser fallback** for boards that block plain HTTP requests. More sources can be added by extending `app/scraper.py`.

## Features

- Search by job title / keyword
- Filter by:
  - Remote-only
  - US-only
  - Job type (contract, full-time, part-time, internship)
  - Employment type (W2, 1099, C2C, contract)
  - Pay range and pay interval (hourly, yearly, monthly)
  - Source site
- Persistent SQLite database for fast filtering and caching
- REST API with CORS enabled for the React frontend

## Project structure

```
contract-scout/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI entrypoint
│   │   ├── api.py           # REST routes
│   │   ├── scraper.py       # JobSpy + public feed scrapers
│   │   ├── models.py        # Pydantic + SQLAlchemy models
│   │   ├── database.py      # DB session management
│   │   └── config.py        # Settings
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── api.js
│   │   ├── components/
│   │   │   ├── SearchFilters.jsx
│   │   │   ├── JobList.jsx
│   │   │   └── JobCard.jsx
│   │   └── index.css
│   ├── package.json
│   └── vite.config.js
└── README.md
```

## Setup

### 1. Clone or create the repo

If you are creating the repo from this local copy:

```bash
git remote add origin https://github.com/YOUR_USERNAME/contract-scout.git
git branch -M main
git push -u origin main
```

Or clone the published repo:

```bash
git clone https://github.com/YOUR_USERNAME/contract-scout.git
cd contract-scout
```

### 2. Backend

```bash
cd backend
python -m venv venv

# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt

# Optional: install the Chromium binary used by the Playwright browser
# fallback for JS-gated boards (Dice). Skipping this leaves the fallback a
# graceful no-op; the httpx path still works.
python -m playwright install chromium

# Run the server
uvicorn app.main:app --reload --port 8001
```

### 3. Frontend

In a new terminal:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

---

## Docker setup

If you prefer containers, the project is split into a backend container (FastAPI) and a frontend container (Nginx serving the built React app).

### 1. Build and run

```bash
docker-compose up --build
```

This starts:
- Backend on [http://localhost:8001](http://localhost:8001)
- Frontend on [http://localhost](http://localhost)

The frontend Nginx config proxies `/api/*` calls to the backend service.

### 2. Persistent data

The SQLite database is stored in `backend/data/jobs.db` and mounted into the backend container, so data survives container restarts.

### 3. Stop

```bash
docker-compose down
```

---

### 4. First search

Type a keyword in the search box and click **Search**. The backend will scrape major and remote-first boards, save results to SQLite, and return the matching remote US contract jobs.

## Environment variables

Create a `.env` file in `backend/` to override defaults:

```env
DATABASE_URL=sqlite:///data/jobs.db
RESULTS_PER_BOARD=25
MAX_RESULTS_PER_BOARD=100
SCRAPER_HOURS_OLD=168
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
APIFY_API_TOKEN=your-apify-token
APIFY_ACTOR_ID=hyperbach/remote-jobs-feed
DEFAULT_SCRAPE_SOURCES=indeed,linkedin,remoteok,weworkremotely,jobicy,remotive,dice,himalayas,apify
CAREERJET_API_KEY=your-careerjet-key
WORKABLE_FEED_URL=https://www.workable.com/boards/workable.xml
GREENHOUSE_BOARDS=company-one,company-two
LEVER_BOARDS=company-one,company-two
ASHBY_BOARDS=company-one,company-two
SMARTRECRUITERS_BOARDS=company-one,company-two
RECRUITEE_BOARDS=company-one,company-two
JOOBLE_API_KEY=your-jooble-key
ADZUNA_APP_ID=your-adzuna-app-id
ADZUNA_APP_KEY=your-adzuna-app-key
USAJOBS_API_KEY=your-usajobs-key
USAJOBS_EMAIL=you@example.com
UPWORK_API_TOKEN=your-upwork-oauth-token
UPWORK_GRAPHQL_URL=https://api.upwork.com/graphql
```

## API reference

### Scrape and store jobs

```bash
POST /api/v1/search
{
  "query": "software engineer",
  "location": "United States",
  "is_remote": true,
  "job_type": "contract",
  "min_pay": 50,
  "max_pay": 200,
  "pay_interval": "hourly",
  "employment_type": "1099",
  "results_wanted": 25
}
```

### List available sources

```bash
GET /api/v1/sources
```

### List stored jobs with filters

```bash
GET /api/v1/jobs?q=python&is_remote=true&is_us=true&employment_type=1099&min_pay=50&pay_interval=hourly&source=indeed&limit=50
```

## Important notes

- **Terms of service:** Many job boards restrict automated scraping. This tool is intended for personal use and job search assistance. Always review a site's robots.txt and Terms of Use before deploying a public scraper.
- **Rate limiting:** JobSpy and public feed clients can be rate limited. Use proxies, increase delays, or lower `results_wanted` if you hit limits.
- **US-only filtering:** JobSpy's `country_indeed='USA'` filters Indeed by country. Other boards return a `location` string that is parsed for remote / US terms. This is a best-effort heuristic; always verify the listing.
- **Employment type detection:** W2 / 1099 / C2C labels are inferred from the job description text using keyword matching, because most job boards do not expose a structured field for it.

## Roadmap

- [x] Add Apify `remote-jobs-feed` as an additional source
- [ ] Add scheduled background scraping with Celery / APScheduler
- [ ] Add user authentication and saved searches
- [ ] Add email alerts for new matching jobs
- [ ] Add pay normalization across currencies and intervals
