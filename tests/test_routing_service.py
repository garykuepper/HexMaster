from unittest.mock import AsyncMock

import pytest

from hexmaster.services.routing_service import RoutingService
from hexmaster.services.stockpile_service import StockpileService


def test_dijkstra_safe_route_friendly():
    routing = RoutingService()
    hex_control = {
        "TheFingersHex": "COLONIAL",
        "EndlessShoreHex": "COLONIAL",
        "MarbanHollow": "COLONIAL",
    }

    res = routing.find_safe_route("The Fingers", "Marban Hollow", hex_control, user_faction="Colonial")

    assert res["status"] == "SAFE"
    assert res["hops"] == 2
    assert "TheFingersHex" in res["path"]
    assert "MarbanHollow" in res["path"]
    assert res["hazard_hexes"] == []


def test_dijkstra_hazard_route_neutral():
    routing = RoutingService()
    hex_control = {
        "TheFingersHex": "COLONIAL",
        "EndlessShoreHex": "NEUTRAL",
        "MarbanHollow": "COLONIAL",
    }

    res = routing.find_safe_route("The Fingers", "Marban Hollow", hex_control, user_faction="Colonial")

    assert res["status"] == "HAZARD"
    assert "EndlessShoreHex" in res["hazard_hexes"]


def test_dijkstra_reroute_around_enemy():
    routing = RoutingService()
    # EndlessShore is WARDEN (enemy to Colonial), so Dijkstra should try detour via TempestIsland -> Godcrofts
    hex_control = {
        "TheFingersHex": "COLONIAL",
        "EndlessShoreHex": "WARDEN",
        "TempestIslandHex": "COLONIAL",
        "GodcroftsHex": "COLONIAL",
        "WeatheredExpanseHex": "COLONIAL",
        "ViperPitHex": "COLONIAL",
        "MarbanHollow": "COLONIAL",
    }

    res = routing.find_safe_route("The Fingers", "Marban Hollow", hex_control, user_faction="Colonial")

    assert "EndlessShoreHex" not in res["path"]
    assert res["status"] == "SAFE"


@pytest.mark.asyncio
async def test_locate_item_with_routing_integration():
    repo = AsyncMock()
    ocr = AsyncMock()
    war_service = AsyncMock()
    routing_service = RoutingService()

    service = StockpileService(repo, ocr, war_service, routing_service)

    repo.get_town_data.return_value = {"name": "The Fingers", "q": 0, "r": 0, "x": 0.5, "y": 0.5}
    repo.search_item_across_stockpiles.return_value = [
        {
            "town": "Marban Hollow",
            "stockpile_name": "Public",
            "struct_type": "Seaport",
            "quantity": 100,
            "total": 100,
            "q": 1,
            "r": 1,
            "x": 0.5,
            "y": 0.5,
            "captured_at": None,
        }
    ]
    war_service.get_hex_ownership.return_value = {
        "TheFingersHex": "COLONIAL",
        "EndlessShoreHex": "COLONIAL",
        "MarbanHollow": "COLONIAL",
    }

    results, _ = await service.locate_item(
        guild_id=123, item="Basic Materials", from_town="The Fingers", user_faction="Colonial"
    )

    assert results is not None
    assert len(results) == 1
    assert results[0]["RouteStatus"] == "SAFE"
    assert "RoutePath" in results[0]
