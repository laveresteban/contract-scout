# Contract Scout

A web app that helps software engineers and tech professionals find **remote, US-based contract work**. It aggregates listings from major job boards and remote-first sites, then lets you search and filter by role, pay rate, and employment type (W2, 1099, C2C, etc.).

## Tech stack

- **Backend:** Python [FastAPI](https://fastapi.tiangolo.com/) + SQLAlchemy (SQLite)
- **Scraping:** [JobSpy](https://github.com/speedyapply/JobSpy) for major boards + [Playwright](https://playwright.dev/) for remote-first boards
- **Frontend:** [React](https://react.dev/) + [Vite](https://vitejs.dev/)

## Research: why JobSpy + Playwright?

Before building, I evaluated several MCP servers and scraping approaches. For a standalone web app, the most reliable approach is to use the underlying libraries directly rather than an MCP layer.

| Tool / Approach | Best for | Why included / not included |
| --- | --- | --- |
| **JobSpy (python-jobspy)** | Scraping LinkedIn, Indeed, ZipRecruiter, Google, Glassdoor concurrently | Has native `job_type='contract'`, `is_remote=True`, and `country_indeed='USA'` filters. Returns a clean DataFrame with salary, company, title, etc. |
| **Playwright** | Remote-first boards (RemoteOK, We Work Remotely) and JavaScript-heavy pages | Used as a fallback when a site has no API or is not supported by JobSpy. Also supports stealth, headless mode, and form filling. |
| **Apify remote-jobs-feed** | Pre-aggregated remote feed | Excellent as an external data source, but costs Apify credits. Can be added later via the `apify-client` dependency. |
| **JobPilot / JobSpy MCP / LinkedIn-Job-Scraper-MCP** | Claude Desktop / MCP clients | These are MCP servers, not web app backends. They are useful for AI assistants, but we need a direct API for the web app. |
| **mcp-playwright-browser** | AI-driven browser control | Overkill for a focused job search; Playwright directly is simpler and cheaper. |

The current implementation uses **JobSpy for major boards** and **Playwright for remote-first boards**. More sources can be added by extending `app/scraper.py`.

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
│   │   ├── scraper.py       # JobSpy + Playwright scrapers
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
playwright install chromium

# Run the server
uvicorn app.main:app --reload --port 8000
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

If you prefer containers, the project is split into a backend container (FastAPI + Playwright) and a frontend container (Nginx serving the built React app).

### 1. Build and run

```bash
docker-compose up --build
```

This starts:
- Backend on [http://localhost:8000](http://localhost:8000)
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

### List stored jobs with filters

```bash
GET /api/v1/jobs?q=python&is_remote=true&is_us=true&employment_type=1099&min_pay=50&pay_interval=hourly&limit=50
```

## Important notes

- **Terms of service:** Many job boards restrict automated scraping. This tool is intended for personal use and job search assistance. Always review a site's robots.txt and Terms of Use before deploying a public scraper.
- **Rate limiting:** JobSpy and Playwright can be rate limited. Use proxies, increase delays, or lower `results_wanted` if you hit limits.
- **US-only filtering:** JobSpy's `country_indeed='USA'` filters Indeed by country. Other boards return a `location` string that is parsed for remote / US terms. This is a best-effort heuristic; always verify the listing.
- **Employment type detection:** W2 / 1099 / C2C labels are inferred from the job description text using keyword matching, because most job boards do not expose a structured field for it.

## Roadmap

- [ ] Add Apify `remote-jobs-feed` as an additional source
- [ ] Add scheduled background scraping with Celery / APScheduler
- [ ] Add user authentication and saved searches
- [ ] Add email alerts for new matching jobs
- [ ] Add pay normalization across currencies and intervals
