# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.
"""Service for managing stockpile data, OCR ingestion, and requisition logic."""

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from hexmaster.services.routing_service import RoutingService
from hexmaster.utils.geo_utils import calculate_distance


class StockpileService:
    """Orchestrates stockpile snapshots, OCR processing, and business logic."""

    def __init__(self, repo: Any, ocr_service: Any, war_service: Any = None, routing_service: Any = None) -> None:
        """Initializes the StockpileService with its dependencies."""
        self.repo = repo
        self.ocr_service = ocr_service
        self.war_service = war_service
        self.routing_service = routing_service or RoutingService()

    def get_qty_crates(self, total: float, catalog_qpc: Optional[int], per_crate: Optional[int]) -> float:
        """Calculates quantity in crates based on available metadata."""
        qpc = catalog_qpc or per_crate or 1
        return total / qpc

    async def parse_remote_image(
        self,
        guild_id: int,
        image_bytes: bytes,
        town: str,
        stockpile_name: str = "Public",
        shard: str | None = "Alpha",
    ) -> dict:
        """Parses an image using OCR and catalog lookups, returning a draft payload without committing to DB."""
        shard = shard or "Alpha"

        df = await self.ocr_service.process_image(image_bytes, town, stockpile_name)
        if df.empty:
            raise ValueError("OCR returned no data from the image.")

        first_row = df.iloc[0]
        struct_type = str(first_row.get("Structure Type", "Unknown")).strip()

        detected_stockpile = str(first_row.get("Stockpile Name", "")).strip()
        if detected_stockpile:
            stockpile_name = detected_stockpile

        code_to_details = await self.repo.get_catalog_items()

        items = []
        for _, r in df.iterrows():
            cname = str(r.get("CodeName", "")).strip()

            if cname in code_to_details:
                details = code_to_details[cname]
                real_name = details["displayname"]
                qpc = details["qty_per_crate"]

                quantity = int(r["Quantity"]) if pd.notna(r.get("Quantity")) else 0
                is_crated = str(r.get("Crated?", "")).upper() in (
                    "TRUE",
                    "YES",
                    "T",
                    "Y",
                )

                total_qty = quantity * qpc if is_crated else quantity

                items.append(
                    {
                        "code_name": cname,
                        "item_name": real_name,
                        "quantity": quantity,
                        "is_crated": is_crated,
                        "per_crate": qpc,
                        "total": total_qty,
                        "description": str(r.get("Description", "")).strip(),
                    }
                )

        return {
            "guild_id": guild_id,
            "shard": shard,
            "town": town,
            "struct_type": struct_type,
            "stockpile_name": stockpile_name,
            "items": items,
        }

    async def commit_snapshot_draft(
        self,
        guild_id: int,
        draft_payload: dict,
        war_number: int | None = None,
    ) -> tuple[int, int, str]:
        """Commits an approved snapshot draft to the database."""
        shard = draft_payload.get("shard", "Alpha")
        town = draft_payload["town"]
        struct_type = draft_payload["struct_type"]
        stockpile_name = draft_payload["stockpile_name"]
        items = draft_payload.get("items", [])

        snapshot_id = await self.repo.ingest_snapshot(
            guild_id, shard, town, struct_type, stockpile_name, items, war_number
        )
        return snapshot_id, len(items), struct_type

    async def process_remote_and_ingest(
        self,
        guild_id: int,
        image_bytes: bytes,
        town: str,
        stockpile_name: str,
        shard: str | None = "Alpha",
        war_number: int | None = None,
    ) -> tuple[int, int, str]:
        """Coordinates the OCR process and database ingestion in a single call."""
        draft = await self.parse_remote_image(guild_id, image_bytes, town, stockpile_name, shard)
        return await self.commit_snapshot_draft(guild_id, draft, war_number)

    async def get_requisition_comparison(
        self,
        guild_id: int,
        shipping_hub: str,
        receiving: str,
        shard: str = "Alpha",
        min_multiplier: Optional[float] = None,
        ship_struct: Optional[str] = None,
        ship_stockpile: Optional[str] = None,
        recv_struct: Optional[str] = None,
        recv_stockpile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculates logic for comparing two towns for requisition."""
        shard = shard or "Alpha"
        priority_list = await self.repo.get_priority_list(guild_id)
        if not priority_list:
            raise ValueError("Priority list is empty.")

        ship_snap, ship_items = await self.repo.get_latest_snapshot_for_town_filtered(
            guild_id, shard, shipping_hub, ship_struct, ship_stockpile
        )
        recv_snap, recv_items = await self.repo.get_latest_snapshot_for_town_filtered(
            guild_id, shard, receiving, recv_struct, recv_stockpile
        )

        if not recv_snap:
            raise ValueError(f"No snapshots found for receiving town `{receiving}`.")

        # Determine multiplier
        hubs = ["Storage Depot", "Seaport"]
        is_recv_hub = any(h in recv_snap["struct_type"] for h in hubs)
        is_ship_hub = any(h in ship_snap["struct_type"] for h in hubs) if ship_snap else False
        actual_multiplier = min_multiplier or (4.0 if is_recv_hub else 1.0)

        # Process inventories
        ship_total_map = self._build_inventory_map(ship_items)
        recv_total_map = {item["code_name"]: item["total"] for item in recv_items}

        comparison_data: List[Dict[str, Any]] = []
        handled_codenames: set[str] = set()

        self._process_priority_requisition(
            priority_list,
            actual_multiplier,
            ship_total_map,
            recv_total_map,
            is_recv_hub,
            comparison_data,
            handled_codenames,
        )
        self._process_non_priority_requisition(
            ship_items, ship_total_map, handled_codenames, is_recv_hub, comparison_data
        )

        warning = ""
        if ship_snap and not is_ship_hub:
            warning = f"⚠️ **Warning**: `{shipping_hub}` is a `{ship_snap['struct_type']}`, not a Hub.\n"

        return {
            "comparison_data": comparison_data,
            "actual_multiplier": actual_multiplier,
            "warning": warning,
            "ship_snap": ship_snap,
            "recv_snap": recv_snap,
        }

    def _build_inventory_map(self, items: List[Dict[str, Any]]) -> Dict[Tuple[str, bool], int]:
        """Builds a map of (code_name, is_crated) to total quantities."""
        total_map: Dict[Tuple[str, bool], int] = {}
        for item in items:
            key = (item["code_name"], item["is_crated"])
            total_map[key] = total_map.get(key, 0) + item["total"]
        return total_map

    def _process_priority_requisition(
        self,
        priority_list: List[Dict[str, Any]],
        multiplier: float,
        ship_map: Dict[Tuple[str, bool], int],
        recv_map: Dict[str, int],
        is_recv_hub: bool,
        comparison_data: List[Dict[str, Any]],
        handled_codenames: set[str],
    ) -> None:
        """Calculates needs for high-priority items."""
        for p in priority_list:
            codename = p["codename"]
            handled_codenames.add(codename)

            qty_per_crate = p["qty_per_crate"] or 1
            target_min_crates = (p["min_for_base_crates"] or 0) * multiplier
            held_crates = recv_map.get(codename, 0) / qty_per_crate
            lacking = target_min_crates - held_crates

            if lacking <= 0:
                continue

            avail_crates = ship_map.get((codename, True), 0) / qty_per_crate
            if avail_crates > 0:
                comparison_data.append(
                    {
                        "Item": p["name"],
                        "Avail": avail_crates,
                        "Need": lacking,
                        "is_crated": True,
                    }
                )

            if is_recv_hub:
                avail_loose = ship_map.get((codename, False), 0) / qty_per_crate
                if avail_loose > 0:
                    comparison_data.append(
                        {
                            "Item": p["name"],
                            "Avail": avail_loose,
                            "Need": lacking,
                            "is_crated": False,
                        }
                    )

            if avail_crates == 0 and (not is_recv_hub or ship_map.get((codename, False), 0) == 0):
                comparison_data.append({"Item": p["name"], "Avail": 0, "Need": lacking, "is_crated": True})

    def _process_non_priority_requisition(
        self,
        ship_items: List[Dict[str, Any]],
        ship_map: Dict[Tuple[str, bool], int],
        handled: set[str],
        is_recv_hub: bool,
        comparison_data: List[Dict[str, Any]],
    ) -> None:
        """Calculates availability for all other items in the shipping town."""
        ship_codenames = {k[0] for k in ship_map.keys()}
        non_priority = ship_codenames - handled

        item_details = {i["code_name"]: i for i in ship_items}
        codename_to_name = {i["code_name"]: i["item_name"] for i in ship_items}

        for cname in sorted(non_priority, key=lambda c: codename_to_name.get(c, c)):
            item_ref = item_details.get(cname)
            if not item_ref:
                continue

            qpc = item_ref.get("catalog_qpc")
            per_crate = item_ref.get("per_crate")

            if ship_map.get((cname, True), 0) > 0:
                comparison_data.append(
                    {
                        "Item": codename_to_name.get(cname, cname),
                        "Avail": self.get_qty_crates(ship_map[(cname, True)], qpc, per_crate),
                        "Need": 0,
                        "is_crated": True,
                    }
                )

            if is_recv_hub and ship_map.get((cname, False), 0) > 0:
                comparison_data.append(
                    {
                        "Item": codename_to_name.get(cname, cname),
                        "Avail": self.get_qty_crates(ship_map[(cname, False)], qpc, per_crate),
                        "Need": 0,
                        "is_crated": False,
                    }
                )

    async def locate_item(
        self,
        guild_id: int,
        item: str,
        from_town: str,
        shard: str | None = "Alpha",
        user_faction: str = "Colonial",
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
        """Locates an item, calculates distance, and evaluates safe routes via Dijkstra pathfinding."""
        shard = shard or "Alpha"
        ref_town = await self.repo.get_town_data(from_town)
        if not ref_town:
            raise ValueError(f"Town `{from_town}` not found.")

        results = await self.repo.search_item_across_stockpiles(guild_id, item, shard)
        if not results:
            return None, ref_town

        hex_control = {}
        if self.war_service:
            try:
                hex_control = await self.war_service.get_hex_ownership(shard)
            except Exception as e:
                print(f"Failed to fetch hex ownership for routing: {e}")

        processed_results = []
        for r in results:
            dist = calculate_distance(ref_town, r)
            qty_crates = self.get_qty_crates(r["total"], r.get("catalog_qpc"), r.get("per_crate"))
            dest_town = r["town"]

            route_info = self.routing_service.find_safe_route(
                start_town_or_hex=from_town,
                end_town_or_hex=dest_town,
                hex_control=hex_control,
                user_faction=user_faction,
            )

            processed_results.append(
                {
                    "Town": dest_town,
                    "Stockpile": r["stockpile_name"],
                    "Type": r["struct_type"],
                    "Qty": qty_crates,
                    "Dist": dist,
                    "captured_at": r.get("captured_at"),
                    "RouteStatus": route_info["status"],
                    "RouteHops": route_info["hops"],
                    "RoutePath": route_info["path"],
                    "HazardHexes": route_info["hazard_hexes"],
                }
            )

        processed_results.sort(key=lambda x: x["Dist"])
        return processed_results, ref_town

    async def check_priority_deficits(self, guild_id: int, shard: str | None = "Alpha") -> list[dict]:
        """Scans town inventories against priority minimums and finds nearest safe supply hubs for deficits."""
        shard = shard or "Alpha"
        towns = await self.repo.get_towns_with_snapshots(guild_id, shard)
        priority_list = await self.repo.get_priority_list(guild_id)
        if not priority_list or not towns:
            return []

        deficits = []

        for town in towns:
            rows = await self.repo.get_latest_inventory(guild_id, shard, town)
            if not rows:
                continue

            struct_type = rows[0]["struct_type"]
            is_hub = any(h in struct_type for h in ["Storage Depot", "Seaport"])
            actual_multiplier = 4.0 if is_hub else 1.0

            held_crates_map: dict[str, float] = {}
            for r in rows:
                cname = r["code_name"]
                qpc = r.get("catalog_qpc") or r.get("per_crate") or 1
                crates = r["total"] / qpc
                held_crates_map[cname] = held_crates_map.get(cname, 0.0) + crates

            for p in priority_list:
                cname = p["codename"]
                min_crates = (p.get("min_for_base_crates") or 0) * actual_multiplier
                held = held_crates_map.get(cname, 0.0)
                if min_crates > 0 and held < min_crates:
                    deficit_amt = min_crates - held

                    # Search nearest supply
                    locate_res, _ = await self.locate_item(guild_id, p["name"], town, shard)
                    nearest_supply = None
                    if locate_res:
                        safe_options = [
                            x for x in locate_res if x["RouteStatus"] in ("SAFE", "HAZARD") and x["Qty"] > 0
                        ]
                        if safe_options:
                            nearest_supply = safe_options[0]

                    deficits.append(
                        {
                            "town": town,
                            "struct_type": struct_type,
                            "item_name": p["name"],
                            "codename": cname,
                            "held_crates": round(held, 1),
                            "min_crates": round(min_crates, 1),
                            "deficit_crates": round(deficit_amt, 1),
                            "nearest_supply": nearest_supply,
                        }
                    )

        return deficits

    async def check_operation_readiness(
        self, guild_id: int, template_name: str, shipping_hub: str, shard: str | None = "Alpha"
    ) -> dict:
        """Audits shipping hub inventory against an operation manifest template."""
        shard = shard or "Alpha"
        templates = await self.repo.get_operation_templates(guild_id, template_name)
        if not templates:
            raise ValueError(f"Operation template `{template_name}` not found.")

        tmpl = templates[0]
        snap, items = await self.repo.get_latest_snapshot_for_town_filtered(guild_id, shard, shipping_hub)
        if not snap:
            raise ValueError(f"No snapshots found for hub `{shipping_hub}`.")

        hub_stock_map: dict[str, float] = {}
        for i in items:
            cname = i["code_name"]
            qpc = i.get("catalog_qpc") or i.get("per_crate") or 1
            crates = i["total"] / qpc
            hub_stock_map[cname] = hub_stock_map.get(cname, 0.0) + crates

        audit_results = []
        fully_ready = True

        for req in tmpl["items"]:
            cname = req["code_name"]
            needed = req["required_crates"]
            avail = hub_stock_map.get(cname, 0.0)
            status = "🟢" if avail >= needed else ("🟡" if avail > 0 else "🔴")
            if avail < needed:
                fully_ready = False

            audit_results.append(
                {
                    "item_name": req["item_name"],
                    "required": needed,
                    "available": round(avail, 1),
                    "status": status,
                }
            )

        return {
            "template_name": tmpl["name"],
            "hub": shipping_hub,
            "fully_ready": fully_ready,
            "items": audit_results,
            "snap_captured_at": snap.get("captured_at"),
        }

    async def get_stockpile_analytics(
        self, guild_id: int, town: str, hours: int = 48, shard: str | None = "Alpha"
    ) -> dict:
        """Computes crate consumption and production burn rates over recent snapshot history."""
        shard = shard or "Alpha"
        history = await self.repo.get_snapshot_history_for_town(guild_id, town, hours, shard)
        if not history:
            return {"town": town, "hours": hours, "rates": []}

        df = pd.DataFrame([dict(r) for r in history])

        # Group by item and compute start vs end total quantity diffs
        rates = []
        for cname, group in df.groupby("code_name"):
            group = group.sort_values("captured_at")
            if len(group) < 2:
                continue

            first_row = group.iloc[0]
            last_row = group.iloc[-1]

            t_start = first_row["captured_at"]
            t_end = last_row["captured_at"]
            time_diff_hours = (t_end - t_start).total_seconds() / 3600.0
            if time_diff_hours <= 0:
                continue

            qpc = last_row.get("catalog_qpc") or last_row.get("per_crate") or 1
            crates_start = first_row["total"] / qpc
            crates_end = last_row["total"] / qpc
            delta_crates = crates_end - crates_start
            burn_rate_per_hour = delta_crates / time_diff_hours

            rates.append(
                {
                    "item_name": last_row["item_name"],
                    "start_crates": round(crates_start, 1),
                    "end_crates": round(crates_end, 1),
                    "delta_crates": round(delta_crates, 1),
                    "rate_per_hour": round(burn_rate_per_hour, 2),
                }
            )

        rates.sort(key=lambda x: x["rate_per_hour"])
        return {"town": town, "hours": hours, "rates": rates}
