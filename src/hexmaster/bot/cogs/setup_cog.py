# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.
"""Cog for server-specific configuration and setup tasks."""

from pathlib import Path
from typing import Optional

import discord
import pandas as pd
from discord import app_commands
from discord.ext import commands

from hexmaster.db.repositories.settings_repository import SettingsRepository
from hexmaster.utils.discord_utils import send_error, send_success


class SetupCog(commands.Cog):
    """Cog for bot configuration and administrative setup."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initializes the SetupCog."""
        self.bot = bot
        self.repo = getattr(bot, "repo")
        self.settings_repo = SettingsRepository(self.repo.engine)
        self.war_service = getattr(bot, "war_service")

    setup_group = app_commands.Group(
        name="setup",
        description="Configure the bot for your server",
        default_permissions=discord.Permissions(administrator=True),
    )

    @setup_group.command(name="config", description="Set your server's faction and shard")
    @app_commands.describe(
        faction="Your faction (Colonial or Warden)",
        shard="The shard you are playing on (Alpha, Bravo, or Charlie)",
    )
    @app_commands.choices(
        faction=[
            app_commands.Choice(name="Colonial", value="Colonial"),
            app_commands.Choice(name="Warden", value="Warden"),
        ],
        shard=[
            app_commands.Choice(name="Alpha", value="Alpha"),
            app_commands.Choice(name="Bravo", value="Bravo"),
            app_commands.Choice(name="Charlie", value="Charlie"),
        ],
    )
    async def configure(
        self,
        interaction: discord.Interaction,
        faction: Optional[str] = None,
        shard: Optional[str] = None,
    ) -> None:
        """Updates the server configuration."""
        if not interaction.guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        await interaction.response.defer(ephemeral=True)
        try:
            await self.settings_repo.upsert_config(interaction.guild_id, faction=faction, shard=shard)

            msg = "Configuration updated!"
            if faction:
                msg += f"\nFaction: **{faction}**"
            if shard:
                msg += f"\nShard: **{shard}**"

            await send_success(interaction, msg)
        except Exception as e:
            await send_error(interaction, f"Error updating configuration: {e}")

    @setup_group.command(name="priorities", description="Load default priorities for your server")
    @app_commands.describe(template="The priority template to load")
    @app_commands.choices(
        template=[
            app_commands.Choice(name="Standard Logistics", value="standard"),
            app_commands.Choice(name="Clear All", value="clear"),
        ]
    )
    async def load_priorities(self, interaction: discord.Interaction, template: str) -> None:
        """Loads a priority template or clears existing priorities."""
        if not interaction.guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        await interaction.response.defer(ephemeral=True)
        try:
            if template == "clear":
                await self.repo.delete_all_priorities(interaction.guild_id)
                return await send_success(interaction, "Cleared all priorities for this server.")

            if template == "standard":
                await self._load_standard_priorities(interaction.guild_id)
                await send_success(interaction, "Loaded standard logistics priorities from template.")

        except Exception as e:
            await send_error(interaction, f"Error loading priorities: {e}")

    async def _load_standard_priorities(self, guild_id: int) -> None:
        """Loads priorities from the shared Priority.csv file."""
        # Check both potential paths
        csv_path = Path("data/Priority.csv")
        if not csv_path.exists():
            csv_path = Path("data/core/Priority.csv")

        if not csv_path.exists():
            raise FileNotFoundError("Priority template file not found.")

        df = pd.read_csv(csv_path)
        for _, row in df.iterrows():
            await self.repo.upsert_priority_item(
                guild_id=guild_id,
                codename=row["CodeName"],
                name=row["Name"],
                qty_per_crate=int(row["Qty per Crate"]),
                min_for_base_crates=(
                    int(row["Min For Base (crates)"]) if pd.notna(row["Min For Base (crates)"]) else None
                ),
                priority=float(row["Priority"]),
            )

    @setup_group.command(name="cleanup_commands", description="Clear legacy guild-specific commands")
    async def cleanup_commands(self, interaction: discord.Interaction) -> None:
        """Removes all commands synced specifically to this guild to resolve duplicates."""
        if not interaction.guild:
            return await send_error(interaction, "This command can only be used in a server.")

        await interaction.response.defer(ephemeral=True)
        try:
            self.bot.tree.clear_commands(guild=interaction.guild)
            await self.bot.tree.sync(guild=interaction.guild)
            await send_success(
                interaction,
                "Guild commands cleared. Global commands will remain available.",
            )
        except Exception as e:
            await send_error(interaction, f"Error cleaning up commands: {e}")


async def setup(bot: commands.Bot) -> None:
    """Standard setup function for Discord extensions."""
    await bot.add_cog(SetupCog(bot))
