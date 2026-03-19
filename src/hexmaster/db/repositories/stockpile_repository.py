# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

from datetime import datetime, timezone

from hexmaster.db.models import (
    CatalogItem,
    Priority,
    Region,
    SnapshotItem,
    StockpileSnapshot,
    Town,
)
from sqlalchemy import desc, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine


# TODO: Add docstrings
class StockpileRepository:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def get_all_towns(self) -> list[str]:
        """Fetches all valid town names from the reference table."""
        async with self.engine.connect() as conn:
            stmt = select(Town.name).order_by(Town.name)
            result = await conn.execute(stmt)
            return [row[0] for row in result.all()]

    def _normalize_name(self, name: str | None) -> str:
        """Helper to normalize town/stockpile names."""
        return name.strip().lower() if name else ""

    def _latest_snapshots_subquery(
        self,
        guild_id: int,
        shard: str | None = "Alpha",
        town: str | None = None,
        struct_type: str | None = None,
        stockpile: str | None = None,
    ):
        """Helper to find the most recent snapshot IDs for unique (town, struct, stockpile) tuples."""
        subq = (
            select(StockpileSnapshot.id)
            .distinct(
                StockpileSnapshot.town,
                StockpileSnapshot.struct_type,
                StockpileSnapshot.stockpile_name,
            )
            .where(StockpileSnapshot.guild_id == guild_id)
            .order_by(
                StockpileSnapshot.town,
                StockpileSnapshot.struct_type,
                StockpileSnapshot.stockpile_name,
                desc(StockpileSnapshot.captured_at),
                desc(StockpileSnapshot.id),
            )
        )
        if shard:
            subq = subq.where(StockpileSnapshot.shard == shard)
        if town:
            subq = subq.where(StockpileSnapshot.town == self._normalize_name(town))
        if struct_type:
            subq = subq.where(StockpileSnapshot.struct_type == struct_type.strip())
        if stockpile:
            subq = subq.where(StockpileSnapshot.stockpile_name == stockpile.strip())
        return subq

    async def get_towns_with_snapshots(self, guild_id: int, shard: str | None = "Alpha") -> list[str]:
        """Fetches unique pretty town names that already have snapshots in the DB for a guild and shard."""
        async with self.engine.connect() as conn:
            stmt = (
                select(Town.name)
                .distinct()
                .join(
                    StockpileSnapshot,
                    text("LOWER(towns.name) = stockpile_snapshots.town"),
                )
                .where(StockpileSnapshot.guild_id == guild_id)
            )
            if shard:
                stmt = stmt.where(StockpileSnapshot.shard == shard)

            stmt = stmt.order_by(Town.name)
            result = await conn.execute(stmt)
            return [row[0] for row in result.all()]

    async def get_struct_types_for_town(self, guild_id: int, town: str, shard: str | None = "Alpha") -> list[str]:
        """Fetches unique structure types for a specific town, guild, and shard."""
        async with self.engine.connect() as conn:
            stmt = (
                select(StockpileSnapshot.struct_type)
                .distinct()
                .where(StockpileSnapshot.guild_id == guild_id)
                .where(StockpileSnapshot.town == self._normalize_name(town))
            )
            if shard:
                stmt = stmt.where(StockpileSnapshot.shard == shard)

            stmt = stmt.order_by(StockpileSnapshot.struct_type)
            result = await conn.execute(stmt)
            return [row[0] for row in result.all()]

    async def get_stockpile_names_for_town(
        self,
        guild_id: int,
        town: str,
        struct_type: str | None = None,
        shard: str | None = "Alpha",
    ) -> list[str]:
        """Fetches unique stockpile names for a specific town, shard, and optional structure type."""
        async with self.engine.connect() as conn:
            stmt = (
                select(StockpileSnapshot.stockpile_name)
                .distinct()
                .where(StockpileSnapshot.guild_id == guild_id)
                .where(StockpileSnapshot.town == self._normalize_name(town))
            )
            if shard:
                stmt = stmt.where(StockpileSnapshot.shard == shard)
            if struct_type:
                stmt = stmt.where(StockpileSnapshot.struct_type == struct_type.strip())

            stmt = stmt.order_by(StockpileSnapshot.stockpile_name)
            result = await conn.execute(stmt)
            return [row[0] for row in result.all()]

    async def get_towns_with_hub_snapshots(
        self, guild_id: int, shard: str | None = "Alpha", war_number: int | None = None
    ) -> list[str]:
        """Fetches pretty town names that have at least one Seaport or Storage Depot snapshot for a guild and shard."""
        async with self.engine.connect() as conn:
            stmt = (
                select(Town.name)
                .distinct()
                .join(
                    StockpileSnapshot,
                    text("LOWER(towns.name) = stockpile_snapshots.town"),
                )
                .where(StockpileSnapshot.guild_id == guild_id)
                .where(
                    (StockpileSnapshot.struct_type.ilike("%Storage Depot%"))
                    | (StockpileSnapshot.struct_type.ilike("%Seaport%"))
                )
            )
            if shard:
                stmt = stmt.where(StockpileSnapshot.shard == shard)
            if war_number:
                stmt = stmt.where(StockpileSnapshot.war_number == war_number)

            stmt = stmt.order_by(Town.name)
            result = await conn.execute(stmt)
            return [row[0] for row in result.all()]

    async def get_catalog_items(self) -> dict[str, dict]:
        """Fetches catalog item details (displayname, qty_per_crate) for validation."""
        async with self.engine.connect() as conn:
            stmt = select(
                CatalogItem.codename,
                CatalogItem.displayname,
                CatalogItem.quantitypercrate,
            )
            result = await conn.execute(stmt)
            return {
                row.codename: {
                    "displayname": row.displayname,
                    "qty_per_crate": row.quantitypercrate or 1,
                }
                for row in result
            }

    async def ingest_snapshot(
        self,
        guild_id: int,
        shard: str,
        town: str,
        struct_type: str,
        stockpile_name: str,
        items_data: list[dict],
        war_number: int | None = None,
    ):
        """Creates a new snapshot and inserts its items in a single transaction."""
        async with self.engine.begin() as conn:
            # 1. Insert the snapshot header
            # Normalize names to avoid duplicates due to casing/spaces
            norm_town = self._normalize_name(town)
            norm_struct = struct_type.strip()
            norm_stockpile = stockpile_name.strip()

            stmt = (
                insert(StockpileSnapshot)
                .values(
                    guild_id=guild_id,
                    shard=shard,
                    town=norm_town,
                    struct_type=norm_struct,
                    stockpile_name=norm_stockpile,
                    war_number=war_number,
                    captured_at=datetime.now(timezone.utc),
                )
                .returning(StockpileSnapshot.id)
            )

            res = await conn.execute(stmt)
            snapshot_id = res.scalar_one()

            # 2. Insert items in bulk
            if items_data:
                for item in items_data:
                    item["snapshot_id"] = snapshot_id

                await conn.execute(insert(SnapshotItem), items_data)

            return snapshot_id

    async def get_latest_inventory(
        self,
        guild_id: int,
        shard: str | None = "Alpha",
        town: str | None = None,
        struct_type: str | None = None,
        stockpile: str | None = None,
    ):
        """Fetches the latest item counts for a specific town, guild, and shard."""
        async with self.engine.connect() as conn:
            subq = self._latest_snapshots_subquery(
                guild_id=guild_id,
                shard=shard,
                town=town,
                struct_type=struct_type,
                stockpile=stockpile,
            )

            # Join with SnapshotItem and Town to get actual inventory with pretty names
            stmt = (
                select(
                    StockpileSnapshot.struct_type,
                    StockpileSnapshot.stockpile_name,
                    SnapshotItem.item_name,
                    SnapshotItem.code_name,
                    SnapshotItem.quantity,
                    SnapshotItem.is_crated,
                    SnapshotItem.total,
                    StockpileSnapshot.war_number,
                    CatalogItem.quantitypercrate.label("catalog_qpc"),
                    Town.name.label("pretty_town"),
                    StockpileSnapshot.captured_at,
                )
                .join(SnapshotItem, SnapshotItem.snapshot_id == StockpileSnapshot.id)
                .join(CatalogItem, CatalogItem.codename == SnapshotItem.code_name)
                .join(Town, text("LOWER(towns.name) = stockpile_snapshots.town"))
                .where(StockpileSnapshot.id.in_(subq))
                .order_by(
                    StockpileSnapshot.stockpile_name,
                    desc(SnapshotItem.is_crated),
                    desc(SnapshotItem.quantity),
                )
            )

            result = await conn.execute(stmt)
            return result.mappings().all()

    async def get_priority_list(self, guild_id: int) -> list[dict]:
        """Fetches the full priority list from the DB for a specific guild."""
        async with self.engine.connect() as conn:
            stmt = select(Priority).where(Priority.guild_id == guild_id).order_by(Priority.priority)
            result = await conn.execute(stmt)
            return [dict(row) for row in result.mappings().all()]

    async def get_latest_snapshot_for_town_filtered(
        self,
        guild_id: int,
        shard: str | None = "Alpha",
        town: str | None = None,
        struct_type: str | None = None,
        stockpile: str | None = None,
    ):
        """Fetches the latest snapshot and its items for a specific town, guild, and shard with optional filters."""
        async with self.engine.connect() as conn:
            norm_town = self._normalize_name(town)
            # Find the latest snapshot IDs for each unique (struct, stockpile) in this town/guild
            subq = self._latest_snapshots_subquery(
                guild_id=guild_id,
                shard=shard,
                town=town,
                struct_type=struct_type,
                stockpile=stockpile,
            )

            # Fetch all items from these latest snapshots
            stmt_items = (
                select(
                    SnapshotItem.code_name,
                    SnapshotItem.item_name,
                    SnapshotItem.total,
                    SnapshotItem.per_crate,
                    SnapshotItem.is_crated,
                    CatalogItem.quantitypercrate.label("catalog_qpc"),
                )
                .join(CatalogItem, CatalogItem.codename == SnapshotItem.code_name)
                .where(SnapshotItem.snapshot_id.in_(subq))
            )
            items_res = await conn.execute(stmt_items)
            items = items_res.mappings().all()

            # Return any snapshot header as a reference, with pretty town name
            latest_snap_stmt = (
                select(
                    StockpileSnapshot.struct_type,
                    StockpileSnapshot.stockpile_name,
                    StockpileSnapshot.war_number,
                    Town.name.label("pretty_town"),
                    StockpileSnapshot.captured_at,
                )
                .join(Town, text("LOWER(towns.name) = stockpile_snapshots.town"))
                .where(StockpileSnapshot.town == norm_town)
                .where(StockpileSnapshot.guild_id == guild_id)
            )
            if shard:
                latest_snap_stmt = latest_snap_stmt.where(StockpileSnapshot.shard == shard)
            if struct_type:
                latest_snap_stmt = latest_snap_stmt.where(StockpileSnapshot.struct_type == struct_type.strip())
            if stockpile:
                latest_snap_stmt = latest_snap_stmt.where(StockpileSnapshot.stockpile_name == stockpile.strip())

            latest_snap_stmt = latest_snap_stmt.order_by(desc(StockpileSnapshot.captured_at)).limit(1)

            snap_res = await conn.execute(latest_snap_stmt)
            snapshot = snap_res.mappings().first()

            return snapshot, items

    async def search_item_across_stockpiles(self, guild_id: int, item_name: str, shard: str | None = "Alpha"):
        """Finds all latest instances of an item across all towns for a guild and shard."""
        async with self.engine.connect() as conn:
            subq = self._latest_snapshots_subquery(guild_id=guild_id, shard=shard)

            stmt = (
                select(
                    Town.name.label("town"),
                    StockpileSnapshot.struct_type,
                    StockpileSnapshot.stockpile_name,
                    SnapshotItem.quantity,
                    SnapshotItem.is_crated,
                    SnapshotItem.per_crate,
                    SnapshotItem.total,
                    CatalogItem.quantitypercrate.label("catalog_qpc"),
                    Town.x,
                    Town.y,
                    Region.q,
                    Region.r,
                    StockpileSnapshot.captured_at,
                )
                .join(SnapshotItem, SnapshotItem.snapshot_id == StockpileSnapshot.id)
                # Join towns to get the pretty name and x, y
                .join(Town, text("LOWER(towns.name) = stockpile_snapshots.town"))
                # Join regions to get q, r
                .join(Region, Region.id == Town.region_id)
                # Join catalog to get canonical crate size
                .join(CatalogItem, CatalogItem.codename == SnapshotItem.code_name)
                .where(StockpileSnapshot.id.in_(subq))
                .where(SnapshotItem.item_name == item_name)
                .order_by(Town.name)
            )

            result = await conn.execute(stmt)
            return result.mappings().all()

    async def get_latest_snapshots_summary(self, guild_id: int, shard: str | None = "Alpha", limit: int = 10):
        """Fetches a summary of the most recent snapshots across all towns for a guild and shard."""
        async with self.engine.connect() as conn:
            stmt = (
                select(
                    StockpileSnapshot.id,
                    Town.name.label("pretty_town"),
                    StockpileSnapshot.struct_type,
                    StockpileSnapshot.stockpile_name,
                    StockpileSnapshot.captured_at,
                    StockpileSnapshot.war_number,
                    StockpileSnapshot.shard,
                )
                .join(Town, text("LOWER(towns.name) = stockpile_snapshots.town"))
                .where(StockpileSnapshot.guild_id == guild_id)
            )
            if shard:
                stmt = stmt.where(StockpileSnapshot.shard == shard)

            stmt = stmt.order_by(desc(StockpileSnapshot.captured_at)).limit(limit)
            result = await conn.execute(stmt)
            return result.mappings().all()

    async def get_town_data(self, town_name: str):
        """Fetches coordinates and region offsets for a specific town (case-insensitive)."""
        async with self.engine.connect() as conn:
            from sqlalchemy import func

            stmt = (
                select(Town.name, Town.x, Town.y, Region.q, Region.r)
                .join(Region, Region.id == Town.region_id)
                .where(func.lower(Town.name) == self._normalize_name(town_name))
            )
            res = await conn.execute(stmt)
            return res.mappings().first()

    async def get_all_catalog_item_names(self) -> list[str]:
        """Fetches all item names from the catalog for autocomplete."""
        async with self.engine.connect() as conn:
            # Use DISTINCT on item_name from SnapshotItem or displayname from CatalogItem
            # CatalogItem is more robust for autocomplete
            stmt = select(CatalogItem.displayname).distinct().order_by(CatalogItem.displayname)
            result = await conn.execute(stmt)
            return [row[0] for row in result.all()]

    async def get_items_in_stockpiles(self, guild_id: int, shard: str | None = "Alpha") -> list[str]:
        """
        Fetches unique item names that are currently present in
        at least one stockpile snapshot for a guild and shard.
        """

        async with self.engine.connect() as conn:
            stmt = (
                select(SnapshotItem.item_name)
                .distinct()
                .join(StockpileSnapshot, StockpileSnapshot.id == SnapshotItem.snapshot_id)
                .where(StockpileSnapshot.guild_id == guild_id)
            )
            if shard:
                stmt = stmt.where(StockpileSnapshot.shard == shard)

            stmt = stmt.order_by(SnapshotItem.item_name)
            result = await conn.execute(stmt)
            return [row[0] for row in result.all() if row[0]]

    async def upsert_priority_item(
        self,
        guild_id: int,
        codename: str,
        name: str,
        qty_per_crate: int,
        min_for_base_crates: int | None,
        priority: float,
    ):
        """Adds or updates an item in the priority list for a specific guild."""
        async with self.engine.begin() as conn:
            from sqlalchemy.dialects.postgresql import insert

            stmt = insert(Priority).values(
                guild_id=guild_id,
                codename=codename,
                name=name,
                qty_per_crate=qty_per_crate,
                min_for_base_crates=min_for_base_crates,
                priority=priority,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[Priority.guild_id, Priority.codename],
                set_={
                    "name": name,
                    "qty_per_crate": qty_per_crate,
                    "min_for_base_crates": min_for_base_crates,
                    "priority": priority,
                },
            )
            await conn.execute(stmt)

    async def delete_priority_item(self, guild_id: int, codename: str):
        """Removes an item from the priority list for a specific guild."""
        async with self.engine.begin() as conn:
            from sqlalchemy import delete

            stmt = delete(Priority).where(Priority.guild_id == guild_id).where(Priority.codename == codename)
            await conn.execute(stmt)

    async def delete_all_priorities(self, guild_id: int):
        """Clears all items from the priority list for a specific guild."""
        async with self.engine.begin() as conn:
            from sqlalchemy import delete

            stmt = delete(Priority).where(Priority.guild_id == guild_id)
            await conn.execute(stmt)

    async def get_catalog_item_by_name(self, displayname: str):
        """Fetches a catalog item by its display name."""
        async with self.engine.connect() as conn:
            stmt = select(CatalogItem).where(CatalogItem.displayname == displayname)
            res = await conn.execute(stmt)
            return res.mappings().first()
