"""Tests fuer die Collector-Basis: der Vertrag ist "wirft niemals"."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from src.collectors.base import Collector
from src.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(str(tmp_path / "test.db"))


class OkCollector(Collector):
    name = "ok"
    category = "test"

    def is_configured(self) -> bool:
        return True

    async def collect(self) -> None:
        self.store.record("test", "wert", 1.0)


class BrokenCollector(Collector):
    name = "kaputt"
    category = "test"

    def is_configured(self) -> bool:
        return True

    async def collect(self) -> None:
        raise RuntimeError("Quelle nicht erreichbar")


class UnconfiguredCollector(Collector):
    name = "unkonfiguriert"
    category = "test"

    def is_configured(self) -> bool:
        return False

    async def collect(self) -> None:  # pragma: no cover - darf nie laufen
        raise AssertionError("darf nicht aufgerufen werden")


async def test_successful_run(store: Store) -> None:
    assert await OkCollector(store).run() is True
    assert store.latest("test")[0]["value"] == 1.0
    assert store.last_runs()[0]["ok"] == 1


async def test_failing_collector_does_not_raise(store: Store) -> None:
    """Der wichtigste Test: eine kaputte Quelle darf das Dashboard nicht mitreissen."""
    assert await BrokenCollector(store).run() is False
    run = store.last_runs()[0]
    assert run["ok"] == 0
    assert "Quelle nicht erreichbar" in run["error"]


async def test_unconfigured_is_skipped(store: Store) -> None:
    assert await UnconfiguredCollector(store).run() is False
    assert store.last_runs()[0]["error"] == "nicht konfiguriert"


async def test_duration_is_recorded(store: Store) -> None:
    await OkCollector(store).run()
    assert store.last_runs()[0]["duration_ms"] >= 0


# --- Vektoren fuer den Ordnervorschlag ------------------------------------


class FakeEmbedStore:
    """Store-Attrappe, die nur die drei Methoden des Embed-Collectors kann."""

    def __init__(self, offen: list[dict[str, Any]]) -> None:
        self.offen = offen
        self.gesetzt: list[tuple[int, str]] = []
        self.werte: dict[str, float] = {}

    def documents_ohne_embed(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.offen[:limit]

    def set_document_embed(self, doc_id: int, vektor: bytes, name: str) -> bool:
        self.gesetzt.append((doc_id, name))
        return True

    def record(self, kategorie: str, key: str, wert: float) -> None:
        self.werte[key] = wert

    def record_run(self, *args: Any, **kwargs: Any) -> None:
        pass


def embed_antwort(anzahl: int) -> Any:
    async def handler(request: httpx.Request) -> httpx.Response:
        gefragt = len(request.read().decode().split('"input"')[1].split("]")[0].split('",'))
        return httpx.Response(
            200, json={"data": [{"embedding": [1.0, 0.0]} for _ in range(gefragt)]}
        )

    return handler


async def test_embed_collector_rechnet_fehlende_nach(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import ordner
    from src.collectors.embed import EmbedCollector

    monkeypatch.setattr(ordner.settings, "embed_url", "http://embed.example:8080")
    echt = httpx.AsyncClient
    monkeypatch.setattr(
        ordner.httpx,
        "AsyncClient",
        lambda *a, **k: echt(*a, **{**k, "transport": httpx.MockTransport(embed_antwort(2))}),
    )

    store = FakeEmbedStore(
        [
            {"id": 1, "name": "Bescheid.pdf", "folder": "/Dokumente/01 A"},
            {"id": 2, "name": "Vertrag.pdf", "folder": "/Dokumente/01 A"},
        ]
    )
    collector = EmbedCollector(store)  # type: ignore[arg-type]
    await collector.collect()

    assert store.gesetzt == [(1, "Bescheid.pdf"), (2, "Vertrag.pdf")]
    assert store.werte["embed_offen"] == 0


async def test_embed_collector_bricht_bei_totem_server_ab(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Weiterklopfen kostet nur Zeit. Der naechste Lauf holt es nach."""
    from src import ordner
    from src.collectors.embed import EmbedCollector

    monkeypatch.setattr(ordner.settings, "embed_url", "http://embed.example:8080")

    async def tot(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("weg")

    echt = httpx.AsyncClient
    monkeypatch.setattr(
        ordner.httpx,
        "AsyncClient",
        lambda *a, **k: echt(*a, **{**k, "transport": httpx.MockTransport(tot)}),
    )

    store = FakeEmbedStore([{"id": i, "name": f"D{i}.pdf", "folder": "/A"} for i in range(40)])
    await EmbedCollector(store).collect()  # type: ignore[arg-type]

    assert store.gesetzt == []
    assert store.werte["embed_offen"] == 40


def test_embed_collector_ohne_server_ist_nicht_konfiguriert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.collectors.embed import EmbedCollector

    monkeypatch.setattr("src.collectors.embed.settings.embed_url", "")
    assert EmbedCollector(FakeEmbedStore([])).is_configured() is False  # type: ignore[arg-type]
