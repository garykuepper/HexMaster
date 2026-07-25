# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import discord
from discord import app_commands
from discord.ext import commands

from hexmaster.services.stockpile_service import StockpileService
from hexmaster.utils.discord_utils import render_and_truncate_table, send_error, send_success


class OperationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.repo = getattr(bot, "repo")
        self.service = StockpileService(
            repo=self.repo,
            ocr_service=getattr(bot, "ocr_service"),
            war_service=getattr(bot, "war_service", None),
        )
        self.settings_repo = getattr(bot, "settings_repo")

    op_group = app_commands.Group(name="operation", description="Manage regiment operation loadout templates")

    @op_group.command(name="create", description="Create an operation supply manifest template")
    @app_commands.describe(
        name="Operation Template Name (e.g. Tank Push)",
        items="Comma-separated items e.g. '5x Falchion, 20x 40mm, 10x Basic Materials'",
    )
    async def create_template(self, interaction: discord.Interaction, name: str, items: str) -> None:
        guild_id = interaction.guild_id
        if not guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        await interaction.response.defer(ephemeral=True)
        try:
            catalog = await self.repo.get_catalog_items()
            name_to_code = {v["displayname"].lower(): k for k, v in catalog.items()}

            raw_entries = [x.strip() for x in items.split(",") if x.strip()]
            parsed_items = []

            for entry in raw_entries:
                parts = entry.split("x", 1)
                if len(parts) == 2 and parts[0].strip().isdigit():
                    qty = int(parts[0].strip())
                    item_str = parts[1].strip()
                else:
                    qty = 1
                    item_str = entry

                cname = name_to_code.get(item_str.lower(), item_str)
                parsed_items.append({"code_name": cname, "item_name": item_str.title(), "required_crates": qty})

            if not parsed_items:
                return await send_error(interaction, "No valid items provided in manifest string.")

            tmpl_id = await self.repo.upsert_operation_template(
                guild_id=guild_id, name=name, items_data=parsed_items, user_id=interaction.user.id
            )
            msg = f"Created Operation Template **{name}** with `{len(parsed_items)}` required items (ID: `{tmpl_id}`)."
            await send_success(interaction, msg, title="Operation Template Created")
        except Exception as e:
            await send_error(interaction, f"Error creating template: {str(e)}")

    @op_group.command(name="check", description="Audit shipping hub stock against an operation manifest")
    @app_commands.describe(name="Operation Template Name", hub="Shipping Hub Town Name")
    async def check_readiness(self, interaction: discord.Interaction, name: str, hub: str) -> None:
        guild_id = interaction.guild_id
        if not guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        await interaction.response.defer(ephemeral=True)
        try:
            config = await self.settings_repo.get_config(guild_id)
            shard = config.shard if config else "Alpha"

            res = await self.service.check_operation_readiness(guild_id, name, hub, shard)
            rows = []
            for i in res["items"]:
                rows.append([i["item_name"][:20], f"{i['required']}", f"{i['available']:g}", i["status"]])

            status_str = "🟢 FULLY READY" if res["fully_ready"] else "🔴 INCOMPLETE"
            title = f"Operation '{res['template_name']}' Readiness at {res['hub'].title()} ({status_str})"

            await render_and_truncate_table(
                interaction, rows, ["Required Item", "Needed", "Available", "Status"], title, as_embed=True
            )
        except Exception as e:
            await send_error(interaction, f"Error checking readiness: {str(e)}")

    @op_group.command(name="list", description="List all regiment operation templates")
    async def list_templates(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id
        if not guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        await interaction.response.defer(ephemeral=True)
        try:
            tmpls = await self.repo.get_operation_templates(guild_id)
            if not tmpls:
                return await send_error(interaction, "No operation templates registered.")

            rows = []
            for t in tmpls:
                summary = ", ".join(f"{i['required_crates']}x {i['item_name']}" for i in t["items"][:3])
                if len(t["items"]) > 3:
                    summary += "..."
                rows.append([t["name"], f"{len(t['items'])} items", summary])

            await render_and_truncate_table(
                interaction,
                rows,
                ["Template Name", "Item Count", "Manifest Preview"],
                "Regiment Operation Templates",
                as_embed=True,
            )
        except Exception as e:
            await send_error(interaction, f"Error listing templates: {str(e)}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OperationCog(bot))
