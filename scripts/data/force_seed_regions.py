# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio
from pathlib import Path

from hexmaster.config import Settings
from hexmaster.db.seed_reference import seed_regions_from_csv
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    settings = Settings.load()
    engine = create_async_engine(settings.database_url)

    print("🔄 Forcing region update from data/Regions.csv...")
    Path("data/Regions.csv")

    await seed_regions_from_csv(engine, Path("data/core/Regions.csv"), force=True)

    await engine.dispose()
    print("✨ Region update complete.")


if __name__ == "__main__":
    asyncio.run(main())
