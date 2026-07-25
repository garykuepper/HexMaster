from unittest.mock import AsyncMock, patch

import pytest

from hexmaster.services.war_service import WarService


@pytest.mark.asyncio
async def test_get_current_war_number_caching():
    service = WarService(default_base_url="https://war-service-live.foxholeservices.com/api")

    with patch.object(service, "get_war_status", new_callable=AsyncMock) as mock_get_war_status:
        mock_get_war_status.return_value = {"warNumber": 120}

        war_number_1 = await service.get_current_war_number("Alpha")
        assert war_number_1 == 120

        # Second call should use cache
        war_number_2 = await service.get_current_war_number("Alpha")
        assert war_number_2 == 120

        # get_war_status called only once due to caching
        assert mock_get_war_status.call_count == 1

