# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

from unittest.mock import MagicMock

import pytest
from hexmaster.bot.cogs.stockpile_cog import StockpileCog
from hexmaster.services.stockpile_service import StockpileService


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.repo = MagicMock()
    bot.settings = MagicMock()
    return bot


@pytest.fixture
def cog(mock_bot):
    return StockpileCog(mock_bot)


@pytest.fixture
def service():
    # Only need repo for init, but we are testing static/pure methods
    repo = MagicMock()
    return StockpileService(repo=repo, ocr_service=MagicMock())


def test_filter_choices(cog):
    """Test the choice filtering logic used in autocompletes."""
    items = ["Apple", "Applesauce", "Banana", "Cherry"]

    # Empty search
    choices = cog._filter_choices("", items)
    assert len(choices) == 4
    assert choices[0].name == "Apple"

    # Partial match
    choices = cog._filter_choices("app", items)
    assert len(choices) == 2
    assert choices[0].name == "Apple"
    assert choices[1].name == "Applesauce"

    # Limit check
    many_items = [f"Item {i}" for i in range(50)]
    choices = cog._filter_choices("", many_items)
    assert len(choices) == 25


def test_build_inventory_map(service):
    """Test building an inventory map from raw rows."""
    items = [
        {"code_name": "basic_ammo", "is_crated": True, "total": 100},
        {"code_name": "basic_ammo", "is_crated": False, "total": 20},
        {"code_name": "rifle", "is_crated": True, "total": 50},
        {"code_name": "basic_ammo", "is_crated": True, "total": 10},  # Duplicate key
    ]

    res = service._build_inventory_map(items)
    assert res[("basic_ammo", True)] == 110
    assert res[("basic_ammo", False)] == 20
    assert res[("rifle", True)] == 50


def test_sort_inventory_rows(cog):
    """Test sorting logic for inventory rows."""
    priority_map = {
        "alpha": {"priority": 1, "min_for_base_crates": 10},
        "beta": {"priority": 2, "min_for_base_crates": 5},
    }

    rows = [
        {
            "code_name": "beta",
            "total": 100,
            "item_name": "Beta Item",
            "catalog_qpc": 1,
            "per_crate": 1,
        },
        {
            "code_name": "alpha",
            "total": 50,
            "item_name": "Alpha Item",
            "catalog_qpc": 1,
            "per_crate": 1,
        },
        {
            "code_name": "gamma",
            "total": 10,
            "item_name": "Gamma Item",
        },  # No priority (9999)
    ]

    # Service mocking for get_qty_crates
    cog.service.get_qty_crates = MagicMock(side_effect=lambda t, q, p: t)

    cog._sort_inventory_rows(rows, priority_map)

    assert rows[0]["code_name"] == "alpha"
    assert rows[1]["code_name"] == "beta"
    assert rows[2]["code_name"] == "gamma"


def test_format_inventory_table_rows(cog):
    """Test formatting raw rows into table strings."""
    priority_map = {
        "alpha": {"priority": 1, "min_for_base_crates": 100},
    }

    rows = [
        {
            "code_name": "alpha",
            "item_name": "Alpha Item",
            "total": 50,
            "catalog_qpc": 1,
            "per_crate": 1,
            "is_crated": True,
            "struct_type": "Storage Depot",
        }
    ]

    cog.service.get_qty_crates = MagicMock(return_value=50.0)

    formatted = cog._format_inventory_table_rows(rows, priority_map)

    assert len(formatted) == 1
    # [Name, Qty, Need, S]
    assert formatted[0][0] == "Alpha Item"
    assert formatted[0][1] == "50"
    assert formatted[0][2] == "50"  # 100 - 50 = 50
    assert formatted[0][3] == "🔴"  # 50 < 100
