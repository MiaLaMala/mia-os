"""Gesundheit: Gewicht und Ernaehrung aus wger."""

from __future__ import annotations

import httpx

from src.collectors.base import Collector
from src.config import settings


class HealthCollector(Collector):
    name = "gesundheit"
    category = "gesundheit"

    def is_configured(self) -> bool:
        return bool(settings.wger_url and settings.wger_token)

    async def collect(self) -> None:
        headers = {"Authorization": f"Token {settings.wger_token}"}
        base = settings.wger_url.rstrip("/")

        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            await self._weight(client, base)
            await self._nutrition(client, base)

    async def _weight(self, client: httpx.AsyncClient, base: str) -> None:
        resp = await client.get(
            f"{base}/api/v2/weightentry/",
            params={"format": "json", "limit": 2, "ordering": "-date"},
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        if not results:
            return

        newest = results[0]
        weight = float(newest["weight"])
        self.store.record("gesundheit", "gewicht", weight, unit="kg")
        self.store.record("gesundheit", "gewicht_datum", text_value=newest["date"])
        self.store.record("gesundheit", "gewicht_eintraege", float(data.get("count", 0)))

        # Trend gegen den vorherigen Eintrag: die Zahl, die Mia wirklich interessiert.
        if len(results) > 1:
            delta = weight - float(results[1]["weight"])
            self.store.record("gesundheit", "gewicht_delta", round(delta, 2), unit="kg")

    async def _nutrition(self, client: httpx.AsyncClient, base: str) -> None:
        resp = await client.get(
            f"{base}/api/v2/nutritiondiary/",
            params={"format": "json", "limit": 1, "ordering": "-datetime"},
        )
        resp.raise_for_status()
        data = resp.json()
        self.store.record("gesundheit", "ernaehrung_eintraege", float(data.get("count", 0)))
        results = data.get("results") or []
        if results:
            self.store.record(
                "gesundheit", "ernaehrung_zuletzt", text_value=results[0].get("datetime")
            )
