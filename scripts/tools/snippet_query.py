# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio

import pandas as pd
from hexmaster.config import Settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from tabulate import tabulate

SQL_LATEST_ITEMS_PER_KEY_FOR_TOWN = """
                                    WITH latest_per_key
                                             AS (SELECT DISTINCT ON (s.town, s.struct_type, s.stockpile_name) s.id,
                                                                                                              s.town,
                                                                                                              s.struct_type,
                                                                                                              s.stockpile_name,
                                                                                                              s.captured_at
                                                 FROM stockpile_snapshots s
                                                 WHERE s.town = :town
                                                 ORDER BY s.town,
                                                          s.struct_type,
                                                          s.stockpile_name,
                                                          s.captured_at DESC,
                                                          s.id DESC)
                                    SELECT l.town,
                                           l.struct_type,
                                           l.stockpile_name,
                                           l.captured_at,
                                           si.code_name,
                                           si.item_name,
                                           si.is_crated,
                                           si.quantity,
                                           si.per_crate,
                                           si.total
                                    FROM latest_per_key l
                                             JOIN snapshot_items si
                                                  ON si.snapshot_id = l.id
                                    ORDER BY l.town,
                                             l.struct_type,
                                             l.stockpile_name,
                                             si.item_name,
                                             si.is_crated DESC; \
                                    """


async def fetch_latest_items_for_town(town: str) -> list[dict]:
    settings = Settings.load()
    engine = create_async_engine(settings.database_url)

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(SQL_LATEST_ITEMS_PER_KEY_FOR_TOWN), {"town": town})
            # mappings() gives dict-like rows keyed by selected column names
            return [dict(row) for row in result.mappings().all()]
    finally:
        await engine.dispose()


async def main() -> None:
    rows = await fetch_latest_items_for_town("TheManacle")
    df = pd.DataFrame(rows)
    print(tabulate(df, headers="keys", tablefmt="psql"))


if __name__ == "__main__":
    asyncio.run(main())
