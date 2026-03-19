# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio
import os

from hexmaster.db.models import Base
from hexmaster.db.repositories.settings_repository import SettingsRepository
from hexmaster.db.repositories.stockpile_repository import StockpileRepository
from sqlalchemy.ext.asyncio import create_async_engine


async def test_isolation():
    # Use in-memory SQLite for verification
    db_url = "sqlite+aiosqlite:///"
    engine = create_async_engine(db_url)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    repo = StockpileRepository(engine)
    settings_repo = SettingsRepository(engine)

    guild_a = 111111111111111111
    guild_b = 222222222222222222

    print("--- Testing Guild Isolation (SQLite) ---")

    # 1. Test Guild Config Isolation
    print("Setting Alpha shard for Guild A and Bravo for Guild B...")
    await settings_repo.upsert_config(guild_a, faction="Colonial", shard="Alpha")
    await settings_repo.upsert_config(guild_b, faction="Warden", shard="Bravo")

    config_a = await settings_repo.get_config(guild_a)
    print(f"Config A type: {type(config_a)}, value: {config_a}")
    config_b = await settings_repo.get_config(guild_b)

    assert config_a is not None
    assert config_b is not None
    assert config_a.shard == "Alpha"
    assert config_b.shard == "Bravo"
    print("✅ Guild configs isolated.")

    # 2. Test Priority Isolation
    print("Adding priority item to Guild A...")
    await repo.upsert_priority_item(guild_a, "soldier_supplies", "Soldier Supplies", 10, 100, 1.0)

    priorities_a = await repo.get_priority_list(guild_a)
    priorities_b = await repo.get_priority_list(guild_b)

    assert len(priorities_a) == 1
    assert len(priorities_b) == 0
    print("✅ Priorities isolated.")

    # 3. Test Snapshot Isolation
    print("Ingesting snapshot for Guild A...")
    items = [{"code_name": "soldier_supplies", "item_name": "Soldier Supplies", "quantity": 500}]
    # We need a town record for the join in get_latest_inventory
    from hexmaster.db.models import Region, Town

    async with engine.begin() as conn:
        from sqlalchemy import insert

        await conn.execute(insert(Region).values(id=1, name="The Fingers"))
        await conn.execute(insert(Town).values(name="The Fingers", region_id=1, x=0, y=0))

    await repo.ingest_snapshot(
        guild_a,
        "Alpha",
        "the fingers",
        "Storage Depot",
        "Public",
        items,
        war_number=110,
    )

    # Verify directly via select to avoid DISTINCT ON issues in SQLite
    async with engine.connect() as conn:
        from hexmaster.db.models import StockpileSnapshot
        from sqlalchemy import select

        res_a = await conn.execute(select(StockpileSnapshot).where(StockpileSnapshot.guild_id == guild_a))
        res_b = await conn.execute(select(StockpileSnapshot).where(StockpileSnapshot.guild_id == guild_b))

        snaps_a = res_a.all()
        snaps_b = res_b.all()

    assert len(snaps_a) == 1
    assert len(snaps_b) == 0
    print("✅ Snapshots isolated.")

    await engine.dispose()
    if os.path.exists("test_isolation.db"):
        os.remove("test_isolation.db")
    print("--- Isolation Test Passed ---")


if __name__ == "__main__":
    asyncio.run(test_isolation())
