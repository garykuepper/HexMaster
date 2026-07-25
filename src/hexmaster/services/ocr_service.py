# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.
"""Service for interacting with external OCR for image processing."""

from typing import Any, Dict, Optional

import aiohttp
import pandas as pd


class OCRServiceError(Exception):
    """Custom exception for OCR Service failures."""

    def __init__(self, status: int, message: str, technical_details: Optional[str] = None) -> None:
        """Initializes the OCRServiceError."""
        super().__init__(message)
        self.status = status
        self.message = message
        self.technical_details = technical_details

    def __str__(self) -> str:
        """Returns the string representation of the error."""
        return f"{self.message} (Status: {self.status})"


class OCRService:
    """Handles communication with the external Foxhole Stockpiles (FS) service."""

    def __init__(self, base_url: str) -> None:
        """Initializes the OCRService with the base URL."""
        self.base_url = base_url.rstrip("/")

    async def process_image(
        self,
        image_bytes: bytes,
        town: Optional[str] = None,
        label: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Sends image to the Foxhole Stockpiles (FS) service and returns a DataFrame.
        """
        url = f"{self.base_url}/ocr/scan_image"

        data = aiohttp.FormData()
        # FS expects the file field to be named 'image'
        data.add_field("image", image_bytes, filename="screenshot.png", content_type="image/png")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, data=data) as resp:
                    return await self._handle_response(resp, town, label)
            except aiohttp.ClientError as e:
                raise OCRServiceError(500, f"Connection to FS Service failed: {str(e)}")

    async def _handle_response(
        self,
        resp: aiohttp.ClientResponse,
        fallback_town: Optional[str],
        fallback_label: Optional[str],
    ) -> pd.DataFrame:
        """Internal helper to handle the FS JSON response."""
        if resp.status != 200:
            raw_text = await resp.text()
            raise OCRServiceError(resp.status, f"FS Service returned error: {raw_text[:200]}")

        try:
            data = await resp.json()
        except Exception:
            raise OCRServiceError(resp.status, "Failed to decode JSON response from FS.")

        if not isinstance(data, dict):
            return pd.DataFrame()

        # FS JSON Structure: { "stockpile": { "name": "...", "type": "...", "items": [...] } }
        # or it might be raw at the top level.
        stockpile_data = data.get("stockpile")
        if not isinstance(stockpile_data, dict):
            stockpile_data = data

        return self._parse_items_to_df(stockpile_data, fallback_label)

    def _parse_items_to_df(self, data: Dict[str, Any], fallback_label: Optional[str]) -> pd.DataFrame:
        """Parses the stockpile items into a standardized DataFrame."""
        detected_name = data.get("name")
        detected_type = data.get("type")

        final_stockpile_name = detected_name if detected_name else fallback_label
        final_struct_type = detected_type if detected_type else "Unknown"

        items = data.get("items", [])
        rows = []
        for item in items:
            if not isinstance(item, dict) or not item.get("code"):
                continue

            rows.append(
                {
                    "Structure Type": final_struct_type,
                    "Stockpile Name": final_stockpile_name,
                    "CodeName": item["code"],
                    "Name": item["code"],
                    "Quantity": item.get("quantity", 0),
                    "Crated?": "YES" if item.get("crated") else "NO",
                    "Per Crate": 0,  # Placeholder
                    "Total": 0,  # Placeholder
                    "Description": "",
                }
            )

        return pd.DataFrame(rows)
