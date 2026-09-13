"""Gemeinsame Fixtures.

Wichtig: ``client`` laedt ``src.config`` und ``src.main`` neu, damit der Store
in ein temporaeres Verzeichnis schreibt. Dabei entsteht ein **neues**
``settings``-Objekt. Jedes Modul, das ``settings`` beim Import gebunden hat,
muss deshalb mitgeladen werden, sonst patcht ein Test das eine Objekt und der
Code liest das andere. Genau daran bin ich am 05.09.2026 schon einmal
haengengeblieben.
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.config import settings as ocr_settings
from src.store import Store

# Der echte Prozessstart, festgehalten bevor ``kein_echtes_ssh`` ihn ersetzt.
#
# Die Sperre unten patcht ``kuma.asyncio.create_subprocess_exec``, und
# ``kuma.asyncio`` ist dasselbe Modulobjekt wie ueberall sonst: die Sperre
# gilt damit prozessweit, nicht nur fuer den Kuma-Collector. Ein Test, der
# absichtlich ein echtes Programm startet (Tesseract in ``test_ocr``), kann
# sie deshalb nicht mit ``asyncio.create_subprocess_exec`` zuruecksetzen, das
# waere bereits die Attrappe. Hier steht das Original.
ECHTER_PROZESSSTART = asyncio.create_subprocess_exec

# Wie Tesseract auf diesem Rechner heisst, festgehalten bevor ``kein_echtes_ocr``
# es abschaltet. Tests, die absichtlich echtes OCR wollen, holen es sich hier.
ECHTES_OCR_BINARY = ocr_settings.ocr_binary


@pytest.fixture(autouse=True)
def kein_echtes_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kein Test startet ungefragt Tesseract.

    Aufgefallen beim Bau des OCR: die vorhandenen Beleg-Tests laden ein Bild
    hoch, und seit der Upload den Text liest, starteten sie auf jedem Rechner
    mit installiertem Tesseract einen echten Prozess. Auf dem CI-Runner ist
    keines installiert, dort waere es nie aufgefallen; lokal kostet es je Test
    eine Sekunde und rennt in die SSH-Sperre.

    Ein leerer Programmname laesst ``ocr.verfuegbar()`` sauber ``False``
    melden, das ist derselbe Weg wie auf einem Rechner ohne Tesseract. Wer
    echtes OCR will, setzt ``ECHTES_OCR_BINARY`` im eigenen Test zurueck.
    """
    import src.ocr

    monkeypatch.setattr(src.ocr.settings, "ocr_binary", "")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DB_PATH", str(tmp_path / "api.db"))

    import src.config
    import src.editor
    import src.main
    import src.store

    importlib.reload(src.config)
    # Reihenfolge zaehlt: erst die Module, die settings binden, dann main.
    importlib.reload(src.editor)
    # store bindet settings seit dem OCR-Text (belege_ordner als Grenze).
    # Ohne den Neuladen patcht ein Test das eine settings-Objekt und der
    # Store liest das andere.
    importlib.reload(src.store)
    importlib.reload(src.main)

    # Mit einer echten Adresse statt des Vorgabewerts "testclient". Seit die
    # Torwache vor der Schnittstelle steht, entscheidet die Adresse mit: eine
    # Anfrage ohne lesbare IP gilt als fremd und bekommt 401. Die Tests
    # spielen den Browser im Heimnetz nach, und der kommt von einer Adresse.
    with TestClient(src.main.app, client=("127.0.0.1", 51000)) as c:
        yield c


@pytest.fixture
def fremder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Ein Client von ausserhalb: kein vertrautes Netz, kein Schluessel.

    Teilt sich den Aufbau mit ``client``, nur die Adresse ist eine oeffentliche.
    Damit laesst sich pruefen, dass die Torwache wirklich zumacht, statt nur
    zu hoffen, dass sie es tut.
    """
    monkeypatch.setenv("DB_PATH", str(tmp_path / "fremd.db"))

    import src.config
    import src.editor
    import src.main
    import src.store

    importlib.reload(src.config)
    importlib.reload(src.editor)
    importlib.reload(src.store)
    importlib.reload(src.main)

    with TestClient(src.main.app, client=("203.0.113.7", 51000)) as c:
        yield c


@pytest.fixture(autouse=True)
def kein_echtes_ssh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verhindert, dass ein Test versehentlich echtes SSH startet.

    ``kuma_ssh_host`` hat mit "pve" eine feste Vorgabe, der Kuma-Collector
    gilt also immer als konfiguriert. Auf einem CI-Runner gibt es keine Route
    ins Heimnetz: der Testlauf hing dadurch 25 Minuten in einem einzigen Test
    fest, bis GitHub abbrach. Lokal fiel das nie auf, weil hier eine Route
    existiert.

    Wer SSH testen will, hebt das im eigenen Test wieder auf.
    """
    import src.collectors.kuma as kuma

    async def kein_start(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "Ein Test wollte einen echten Prozess starten (vermutlich ssh). "
            "Das gehört gemockt, sonst hängt die CI."
        )

    monkeypatch.setattr(kuma.asyncio, "create_subprocess_exec", kein_start)


@pytest.fixture
def store(tmp_path: Path) -> Store:
    """Ein leerer Store fuer Tests, die keine HTTP-Schicht brauchen."""
    return Store(str(tmp_path / "store.db"))
