from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

from hexmaster.services.stockpile_service import StockpileService


@pytest.fixture
def stockpile_service():
    repo = AsyncMock()
    ocr_service = AsyncMock()
    war_service = Mock()
    return StockpileService(repo, ocr_service, war_service), repo, ocr_service, war_service


@pytest.mark.asyncio
async def test_requisition_hub_to_hub(stockpile_service):
    service, repo, _, _ = stockpile_service
    guild_id = 123
    ship_town = "Seaport A"
    recv_town = "Seaport B"

    repo.get_priority_list.return_value = [
        {"codename": "C1", "name": "Item1", "qty_per_crate": 10, "min_for_base_crates": 5, "priority": 1}
    ]

    ship_snap = {"struct_type": "Seaport", "captured_at": "now"}
    recv_snap = {"struct_type": "Seaport", "captured_at": "now"}

    ship_items = [
        {"code_name": "C1", "item_name": "Item1", "total": 100, "is_crated": False, "catalog_qpc": 10, "per_crate": 10},
        {"code_name": "C1", "item_name": "Item1", "total": 50, "is_crated": True, "catalog_qpc": 10, "per_crate": 10},
    ]
    recv_items: list[dict] = []

    repo.get_latest_snapshot_for_town_filtered.side_effect = [(ship_snap, ship_items), (recv_snap, recv_items)]

    result = await service.get_requisition_comparison(guild_id, ship_town, recv_town)

    data = result["comparison_data"]
    assert len(data) == 2

    crated_entry = next(d for d in data if d["is_crated"] is True)
    assert crated_entry["Avail"] == 5.0

    loose_entry = next(d for d in data if d["is_crated"] is False)
    assert loose_entry["Avail"] == 10.0


@pytest.mark.asyncio
async def test_requisition_hub_to_base(stockpile_service):
    service, repo, _, _ = stockpile_service
    guild_id = 123
    ship_town = "Seaport A"
    recv_town = "Base B"

    repo.get_priority_list.return_value = [
        {"codename": "C1", "name": "Item1", "qty_per_crate": 10, "min_for_base_crates": 5, "priority": 1}
    ]

    ship_snap = {"struct_type": "Seaport", "captured_at": "now"}
    recv_snap = {"struct_type": "Relic Base", "captured_at": "now"}

    ship_items = [
        {"code_name": "C1", "item_name": "Item1", "total": 100, "is_crated": False, "catalog_qpc": 10, "per_crate": 10},
        {"code_name": "C1", "item_name": "Item1", "total": 50, "is_crated": True, "catalog_qpc": 10, "per_crate": 10},
    ]
    recv_items: list[dict] = []

    repo.get_latest_snapshot_for_town_filtered.side_effect = [(ship_snap, ship_items), (recv_snap, recv_items)]

    result = await service.get_requisition_comparison(guild_id, ship_town, recv_town)

    data = result["comparison_data"]
    assert len(data) == 1
    assert data[0]["is_crated"] is True
    assert data[0]["Avail"] == 5.0


@pytest.mark.asyncio
async def test_process_remote_and_ingest_calculates_totals(stockpile_service):
    service, repo, ocr_service, _ = stockpile_service

    mock_df = pd.DataFrame(
        [
            {
                "Structure Type": "Seaport",
                "Stockpile Name": "Public",
                "CodeName": "BasicMaterials",
                "Name": "Basic Materials",
                "Quantity": 10,
                "Crated?": "YES",
                "Per Crate": 0,
                "Total": 0,
            },
            {
                "Structure Type": "Seaport",
                "Stockpile Name": "Public",
                "CodeName": "SoldierSupplies",
                "Name": "Soldier Supplies",
                "Quantity": 50,
                "Crated?": "NO",
                "Per Crate": 0,
                "Total": 0,
            },
        ]
    )
    ocr_service.process_image.return_value = mock_df

    repo.get_catalog_items.return_value = {
        "BasicMaterials": {"displayname": "Basic Materials", "qty_per_crate": 100},
        "SoldierSupplies": {"displayname": "Soldier Supplies", "qty_per_crate": 10},
    }

    await service.process_remote_and_ingest(
        guild_id=123,
        image_bytes=b"fake_image",
        town="Tine",
        stockpile_name="Public",
    )

    args, kwargs = repo.ingest_snapshot.call_args
    items = args[5]

    bm = next(i for i in items if i["code_name"] == "BasicMaterials")
    assert bm["quantity"] == 10
    assert bm["is_crated"] is True
    assert bm["per_crate"] == 100
    assert bm["total"] == 1000

    ss = next(i for i in items if i["code_name"] == "SoldierSupplies")
    assert ss["quantity"] == 50
    assert ss["is_crated"] is False
    assert ss["per_crate"] == 10
    assert ss["total"] == 50
