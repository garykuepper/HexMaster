from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

from hexmaster.bot.views.ocr_review_view import build_review_embed
from hexmaster.services.stockpile_service import StockpileService


@pytest.fixture
def stockpile_service():
    repo = AsyncMock()
    ocr_service = AsyncMock()
    war_service = Mock()
    return StockpileService(repo, ocr_service, war_service), repo, ocr_service, war_service


@pytest.mark.asyncio
async def test_parse_remote_image_builds_draft(stockpile_service):
    service, repo, ocr_service, _ = stockpile_service

    mock_df = pd.DataFrame(
        [
            {
                "Structure Type": "Seaport",
                "Stockpile Name": "Public",
                "CodeName": "BasicMaterials",
                "Quantity": 10,
                "Crated?": "YES",
            }
        ]
    )
    ocr_service.process_image.return_value = mock_df
    repo.get_catalog_items.return_value = {
        "BasicMaterials": {"displayname": "Basic Materials", "qty_per_crate": 100}
    }

    draft = await service.parse_remote_image(
        guild_id=123, image_bytes=b"test_image", town="Tine", stockpile_name="Public", shard="Alpha"
    )

    assert draft["guild_id"] == 123
    assert draft["town"] == "Tine"
    assert draft["struct_type"] == "Seaport"
    assert len(draft["items"]) == 1
    assert draft["items"][0]["code_name"] == "BasicMaterials"
    assert draft["items"][0]["quantity"] == 10
    assert draft["items"][0]["total"] == 1000


@pytest.mark.asyncio
async def test_commit_snapshot_draft_persists(stockpile_service):
    service, repo, _, _ = stockpile_service
    repo.ingest_snapshot.return_value = 999

    draft = {
        "shard": "Alpha",
        "town": "tine",
        "struct_type": "Seaport",
        "stockpile_name": "Public",
        "items": [{"code_name": "BasicMaterials", "quantity": 10}],
    }

    snap_id, count, struct = await service.commit_snapshot_draft(guild_id=123, draft_payload=draft, war_number=110)

    assert snap_id == 999
    assert count == 1
    assert struct == "Seaport"
    repo.ingest_snapshot.assert_called_once_with(123, "Alpha", "tine", "Seaport", "Public", draft["items"], 110)


def test_build_review_embed_formatting():
    draft = {
        "town": "tine",
        "struct_type": "Seaport",
        "stockpile_name": "Public",
        "items": [
            {
                "item_name": "Basic Materials",
                "is_crated": True,
                "quantity": 10,
                "total": 1000,
            }
        ],
    }

    embed = build_review_embed(draft)
    assert "Tine" in embed.title
    assert len(embed.fields) == 4
    assert embed.fields[0].name == "Structure"
    assert embed.fields[0].value == "Seaport"
