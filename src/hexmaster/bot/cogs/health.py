# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.
"""Cog for bot health checks, system status, and administrative utilities."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import text

if TYPE_CHECKING:
    from hexmaster.db.repositories.stockpile_repository import StockpileRepository

from hexmaster.utils.datetime_utils import get_age_str
from hexmaster.utils.discord_utils import (
    EMBED_COLOR_INFO,
    render_and_truncate_table,
    send_error,
    send_success,
)


class HealthCog(commands.Cog):
    """Cog for system health monitoring and diagnostic tools."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initializes the HealthCog."""
        self.bot = bot
        self.repo: StockpileRepository = getattr(bot, "repo")

    @property
    def engine(self) -> Any:
        """Convenience property to access the database engine."""
        return getattr(self.bot, "engine")

    @app_commands.command(name="ping", description="Healthcheck and DB connectivity test.")
    @app_commands.default_permissions(administrator=True)
    async def ping(self, interaction: discord.Interaction) -> None:
        """Checks database connectivity and measures latency."""
        start_time = time.time()
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency = (time.time() - start_time) * 1000
        await send_success(
            interaction,
            f"Database connectivity active.\nLatency: `{latency:.1f}ms`",
            title="Pong",
            ephemeral=True,
        )

    @app_commands.command(name="db_stats", description="Show system database statistics.")
    @app_commands.default_permissions(administrator=True)
    async def db_stats(self, interaction: discord.Interaction) -> None:
        """Displays counts of snapshots and items in the database."""
        async with self.engine.connect() as conn:
            snapshots = await conn.scalar(text("SELECT COUNT(*) FROM stockpile_snapshots"))
            items = await conn.scalar(text("SELECT COUNT(*) FROM snapshot_items"))

        table_rows = [["Snapshots", snapshots or 0], ["Items", items or 0]]
        await render_and_truncate_table(
            interaction,
            table_rows,
            ["Stat", "Value"],
            "**System Database Statistics**",
            as_embed=True,
        )

    @app_commands.command(name="check_towns", description="Verify the towns table content.")
    @app_commands.default_permissions(administrator=True)
    async def check_towns(self, interaction: discord.Interaction) -> None:
        """Health check to see if towns are correctly seeded."""
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT t.name, r.name FROM towns t JOIN regions r ON t.region_id = r.id "
                    "ORDER BY t.name LIMIT 10"
                )
            )
            rows = result.all()
            total = await conn.scalar(text("SELECT COUNT(*) FROM towns"))

        if not rows:
            return await send_error(interaction, "The `towns` table is empty!")

        table_rows = [[r[0], r[1]] for r in rows]
        await render_and_truncate_table(
            interaction,
            table_rows,
            ["Town", "Region"],
            f"**Towns Preview (Total: {total})**",
            as_embed=True,
        )

    @app_commands.command(name="check_regions", description="Verify the regions table content.")
    @app_commands.default_permissions(administrator=True)
    async def check_regions(self, interaction: discord.Interaction) -> None:
        """Health check to see if regions are correctly seeded."""
        async with self.engine.connect() as conn:
            result = await conn.execute(text("SELECT name, q, r FROM regions ORDER BY name LIMIT 10"))
            rows = result.all()
            total = await conn.scalar(text("SELECT COUNT(*) FROM regions"))

        if not rows:
            return await send_error(interaction, "The `regions` table is empty!")

        table_rows = [[r[0], r[1], r[2]] for r in rows]
        await render_and_truncate_table(
            interaction,
            table_rows,
            ["Region", "Q", "R"],
            f"**Regions Preview (Total: {total})**",
            as_embed=True,
        )

    @app_commands.command(name="check_priority", description="Verify the priority table content.")
    @app_commands.default_permissions(administrator=True)
    async def check_priority(self, interaction: discord.Interaction) -> None:
        """Health check to see if priority list is correctly seeded."""
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name, codename, priority FROM priority ORDER BY priority LIMIT 10")
            )
            rows = result.all()
            total = await conn.scalar(text("SELECT COUNT(*) FROM priority"))

        if not rows:
            return await send_error(interaction, "The `priority` table is empty!")

        table_rows = [[r[0], r[1], f"{r[2]:g}"] for r in rows]
        await render_and_truncate_table(
            interaction,
            table_rows,
            ["Item", "Codename", "Priority"],
            f"**Priority Preview (Total: {total})**",
            as_embed=True,
        )

    @app_commands.command(name="snapshots", description="View recently uploaded snapshots")
    @app_commands.describe(limit="Number of snapshots to show (default 10, max 25)")
    @app_commands.default_permissions(administrator=True)
    async def view_snapshots(self, interaction: discord.Interaction, limit: int = 10) -> None:
        """Lists the most recent snapshots ingested into the system."""
        limit = max(1, min(limit, 25))
        await interaction.response.defer(ephemeral=True)

        try:
            guild_id = interaction.guild_id
            if not guild_id:
                await interaction.followup.send("This command can only be used in a server.")
                return

            results = await self.repo.get_latest_snapshots_summary(guild_id, shard=None, limit=limit)
            if not results:
                await interaction.followup.send("No snapshots found.")
                return

            table_rows = [
                [
                    r["id"],
                    r["pretty_town"],
                    r["struct_type"],
                    r["stockpile_name"],
                    get_age_str(r["captured_at"]),
                ]
                for r in results
            ]
            await render_and_truncate_table(
                interaction,
                table_rows,
                ["ID", "Town", "Type", "Stockpile", "Age"],
                f"Latest {len(results)} Snapshots",
                as_embed=True,
            )
        except Exception as e:
            await interaction.followup.send(f"❌ **Error fetching snapshots:** {str(e)}")

    @app_commands.command(name="system_status", description="Comprehensive system health overview.")
    @app_commands.default_permissions(administrator=True)
    async def system_status(self, interaction: discord.Interaction) -> None:
        """Displays a summary of the bot, database, and API status."""
        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(title="🌐 HexMaster System Status", color=EMBED_COLOR_INFO)

        # DB Info
        try:
            async with self.engine.connect() as conn:
                snaps = await conn.scalar(text("SELECT COUNT(*) FROM stockpile_snapshots"))
                items = await conn.scalar(text("SELECT COUNT(*) FROM snapshot_items"))
                db_st = "✅ Connected"
        except Exception:
            db_st, snaps, items = "❌ Disconnected", 0, 0
        embed.add_field(
            name="🗄️ Database",
            value=f"**Status:** {db_st}\n**Snapshots:** {snaps}\n**Items:** {items}",
            inline=True,
        )

        # War API Info
        war_st, war_num, shard = "❌ Offline", "N/A", "Alpha"
        try:
            if interaction.guild_id:
                conf = await self.bot.settings_repo.get_config(interaction.guild_id)
                shard = conf.shard if conf and conf.shard else "Alpha"
            data = await self.bot.war_service.get_war_status(shard)
            war_num, war_st = data.get("warNumber", "Unknown"), "✅ Online"
        except Exception:
            pass
        embed.add_field(
            name="⚔️ War API",
            value=f"**Status:** {war_st}\n**Shard:** {shard}\n**War:** {war_num}",
            inline=True,
        )

        # Bot Info
        embed.add_field(
            name="🤖 Bot",
            value=f"**Latency:** {round(self.bot.latency * 1000, 1)}ms\n**Guilds:** {len(self.bot.guilds)}",
            inline=True,
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="help", description="List all available commands.")
    async def help(self, interaction: discord.Interaction) -> None:
        """Displays a dynamic help menu based on user permissions."""
        is_admin = interaction.permissions.administrator
        embed = discord.Embed(title="🛠️ HexMaster Help", color=EMBED_COLOR_INFO)

        logistics = (
            "• `/report`: Upload snapshot.\n"
            "• `/inventory`: View town assets.\n"
            "• `/locate`: Search globally.\n"
            "• `/requisition`: Calculate needs."
        )
        embed.add_field(name="🚛 Logistics", value=logistics, inline=False)

        if is_admin:
            admin = "• `/system_status`, `/snapshots`, `/check_priority`, `/ping`, `/db_stats`"
            embed.add_field(name="🛡️ Admin", value=admin, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Standard setup function for Discord extensions."""
    await bot.add_cog(HealthCog(bot))
