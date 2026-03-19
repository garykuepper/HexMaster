# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio

import pandas as pd
from hexmaster.config import Settings
from hexmaster.db.models import CatalogItem
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import create_async_engine


async def seed_catalog():
    settings = Settings.load()
    engine = create_async_engine(settings.database_url)

    # Read the CSV (assuming it has columns: codename, displayname)
    df = pd.read_csv("data/core/catalog.csv")

    # Transform into dictionary list for bulk insert
    items = df.to_dict(orient="records")

    async with engine.begin() as conn:
        print(f"Injecting {len(items)} items into the catalog...")
        # This will insert or you can add logic to skip duplicates
        await conn.execute(insert(CatalogItem), items)
        print("Success!")


if __name__ == "__main__":
    asyncio.run(seed_catalog())
