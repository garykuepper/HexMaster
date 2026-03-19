# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio

from hexmaster.config import Settings
from hexmaster.db.repositories.stockpile_repository import StockpileRepository
from sqlalchemy.ext.asyncio import create_async_engine


async def test_war_ingestion():
    settings = Settings.load()
    engine = create_async_engine(settings.database_url)
    repo = StockpileRepository(engine)

    town = "Tine"
    struct = "Seaport"
    stockpile = "TestWarStockpile"
    war_number = 100  # Artificial war number

    # Needs some real item codenames from catalog
    # I'll just use what's likely there or skip item insertion if I can
    items: list[dict] = []
    guild_id = 12345
    shard = "Alpha"

    print(f"Ingesting snapshot for {town} with War {war_number}...")
    snapshot_id = await repo.ingest_snapshot(guild_id, shard, town, struct, stockpile, items, war_number)
    print(f"Inserted snapshot_id: {snapshot_id}")

    print(f"Fetching latest inventory for {town}...")
    await repo.get_latest_inventory(guild_id, shard, town)

    # Since we inserted 0 items, get_latest_inventory might return nothing if it joins with items
    # Let's check the snapshot header directly instead using a new repo method or simple query
    from hexmaster.db.models import StockpileSnapshot
    from sqlalchemy import select

    async with engine.connect() as conn:
        stmt = select(StockpileSnapshot.war_number).where(StockpileSnapshot.id == snapshot_id)
        res = await conn.execute(stmt)
        saved_war = res.scalar()
        print(f"Retrieved War Number from DB: {saved_war}")

    if saved_war == war_number:
        print("✅ War number correctly stored and retrieved!")
    else:
        print(f"❌ War number mismatch: Expected {war_number}, got {saved_war}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_war_ingestion())
