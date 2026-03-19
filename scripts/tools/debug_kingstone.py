# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio

from hexmaster.config import Settings
from hexmaster.db.models import SnapshotItem, StockpileSnapshot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine


async def debug_kingstone():
    settings = Settings.load()
    engine = create_async_engine(settings.database_url)

    async with engine.connect() as conn:
        print("--- Snapshots for Kingstone ---")
        stmt = select(StockpileSnapshot).where(StockpileSnapshot.town == "Kingstone")
        res = await conn.execute(stmt)
        snapshots = res.mappings().all()

        if not snapshots:
            print("No snapshots found for Kingstone.")
            return

        for s in snapshots:
            print(f"ID: {s['id']}, Type: {s['struct_type']}, Name: {s['stockpile_name']}, Time: {s['captured_at']}")

            stmt_items = select(SnapshotItem).where(SnapshotItem.snapshot_id == s["id"])
            res_items = await conn.execute(stmt_items)
            items = res_items.mappings().all()
            print(f"  Item count: {len(items)}")
            if items:
                print(f"  First 3 items: {[item['item_name'] for item in items[:3]]}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(debug_kingstone())
