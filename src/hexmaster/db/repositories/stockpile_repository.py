# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from hexmaster.db.models import (
    CatalogItem,
    OperationTemplate,
    OperationTemplateItem,
    Priority,
    Region,
    ReserveStockpileCode,
    SnapshotItem,
    StockpileSnapshot,
    Town,
)


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

    async def upsert_reserve_code(
        self,
        guild_id: int,
        town: str,
        struct_type: str,
        stockpile_name: str,
        access_code: str,
        user_id: int | None = None,
        channel_id: int | None = None,
    ) -> int:
        """Registers or updates a 6-digit reserve stockpile code."""
        async with self.engine.begin() as conn:
            norm_town = self._normalize_name(town)
            norm_stockpile = stockpile_name.strip()

            # Check if active entry exists
            stmt_check = (
                select(ReserveStockpileCode.id)
                .where(ReserveStockpileCode.guild_id == guild_id)
                .where(ReserveStockpileCode.town == norm_town)
                .where(ReserveStockpileCode.stockpile_name == norm_stockpile)
                .where(ReserveStockpileCode.is_active)
            )
            res = await conn.execute(stmt_check)
            existing_id = res.scalar()

            now = datetime.now(timezone.utc)
            if existing_id:
                from sqlalchemy import update

                stmt_update = (
                    update(ReserveStockpileCode)
                    .where(ReserveStockpileCode.id == existing_id)
                    .values(
                        access_code=access_code.strip(),
                        struct_type=struct_type.strip(),
                        last_refreshed_at=now,
                        alert_level=0,
                        alert_channel_id=channel_id,
                    )
                )
                await conn.execute(stmt_update)
                return existing_id
            else:
                stmt_insert = (
                    insert(ReserveStockpileCode)
                    .values(
                        guild_id=guild_id,
                        town=norm_town,
                        struct_type=struct_type.strip(),
                        stockpile_name=norm_stockpile,
                        access_code=access_code.strip(),
                        last_refreshed_at=now,
                        created_by_user_id=user_id,
                        alert_channel_id=channel_id,
                        alert_level=0,
                        is_active=True,
                    )
                    .returning(ReserveStockpileCode.id)
                )
                res_ins = await conn.execute(stmt_insert)
                return res_ins.scalar_one()

    async def refresh_reserve_code(self, guild_id: int, town: str, stockpile_name: str) -> bool:
        """Resets the 48-hour expiration timer for a reserve code to now."""
        async with self.engine.begin() as conn:
            from sqlalchemy import update

            norm_town = self._normalize_name(town)
            norm_stockpile = stockpile_name.strip()
            now = datetime.now(timezone.utc)

            stmt = (
                update(ReserveStockpileCode)
                .where(ReserveStockpileCode.guild_id == guild_id)
                .where(ReserveStockpileCode.town == norm_town)
                .where(ReserveStockpileCode.stockpile_name == norm_stockpile)
                .where(ReserveStockpileCode.is_active)
                .values(last_refreshed_at=now, alert_level=0)
            )
            res = await conn.execute(stmt)
            return res.rowcount > 0

    async def get_active_reserve_codes(self, guild_id: int | None = None) -> list[ReserveStockpileCode]:
        """Fetches all active reserve stockpile codes for a guild (or all guilds if None)."""
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(self.engine) as session:
            stmt = select(ReserveStockpileCode).where(ReserveStockpileCode.is_active)
            if guild_id:
                stmt = stmt.where(ReserveStockpileCode.guild_id == guild_id)
            stmt = stmt.order_by(ReserveStockpileCode.last_refreshed_at)
            res = await session.execute(stmt)
            return list(res.scalars().all())

    async def update_code_alert_level(self, code_id: int, alert_level: int) -> None:
        """Updates the notification alert level (0=normal, 1=6h warning, 2=2h emergency)."""
        async with self.engine.begin() as conn:
            from sqlalchemy import update

            stmt = (
                update(ReserveStockpileCode)
                .where(ReserveStockpileCode.id == code_id)
                .values(alert_level=alert_level)
            )
            await conn.execute(stmt)

    async def deactivate_reserve_code(self, code_id: int) -> None:
        """Deactivates an expired reserve code entry."""
        async with self.engine.begin() as conn:
            from sqlalchemy import update

            stmt = update(ReserveStockpileCode).where(ReserveStockpileCode.id == code_id).values(is_active=False)
            await conn.execute(stmt)

    async def upsert_operation_template(
        self,
        guild_id: int,
        name: str,
        items_data: list[dict],
        user_id: int | None = None,
    ) -> int:
        """Creates or replaces an operation loadout template for a guild."""
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(self.engine) as session:
            async with session.begin():
                # Delete existing template if name matches
                stmt_del = (
                    select(OperationTemplate)
                    .where(OperationTemplate.guild_id == guild_id)
                    .where(OperationTemplate.name == name.strip())
                )
                res_del = await session.execute(stmt_del)
                existing = res_del.scalar_one_or_none()
                if existing:
                    await session.delete(existing)
                    await session.flush()

                template = OperationTemplate(
                    guild_id=guild_id,
                    name=name.strip(),
                    created_by_user_id=user_id,
                )
                session.add(template)
                await session.flush()
                tmpl_id = template.id

                for item in items_data:
                    item_obj = OperationTemplateItem(
                        template_id=tmpl_id,
                        code_name=item.get("code_name", ""),
                        item_name=item.get("item_name", item.get("code_name", "")),
                        required_crates=item.get("required_crates", 1),
                    )
                    session.add(item_obj)

                return tmpl_id

    async def get_operation_templates(
        self, guild_id: int, name: str | None = None
    ) -> list[dict]:
        """Fetches operation loadout templates and items for a guild."""
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(self.engine) as session:
            stmt = select(OperationTemplate).where(OperationTemplate.guild_id == guild_id)
            if name:
                stmt = stmt.where(OperationTemplate.name == name.strip())
            res = await session.execute(stmt)
            templates = res.scalars().all()

            results = []
            for t in templates:
                items_stmt = select(OperationTemplateItem).where(OperationTemplateItem.template_id == t.id)
                items_res = await session.execute(items_stmt)
                items_list = items_res.scalars().all()

                results.append(
                    {
                        "id": t.id,
                        "name": t.name,
                        "created_by_user_id": t.created_by_user_id,
                        "created_at": t.created_at,
                        "items": [
                            {
                                "code_name": i.code_name,
                                "item_name": i.item_name,
                                "required_crates": i.required_crates,
                            }
                            for i in items_list
                        ],
                    }
                )
            return results

    async def delete_operation_template(self, guild_id: int, name: str) -> bool:
        """Deletes an operation template by name."""
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(self.engine) as session:
            async with session.begin():
                stmt = (
                    select(OperationTemplate)
                    .where(OperationTemplate.guild_id == guild_id)
                    .where(OperationTemplate.name == name.strip())
                )
                res = await session.execute(stmt)
                t = res.scalar_one_or_none()
                if t:
                    await session.delete(t)
                    await session.commit()
                    return True
                return False

    async def get_snapshot_history_for_town(
        self, guild_id: int, town: str, hours: int = 48, shard: str | None = "Alpha"
    ):
        """Fetches historical snapshots and item quantities for a town over the last N hours."""
        norm_town = self._normalize_name(town)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        async with self.engine.connect() as conn:
            stmt = (
                select(
                    StockpileSnapshot.id,
                    StockpileSnapshot.captured_at,
                    StockpileSnapshot.struct_type,
                    StockpileSnapshot.stockpile_name,
                    SnapshotItem.code_name,
                    SnapshotItem.item_name,
                    SnapshotItem.quantity,
                    SnapshotItem.is_crated,
                    SnapshotItem.total,
                    CatalogItem.quantitypercrate.label("catalog_qpc"),
                    SnapshotItem.per_crate,
                )
                .join(SnapshotItem, SnapshotItem.snapshot_id == StockpileSnapshot.id)
                .join(CatalogItem, CatalogItem.codename == SnapshotItem.code_name)
                .where(StockpileSnapshot.guild_id == guild_id)
                .where(StockpileSnapshot.town == norm_town)
                .where(StockpileSnapshot.captured_at >= cutoff)
            )
            if shard:
                stmt = stmt.where(StockpileSnapshot.shard == shard)

            stmt = stmt.order_by(StockpileSnapshot.captured_at)
            res = await conn.execute(stmt)
            return res.mappings().all()
