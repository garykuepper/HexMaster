# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio
from pathlib import Path

import discord
from discord.ext import commands
from sqlalchemy.ext.asyncio import create_async_engine

from hexmaster.config import Settings
from hexmaster.db.init import init_db
from hexmaster.db.repositories.settings_repository import SettingsRepository
from hexmaster.db.repositories.stockpile_repository import StockpileRepository
from hexmaster.db.seed_reference import (
    seed_catalog_from_csv,
    seed_priority_from_csv,
    seed_regions_from_csv,
    seed_towns_from_csv,
)
from hexmaster.logging import configure_logging
from hexmaster.services.ocr_service import OCRService
from hexmaster.services.war_service import WarService


class HexMasterBot(commands.Bot):
    def __init__(self, settings: Settings):
        # Default intents are enough for Slash Commands
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.engine = create_async_engine(settings.database_url)

        # Dependency Injection: Initialize once, use everywhere
        self.repo = StockpileRepository(self.engine)
        self.settings_repo = SettingsRepository(self.engine)
        self.ocr_service = OCRService(settings.ocr_url)
        self.war_service = WarService(settings.warapi_base_url)

    #
    async def setup_hook(self):
        # 1. Ensure DB schema is created (Replaces manual SQL files)
        await init_db(self.engine)

        # 2. Seed database if empty
        async with self.engine.connect() as conn:
            from sqlalchemy import text

            town_count = await conn.scalar(text("SELECT COUNT(*) FROM towns"))

        if town_count == 0:
            print("🌱 Seeding database...")
            data_dir = Path("data/core")
            await seed_regions_from_csv(self.engine, data_dir / "Regions.csv")
            await seed_towns_from_csv(self.engine, data_dir / "Towns.csv")
            await seed_catalog_from_csv(self.engine, data_dir / "catalog.csv")
            await seed_priority_from_csv(self.engine, data_dir / "Priority.csv")
        else:
            print("✅ Database already seeded. Skipping initial seed.")

        # 3.
        await self.load_extension("hexmaster.bot.cogs.stockpile_cog")
        await self.load_extension("hexmaster.bot.cogs.health")
        await self.load_extension("hexmaster.bot.cogs.priority_cog")
        await self.load_extension("hexmaster.bot.cogs.setup_cog")
        await self.load_extension("hexmaster.bot.cogs.code_cog")
        await self.load_extension("hexmaster.bot.cogs.deficit_cog")
        await self.load_extension("hexmaster.bot.cogs.operation_cog")
        await self.load_extension("hexmaster.bot.cogs.analytics_cog")

        # 4. Syncing globally (Guild agnostic)
        await self.tree.sync()
        print("✅ Synced commands globally")

    async def on_ready(self):
        assert self.user is not None
        print(f"Logged in as {self.user} (ID: {self.user.id})")


async def main():
    configure_logging()
    settings = Settings.load()

    bot = HexMasterBot(settings)
    async with bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
