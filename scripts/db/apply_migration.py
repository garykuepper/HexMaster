# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio

from hexmaster.config import Settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def run_migration():
    settings = Settings.load()
    engine = create_async_engine(settings.database_url)

    print("Running migration: ADD COLUMN war_number TO stockpile_snapshots...")
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE stockpile_snapshots ADD COLUMN IF NOT EXISTS war_number INTEGER;"))
    print("✅ Migration complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_migration())
