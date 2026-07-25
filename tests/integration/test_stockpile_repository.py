import pytest
from sqlalchemy import insert

from hexmaster.db.models import (
    CatalogItem,
    Region,
    Town,
)

GUILD_ID = 123456789
SHARD = "Alpha"


@pytest.mark.asyncio
async def test_repository_seed_and_get_towns(repo, engine):
    """Test inserting and retrieving town data."""
    async with engine.begin() as conn:
        await conn.execute(insert(Region).values(id=1000, name="R1000", q=0, r=0))
        await conn.execute(insert(Town).values(name="Town1000", region_id=1000))

    towns = await repo.get_all_towns()
    assert any("Town1000" in t for t in towns)


@pytest.mark.asyncio
async def test_ingest_snapshot(repo, engine):
    """Test ingesting a stockpile snapshot."""
    async with engine.begin() as conn:
        await conn.execute(insert(Region).values(id=1001, name="R1001", q=0, r=0))
        await conn.execute(insert(Town).values(name="Town1001", region_id=1001))
        await conn.execute(
            insert(CatalogItem).values(
                codename="code1001",
                displayname="Item 1001",
                factionvariant="Neutral",
                quantitypercrate=100,
            )
        )

    items = [
        {
            "code_name": "code1001",
            "item_name": "Item 1001",
            "quantity": 10,
            "is_crated": True,
            "per_crate": 100,
            "total": 1000,
        }
    ]

    snapshot_id = await repo.ingest_snapshot(GUILD_ID, SHARD, "Town1001", "Storage Depot", "Public", items)
    assert snapshot_id is not None

    inventory = await repo.get_latest_inventory(GUILD_ID, SHARD, "Town1001")
    assert len(inventory) == 1
    assert inventory[0]["code_name"] == "code1001"
    assert inventory[0]["total"] == 1000


@pytest.mark.asyncio
async def test_search_item_across_stockpiles(repo, engine):
    """Test searching for an item across different towns."""
    async with engine.begin() as conn:
        await conn.execute(insert(Region).values(id=1003, name="R1003", q=0, r=0))
        await conn.execute(insert(Region).values(id=1004, name="R1004", q=1, r=1))

        await conn.execute(insert(Town).values(name="Town1003", region_id=1003))
        await conn.execute(insert(Town).values(name="Town1004", region_id=1004))

        await conn.execute(
            insert(CatalogItem).values(
                codename="rifle1003",
                displayname="Rifle 1003",
                factionvariant="Warden",
                quantitypercrate=20,
            )
        )

    await repo.ingest_snapshot(
        GUILD_ID,
        SHARD,
        "Town1003",
        "Seaport",
        "Private",
        [
            {
                "code_name": "rifle1003",
                "item_name": "Rifle 1003",
                "total": 100,
                "is_crated": True,
                "per_crate": 20,
                "quantity": 5,
            }
        ],
    )

    results = await repo.search_item_across_stockpiles(GUILD_ID, "Rifle 1003", SHARD)
    assert len(results) >= 1
    assert any(r["town"] == "Town1003" for r in results)
