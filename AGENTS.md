# Agent rules for contract-scout

## Project overview

FastAPI backend + React/Vite frontend that scrapes and indexes remote US contract job listings.

- Backend: `backend/` (Python, FastAPI, SQLAlchemy/SQLite, JobSpy)
- Frontend: `frontend/` (React, Vite)
- Docker: `docker-compose.yml` with a backend service and an Nginx frontend service

## Commands that are safe to run without asking

The following are standard, non-destructive commands for this repo. You may run them directly when needed.

### Backend
- `cd backend && python -m venv venv`
- `cd backend && venv\Scripts\activate` (Windows)
- `cd backend && pip install -r requirements.txt`
- `cd backend && uvicorn app.main:app --reload --port 8001`
- `cd backend && pytest`

### Frontend
- `cd frontend && npm install`
- `cd frontend && npm run dev`
- `cd frontend && npm run build`
- `cd frontend && npm run preview`
- `cd frontend && npm run lint`

### Gauge verification
- `cd gauge-tests && npm install`
- `cd gauge-tests && npm test` (requires the backend on port 8001; creates a local Python virtual environment on first run)

### Docker
- `docker compose up --build`
- `docker compose up -d`
- `docker compose down`
- `docker compose logs -f backend`
- `docker compose logs -f frontend`

### Inspection / git
- `git status`, `git diff`, `git log`, `git add`, `git commit`
- `ls`, `find`, `cat`, `grep`, `read`
- `cd backend`, `cd frontend`

## Commands that require explicit approval

- Destructive file operations (`rm -rf`, `del /F /Q`, etc.)
- Remote git mutations (`git push --force`, `git reset --hard`)
- Global package installs or untrusted scripts
- Manually editing or deleting `backend/data/jobs.db` outside of normal app flow
