# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio
import inspect
import time
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from hexmaster.bot.views.ocr_review_view import OCRReviewView, build_review_embed
from hexmaster.db.repositories.settings_repository import SettingsRepository
from hexmaster.services.ocr_service import OCRServiceError
from hexmaster.services.stockpile_service import StockpileService
from hexmaster.utils.datetime_utils import get_age_str
from hexmaster.utils.discord_utils import (
    render_and_truncate_table,
    send_error,
    send_success,
)


class StockpileCog(commands.Cog):
    """Handles commands for reporting and viewing stockpile snapshot data."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initializes the StockpileCog with its dependencies and local cache."""
        self.bot = bot
        self.repo = getattr(bot, "repo")

        # Initialize business service
        self.service = StockpileService(
            repo=self.repo,
            ocr_service=getattr(bot, "ocr_service"),
            war_service=getattr(bot, "war_service", None),
        )

        self.war_service = self.service.war_service
        self.settings = getattr(bot, "settings", None)
        self.settings_repo = SettingsRepository(self.repo.engine)

        # Cache for autocomplete results (cache_key -> (timestamp, list_of_strings))
        self._autocomplete_cache: Dict[str, Tuple[float, List[str]]] = {}

    async def _get_shard(self, guild_id: Optional[int]) -> str:
        """Fetches the configured shard for a guild, defaulting to Alpha."""
        if not guild_id:
            return "Alpha"
        config = await self.settings_repo.get_config(guild_id)
        return (config.shard or "Alpha") if config else "Alpha"

    async def _get_cached_town_choices(
        self, current: str, cache_key: str, fetch_func: Any
    ) -> List[app_commands.Choice[str]]:
        """Helper to handle caching and filtering for town autocomplete."""
        now = time.time()

        if cache_key in self._autocomplete_cache:
            timestamp, cached_towns = self._autocomplete_cache[cache_key]
            if now - timestamp < 60:
                return self._filter_choices(current, cached_towns)

        # Fetch fresh data
        try:
            towns = await (fetch_func() if inspect.iscoroutinefunction(fetch_func) else asyncio.to_thread(fetch_func))
            self._autocomplete_cache[cache_key] = (now, towns)
            return self._filter_choices(current, towns)
        except Exception as e:
            print(f"Autocomplete error for {cache_key}: {e}")
            return []

    def _filter_choices(self, current: str, items: List[str]) -> List[app_commands.Choice[str]]:
        """Filters a list of strings into a list of discord.py Choices."""
        search = current.lower().strip()
        choices = []
        for item in items:
            if not item:
                continue
            name = str(item)
            if not search or search in name.lower():
                choices.append(app_commands.Choice(name=name[:100], value=name[:100]))
            if len(choices) >= 25:
                break
        return choices

    async def _get_cached_choices(
        self, current: str, cache_key: str, fetch_func: Any, *args: Any
    ) -> List[app_commands.Choice[str]]:
        """Helper to handle caching and filtering for general autocomplete."""
        now = time.time()
        f_key = f"{cache_key}:{':'.join(map(str, args))}" if args else cache_key

        if f_key in self._autocomplete_cache:
            ts, cached = self._autocomplete_cache[f_key]
            if now - ts < 30:
                return self._filter_choices(current, cached)

        try:
            items = await (
                fetch_func(*args) if inspect.iscoroutinefunction(fetch_func) else asyncio.to_thread(fetch_func, *args)
            )
            self._autocomplete_cache[f_key] = (now, items)
            return self._filter_choices(current, items)
        except Exception as e:
            print(f"Autocomplete error for {f_key}: {e}")
            return []

    @app_commands.command(name="report", description="File an Intelligence Report (upload screenshot)")
    @app_commands.describe(image="Stockpile screenshot", town="Town Name", stockpile="Stockpile Name")
    async def report(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        town: str,
        stockpile: str = "Public",
    ) -> None:
        """Processes an image report and ingests items into the database."""
        guild_id = interaction.guild_id
        if not guild_id:
            await send_error(interaction, "This command can only be used in a server.")
            return

        if not image.content_type or not image.content_type.startswith("image/"):
            await send_error(interaction, "Please upload a valid image file.")
            return

        await interaction.response.defer(ephemeral=True)
        try:
            image_bytes = await image.read()
            shard = await self._get_shard(guild_id)
            war_number = await self._get_war_number(shard)

            draft = await self.service.parse_remote_image(guild_id, image_bytes, town, stockpile, shard)
            embed = build_review_embed(draft)
            view = OCRReviewView(
                service=self.service,
                guild_id=guild_id,
                draft_payload=draft,
                war_number=war_number,
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except OCRServiceError as e:
            await self._handle_ocr_error(interaction, e)
        except Exception as e:
            await send_error(interaction, f"Error during upload: {str(e)}")

    async def _get_war_number(self, shard: str) -> Optional[int]:
        """Utility to fetch the current war number for a given shard."""
        if not self.war_service:
            return None
        war_num = await self.war_service.get_current_war_number(shard)
        return int(war_num) if war_num is not None else None

    async def _handle_ocr_error(self, interaction: discord.Interaction, e: OCRServiceError) -> None:
        """Centralized error handling for OCR-specific failures."""
        print(f"OCR Service Error: {e.message}\nDetails: {e.technical_details}")
        await send_error(
            interaction,
            (
                f"**OCR Service Error**\n{e.message}\n\n"
                "*Transient errors are common during high load. Please try again in a few minutes.*"
            ),
            title="OCR Failure",
        )

    @report.autocomplete("town")
    async def report_town_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._get_cached_town_choices(current, "all_towns", self.repo.get_all_towns)

    @app_commands.command(name="inventory", description="View the Inventory for a specific town")
    @app_commands.describe(town="Town Name", structure="Structure Type", stockpile="Stockpile Name")
    async def view_inventory(
        self,
        interaction: discord.Interaction,
        town: str,
        structure: Optional[str] = None,
        stockpile: Optional[str] = None,
    ) -> None:
        """Displays a formatted table of items in a specified town's stockpile."""
        if not interaction.guild_id:
            await send_error(interaction, "This command can only be used in a server.")
            return

        town_input = town.strip() if town else ""
        if not town_input:
            await send_error(interaction, "Town is required.")
            return

        await self._send_inventory_results(interaction, interaction.guild_id, town_input, structure, stockpile)

    async def _send_inventory_results(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        town_name: str,
        structure: str | None = None,
        stockpile: str | None = None,
        success_msg: str | None = None,
    ) -> None:
        """Reusable helper to fetch inventory and render table."""
        shard = await self._get_shard(guild_id)
        rows = await self.repo.get_latest_inventory(guild_id, shard, town_name, structure, stockpile)

        if not rows:
            filter_msg = f" (filtered by `{structure}`/ `{stockpile}`)" if structure or stockpile else ""
            await send_error(interaction, f"No snapshots found for `{town_name}`{filter_msg}.")
            return

        priority_list = await self.repo.get_priority_list(guild_id)
        priority_map = {p["codename"]: p for p in priority_list}

        self._sort_inventory_rows(rows, priority_map)
        table_rows = self._format_inventory_table_rows(rows, priority_map)

        title = await self._generate_inventory_title(guild_id, rows, town_name, stockpile)
        if success_msg:
            title = f"{success_msg}\n{title}"

        await render_and_truncate_table(interaction, table_rows, ["Item", "Qty", "Need", "S"], title, as_embed=True)

    def _sort_inventory_rows(self, rows: List[Dict[str, Any]], priority_map: Dict[str, Dict[str, Any]]) -> None:
        """Sorts inventory rows by priority, then quantity, then name."""

        def sort_key(r: Dict[str, Any]) -> Tuple[float, float, str]:
            p_data = priority_map.get(r["code_name"])
            priority_val = p_data["priority"] if p_data else 9999
            qty_crates = self.service.get_qty_crates(r["total"], r.get("catalog_qpc"), r.get("per_crate"))
            return (priority_val, -qty_crates, (r.get("item_name") or "").lower())

        rows.sort(key=sort_key)

    def _format_inventory_table_rows(
        self, rows: List[Dict[str, Any]], priority_map: Dict[str, Dict[str, Any]]
    ) -> List[List[str]]:
        """Transforms raw inventory data into formatted strings for table display."""
        table_rows = []
        is_hub = any(h in rows[0]["struct_type"] for h in ["Storage Depot", "Seaport"])

        for r in rows:
            qty = self.service.get_qty_crates(r["total"], r.get("catalog_qpc"), r.get("per_crate"))
            p_data = priority_map.get(r["code_name"])

            min_val = p_data.get("min_for_base_crates", 0) if p_data else 0
            status = "🟢" if (p_data and qty >= min_val) else ("🔴" if p_data else " ")
            need_val = max(0, min_val - qty) if p_data else 0

            tag = " (itm)" if is_hub and not r["is_crated"] else ""
            name = (r["item_name"] or "Unknown")[:20].strip()
            if len(r["item_name"] or "") > 20:
                name += "..."

            table_rows.append(
                [
                    f"{name}{tag}",
                    f"{round(qty, 1):g}",
                    f"{round(need_val, 1):g}" if need_val > 0 else "-",
                    status,
                ]
            )
        return table_rows

    async def _generate_inventory_title(
        self,
        guild_id: int,
        rows: List[Dict[str, Any]],
        town_input: str,
        stockpile_filter: Optional[str],
    ) -> str:
        """Creates a detailed title string including age, war number, and warnings."""
        pretty_name = rows[0].get("pretty_town") or town_input.title()
        war_num = rows[0].get("war_number")
        oldest_snapshot = min(r["captured_at"] for r in rows if r.get("captured_at"))

        title = f"{pretty_name} ({get_age_str(oldest_snapshot)})"
        if war_num:
            title += f" (War {war_num})"
        if stockpile_filter:
            title += f" (Filter: {stockpile_filter})"

        shard = await self._get_shard(guild_id)
        current_war = await self._get_war_number(shard)
        if war_num and current_war and war_num < current_war:
            title += f"\n⚠️ **Warning: Data from past war (War {war_num})**"

        return title

    @view_inventory.autocomplete("town")
    async def inventory_town_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_id = interaction.guild_id
        if not guild_id:
            return []
        shard = await self._get_shard(guild_id)
        return await self._get_cached_choices(
            current,
            "snapshot_towns",
            self.repo.get_towns_with_snapshots,
            guild_id,
            shard,
        )

    @view_inventory.autocomplete("structure")
    async def inventory_struct_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_id = interaction.guild_id
        town = interaction.namespace.town
        if not town or not guild_id:
            return []
        shard = await self._get_shard(guild_id)
        return await self._get_cached_choices(
            current,
            "struct_types",
            self.repo.get_struct_types_for_town,
            guild_id,
            town,
            shard,
        )

    @view_inventory.autocomplete("stockpile")
    async def inventory_stockpile_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_id = interaction.guild_id
        town = interaction.namespace.town
        struct = interaction.namespace.structure
        if not town or not guild_id:
            return []
        shard = await self._get_shard(guild_id)
        return await self._get_cached_choices(
            current,
            "stockpile_names",
            self.repo.get_stockpile_names_for_town,
            guild_id,
            town,
            struct,
            shard,
        )

    @app_commands.command(name="requisition", description="Calculate needs between two towns.")
    @app_commands.describe(
        ship_town="Shipping Town",
        ship_struct="Shipping Structure",
        ship_stockpile="Shipping Stockpile",
        recv_town="Receiving Town",
        recv_struct="Receiving Structure",
        recv_stockpile="Receiving Stockpile",
        multiplier="Multiplier",
    )
    async def requisition(
        self,
        interaction: discord.Interaction,
        ship_town: str,
        recv_town: str,
        ship_struct: Optional[str] = None,
        ship_stockpile: Optional[str] = None,
        recv_struct: Optional[str] = None,
        recv_stockpile: Optional[str] = None,
        multiplier: Optional[float] = None,
    ) -> None:
        """Compares two towns and displays an order of needed supplies."""
        if not interaction.guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        await interaction.response.defer(ephemeral=True)
        try:
            shard = await self._get_shard(interaction.guild_id)
            result = await self.service.get_requisition_comparison(
                interaction.guild_id,
                ship_town,
                recv_town,
                shard,
                multiplier,
                ship_struct,
                ship_stockpile,
                recv_struct,
                recv_stockpile,
            )

            if not result["comparison_data"]:
                return await self._handle_fulfilled_requisition(interaction, recv_town, result)

            table_rows = self._format_requisition_table_rows(result["comparison_data"])
            title = self._generate_requisition_title(ship_town, recv_town, result)

            await render_and_truncate_table(
                interaction,
                table_rows,
                ["Item", "Avail", "Need", "S"],
                title,
                as_embed=True,
            )
        except Exception as e:
            await send_error(interaction, f"Error during comparison: {str(e)}")

    async def _handle_fulfilled_requisition(
        self, interaction: discord.Interaction, town: str, res: Dict[str, Any]
    ) -> None:
        """Sends a success message when all priority needs are met."""
        msg = f"✅ `{town}` meets all priority minimums!"
        if res.get("warning"):
            msg = f"{res['warning']}\n{msg}"
        await send_success(interaction, msg, title="Requisition Order Complete")

    def _format_requisition_table_rows(self, data: List[Dict[str, Any]]) -> List[List[str]]:
        """Formats item needs and availability for the requisition table."""
        table_rows = []
        for d in data:
            status = "🔴" if d["Avail"] <= 0 else ("🟡" if d["Avail"] < d["Need"] else "🟢")
            tag = " (itm)" if not d.get("is_crated", True) else ""
            name = (d["Item"] or "Unknown")[:20].strip()
            if len(d["Item"] or "") > 20:
                name += "..."

            table_rows.append(
                [
                    f"{name}{tag}",
                    f"{round(d['Avail'], 1):g}",
                    f"{round(d['Need'], 1):g}",
                    status,
                ]
            )
        return table_rows

    def _generate_requisition_title(self, ship_town: str, recv_town: str, res: Dict[str, Any]) -> str:
        """Constructs the directional title for a requisition order."""
        ship_snap, recv_snap = res["ship_snap"], res["recv_snap"]
        s_name = ship_snap.get("pretty_town") if ship_snap else ship_town.title()
        r_name = recv_snap.get("pretty_town") if recv_snap else recv_town.title()
        s_age = f" ({get_age_str(ship_snap['captured_at'])})" if ship_snap else ""
        r_age = f" ({get_age_str(recv_snap['captured_at'])})" if recv_snap else ""

        title = f"{s_name}{s_age} ➔ {r_name}{r_age} ({res['actual_multiplier']:g}x)"
        if res.get("warning"):
            title = f"{res['warning']}\n{title}"
        return title

    @requisition.autocomplete("ship_town")
    async def requisition_ship_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_id = interaction.guild_id
        if not guild_id:
            return []
        shard = await self._get_shard(guild_id)
        war_number = await self._get_war_number(shard)
        return await self._get_cached_choices(
            current,
            "hub_towns",
            self.repo.get_towns_with_hub_snapshots,
            guild_id,
            shard,
            war_number,
        )

    @requisition.autocomplete("ship_struct")
    async def requisition_ship_struct_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_id = interaction.guild_id
        town = interaction.namespace.ship_town
        if not town or not guild_id:
            return []
        shard = await self._get_shard(guild_id)
        return await self._get_cached_choices(
            current,
            "struct_types",
            self.repo.get_struct_types_for_town,
            guild_id,
            town,
            shard,
        )

    @requisition.autocomplete("ship_stockpile")
    async def requisition_ship_stockpile_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_id = interaction.guild_id
        town = interaction.namespace.ship_town
        struct = interaction.namespace.ship_struct
        if not town or not guild_id:
            return []
        shard = await self._get_shard(guild_id)
        return await self._get_cached_choices(
            current,
            "stockpile_names",
            self.repo.get_stockpile_names_for_town,
            guild_id,
            town,
            struct,
            shard,
        )

    @requisition.autocomplete("recv_town")
    async def requisition_recv_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_id = interaction.guild_id
        if not guild_id:
            return []
        shard = await self._get_shard(guild_id)
        return await self._get_cached_choices(
            current,
            "snapshot_towns",
            self.repo.get_towns_with_snapshots,
            guild_id,
            shard,
        )

    @requisition.autocomplete("recv_struct")
    async def requisition_recv_struct_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        # Need to handle recv_town namespace specifically
        guild_id = interaction.guild_id
        town = interaction.namespace.recv_town
        if not town or not guild_id:
            return []
        shard = await self._get_shard(guild_id)
        return await self._get_cached_choices(
            current,
            "struct_types",
            self.repo.get_struct_types_for_town,
            guild_id,
            town,
            shard,
        )

    @requisition.autocomplete("recv_stockpile")
    async def requisition_recv_stockpile_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_id = interaction.guild_id
        town = interaction.namespace.recv_town
        struct = interaction.namespace.recv_struct
        if not town or not guild_id:
            return []
        shard = await self._get_shard(guild_id)
        return await self._get_cached_choices(
            current,
            "stockpile_names",
            self.repo.get_stockpile_names_for_town,
            guild_id,
            town,
            struct,
            shard,
        )

    @app_commands.command(name="locate", description="Locate an item globally.")
    @app_commands.describe(item="Item name (autocomplete)", from_town="Reference town")
    async def locate(self, interaction: discord.Interaction, item: str, from_town: str) -> None:
        """Finds where an item is stored, sorted by distance from a town."""
        guild_id = interaction.guild_id
        if not guild_id:
            await send_error(interaction, "This command can only be used in a server.")
            return

        await interaction.response.defer(ephemeral=True)
        try:
            shard = await self._get_shard(guild_id)
            config = await self.settings_repo.get_config(guild_id)
            user_faction: str = (config.faction if config and config.faction else "Colonial")

            results, ref_town = await self.service.locate_item(
                guild_id, item, from_town, shard, user_faction=user_faction
            )

            if not results:
                await send_error(interaction, f"No stockpiles found containing `{item}`.")
                return

            table_rows = []
            for d in results:
                qty = d["Qty"]
                if qty >= 50:
                    status = "🟢"
                elif qty < 10:
                    status = "🔴"
                else:
                    status = "🟡"

                route_badge = "🟢 Safe"
                if d.get("RouteStatus") == "HAZARD":
                    route_badge = "🟡 Hazard"
                elif d.get("RouteStatus") == "BLOCKED":
                    route_badge = "🔴 Blocked"

                table_rows.append(
                    [
                        d["Town"][:12],
                        d["Stockpile"][:10],
                        d["Type"][:6],
                        f"{round(qty, 1):g}",
                        f"{d['Dist']:.1f}",
                        get_age_str(d["captured_at"]),
                        status,
                        route_badge,
                    ]
                )

            title = f"Global Search: {item} (from {ref_town['name'] if ref_town else 'Unknown'})"
            await render_and_truncate_table(
                interaction,
                table_rows,
                ["Town", "Stockp", "Type", "Qty", "Hex", "Age", "S", "Route"],
                title,
                as_embed=True,
            )
        except Exception as e:
            await send_error(interaction, f"Error locating item: {str(e)}")

    @locate.autocomplete("item")
    async def locate_item_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_id = interaction.guild_id
        if not guild_id:
            return []
        shard = await self._get_shard(guild_id)
        return await self._get_cached_choices(
            current,
            "snapshot_items",
            self.repo.get_items_in_stockpiles,
            guild_id,
            shard,
        )

    @locate.autocomplete("from_town")
    async def locate_town_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._get_cached_town_choices(current, "all_towns", self.repo.get_all_towns)


async def setup(bot: commands.Bot) -> None:
    """Standard setup function for Discord extensions."""
    await bot.add_cog(StockpileCog(bot))
