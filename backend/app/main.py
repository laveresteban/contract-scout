import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api import router
from app.auth import router as auth_router
from app.config import CORS_ORIGINS, JWT_SECRET
from app.database import init_db
from app.prefs import router as prefs_router
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(
    title="Contract Scout",
    description="Remote US contract job aggregator for software engineers and tech professionals.",
    version="0.2.0",
    lifespan=lifespan,
)

# Session middleware backs the OAuth authorization-code state handshake.
app.add_middleware(SessionMiddleware, secret_key=JWT_SECRET, same_site="lax")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(prefs_router, prefix="/api/v1/prefs", tags=["prefs"])


@app.get("/health")
def health():
    return {"status": "ok"}
