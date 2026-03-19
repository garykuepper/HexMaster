# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.
"""Cog for managing the stockpile priority list for requisitions."""

import discord
from discord import app_commands
from discord.ext import commands

from hexmaster.utils.discord_utils import (
    render_and_truncate_table,
    send_error,
    send_success,
)


class PriorityCog(commands.Cog):
    """Cog for managing the stockpile priority list."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initializes the PriorityCog."""
        self.bot = bot
        self.repo = getattr(bot, "repo")

    priority_group = app_commands.Group(
        name="priority",
        description="Manage the stockpile priority list",
        default_permissions=discord.Permissions(administrator=True),
    )

    @priority_group.command(name="list", description="List all items in the priority list")
    async def list_priority(self, interaction: discord.Interaction) -> None:
        """Displays the current priority list in a table format."""
        if not interaction.guild_id:
            await send_error(interaction, "This command can only be used in a server.")
            return

        await interaction.response.defer(ephemeral=True)
        try:
            items = await self.repo.get_priority_list(interaction.guild_id)
            if not items:
                await interaction.followup.send("The priority list is currently empty.")
                return

            items.sort(key=lambda x: x["priority"])
            table_rows = [
                [
                    item["name"],
                    f"{item['qty_per_crate']}",
                    f"{item['min_for_base_crates'] or 0}",
                    f"{item['priority']:g}",
                ]
                for item in items
            ]
            await render_and_truncate_table(
                interaction,
                table_rows,
                ["Item", "QPC", "Min", "Prio"],
                "Current Priority List",
                as_embed=True,
            )
        except Exception as e:
            await send_error(interaction, f"Error listing priority: {e}")

    @priority_group.command(name="add", description="Add or update an item in the priority list")
    @app_commands.describe(
        item="The item to add (from catalog)",
        min_crates="Target minimum crates",
        priority="Priority weight (lower is higher in list)",
    )
    async def add_priority(
        self,
        interaction: discord.Interaction,
        item: str,
        min_crates: int,
        priority: float,
    ) -> None:
        """Adds or updates an item's priority settings."""
        if not interaction.guild_id:
            await send_error(interaction, "This command can only be used in a server.")
            return

        await interaction.response.defer(ephemeral=True)
        try:
            catalog_item = await self.repo.get_catalog_item_by_name(item)
            if not catalog_item:
                await send_error(interaction, f"Item `{item}` not found in catalog.")
                return

            await self.repo.upsert_priority_item(
                guild_id=interaction.guild_id,
                codename=catalog_item.codename,
                name=catalog_item.displayname,
                qty_per_crate=catalog_item.quantitypercrate or 1,
                min_for_base_crates=min_crates,
                priority=priority,
            )
            await send_success(interaction, f"Updated priority for **{catalog_item.displayname}**.")
        except Exception as e:
            await send_error(interaction, f"Error updating priority: {e}")

    @add_priority.autocomplete("item")
    async def add_priority_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Provides autocomplete for catalog items."""
        names = await self.repo.get_all_catalog_item_names()
        return [
            app_commands.Choice(name=name[:100], value=name[:100]) for name in names if current.lower() in name.lower()
        ][:25]

    @priority_group.command(name="remove", description="Remove an item from the priority list")
    @app_commands.describe(item="The item to remove")
    async def remove_priority(self, interaction: discord.Interaction, item: str) -> None:
        """Removes a specified item from the priority list."""
        if not interaction.guild_id:
            await send_error(interaction, "This command can only be used in a server.")
            return

        await interaction.response.defer(ephemeral=True)
        try:
            priority_list = await self.repo.get_priority_list(interaction.guild_id)
            matched = next((p for p in priority_list if p["name"] == item), None)

            if not matched:
                await send_error(interaction, f"Item `{item}` not found in priority list.")
                return

            await self.repo.delete_priority_item(interaction.guild_id, matched["codename"])
            await send_success(interaction, f"Removed **{item}** from priority list.")
        except Exception as e:
            await send_error(interaction, f"Error removing priority: {e}")

    @remove_priority.autocomplete("item")
    async def remove_priority_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Provides autocomplete for priority list items."""
        if not interaction.guild_id:
            return []
        priority_list = await self.repo.get_priority_list(interaction.guild_id)
        return [
            app_commands.Choice(name=p["name"][:100], value=p["name"][:100])
            for p in priority_list
            if current.lower() in p["name"].lower()
        ][:25]


async def setup(bot: commands.Bot) -> None:
    """Standard setup function for Discord extensions."""
    await bot.add_cog(PriorityCog(bot))
