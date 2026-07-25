# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import heapq

# Foxhole World Conquest Map Hex Adjacency Graph (standard map connections)
FOXHOLE_HEX_GRAPH: dict[str, list[str]] = {
    "TheFingersHex": ["TempestIslandHex", "EndlessShoreHex"],
    "TempestIslandHex": ["TheFingersHex", "EndlessShoreHex", "GodcroftsHex"],
    "EndlessShoreHex": ["TheFingersHex", "TempestIslandHex", "AllodsBightHex", "MarbanHollow"],
    "AllodsBightHex": ["EndlessShoreHex", "ShackledChasmHex", "ReachingTrailHex"],
    "ShackledChasmHex": ["AllodsBightHex", "DrownedValeHex"],
    "DrownedValeHex": ["ShackledChasmHex", "MarbanHollow", "ViperPitHex"],
    "MarbanHollow": ["DrownedValeHex", "EndlessShoreHex", "LinnOfMercyHex", "ViperPitHex"],
    "LinnOfMercyHex": ["MarbanHollow", "DeadLandsHex", "CallamsCapeHex"],
    "DeadLandsHex": ["LinnOfMercyHex", "FarranacCoastHex", "LochBerthHex"],
    "FarranacCoastHex": ["DeadLandsHex", "WestgateHex", "FishermansRowHex"],
    "WestgateHex": ["FarranacCoastHex", "OriginHex", "StablesHex"],
    "FishermansRowHex": ["FarranacCoastHex", "OriginHex"],
    "OriginHex": ["WestgateHex", "FishermansRowHex", "StygianHex"],
    "ViperPitHex": ["DrownedValeHex", "MarbanHollow", "WeatheredExpanseHex"],
    "WeatheredExpanseHex": ["ViperPitHex", "GodcroftsHex", "ClahstraHex"],
    "GodcroftsHex": ["TempestIslandHex", "WeatheredExpanseHex"],
    "LochBerthHex": ["DeadLandsHex", "CallamsCapeHex"],
    "CallamsCapeHex": ["LinnOfMercyHex", "LochBerthHex", "ReachingTrailHex"],
    "ReachingTrailHex": ["CallamsCapeHex", "AllodsBightHex"],
    "StablesHex": ["WestgateHex"],
    "StygianHex": ["OriginHex"],
}


class RoutingService:
    """Graph pathfinding service using Dijkstra's algorithm for Foxhole logi routing."""

    def __init__(self, graph: dict[str, list[str]] | None = None):
        self.graph = graph if graph is not None else FOXHOLE_HEX_GRAPH

    def _normalize_hex(self, hex_name: str) -> str:
        clean = hex_name.strip().replace(" ", "").replace("_", "")
        if not clean.endswith("Hex") and not clean.endswith("Hollow"):
            clean += "Hex"
        return clean

    def find_safe_route(
        self,
        start_town_or_hex: str,
        end_town_or_hex: str,
        hex_control: dict[str, str],
        user_faction: str = "Colonial",
    ) -> dict:
        """
        Runs Dijkstra's algorithm to compute the shortest safe route.
        Returns:
          {
            "status": "SAFE" | "HAZARD" | "BLOCKED",
            "hops": int,
            "path": list[str],
            "hazard_hexes": list[str],
            "total_cost": float,
          }
        """
        user_faction_upper = user_faction.upper()
        enemy_faction_upper = "WARDEN" if user_faction_upper == "COLONIAL" else "COLONIAL"

        start_node = self._normalize_hex(start_town_or_hex)
        end_node = self._normalize_hex(end_town_or_hex)

        # Fallbacks if hex names aren't in graph
        if start_node not in self.graph or end_node not in self.graph:
            return {
                "status": "SAFE",
                "hops": 1,
                "path": [start_town_or_hex, end_town_or_hex],
                "hazard_hexes": [],
                "total_cost": 1.0,
            }

        # Priority queue: (cost, current_node, path)
        pq: list[tuple[float, str, list[str]]] = [(0.0, start_node, [start_node])]
        visited: dict[str, float] = {}

        best_cost = float("inf")
        best_path: list[str] = []

        while pq:
            cost, curr, path = heapq.heappop(pq)

            if curr in visited and visited[curr] <= cost:
                continue
            visited[curr] = cost

            if curr == end_node:
                best_cost = cost
                best_path = path
                break

            for neighbor in self.graph.get(curr, []):
                ctrl = hex_control.get(neighbor, "NEUTRAL").upper()
                if ctrl == enemy_faction_upper:
                    edge_weight = 100.0  # Heavy penalty for enemy hex
                elif ctrl == "NEUTRAL" or ctrl == "NONE":
                    edge_weight = 5.0  # Moderate penalty for neutral/contested hex
                else:
                    edge_weight = 1.0  # Base cost for friendly hex

                new_cost = cost + edge_weight
                if neighbor not in visited or new_cost < visited[neighbor]:
                    heapq.heappush(pq, (new_cost, neighbor, path + [neighbor]))

        if not best_path:
            return {
                "status": "BLOCKED",
                "hops": 0,
                "path": [],
                "hazard_hexes": [],
                "total_cost": float("inf"),
            }

        # Analyze route hazard status
        hazard_hexes = []
        is_blocked = False
        for node in best_path:
            ctrl = hex_control.get(node, "NEUTRAL").upper()
            if ctrl == enemy_faction_upper:
                is_blocked = True
                hazard_hexes.append(node)
            elif ctrl == "NEUTRAL" or ctrl == "NONE":
                hazard_hexes.append(node)

        status = "BLOCKED" if is_blocked else ("HAZARD" if hazard_hexes else "SAFE")
        hops = max(0, len(best_path) - 1)

        return {
            "status": status,
            "hops": hops,
            "path": best_path,
            "hazard_hexes": hazard_hexes,
            "total_cost": round(best_cost, 1),
        }
