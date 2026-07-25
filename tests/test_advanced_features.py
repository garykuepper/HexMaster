from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from hexmaster.db.repositories.stockpile_repository import StockpileRepository
from hexmaster.services.stockpile_service import StockpileService


@pytest.mark.asyncio
async def test_operation_template_crud(async_engine):
    repo = StockpileRepository(async_engine)
    guild_id = 999111

    # 1. Upsert template
    items = [
        {"code_name": "SoldierSupplies", "item_name": "Soldier Supplies", "required_crates": 10},
        {"code_name": "BasicMaterials", "item_name": "Basic Materials", "required_crates": 50},
    ]
    tmpl_id = await repo.upsert_operation_template(
        guild_id=guild_id, name="Tank Push", items_data=items, user_id=123
    )
    assert tmpl_id > 0

    tmpls = await repo.get_operation_templates(guild_id)
    assert len(tmpls) == 1
    assert tmpls[0]["name"] == "Tank Push"
    assert len(tmpls[0]["items"]) == 2

    # 2. Delete template
    deleted = await repo.delete_operation_template(guild_id, "Tank Push")
    assert deleted is True

    tmpls_after = await repo.get_operation_templates(guild_id)
    assert len(tmpls_after) == 0


@pytest.mark.asyncio
async def test_priority_deficits_calculation():
    repo = AsyncMock()
    ocr = AsyncMock()
    service = StockpileService(repo, ocr)

    guild_id = 123
    repo.get_towns_with_snapshots.return_value = ["Tine"]
    repo.get_priority_list.return_value = [
        {
            "codename": "SoldierSupplies",
            "name": "Soldier Supplies",
            "qty_per_crate": 10,
            "min_for_base_crates": 50,
            "priority": 1.0,
        }
    ]
    # Town inventory has 200 items (20 crates of 10)
    repo.get_latest_inventory.return_value = [
        {
            "struct_type": "Relic Base",
            "code_name": "SoldierSupplies",
            "item_name": "Soldier Supplies",
            "total": 200,
            "catalog_qpc": 10,
        }
    ]
    # locate_item mock
    repo.get_town_data.return_value = {"name": "Tine", "x": 0.5, "y": 0.5, "q": 0, "r": 0}
    repo.search_item_across_stockpiles.return_value = []

    deficits = await service.check_priority_deficits(guild_id, shard="Alpha")
    assert len(deficits) == 1
    assert deficits[0]["town"] == "Tine"
    assert deficits[0]["held_crates"] == 20.0
    assert deficits[0]["min_crates"] == 50.0
    assert deficits[0]["deficit_crates"] == 30.0


@pytest.mark.asyncio
async def test_operation_readiness_check():
    repo = AsyncMock()
    ocr = AsyncMock()
    service = StockpileService(repo, ocr)

    guild_id = 123
    repo.get_operation_templates.return_value = [
        {
            "id": 1,
            "name": "Arty Ops",
            "items": [
                {"code_name": "120mm", "item_name": "120mm Artillery", "required_crates": 20},
            ],
        }
    ]
    repo.get_latest_snapshot_for_town_filtered.return_value = (
        {"captured_at": datetime.now(timezone.utc)},
        [
            {"code_name": "120mm", "item_name": "120mm Artillery", "total": 100, "catalog_qpc": 5},
        ],
    )

    res = await service.check_operation_readiness(guild_id, "Arty Ops", "Seaport Alpha")
    assert res["fully_ready"] is True
    assert res["items"][0]["available"] == 20.0
    assert res["items"][0]["status"] == "🟢"


@pytest.mark.asyncio
async def test_stockpile_analytics_burn_rate():
    repo = AsyncMock()
    ocr = AsyncMock()
    service = StockpileService(repo, ocr)

    guild_id = 123
    t1 = datetime.now(timezone.utc) - timedelta(hours=10)
    t2 = datetime.now(timezone.utc)

    repo.get_snapshot_history_for_town.return_value = [
        {
            "id": 1,
            "captured_at": t1,
            "code_name": "SoldierSupplies",
            "item_name": "Soldier Supplies",
            "total": 1000,
            "catalog_qpc": 10,
        },
        {
            "id": 2,
            "captured_at": t2,
            "code_name": "SoldierSupplies",
            "item_name": "Soldier Supplies",
            "total": 500,
            "catalog_qpc": 10,
        },
    ]

    res = await service.get_stockpile_analytics(guild_id, "Tine", hours=48)
    assert len(res["rates"]) == 1
    rate_info = res["rates"][0]
    assert rate_info["start_crates"] == 100.0
    assert rate_info["end_crates"] == 50.0
    assert rate_info["delta_crates"] == -50.0
    assert rate_info["rate_per_hour"] == -5.0
