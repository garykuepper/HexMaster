# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.
"""Service for interacting with the Foxhole WarAPI across multiple shards."""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp


class WarService:
    """Provides access to WarAPI data with per-shard caching."""

    SHARD_URLS = {
        "Alpha": "https://war-service-live.foxholeservices.com/api",
        "Bravo": "https://war-service-live-2.foxholeservices.com/api",
        "Charlie": "https://war-service-live-3.foxholeservices.com/api",
    }

    def __init__(self, default_base_url: str) -> None:
        """Initializes the WarService with caching and locks."""
        self.default_base_url = default_base_url
        # Per-shard cache: shard_name -> {"warNumber": int, "last_fetch": datetime}
        self._shard_caches: Dict[str, Dict[str, Any]] = {}
        self._cache_duration = timedelta(hours=1)
        self._lock = asyncio.Lock()

    def _get_url(self, shard_name: Optional[str]) -> str:
        """Returns the base URL for a given shard name, or default if not found."""
        if not shard_name:
            return self.default_base_url
        return self.SHARD_URLS.get(shard_name, self.default_base_url)

    async def get_maps(self, shard_name: Optional[str] = None) -> List[str]:
        """Fetches the list of active maps (hexes) from the specified shard."""
        url = f"{self._get_url(shard_name)}/worldconquest/maps"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"WarAPI {shard_name or ''} returned status {resp.status}: {error_text}")
                result = await resp.json()
                return list(result)

    async def get_war_status(self, shard_name: Optional[str] = None) -> Dict[str, Any]:
        """Fetches the current war status from the specified shard."""
        url = f"{self._get_url(shard_name)}/worldconquest/war"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"WarAPI {shard_name or ''} returned status {resp.status}: {error_text}")
                result = await resp.json()
                return dict(result)

    async def get_current_war_number(self, shard_name: str = "Alpha") -> Optional[int]:
        """Fetches the current war number for a shard, using cache if available."""
        async with self._lock:
            now = datetime.now()
            shard_key = shard_name or "Alpha"
            cache = self._shard_caches.get(shard_key)

            if cache and cache.get("last_fetch"):
                if now - cache["last_fetch"] < self._cache_duration:
                    return cache.get("warNumber")

            try:
                data = await self.get_war_status(shard_key)
                war_number = data.get("warNumber")
                self._shard_caches[shard_key] = {
                    "warNumber": war_number,
                    "last_fetch": now,
                }
                return int(war_number) if war_number is not None else None
            except Exception as e:
                # Log error and fallback to stale cache if available
                print(f"Error fetching war info for {shard_key}: {e}")

            return self._shard_caches.get(shard_key, {}).get("warNumber")

    async def get_map_dynamic(self, map_name: str, shard_name: str | None = "Alpha") -> dict:
        """Fetches dynamic map items (town halls, forts, faction flags) for a specific hex."""
        url = f"{self._get_url(shard_name)}/worldconquest/maps/{map_name}/dynamic/public"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return {}
                return dict(await resp.json())

    async def get_hex_ownership(self, shard_name: str | None = "Alpha") -> dict[str, str]:
        """
        Compiles a dict mapping hex map names to dominant controlling faction
        (e.g., {'TheFingersHex': 'COLONIAL', 'MarbanHollow': 'WARDEN'}).
        """
        hex_control: dict[str, str] = {}
        try:
            maps = await self.get_maps(shard_name)
            for map_name in maps:
                data = await self.get_map_dynamic(map_name, shard_name)
                map_items = data.get("mapItems", [])
                faction_counts: dict[str, int] = {"COLONIAL": 0, "WARDEN": 0}
                for item in map_items:
                    team = item.get("team")
                    if team in faction_counts:
                        faction_counts[team] += 1

                col_count = faction_counts["COLONIAL"]
                war_count = faction_counts["WARDEN"]

                if col_count > war_count:
                    hex_control[map_name] = "COLONIAL"
                elif war_count > col_count:
                    hex_control[map_name] = "WARDEN"
                else:
                    hex_control[map_name] = "NEUTRAL"
        except Exception as e:
            print(f"Error compiling hex ownership for {shard_name}: {e}")

        return hex_control

