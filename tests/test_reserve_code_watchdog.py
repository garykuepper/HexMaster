from datetime import datetime, timedelta, timezone

import pytest

from hexmaster.db.repositories.stockpile_repository import StockpileRepository


@pytest.mark.asyncio
async def test_reserve_code_upsert_and_refresh(async_engine):
    repo = StockpileRepository(async_engine)
    guild_id = 111111

    # 1. Upsert code
    code_id = await repo.upsert_reserve_code(
        guild_id=guild_id,
        town="Tine",
        struct_type="Seaport",
        stockpile_name="Alpha Reserve",
        access_code="123456",
        user_id=999,
        channel_id=888,
    )
    assert code_id > 0

    codes = await repo.get_active_reserve_codes(guild_id)
    assert len(codes) == 1
    assert codes[0].access_code == "123456"
    assert codes[0].town == "tine"
    assert codes[0].alert_level == 0

    # 2. Refresh code timer
    refreshed = await repo.refresh_reserve_code(guild_id, "Tine", "Alpha Reserve")
    assert refreshed is True

    # 3. Update alert level and deactivate
    await repo.update_code_alert_level(code_id, alert_level=1)
    updated_codes = await repo.get_active_reserve_codes(guild_id)
    assert updated_codes[0].alert_level == 1

    await repo.deactivate_reserve_code(code_id)
    active_after_deactivate = await repo.get_active_reserve_codes(guild_id)
    assert len(active_after_deactivate) == 0


def test_watchdog_timer_math():
    now = datetime.now(timezone.utc)

    # 34 hours remaining
    refreshed_34h_ago = now - timedelta(hours=14)
    elapsed_34h = now - refreshed_34h_ago
    remaining_34h = (timedelta(hours=48) - elapsed_34h).total_seconds() / 3600.0
    assert 33.9 < remaining_34h < 34.1

    # 5 hours remaining (should trigger alert_level 1 warning)
    refreshed_43h_ago = now - timedelta(hours=43)
    elapsed_43h = now - refreshed_43h_ago
    remaining_5h = (timedelta(hours=48) - elapsed_43h).total_seconds() / 3600.0
    assert 4.9 < remaining_5h < 5.1
    assert remaining_5h <= 6.0

    # 1 hour remaining (should trigger alert_level 2 emergency)
    refreshed_47h_ago = now - timedelta(hours=47)
    elapsed_47h = now - refreshed_47h_ago
    remaining_1h = (timedelta(hours=48) - elapsed_47h).total_seconds() / 3600.0
    assert 0.9 < remaining_1h < 1.1
    assert remaining_1h <= 2.0
