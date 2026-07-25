# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

"""Database repository for guild-level configuration settings."""

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from hexmaster.db.models import GuildConfig


class SettingsRepository:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def get_config(self, guild_id: int) -> GuildConfig | None:
        """Fetches the configuration for a specific guild."""
        async with AsyncSession(self.engine) as session:
            stmt = select(GuildConfig).where(GuildConfig.guild_id == guild_id)
            result = await session.execute(stmt)
            return cast(GuildConfig | None, result.scalars().first())

    async def upsert_config(self, guild_id: int, faction: str | None = None, shard: str | None = None) -> None:
        """Adds or updates the configuration for a guild."""
        async with AsyncSession(self.engine) as session:
            async with session.begin():
                # Fetch existing to avoid conflicts
                stmt = select(GuildConfig).where(GuildConfig.guild_id == guild_id)
                res = await session.execute(stmt)
                config = res.scalars().first()

                if config:
                    if faction is not None:
                        config.faction = faction
                    if shard is not None:
                        config.shard = shard
                    # SQLAlchemy marks it as dirty automatically
                else:
                    new_config = GuildConfig(guild_id=guild_id, faction=faction, shard=shard)
                    session.add(new_config)
            await session.commit()
