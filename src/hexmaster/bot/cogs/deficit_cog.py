# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import discord
from discord import app_commands
from discord.ext import commands, tasks

from hexmaster.services.stockpile_service import StockpileService
from hexmaster.utils.discord_utils import render_and_truncate_table, send_error


class DeficitCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.repo = getattr(bot, "repo")
        self.service = StockpileService(
            repo=self.repo,
            ocr_service=getattr(bot, "ocr_service"),
            war_service=getattr(bot, "war_service", None),
        )
        self.settings_repo = getattr(bot, "settings_repo")
        self.deficit_loop.start()

    async def cog_unload(self) -> None:
        self.deficit_loop.cancel()

    deficit_group = app_commands.Group(name="deficit", description="Monitor frontline stockpile supply deficits")

    @deficit_group.command(name="check", description="Check current supply deficits across all server stockpiles")
    async def check_deficits(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id
        if not guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        await interaction.response.defer(ephemeral=True)
        try:
            config = await self.settings_repo.get_config(guild_id)
            shard = config.shard if config else "Alpha"
            deficits = await self.service.check_priority_deficits(guild_id, shard)

            if not deficits:
                return await interaction.followup.send("✅ All monitored bases meet priority supply minimums!")

            table_rows = []
            for d in deficits:
                sup_str = "-"
                if d.get("nearest_supply"):
                    ns = d["nearest_supply"]
                    sup_str = f"{ns['Town'][:10]} ({ns['Dist']:.1f}h)"

                table_rows.append(
                    [
                        d["town"].title()[:12],
                        d["item_name"][:16],
                        f"{d['held_crates']:g}",
                        f"{d['min_crates']:g}",
                        f"{d['deficit_crates']:g}",
                        sup_str,
                    ]
                )

            await render_and_truncate_table(
                interaction,
                table_rows,
                ["Town", "Item", "Held", "Min", "Need", "Nearest Supply"],
                "🚨 Monitored Stockpile Supply Deficits",
                as_embed=True,
            )
        except Exception as e:
            await send_error(interaction, f"Error checking deficits: {str(e)}")

    @tasks.loop(minutes=30)
    async def deficit_loop(self) -> None:
        """Background loop scanning for severe supply deficits."""
        try:
            for guild in self.bot.guilds:
                config = await self.settings_repo.get_config(guild.id)
                shard = config.shard if config else "Alpha"
                deficits = await self.service.check_priority_deficits(guild.id, shard)

                critical = [d for d in deficits if d["held_crates"] == 0]
                if critical:
                    channel = guild.system_channel
                    if channel:
                        embed = discord.Embed(
                            title=f"🚨 CRITICAL SUPPLY DEFICIT ({len(critical)} Items Empty)",
                            color=discord.Color.red(),
                        )
                        lines = []
                        for c in critical[:5]:
                            lines.append(
                                f"• **{c['town'].title()}**: `{c['item_name']}` (0/{c['min_crates']} crates)"
                            )
                        embed.description = "\n".join(lines)
                        embed.set_footer(text="Run /deficit check for full report & nearest supply hubs.")
                        await channel.send(embed=embed)
        except Exception as e:
            print(f"Error in deficit watchdog loop: {e}")

    @deficit_loop.before_loop
    async def before_deficit_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DeficitCog(bot))
