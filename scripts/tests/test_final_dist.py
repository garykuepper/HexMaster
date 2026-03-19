# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio
import math

from hexmaster.config import Settings
from hexmaster.db.repositories.stockpile_repository import StockpileRepository
from sqlalchemy.ext.asyncio import create_async_engine


async def verify_final_dist():
    settings = Settings.load()
    engine = create_async_engine(settings.database_url)
    repo = StockpileRepository(engine)

    # 1. Abandoned Ward (Deadlands 0,0)
    aw = await repo.get_town_data("Abandoned Ward")
    # 2. Basinhome (Basin Sionnach 0,-3)
    bh = await repo.get_town_data("Basinhome")

    print(f"Abandoned Ward: {aw}")
    print(f"Basinhome: {bh}")

    if aw and bh:
        SQRT3 = 1.73205
        # Ref-town (AW)
        x1 = aw["q"] * 1.5 + (aw["x"] - 0.5) * 2.0
        y1 = (aw["r"] + aw["q"] / 2.0) * SQRT3 + (aw["y"] - 0.5) * SQRT3

        # Target-town (BH)
        x2 = bh["q"] * 1.5 + (bh["x"] - 0.5) * 2.0
        y2 = (bh["r"] + bh["q"] / 2.0) * SQRT3 + (bh["y"] - 0.5) * SQRT3

        dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        print(f"Calculated Global Distance AW to BH: {dist:.2f}")
        print("Expected: Approx 3 * 1.732 ~= 5.20")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(verify_final_dist())
