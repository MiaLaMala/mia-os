"""Version, Änderungsverlauf und was Mia OS gerade kann.

Die Datei ``version.json`` entsteht beim Bauen aus der Git-Historie
(``scripts/version_bauen.py``). Im Container gibt es kein Git, deshalb wird
sie hier nur noch gelesen.

**Fehlt sie, ist das kein Fehler**, sondern eine Entwicklungsumgebung ohne
vorherigen Build. Dann steht in der Oberfläche „unbekannt", und der Rest der
Seite funktioniert weiter. Eine About-Seite, die eine Ausnahme wirft, wäre
die schlechteste aller Antworten auf eine fehlende Zahl.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

VERSION_DATEI = Path(__file__).parent / "version.json"

LEER: dict[str, Any] = {
    "version": "unbekannt",
    "commit": "",
    "gebaut_am": "",
    "commits": 0,
    "seit": "",
    "changelog": [],
}


@cache
def _daten() -> dict[str, Any]:
    """Die gebauten Angaben. Einmal gelesen, dann gemerkt.

    ``cache``, weil die Datei sich zur Laufzeit nicht ändert: sie entsteht
    beim Bauen des Abbilds. Ein Neustart holt eine neue Fassung.
    """
    try:
        geladen: dict[str, Any] = json.loads(VERSION_DATEI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(LEER)
    return {**LEER, **geladen}


def version() -> str:
    """Nur die Nummer, für Seitenkopf und OpenAPI."""
    fassung: str = _daten()["version"]
    return fassung


def _laufzeit(gestartet: datetime | None) -> str:
    """Wie lange der Dienst schon läuft, in Worten.

    Sekundengenau wäre hier Angeberei: interessant ist, ob er seit Minuten
    oder seit Wochen läuft.
    """
    if gestartet is None:
        return ""
    sekunden = int((datetime.now(UTC) - gestartet).total_seconds())
    if sekunden < 90:
        return "gerade neu gestartet"
    minuten = sekunden // 60
    if minuten < 60:
        return f"seit {minuten} Minuten"
    stunden = minuten // 60
    if stunden < 24:
        return f"seit {stunden} Stunden"
    tage = stunden // 24
    return "seit einem Tag" if tage == 1 else f"seit {tage} Tagen"


def ueberblick(
    store: Any,
    quellen: list[dict[str, Any]],
    gestartet: datetime | None = None,
) -> dict[str, Any]:
    """Alles für die About-Seite in einem Aufruf.

    Bewusst mit Zahlen aus der echten Datenbank statt einer gepflegten
    Liste: eine Aufzählung, die von Hand aktuell gehalten werden muss, ist
    nach zwei Wochen falsch.

    **Keine Namen, nur Anzahlen.** Auf einer Seite über die Anwendung haben
    Dokumenttitel und Eintragstexte nichts verloren, dieselbe Regel wie auf
    der Startseite.
    """
    daten = _daten()

    dokumente = store.document_stats()
    eintraege = len(store.list_entries(mit_archiv=True))
    seiten = len(store.list_pages())

    return {
        "version": daten["version"],
        "commit": daten["commit"],
        "gebaut_am": daten["gebaut_am"],
        "commits": daten["commits"],
        "seit": daten["seit"],
        "laufzeit": _laufzeit(gestartet),
        "changelog": daten["changelog"],
        "zahlen": [
            {"titel": "Einträge", "wert": eintraege},
            {"titel": "Seiten", "wert": seiten},
            {"titel": "Dokumente", "wert": dokumente["gesamt"]},
            {"titel": "Änderungen", "wert": daten["commits"]},
        ],
        # Welche Datenquellen angebunden sind und ob sie zuletzt geliefert
        # haben. Kommt aus derselben Abfrage wie die Startseite.
        "quellen": quellen,
    }
