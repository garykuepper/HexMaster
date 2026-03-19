import pandas as pd
import pytest
from hexmaster.db.models import CatalogItem, Priority, Region, Town
from sqlalchemy import insert

GUILD_ID = 987654321
SHARD = "Alpha"


@pytest.mark.asyncio
async def test_process_remote_and_ingest_success(stockpile_service, mock_ocr_service, repo, engine):
    """Test full flow of OCR processing and database ingestion."""
    df = pd.DataFrame(
        [
            {
                "CodeName": "bmat2000",
                "Name": "Item 2000",
                "Quantity": 10,
                "Crated?": "Yes",
                "Per Crate": 100,
                "Total": 1000,
                "Structure Type": "Storage Depot",
                "Stockpile Name": "Public",
            }
        ]
    )
    mock_ocr_service.process_image.return_value = df

    async with engine.begin() as conn:
        await conn.execute(insert(Region).values(id=2000, name="R2000", q=0, r=0))
        await conn.execute(insert(Town).values(name="Town2000", region_id=2000))
        await conn.execute(
            insert(CatalogItem).values(
                codename="bmat2000",
                displayname="Item 2000",
                factionvariant="Neutral",
                quantitypercrate=100,
            )
        )

    snapshot_id, count, struct_type = await stockpile_service.process_remote_and_ingest(
        GUILD_ID, b"fake_image", "Town2000", "Public", SHARD
    )

    assert snapshot_id is not None
    assert count == 1

    inventory = await repo.get_latest_inventory(GUILD_ID, SHARD, "Town2000")
    assert inventory[0]["total"] == 1000


@pytest.mark.asyncio
async def test_get_requisition_comparison(stockpile_service, repo, engine):
    """Test requisition math between two towns."""
    async with engine.begin() as conn:
        await conn.execute(insert(Region).values(id=2001, name="R2001", q=0, r=0))
        await conn.execute(insert(Town).values(name="Hub2001", region_id=2001))
        await conn.execute(insert(Town).values(name="Front2001", region_id=2001))
        await conn.execute(
            insert(CatalogItem).values(
                codename="rifle2001",
                displayname="Rifle 2001",
                factionvariant="Neutral",
                quantitypercrate=20,
            )
        )
        await conn.execute(
            insert(Priority).values(
                guild_id=GUILD_ID,
                codename="rifle2001",
                name="Rifle 2001",
                qty_per_crate=20,
                min_for_base_crates=10,
                priority=1.0,
            )
        )

    await repo.ingest_snapshot(
        GUILD_ID,
        SHARD,
        "Hub2001",
        "Seaport",
        "Public",
        [
            {
                "code_name": "rifle2001",
                "item_name": "Rifle 2001",
                "total": 1000,
                "is_crated": True,
                "per_crate": 20,
                "quantity": 50,
            }
        ],
    )
    await repo.ingest_snapshot(
        GUILD_ID,
        SHARD,
        "Front2001",
        "Bunker Base",
        "Public",
        [
            {
                "code_name": "rifle2001",
                "item_name": "Rifle 2001",
                "total": 100,
                "is_crated": True,
                "per_crate": 20,
                "quantity": 5,
            }
        ],
    )

    result = await stockpile_service.get_requisition_comparison(GUILD_ID, "Hub2001", "Front2001", SHARD)
    data = result["comparison_data"]
    assert len(data) == 1
    assert data[0]["Item"] == "Rifle 2001"
    assert data[0]["Need"] == 5.0


@pytest.mark.asyncio
async def test_locate_item_system(stockpile_service, repo, engine):
    """Test locating an item and sorting by distance."""
    async with engine.begin() as conn:
        await conn.execute(insert(Region).values(id=2002, name="R2002", q=0, r=0))
        await conn.execute(insert(Town).values(name="Ref2002", region_id=2002, x=0.5, y=0.5))
        await conn.execute(insert(Town).values(name="Near2002", region_id=2002, x=0.6, y=0.6))
        await conn.execute(insert(Town).values(name="Far2002", region_id=2002, x=0.9, y=0.9))
        await conn.execute(
            insert(CatalogItem).values(
                codename="mat2002",
                displayname="Mat 2002",
                factionvariant="Neutral",
                quantitypercrate=1,
            )
        )

    await repo.ingest_snapshot(
        GUILD_ID,
        SHARD,
        "Near2002",
        "Depot",
        "P",
        [
            {
                "code_name": "mat2002",
                "item_name": "Mat 2002",
                "total": 10,
                "is_crated": False,
                "per_crate": 1,
                "quantity": 10,
            }
        ],
    )
    await repo.ingest_snapshot(
        GUILD_ID,
        SHARD,
        "Far2002",
        "Depot",
        "P",
        [
            {
                "code_name": "mat2002",
                "item_name": "Mat 2002",
                "total": 20,
                "is_crated": False,
                "per_crate": 1,
                "quantity": 20,
            }
        ],
    )

    results, ref_town = await stockpile_service.locate_item(GUILD_ID, "Mat 2002", "Ref2002", SHARD)

    assert len(results) == 2
    assert results[0]["Town"] == "Near2002"
    assert results[1]["Town"] == "Far2002"
