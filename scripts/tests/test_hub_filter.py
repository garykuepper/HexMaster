# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio

from hexmaster.config import Settings
from hexmaster.db.repositories.stockpile_repository import StockpileRepository
from sqlalchemy.ext.asyncio import create_async_engine


async def test_hub_filter():
    settings = Settings.load()
    engine = create_async_engine(settings.database_url)
    repo = StockpileRepository(engine)

    print("Fetching towns with hub snapshots...")
    guild_id = 777
    hub_towns = await repo.get_towns_with_hub_snapshots(guild_id)
    print(f"Hub Towns: {hub_towns}")

    if hub_towns:
        town = hub_towns[0]
        snap, _ = await repo.get_latest_snapshot_for_town_filtered(guild_id, town)
        print(f"Town: {town}, Structure: {snap['struct_type']}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_hub_filter())
