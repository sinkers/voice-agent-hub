"""
Test configuration.

IMPORTANT: environment variables must be set BEFORE backend modules are imported,
because backend.config.Settings reads them at class-definition time.
"""
import os

from cryptography.fernet import Fernet

# Generate a valid Fernet key for tests
_TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()

os.environ.setdefault("HUB_SECRET", "test-hub-secret-for-pytest")
os.environ.setdefault("HUB_ENCRYPTION_KEY", _TEST_ENCRYPTION_KEY)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("BASE_URL", "http://testserver")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from backend.database import Base, get_db  # noqa: E402
from backend.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Test database engine — single in-memory SQLite shared via StaticPool
# ---------------------------------------------------------------------------

test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    poolclass=StaticPool,
    echo=False,
)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_client():
    """AsyncClient wired to the FastAPI app with an isolated in-memory DB."""
    # Create tables on the test engine before each test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client

    app.dependency_overrides.clear()

    # Drop tables after each test so the next test starts clean
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session():
    """Direct DB session for test-side data manipulation."""
    async with TestSessionLocal() as session:
        yield session
