"""Ordnervorschlag: wohin ein frischer Beleg gehoert.

Der Kern ist kein Modell, sondern eine Entscheidung darueber, wann man den
Mund haelt. Diese Tests halten beides fest: das Rechnen und das Schweigen.
"""

from __future__ import annotations

import math
from typing import Any

import httpx
import pytest

from src import ordner


def richtung(*werte: float) -> list[float]:
    """Ein normierter Vektor aus wenigen Zahlen, zum Rechnen von Hand."""
    laenge = math.sqrt(sum(w * w for w in werte))
    return [w / laenge for w in werte]


# --- Packen ---------------------------------------------------------------


def test_vektor_ueberlebt_packen_und_auspacken() -> None:
    v = richtung(1.0, 2.0, 3.0)
    zurueck = ordner.auspacken(ordner.packen(v))
    assert len(zurueck) == len(v)
    assert all(abs(a - b) < 1e-6 for a, b in zip(v, zurueck, strict=True))


def test_packen_ist_deutlich_kleiner_als_json() -> None:
    """768 float32 sind 3 KB, dieselben Zahlen als JSON gut das Fuenffache."""
    v = [0.123456789] * 768
    assert len(ordner.packen(v)) == 768 * 4


# --- Sachordner -----------------------------------------------------------


@pytest.mark.parametrize(
    ("pfad", "erwartet"),
    [
        ("/Dokumente/02 Medizinisch", "/Dokumente/02 Medizinisch"),
        ("/Dokumente/02 Medizinisch/Praxis Nord/Uncompressed", "/Dokumente/02 Medizinisch"),
        ("/Dokumente", ""),
        ("", ""),
    ],
)
def test_sachordner_schneidet_auf_zwei_ebenen(pfad: str, erwartet: str) -> None:
    """Tiefer waeren es Vorgaenge statt Sachgebiete, und die sind zu fein."""
    assert ordner.sachordner(pfad) == erwartet


# --- Schwerpunkte ---------------------------------------------------------


def test_ordner_mit_zu_wenigen_dokumenten_faellt_raus() -> None:
    """Ein Ordner mit einer Datei hat keinen Schwerpunkt, nur diese Datei.

    Ohne die Grenze zieht er alles an, was ihr entfernt aehnelt, und ein
    einziges verirrtes Dokument macht daraus einen Magneten.
    """
    dokumente = [
        {"folder": "/Dokumente/A", "vektor": richtung(1, 0, 0)},
        {"folder": "/Dokumente/B", "vektor": richtung(0, 1, 0)},
        {"folder": "/Dokumente/B", "vektor": richtung(0, 1, 0.1)},
        {"folder": "/Dokumente/B", "vektor": richtung(0, 1, 0.2)},
    ]
    zentren = ordner.zentren(dokumente)
    assert set(zentren) == {"/Dokumente/B"}


def test_belegordner_ist_kein_ziel() -> None:
    """Er ist der Ausgangspunkt. Ihn vorzuschlagen waere ein leerer Klick."""
    dokumente = [{"folder": "/Dokumente/00 Belege", "vektor": richtung(1, 0, 0)} for _ in range(5)]
    assert ordner.zentren(dokumente) == {}


def test_schwerpunkt_liegt_zwischen_seinen_dokumenten() -> None:
    dokumente = [
        {"folder": "/Dokumente/A", "vektor": richtung(1, 0, 0)},
        {"folder": "/Dokumente/A", "vektor": richtung(0, 1, 0)},
        {"folder": "/Dokumente/A", "vektor": richtung(1, 1, 0)},
    ]
    mitte = ordner.zentren(dokumente)["/Dokumente/A"]
    assert abs(mitte[0] - mitte[1]) < 1e-6
    assert abs(math.sqrt(sum(x * x for x in mitte)) - 1.0) < 1e-6


# --- Vorschlagen ----------------------------------------------------------


def test_klarer_treffer_wird_vorgeschlagen() -> None:
    zentren = {"/A": richtung(1, 0, 0), "/B": richtung(0, 1, 0)}
    treffer = ordner.vorschlagen(richtung(1, 0.05, 0), zentren)
    assert treffer is not None
    assert treffer["ordner"] == "/A"
    assert treffer["abstand"] >= ordner.MIN_ABSTAND


def test_knapper_abstand_schweigt() -> None:
    """Genau hier liegt der Wert des Ganzen.

    Bei Gleichstand zwischen zwei Ordnern ist der beste Vorschlag keiner. Ein
    falscher kostet Mia mehr als gar keiner: sie muss ihn lesen, pruefen und
    ablehnen, und beim dritten falschen klickt niemand mehr hin.
    """
    zentren = {"/A": richtung(1, 0, 0), "/B": richtung(1, 0.001, 0)}
    assert ordner.vorschlagen(richtung(1, 0.0005, 0), zentren) is None


def test_ein_einziger_ordner_ergibt_keinen_vorschlag() -> None:
    """Ohne zweiten Platz gibt es keinen Abstand und damit kein Signal."""
    assert ordner.vorschlagen(richtung(1, 0, 0), {"/A": richtung(1, 0, 0)}) is None


def test_ohne_vektor_kein_vorschlag() -> None:
    assert ordner.vorschlagen([], {"/A": richtung(1, 0, 0), "/B": richtung(0, 1, 0)}) is None


# --- Dokumenttext ---------------------------------------------------------


def test_dokumenttext_traegt_das_aufgaben_praefix() -> None:
    """Ohne die Praefixe fiel die Trefferquote am 09.09. von 9/9 auf 6/9."""
    assert ordner.dokumenttext("Bescheid.pdf").startswith(ordner.PRAEFIX_DOKUMENT)


def test_ocr_text_wird_gedeckelt() -> None:
    """Ein ganzes Blatt verwaessert den Vektor.

    Anschrift, Fusszeile und Rechtsbehelfsbelehrung stehen auf jedem Bescheid
    und sagen nichts darueber aus, in welchen Ordner er gehoert.
    """
    text = ordner.dokumenttext("Bescheid.pdf", "Wort " * 5000)
    assert len(text) <= len(ordner.PRAEFIX_DOKUMENT) + ordner.MAX_TEXT


# --- Einbetten ------------------------------------------------------------


def antwort_mit(vektoren: list[list[float]]) -> Any:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"embedding": v} for v in vektoren]})

    return handler


@pytest.fixture
def embed_server(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(ordner.settings, "embed_url", "http://embed.example:8080")

    def stelle(handler: Any) -> None:
        echt = httpx.AsyncClient

        def gefaelscht(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
            kwargs["transport"] = httpx.MockTransport(handler)
            return echt(*args, **kwargs)

        monkeypatch.setattr(ordner.httpx, "AsyncClient", gefaelscht)

    return stelle


async def test_einbetten_normiert(embed_server: Any) -> None:
    embed_server(antwort_mit([[3.0, 4.0]]))
    vektoren = await ordner.einbetten(["irgendwas"])
    assert abs(math.sqrt(sum(x * x for x in vektoren[0])) - 1.0) < 1e-6


async def test_einbetten_bricht_bei_falscher_anzahl_ab(embed_server: Any) -> None:
    """Weniger Vektoren als Texte waere still gefaehrlich.

    Die Zuordnung Text zu Vektor liefe danach um eins verschoben, und jedes
    Dokument bekaeme den Vektor eines anderen. Das faellt nirgends auf, es
    macht die Vorschlaege nur schleichend falsch.
    """
    embed_server(antwort_mit([[1.0, 0.0]]))
    assert await ordner.einbetten(["eins", "zwei"]) == []


async def test_einbetten_wirft_nie(embed_server: Any) -> None:
    """Der Aufrufer steht mitten in einem Upload, der bereits geglueckt ist."""

    async def kaputt(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("weg")

    embed_server(kaputt)
    assert await ordner.einbetten(["irgendwas"]) == []


async def test_ohne_server_kein_aufruf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ordner.settings, "embed_url", "")
    assert await ordner.einbetten(["irgendwas"]) == []
    assert not ordner.verfuegbar()
