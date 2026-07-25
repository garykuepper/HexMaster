# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from hexmaster.config import Settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from tabulate import tabulate


def parse_bool(x) -> bool | None:
    if pd.isna(x):
        return None
    s = str(x).strip().upper()
    if s in ("TRUE", "T", "1", "YES", "Y"):
        return True
    if s in ("FALSE", "F", "0", "NO", "N"):
        return False
    return None


async def ingest_tsv(tsv_path: str, town: str, struct_type: str, stockpile_name: str) -> int:
    """
    Inserts:
      - 1 row into stockpile_snapshots
      - N rows into snapshot_items (one per TSV line)
    Returns snapshot_id.
    """
    settings = Settings.load()
    db_url = settings.database_url

    # This script must match an async URL (postgresql+asyncpg://...) with an async engine.
    engine = create_async_engine(db_url)

    df = pd.read_csv(tsv_path, sep="\t", dtype=str).fillna("")

    # Expected columns include:
    # Quantity, Name, Crated?, Per Crate, Total, Description, CodeName, etc.

    # Normalize / convert types
    df["quantity"] = pd.to_numeric(df.get("Quantity", ""), errors="coerce").astype("Int64")
    df["per_crate"] = pd.to_numeric(df.get("Per Crate", ""), errors="coerce").astype("Int64")
    df["total"] = pd.to_numeric(df.get("Total", ""), errors="coerce").astype("Int64")
    df["is_crated"] = df.get("Crated?", "").map(parse_bool)

    captured_at = datetime.now(timezone.utc)

    town = town.strip()
    struct_type = struct_type.strip()
    stockpile_name = (stockpile_name or "").strip() or "Public"

    async with engine.begin() as conn:
        # 1. Fetch valid keys from the catalog to prevent Foreign Key violations
        catalog_res = await conn.execute(text("SELECT codename, displayname FROM catalog_items"))
        valid_keys = {(row.codename, row.displayname) for row in catalog_res}

        snapshot_id = await conn.execute(
            text(
                """
                INSERT INTO stockpile_snapshots (town, struct_type, stockpile_name, captured_at)
                VALUES (:town, :struct_type, :stockpile_name, :captured_at)
                RETURNING id
                """
            ),
            {
                "town": town,
                "struct_type": struct_type,
                "stockpile_name": stockpile_name,
                "captured_at": captured_at,
            },
        )
        snapshot_id = snapshot_id.scalar_one()

        rows: list[dict] = []
        for _, r in df.iterrows():
            code_name = r.get("CodeName", "").strip()
            item_name = r.get("Name", "").strip()

            if not code_name or not item_name:
                continue  # skip malformed lines

            # 2. Skip items not present in the master catalog
            if (code_name, item_name) not in valid_keys:
                print(f"Warning: Skipping {item_name} ({code_name}) - not found in catalog_items.")
                continue

            rows.append(
                {
                    "snapshot_id": snapshot_id,
                    "code_name": code_name,
                    "item_name": item_name,
                    "quantity": None if pd.isna(r["quantity"]) else int(r["quantity"]),
                    "is_crated": r["is_crated"],
                    "per_crate": None if pd.isna(r["per_crate"]) else int(r["per_crate"]),
                    "total": None if pd.isna(r["total"]) else int(r["total"]),
                    "description": r.get("Description", "").strip(),
                }
            )

        if rows:
            await conn.execute(
                text(
                    """
                    INSERT INTO snapshot_items
                    (snapshot_id, code_name, item_name, quantity, is_crated, per_crate, total, description)
                    VALUES (:snapshot_id, :code_name, :item_name, :quantity, :is_crated, :per_crate, :total,
                            :description)
                    """
                ),
                rows,
            )

    await engine.dispose()
    return int(snapshot_id)


SQL_LATEST_ITEMS_PER_KEY_FOR_TOWN = """
SELECT
  snapshot_items.item_name,
  snapshot_items.code_name,
  snapshot_items.quantity,
  snapshot_items.is_crated,
  stockpile_snapshots.captured_at
FROM snapshot_items
LEFT JOIN stockpile_snapshots ON snapshot_items.snapshot_id = stockpile_snapshots.id
WHERE stockpile_snapshots.town = :town
AND snapshot_items.item_name || snapshot_items.code_name || stockpile_snapshots.captured_at IN (
  SELECT
    snapshot_items.item_name || snapshot_items.code_name || MAX(stockpile_snapshots.captured_at)
  FROM snapshot_items
  LEFT JOIN stockpile_snapshots ON snapshot_items.snapshot_id = stockpile_snapshots.id
  WHERE stockpile_snapshots.town = :town
  GROUP BY
    snapshot_items.item_name,
    snapshot_items.code_name
)
"""


async def fetch_latest_items_for_town(town: str) -> list[dict]:
    settings = Settings.load()
    engine = create_async_engine(settings.database_url)

    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(SQL_LATEST_ITEMS_PER_KEY_FOR_TOWN),
                {"town": town},
            )
            rows = [dict(row) for row in result.mappings()]  # convert RowProxy -> dict
            return rows
    finally:
        await engine.dispose()


async def main() -> None:
    town = "Tine"

    # Calculate the path relative to this script's location
    # This script is in /scripts, so we go up one level and then into /data
    script_dir = Path(__file__).parent
    tsv_path = script_dir.parent / "data" / f"Foxhole Logi Tool - {town}.tsv"

    if not tsv_path.exists():
        print(f"Error: TSV file not found at: {tsv_path.absolute()}")
        return

    snapshot_id = await ingest_tsv(
        tsv_path=str(tsv_path),
        town=town,
        struct_type="Seaport",
        stockpile_name="Public",
    )
    print(f"Inserted snapshot_id={snapshot_id}")

    rows = await fetch_latest_items_for_town(town=town)
    print(f"Latest items in {town}:\n{tabulate(rows, headers='keys')}")


if __name__ == "__main__":
    asyncio.run(main())
