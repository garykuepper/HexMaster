from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from hexmaster.db.base import Base
from hexmaster.db.repositories.stockpile_repository import StockpileRepository
from hexmaster.services.stockpile_service import StockpileService
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture
def mock_ocr_service():
    service = AsyncMock()
    return service


@pytest.fixture
def mock_war_service():
    service = AsyncMock()
    return service


@pytest_asyncio.fixture
async def engine():
    # Use aiosqlite for an in-memory test database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_maker(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def repo(engine):
    return StockpileRepository(engine)


@pytest_asyncio.fixture
async def stockpile_service(repo, mock_ocr_service, mock_war_service):
    return StockpileService(repo, mock_ocr_service, mock_war_service)
