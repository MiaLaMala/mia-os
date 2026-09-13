"""Registry aller Collectors."""

from __future__ import annotations

from src.collectors.base import Collector
from src.collectors.calendar import CalendarCollector
from src.collectors.documents import DocumentCollector
from src.collectors.embed import EmbedCollector
from src.collectors.health import HealthCollector
from src.collectors.homelab import HomelabCollector
from src.collectors.kuma import KumaCollector
from src.store import Store

__all__ = [
    "CalendarCollector",
    "Collector",
    "DocumentCollector",
    "EmbedCollector",
    "HealthCollector",
    "HomelabCollector",
    "KumaCollector",
    "all_collectors",
]


def all_collectors(store: Store) -> list[Collector]:
    """Alle bekannten Collectors, in Anzeigereihenfolge.

    ``EmbedCollector`` steht hinter ``DocumentCollector``: er rechnet auf
    dessen Ergebnis, und andersherum haette eine frisch gefundene Datei eine
    ganze Runde lang keinen Vektor.
    """
    return [
        HealthCollector(store),
        CalendarCollector(store),
        HomelabCollector(store),
        KumaCollector(store),
        DocumentCollector(store),
        EmbedCollector(store),
    ]
