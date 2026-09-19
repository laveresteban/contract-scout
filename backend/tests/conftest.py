import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base, get_db
from app.main import app


@pytest_asyncio.fixture
async def session_factory():
    # Fresh in-memory DB per test.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def db(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def make_job():
    from datetime import datetime, timedelta, timezone

    from app.models import Job

    def _make(**overrides):
        defaults = dict(
            id="job-1",
            title="Engineer",
            company="Acme",
            is_remote=True,
            is_us=True,  # Contract Scout targets remote + US-eligible roles.
            job_url="https://jobs.example.com/1",
            date_posted=datetime.now(timezone.utc) - timedelta(days=5),
            description="A remote engineering role.",
        )
        defaults.update(overrides)
        return Job(**defaults)

    return _make
