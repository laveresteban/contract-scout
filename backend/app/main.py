import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from . import config
from .config import get_settings
from .db import create_all
from .routers import auth, jobs, prefs
from .services import scan_adapter
from .services import scheduler
from .services import scraper as scraper_module

logging.basicConfig(level=logging.INFO)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        await create_all()
    # Wire the real board scraper into the saved-search scan, then start the
    # background loops (scan + scheduled scrape; each a no-op if disabled).
    scraper_module.set_scraper(scan_adapter.scan_scraper)
    scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()


app = FastAPI(
    title="Contract Scout",
    description="Remote US contract job aggregator for software engineers and tech professionals.",
    version="0.3.0",
    lifespan=lifespan,
)

# Session middleware backs the OAuth authorization-code state handshake.
app.add_middleware(SessionMiddleware, secret_key=config.JWT_SECRET, same_site="lax")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

app.include_router(jobs.router)
app.include_router(auth.router)
app.include_router(prefs.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
