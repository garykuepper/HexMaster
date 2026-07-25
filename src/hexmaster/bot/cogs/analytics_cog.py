# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import discord
from discord import app_commands
from discord.ext import commands

from hexmaster.services.stockpile_service import StockpileService
from hexmaster.utils.discord_utils import render_and_truncate_table, send_error


class AnalyticsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.repo = getattr(bot, "repo")
        self.service = StockpileService(
            repo=self.repo,
            ocr_service=getattr(bot, "ocr_service"),
            war_service=getattr(bot, "war_service", None),
        )
        self.settings_repo = getattr(bot, "settings_repo")

    @app_commands.command(name="analytics", description="View crate burn rates and production trends over time")
    @app_commands.describe(town="Town Name", hours="Historical timeframe in hours (default: 48)")
    async def view_analytics(self, interaction: discord.Interaction, town: str, hours: int = 48) -> None:
        guild_id = interaction.guild_id
        if not guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        await interaction.response.defer(ephemeral=True)
        try:
            config = await self.settings_repo.get_config(guild_id)
            shard = config.shard if config else "Alpha"

            res = await self.service.get_stockpile_analytics(guild_id, town, hours, shard)
            if not res["rates"]:
                return await send_error(
                    interaction, f"Insufficient historical snapshot data for `{town}` over the last {hours} hours."
                )

            rows = []
            for r in res["rates"]:
                rate_str = f"{r['rate_per_hour']:+.2f}/h"
                if r["rate_per_hour"] < 0:
                    trend = "🔻 CONSUMING"
                elif r["rate_per_hour"] > 0:
                    trend = "🟢 PRODUCING"
                else:
                    trend = "➖ STABLE"
                rows.append(
                    [
                        r["item_name"][:18],
                        f"{r['start_crates']:g}",
                        f"{r['end_crates']:g}",
                        f"{r['delta_crates']:+g}",
                        rate_str,
                        trend,
                    ]
                )

            title = f"Stockpile Consumption & Burn Rates — {town.title()} ({hours}h Window)"
            await render_and_truncate_table(
                interaction,
                rows,
                ["Item Name", "Start", "End", "Delta", "Burn Rate", "Trend"],
                title,
                as_embed=True,
            )
        except Exception as e:
            await send_error(interaction, f"Error computing analytics: {str(e)}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AnalyticsCog(bot))
