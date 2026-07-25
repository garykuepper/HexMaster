from unittest.mock import patch

import pytest

from hexmaster.bot.main import HexMasterBot
from hexmaster.config import Settings


@pytest.mark.asyncio
async def test_bot_cog_loading():
    """Test that cogs can be loaded without errors."""
    # Mock settings
    settings = Settings(
        discord_token="fake_token",
        database_url="sqlite+aiosqlite:///:memory:",
        ocr_url="http://fake-ocr",
        warapi_base_url="http://fake-war",
    )

    # Patch discord elements
    with (
        patch("discord.Object"),
        patch("discord.ext.commands.Bot.start"),
        patch("hexmaster.db.init.init_db"),
    ):
        bot = HexMasterBot(settings)

        # Manually load extensions to verify they can be imported and initialized
        extensions = [
            "hexmaster.bot.cogs.stockpile_cog",
            "hexmaster.bot.cogs.health",
            "hexmaster.bot.cogs.priority_cog",
        ]

        for ext in extensions:
            await bot.load_extension(ext)

        # Check for registered cogs (case-sensitive)
        cog_names = bot.cogs.keys()
        assert "StockpileCog" in cog_names
        assert "HealthCog" in cog_names
        assert "PriorityCog" in cog_names
