# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio
import inspect
import time

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
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Core data access
        self.repo = getattr(bot, "repo")

        # Initialize business service
        self.service = StockpileService(
            repo=self.repo,
            ocr_service=getattr(bot, "ocr_service"),
            war_service=getattr(bot, "war_service", None),
        )

        self.war_service = self.service.war_service
        self.settings = getattr(bot, "settings")
        self.settings_repo = SettingsRepository(self.repo.engine)

        # Cache for autocomplete results (cache_key -> (timestamp, list_of_strings))
        self._autocomplete_cache: dict[str, tuple[float, list[str]]] = {}

    async def _get_shard(self, guild_id: int | None) -> str | None:
        """Fetches the configured shard for a guild."""
        if not guild_id:
            return None
        config = await self.settings_repo.get_config(guild_id)
        return config.shard if config else "Alpha"

    async def cog_load(self) -> None:
        """Called when the cog is loaded."""
        pass  # Autocomplete warming is harder now due to guild_id being required

    async def _get_cached_town_choices(
        self, current: str, cache_key: str, fetch_func
    ) -> list[app_commands.Choice[str]]:
        """Helper to handle caching and filtering for town autocomplete."""
        now = time.time()
        try:
            if cache_key in self._autocomplete_cache:
                timestamp, cached_towns = self._autocomplete_cache[cache_key]
                if now - timestamp < 60:
                    towns = cached_towns
                else:
                    towns = await (
                        fetch_func() if inspect.iscoroutinefunction(fetch_func) else asyncio.to_thread(fetch_func)
                    )
                    self._autocomplete_cache[cache_key] = (now, towns)
            else:
                towns = await (
                    fetch_func() if inspect.iscoroutinefunction(fetch_func) else asyncio.to_thread(fetch_func)
                )
                self._autocomplete_cache[cache_key] = (now, towns)

            search = current.lower().strip()
            choices = []

            for town in towns:
                if not town:
                    continue
                town_name = str(town)
                if not search or search in town_name.lower():
                    choices.append(app_commands.Choice(name=town_name[:100], value=town_name[:100]))
                if len(choices) >= 25:
                    break
            return choices
        except Exception as e:
            print(f"Autocomplete error for {cache_key}: {e}")
            return []

    async def _get_cached_choices(
        self, current: str, cache_key: str, fetch_func, *args
    ) -> list[app_commands.Choice[str]]:
        """Helper to handle caching and filtering for general autocomplete."""
        now = time.time()
        # Decorate cache key with args if any
        full_cache_key = f"{cache_key}:{':'.join(map(str, args))}" if args else cache_key

        try:
            if full_cache_key in self._autocomplete_cache:
                timestamp, cached_items = self._autocomplete_cache[full_cache_key]
                if now - timestamp < 30:  # Shorter cache for town-specific items
                    items = cached_items
                else:
                    items = await (
                        fetch_func(*args)
                        if inspect.iscoroutinefunction(fetch_func)
                        else asyncio.to_thread(fetch_func, *args)
                    )
                    self._autocomplete_cache[full_cache_key] = (now, items)
            else:
                items = await (
                    fetch_func(*args)
                    if inspect.iscoroutinefunction(fetch_func)
                    else asyncio.to_thread(fetch_func, *args)
                )
                self._autocomplete_cache[full_cache_key] = (now, items)

            search = current.lower().strip()
            choices = []

            for item in items:
                if not item:
                    continue
                item_name = str(item)
                if not search or search in item_name.lower():
                    choices.append(app_commands.Choice(name=item_name[:100], value=item_name[:100]))
                if len(choices) >= 25:
                    break
            return choices
        except Exception as e:
            print(f"Autocomplete error for {full_cache_key}: {e}")
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
        guild_id = interaction.guild_id
        if not guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        if not image.content_type or not image.content_type.startswith("image/"):
            return await send_error(interaction, "Please upload a valid image file.")

        await interaction.response.defer(ephemeral=True)
        try:
            image_bytes = await image.read()
            shard = await self._get_shard(guild_id)
            war_number = await self.war_service.get_current_war_number(shard) if self.war_service else None

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
            print(f"OCR Service Error: {e.message}\nDetails: {e.technical_details}")
            await send_error(
                interaction,
                (
                    f"**OCR Service Error**\n{e.message}\n\n"
                    "*Transient errors are common during high load. Please try again in a few minutes.*"
                ),
                title="OCR Failure",
            )
        except Exception as e:
            print(f"General Error during report: {str(e)}")
            await send_error(interaction, f"Error during upload: {str(e)}")

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
        structure: str | None = None,
        stockpile: str | None = None,
    ) -> None:
        guild_id = interaction.guild_id
        if not guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        town_input = (town or "").strip()
        if not town_input:
            return await send_error(interaction, "Town is required.")

        await self._send_inventory_results(interaction, guild_id, town_input, structure, stockpile)

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
            return await send_error(interaction, f"No snapshots found for `{town_name}`{filter_msg}.")

        priority_list = await self.repo.get_priority_list(guild_id)
        priority_map = {p["codename"]: p for p in priority_list}

        # Sort rows: priority (asc), then qty (desc), then name (asc)
        def sort_key(r):
            p_data = priority_map.get(r["code_name"])
            priority_val = p_data["priority"] if p_data else 9999
            qty_crates = self.service.get_qty_crates(r["total"], r.get("catalog_qpc"), r.get("per_crate"))
            return (priority_val, -qty_crates, (r.get("item_name") or "").lower())

        rows.sort(key=sort_key)
        table_rows = []
        for r in rows:
            qty_crates = self.service.get_qty_crates(r["total"], r.get("catalog_qpc"), r.get("per_crate"))

            p_data = priority_map.get(r["code_name"])
            status = " "  # Default empty
            min_val = 0

            if p_data:
                min_val = p_data.get("min_for_base_crates") or 0
                if qty_crates < min_val:
                    status = "🔴"
                else:
                    status = "🟢"

            need_val = max(0, min_val - qty_crates) if p_data else 0
            # Determine tags based on location type
            # Hubs: Crates = No Tag, Loose = (itm)
            # Bases: All = No Tag
            hubs = ["Storage Depot", "Seaport"]
            is_hub = any(h in rows[0]["struct_type"] for h in hubs)

            crated_tag = ""
            if is_hub:
                if not r["is_crated"]:
                    crated_tag = " (itm)"
            else:
                # Base/other: No tags for anything, everything assumed loose/available
                pass

            # Truncate item name to 20 chars
            base_name = r["item_name"] or "Unknown"
            if len(base_name) > 20:
                base_name = base_name[:20].strip() + "..."

            table_rows.append(
                [
                    f"{base_name}{crated_tag}",
                    f"{round(qty_crates, 1):g}",
                    f"{round(need_val, 1):g}" if need_val > 0 else "-",
                    status,
                ]
            )

        pretty_name = rows[0].get("pretty_town") or town_name.title()
        war_num = rows[0].get("war_number")

        past_war_warning = ""
        if self.war_service:
            shard = await self._get_shard(guild_id)
            current_war = await self.war_service.get_current_war_number(shard)
            if war_num and current_war and war_num < current_war:
                past_war_warning = f"\n⚠️ **Warning: Data from past war (War {war_num})**"

        oldest_snapshot = min(r["captured_at"] for r in rows if r.get("captured_at"))
        age_str = get_age_str(oldest_snapshot)
        title = f"{pretty_name} [{age_str}]"
        if success_msg:
            title = f"{success_msg}\n{title}"
        if war_num and not past_war_warning:
            title += f" War {war_num}"
        if stockpile:
            title += f" (Filter: {stockpile})"
        if past_war_warning:
            title += past_war_warning

        title = f"{pretty_name} ({age_str})"
        if war_num and not past_war_warning:
            title += f" (War {war_num})"
        if stockpile:
            title += f" (Filter: {stockpile})"
        if past_war_warning:
            title += past_war_warning

        await render_and_truncate_table(interaction, table_rows, ["Item", "Qty", "Need", "S"], title, as_embed=True)

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

    @app_commands.command(name="requisition", description="Requisition Order")
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
        ship_struct: str | None = None,
        ship_stockpile: str | None = None,
        recv_struct: str | None = None,
        recv_stockpile: str | None = None,
        multiplier: float | None = None,
    ) -> None:
        guild_id = interaction.guild_id
        if not guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        await interaction.response.defer(ephemeral=True)

        try:
            shard = await self._get_shard(guild_id)
            result = await self.service.get_requisition_comparison(
                guild_id,
                ship_town,
                recv_town,
                shard,
                multiplier,
                ship_struct,
                ship_stockpile,
                recv_struct,
                recv_stockpile,
            )

            comparison_data = result["comparison_data"]
            if not comparison_data:
                msg = f"✅ `{recv_town}` meets all priority minimums!"
                if result.get("warning"):
                    msg = f"{result['warning']}\n{msg}"
                return await send_success(interaction, msg, title="Requisition Order Complete")

            table_rows = []
            for d in comparison_data:
                if d["Avail"] <= 0:
                    status = "🔴"
                elif d["Avail"] < d["Need"]:
                    status = "🟡"
                else:
                    status = "🟢"

                # Truncate item name for requisition (20 chars)
                item_name = d["Item"] or "Unknown"
                if len(item_name) > 20:
                    item_name = item_name[:20].strip() + "..."

                # Tag logic for Requisition
                # If is_crated is True, no tag.
                # If is_crated is False, add (itm) tag.
                # Note: The service layer already filters strictly for Base destinations,
                # so we can just trust the is_crated flag here.
                tag = ""
                if not d.get("is_crated", True):
                    tag = " (itm)"

                table_rows.append(
                    [
                        f"{item_name}{tag}",
                        f"{round(d['Avail'], 1):g}",
                        f"{round(d['Need'], 1):g}",
                        status,
                    ]
                )

            ship_snap, recv_snap = result["ship_snap"], result["recv_snap"]
            ship_p = ship_snap["pretty_town"] if ship_snap and ship_snap.get("pretty_town") else ship_town.title()
            recv_p = recv_snap["pretty_town"] if recv_snap and recv_snap.get("pretty_town") else recv_town.title()

            ship_age = f" ({get_age_str(ship_snap['captured_at'])})" if ship_snap else ""
            recv_age = f" ({get_age_str(recv_snap['captured_at'])})" if recv_snap else ""

            # Enhance title with filters
            filter_info = ""
            if any([ship_struct, ship_stockpile, recv_struct, recv_stockpile]):
                filters = []
                if ship_struct or ship_stockpile:
                    filters.append(f"Ship: {ship_struct or ''} {ship_stockpile or ''}")
                if recv_struct or recv_stockpile:
                    filters.append(f"Recv: {recv_struct or ''} {recv_stockpile or ''}")
                filter_info = f"\nFilters: {' | '.join(filters)}"

            title = f"{ship_p}{ship_age} ➔ {recv_p}{recv_age} ({result['actual_multiplier']:g}x)"
            if filter_info:
                title += f"\n{filter_info}"

            await render_and_truncate_table(
                interaction,
                table_rows,
                ["Item", "Avail", "Need", "S"],
                title,
                as_embed=True,
            )

        except Exception as e:
            await send_error(interaction, f"Error during comparison: {str(e)}")

    @requisition.autocomplete("ship_town")
    async def requisition_ship_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_id = interaction.guild_id
        if not guild_id:
            return []

        shard = await self._get_shard(guild_id)
        war_number = await self.war_service.get_current_war_number(shard) if self.war_service else None

        # Pass war_number to ensure we only see hubs for the current war
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

    @app_commands.command(name="locate", description="Locate an item")
    @app_commands.describe(item="Item Name", ref_town="Reference Town")
    async def locate(self, interaction: discord.Interaction, item: str, ref_town: str) -> None:
        guild_id = interaction.guild_id
        if not guild_id:
            return await send_error(interaction, "This command can only be used in a server.")

        await interaction.response.defer(ephemeral=True)

        try:
            shard = await self._get_shard(guild_id)
            config = await self.settings_repo.get_config(guild_id)
            user_faction: str = (config.faction if config and config.faction else "Colonial")

            results, ref_town_data = await self.service.locate_item(
                guild_id, item, ref_town, shard, user_faction=user_faction
            )
            if not results:
                return await send_error(interaction, f"`{item}` is not in any stockpile.")

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

            title = f"Available Stockpiles for {item}"
            if ref_town_data and ref_town_data.get("name"):
                title += f" (Ref: {ref_town_data['name']})"

            await render_and_truncate_table(
                interaction,
                table_rows,
                ["Town", "Stockp", "Type", "Qty", "Hex", "Age", "S", "Route"],
                title,
                as_embed=True,
            )

        except Exception as e:
            await send_error(interaction, f"Error during search: {str(e)}")

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
            "stockpile_items",
            self.repo.get_items_in_stockpiles,
            guild_id,
            shard,
        )

    @locate.autocomplete("ref_town")
    async def locate_town_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._get_cached_town_choices(current, "all_towns", self.repo.get_all_towns)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StockpileCog(bot))
