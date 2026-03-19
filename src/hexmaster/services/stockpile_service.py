# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.
"""Service for managing stockpile data, OCR ingestion, and requisition logic."""

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from hexmaster.utils.geo_utils import calculate_distance


class StockpileService:
    """Orchestrates stockpile snapshots, OCR processing, and business logic."""

    def __init__(self, repo: Any, ocr_service: Any, war_service: Any = None) -> None:
        """Initializes the StockpileService with its dependencies."""
        self.repo = repo
        self.ocr_service = ocr_service
        self.war_service = war_service

    def get_qty_crates(self, total: float, catalog_qpc: Optional[int], per_crate: Optional[int]) -> float:
        """Calculates quantity in crates based on available metadata."""
        qpc = catalog_qpc or per_crate or 1
        return total / qpc

    async def process_remote_and_ingest(
        self,
        guild_id: int,
        image_bytes: bytes,
        town: str,
        stockpile_name: str,
        shard: str = "Alpha",
        war_number: Optional[int] = None,
    ) -> Tuple[int, int, str]:
        """Coordinates the OCR process and database ingestion."""
        shard = shard or "Alpha"

        # Town and stockpile_name are fallbacks
        df = await self.ocr_service.process_image(image_bytes, town, stockpile_name)
        if df.empty:
            raise ValueError("OCR returned no data from the image.")

        # Extract metadata from the first row (populated by OCRService)
        first_row = df.iloc[0]
        struct_type = str(first_row.get("Structure Type", "Unknown")).strip()

        # Priority: OCR Detected Name > User Fallback
        detected_stockpile = str(first_row.get("Stockpile Name", "")).strip()
        if detected_stockpile:
            stockpile_name = detected_stockpile

        # Map DataFrame rows to database item objects
        code_to_details = await self.repo.get_catalog_items()
        items = self._map_ocr_data_to_items(df, code_to_details)

        snapshot_id = await self.repo.ingest_snapshot(
            guild_id, shard, town, struct_type, stockpile_name, items, war_number
        )
        return snapshot_id, len(items), struct_type

    def _map_ocr_data_to_items(self, df: pd.DataFrame, catalog: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Maps OCR DataFrame rows to a list of item dictionaries using the catalog."""
        items = []
        for _, r in df.iterrows():
            cname = str(r.get("CodeName", "")).strip()
            if cname not in catalog:
                continue

            details = catalog[cname]
            qpc = details["qty_per_crate"]
            quantity = int(r["Quantity"]) if pd.notna(r.get("Quantity")) else 0
            is_crated = str(r.get("Crated?", "")).upper() in ("TRUE", "YES", "T", "Y")

            total_qty = quantity * qpc if is_crated else quantity

            items.append(
                {
                    "code_name": cname,
                    "item_name": details["displayname"],
                    "quantity": quantity,
                    "is_crated": is_crated,
                    "per_crate": qpc,
                    "total": total_qty,
                    "description": str(r.get("Description", "")).strip(),
                }
            )
        return items

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
        self, guild_id: int, item: str, from_town: str, shard: str = "Alpha"
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
        """Locates an item and calculates distances from a reference town."""
        shard = shard or "Alpha"
        ref_town = await self.repo.get_town_data(from_town)
        if not ref_town:
            raise ValueError(f"Town `{from_town}` not found.")

        results = await self.repo.search_item_across_stockpiles(guild_id, item, shard)
        if not results:
            return None, ref_town

        processed_results = []
        for r in results:
            dist = calculate_distance(ref_town, r)
            qty_crates = self.get_qty_crates(r["total"], r.get("catalog_qpc"), r.get("per_crate"))

            processed_results.append(
                {
                    "Town": r["town"],
                    "Stockpile": r["stockpile_name"],
                    "Type": r["struct_type"],
                    "Qty": qty_crates,
                    "Dist": dist,
                    "captured_at": r.get("captured_at"),
                }
            )

        processed_results.sort(key=lambda x: x["Dist"])
        return processed_results, ref_town
