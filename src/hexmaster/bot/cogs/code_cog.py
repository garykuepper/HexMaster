# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from hexmaster.utils.discord_utils import render_and_truncate_table, send_error, send_success


class CodeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.repo = getattr(bot, "repo")
        self.watchdog_loop.start()

    async def cog_unload(self) -> None:
        self.watchdog_loop.cancel()

    code_group = app_commands.Group(name="code", description="Manage private 6-digit reserve stockpile codes")

    @code_group.command(name="add", description="Register a 6-digit reserve stockpile access code")
    @app_commands.describe(
        town="Town Name",
        stockpile="Stockpile Name",
        code="6-digit Access Code",
        structure="Structure Type (Seaport or Storage Depot)",
    )
    async def add_code(
        self,
        interaction: discord.Interaction,
        town: str,
        stockpile: str,
        code: str,
        structure: str = "Seaport",
    ) -> None:
        guild_id = interaction.guild_id
        if not guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        code_clean = code.strip()
        if not code_clean.isdigit() or len(code_clean) not in (5, 6):
            return await send_error(interaction, "Access code must be a 5 or 6-digit number.")

        await interaction.response.defer(ephemeral=True)
        try:
            code_id = await self.repo.upsert_reserve_code(
                guild_id=guild_id,
                town=town,
                struct_type=structure,
                stockpile_name=stockpile,
                access_code=code_clean,
                user_id=interaction.user.id,
                channel_id=interaction.channel_id,
            )
            msg = (
                f"Registered Reserve Code `{code_clean}` for **{stockpile}** at **{town.title()}** (ID: `{code_id}`).\n"
                "48-hour expiration timer started!"
            )
            await send_success(interaction, msg, title="Reserve Stockpile Registered")
        except Exception as e:
            await send_error(interaction, f"Error registering code: {str(e)}")

    @code_group.command(name="refresh", description="Reset 48-hour timer for a reserve stockpile after in-game refresh")
    @app_commands.describe(town="Town Name", stockpile="Stockpile Name")
    async def refresh_code(self, interaction: discord.Interaction, town: str, stockpile: str) -> None:
        guild_id = interaction.guild_id
        if not guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        await interaction.response.defer(ephemeral=True)
        try:
            updated = await self.repo.refresh_reserve_code(guild_id, town, stockpile)
            if updated:
                msg = f"Reset 48-hour timer for **{stockpile}** at **{town.title()}** to 48:00:00 remaining!"
                await send_success(interaction, msg, title="Reserve Timer Refreshed")
            else:
                await send_error(interaction, f"No active reserve code found for `{stockpile}` at `{town}`.")
        except Exception as e:
            await send_error(interaction, f"Error refreshing code: {str(e)}")

    @code_group.command(name="list", description="List active reserve stockpile codes and countdown timers")
    async def list_codes(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id
        if not guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        await interaction.response.defer(ephemeral=True)
        try:
            codes = await self.repo.get_active_reserve_codes(guild_id)
            if not codes:
                return await send_error(interaction, "No active reserve codes registered for this server.")

            now = datetime.now(timezone.utc)
            table_rows = []
            for c in codes:
                refreshed_at = c.last_refreshed_at
                if refreshed_at.tzinfo is None:
                    refreshed_at = refreshed_at.replace(tzinfo=timezone.utc)

                elapsed = now - refreshed_at
                remaining = timedelta(hours=48) - elapsed
                total_secs = int(remaining.total_seconds())

                if total_secs <= 0:
                    time_str = "EXPIRED"
                    status = "🔴"
                else:
                    hours, remainder = divmod(total_secs, 3600)
                    minutes, _ = divmod(remainder, 60)
                    time_str = f"{hours}h {minutes}m"
                    status = "🔴" if hours < 2 else ("🟡" if hours < 6 else "🟢")

                table_rows.append(
                    [
                        c.town.title()[:12],
                        c.stockpile_name[:12],
                        c.access_code,
                        time_str,
                        status,
                    ]
                )

            await render_and_truncate_table(
                interaction,
                table_rows,
                ["Town", "Stockpile", "Code", "Remaining", "S"],
                "Active Reserve Stockpile Codes (48h Expiration)",
                as_embed=True,
            )
        except Exception as e:
            await send_error(interaction, f"Error listing codes: {str(e)}")

    @tasks.loop(minutes=15)
    async def watchdog_loop(self) -> None:
        """Background watchdog checking 48-hour reserve stockpile code expirations."""
        try:
            codes = await self.repo.get_active_reserve_codes(guild_id=None)
            now = datetime.now(timezone.utc)

            for c in codes:
                refreshed_at = c.last_refreshed_at
                if refreshed_at.tzinfo is None:
                    refreshed_at = refreshed_at.replace(tzinfo=timezone.utc)

                elapsed = now - refreshed_at
                remaining_hours = (timedelta(hours=48) - elapsed).total_seconds() / 3600.0

                if remaining_hours <= 0:
                    await self.repo.deactivate_reserve_code(c.id)
                elif remaining_hours <= 2.0 and c.alert_level < 2:
                    await self._send_alert(c, remaining_hours, is_emergency=True)
                    await self.repo.update_code_alert_level(c.id, 2)
                elif remaining_hours <= 6.0 and c.alert_level < 1:
                    await self._send_alert(c, remaining_hours, is_emergency=False)
                    await self.repo.update_code_alert_level(c.id, 1)
        except Exception as e:
            print(f"Error in reserve code watchdog loop: {e}")

    @watchdog_loop.before_loop
    async def before_watchdog_loop(self) -> None:
        await self.bot.wait_until_ready()

    async def _send_alert(self, code_entry, remaining_hours: float, is_emergency: bool) -> None:
        if not code_entry.alert_channel_id:
            return
        channel = self.bot.get_channel(code_entry.alert_channel_id)
        if not channel:
            return

        title = "🚨 EMERGENCY: Reserve Stockpile Expiring Soon!" if is_emergency else "⚠️ Reserve Stockpile Warning"
        color = discord.Color.red() if is_emergency else discord.Color.gold()
        hours_int = int(remaining_hours)

        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="Town", value=code_entry.town.title(), inline=True)
        embed.add_field(name="Stockpile", value=code_entry.stockpile_name, inline=True)
        embed.add_field(name="Access Code", value=f"`{code_entry.access_code}`", inline=True)
        embed.add_field(
            name="Remaining Time",
            value=f"⏳ **~{hours_int} hours remaining** before code wipes to public!",
            inline=False,
        )
        embed.set_footer(text="Use /code refresh <town> <stockpile> after refreshing in-game.")

        try:
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                await channel.send(embed=embed)
        except Exception as e:
            print(f"Failed to send expiration alert to channel {code_entry.alert_channel_id}: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CodeCog(bot))
