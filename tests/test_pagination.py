from unittest.mock import AsyncMock, MagicMock

import pytest

import hexmaster.utils.discord_utils as du
from hexmaster.utils.discord_utils import render_and_truncate_table


@pytest.mark.asyncio
async def test_pagination():
    interaction = MagicMock()
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.response.is_done.return_value = False

    headers = ["Col1", "Col2"]
    rows = [[f"R{i}", f"V{i}"] for i in range(1, 51)]
    title = "Test Paging"

    captured_pages = []

    async def mock_send_response(inter, content=None, embed=None, view=None, ephemeral=True):
        if view:
            captured_pages.extend(view.pages)

    du.send_response = AsyncMock(side_effect=mock_send_response)

    await render_and_truncate_table(interaction, rows, headers, title, max_rows=20)

    assert len(captured_pages) == 3
    assert "R1" in captured_pages[0]
    assert "R20" in captured_pages[0]
    assert "R21" in captured_pages[1]
    assert "R40" in captured_pages[1]
    assert "R41" in captured_pages[2]
    assert "R50" in captured_pages[2]
