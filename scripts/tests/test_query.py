# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio

from hexmaster.config import Settings
from hexmaster.db.repositories.stockpile_repository import StockpileRepository
from sqlalchemy.ext.asyncio import create_async_engine


async def test_inventory_query():
    settings = Settings.load()
    engine = create_async_engine(settings.database_url)
    repo = StockpileRepository(engine)

    town = "Kingstone"
    guild_id = 555
    print(f"--- Testing get_latest_inventory for {town} ---")
    rows = await repo.get_latest_inventory(guild_id, town)

    print(f"Found {len(rows)} rows.")
    if rows:
        print(f"First 5 rows: {rows[:5]}")
    else:
        # Check if subquery returns anything
        from hexmaster.db.models import StockpileSnapshot
        from sqlalchemy import desc, select

        async with engine.connect() as conn:
            subq = (
                select(StockpileSnapshot.id)
                .where(StockpileSnapshot.town == town)
                .distinct(StockpileSnapshot.town, StockpileSnapshot.struct_type, StockpileSnapshot.stockpile_name)
                .order_by(
                    StockpileSnapshot.town,
                    StockpileSnapshot.struct_type,
                    StockpileSnapshot.stockpile_name,
                    desc(StockpileSnapshot.captured_at),
                    desc(StockpileSnapshot.id),
                )
            )
            res = await conn.execute(subq)
            ids = [r[0] for r in res.all()]
            print(f"Subquery IDs: {ids}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_inventory_query())
