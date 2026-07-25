import asyncio
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hexmaster.db.models import Base
from hexmaster.db.repositories.stockpile_repository import StockpileRepository
from hexmaster.services.stockpile_service import StockpileService


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_ocr_service():
    service = AsyncMock()
    return service


@pytest.fixture
def mock_war_service():
    service = AsyncMock()
    return service


@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def engine(async_engine):
    yield async_engine


@pytest_asyncio.fixture
async def db_session(async_engine):
    async_session = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def repo(async_engine):
    return StockpileRepository(async_engine)


@pytest_asyncio.fixture
async def stockpile_service(repo, mock_ocr_service, mock_war_service):
    return StockpileService(repo, mock_ocr_service, mock_war_service)
