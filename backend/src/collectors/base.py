"""Basisklasse fuer Collectors.

Vertrag: ein Collector wirft nie nach oben. Faellt eine Quelle aus, wird der
Fehler protokolliert und das Dashboard zeigt die Kategorie als "stale" an,
statt komplett auszufallen.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from src.store import Store


class Collector(ABC):
    """Eine Datenquelle."""

    name: str = "unnamed"
    category: str = "sonstiges"

    def __init__(self, store: Store) -> None:
        self.store = store

    @abstractmethod
    async def collect(self) -> None:
        """Werte holen und via ``self.store.record`` ablegen."""

    @abstractmethod
    def is_configured(self) -> bool:
        """False, wenn Zugangsdaten fehlen. Dann wird uebersprungen."""

    async def run(self) -> bool:
        """Collector ausfuehren, Ergebnis protokollieren. Wirft nie."""
        if not self.is_configured():
            self.store.record_run(self.name, False, "nicht konfiguriert", 0)
            return False

        start = time.monotonic()
        try:
            await self.collect()
        except Exception as exc:
            duration = int((time.monotonic() - start) * 1000)
            self.store.record_run(self.name, False, f"{type(exc).__name__}: {exc}", duration)
            return False

        duration = int((time.monotonic() - start) * 1000)
        self.store.record_run(self.name, True, None, duration)
        return True
