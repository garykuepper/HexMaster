import pytest
from sqlalchemy import insert, select

from hexmaster.db.models import Region, StockpileSnapshot, Town
from hexmaster.db.repositories.settings_repository import SettingsRepository
from hexmaster.db.repositories.stockpile_repository import StockpileRepository


@pytest.mark.asyncio
async def test_guild_isolation(async_engine):
    repo = StockpileRepository(async_engine)
    settings_repo = SettingsRepository(async_engine)

    guild_a = 111111111111111111
    guild_b = 222222222222222222

    # 1. Test Guild Config Isolation
    await settings_repo.upsert_config(guild_a, faction="Colonial", shard="Alpha")
    await settings_repo.upsert_config(guild_b, faction="Warden", shard="Bravo")

    config_a = await settings_repo.get_config(guild_a)
    config_b = await settings_repo.get_config(guild_b)

    assert config_a is not None
    assert config_b is not None
    assert config_a.shard == "Alpha"
    assert config_b.shard == "Bravo"

    # 2. Test Priority Isolation
    await repo.upsert_priority_item(guild_a, "soldier_supplies", "Soldier Supplies", 10, 100, 1.0)

    priorities_a = await repo.get_priority_list(guild_a)
    priorities_b = await repo.get_priority_list(guild_b)

    assert len(priorities_a) == 1
    assert len(priorities_b) == 0

    # 3. Test Snapshot Isolation
    items = [{"code_name": "soldier_supplies", "item_name": "Soldier Supplies", "quantity": 500}]

    async with async_engine.begin() as conn:
        await conn.execute(insert(Region).values(id=1, name="The Fingers"))
        await conn.execute(insert(Town).values(name="The Fingers", region_id=1, x=0, y=0))

    await repo.ingest_snapshot(guild_a, "Alpha", "the fingers", "Storage Depot", "Public", items, war_number=110)

    async with async_engine.connect() as conn:
        res_a = await conn.execute(select(StockpileSnapshot).where(StockpileSnapshot.guild_id == guild_a))
        res_b = await conn.execute(select(StockpileSnapshot).where(StockpileSnapshot.guild_id == guild_b))

        snaps_a = res_a.all()
        snaps_b = res_b.all()

    assert len(snaps_a) == 1
    assert len(snaps_b) == 0
