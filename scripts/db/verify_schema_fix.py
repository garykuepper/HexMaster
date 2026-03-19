# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import asyncio
import os
import sys

sys.path.insert(0, "/app/src")
import hexmaster.db.init as db_init
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

print(f"📍 hexmaster.db.init file: {db_init.__file__}")


async def verify_fix():
    print("🚀 Running verification...")
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL not found")
        return

    engine = create_async_engine(db_url)

    # Run init_db to trigger schema_sync
    print("🔄 Running init_db...")
    await db_init.init_db(engine)

    async with engine.connect() as conn:
        # Check stockpile_snapshots
        print("📊 Checking 'stockpile_snapshots' columns...")
        result = await conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'stockpile_snapshots'")
        )
        columns = [row[0] for row in result]
        print(f"Columns: {columns}")

        required_snapshots = ["war_number", "guild_id"]
        for col in required_snapshots:
            if col in columns:
                print(f"✅ Column '{col}' exists")
            else:
                print(f"❌ Column '{col}' MISSING")

        # Check towns
        print("📊 Checking 'towns' columns...")
        result = await conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'towns'")
        )
        columns = [row[0] for row in result]
        print(f"Columns: {columns}")

        required_towns = ["x", "y", "marker_type"]
        for col in required_towns:
            if col in columns:
                print(f"✅ Column '{col}' exists")
            else:
                print(f"❌ Column '{col}' MISSING")

    await engine.dispose()
    print("🏁 Verification complete.")


if __name__ == "__main__":
    asyncio.run(verify_fix())
