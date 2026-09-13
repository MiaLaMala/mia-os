"""Wacht darueber, dass der MCP-Server zur API passt.

Der MCP-Server unter ``mcp/`` ruft die API mit festen Pfaden auf. Wird ein
Endpunkt umbenannt oder kommt einer dazu, faellt das sonst erst auf, wenn
der Assistent ihn braucht und ins Leere greift. Genau das war Mias Sorge:
"du vergisst den MCP-Server zu pflegen".

Der Test liest keine laufende Instanz, sondern vergleicht die Routen aus
``src.api`` mit den Pfaden, die im Serverquelltext stehen.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MCP_SERVER = Path(__file__).resolve().parents[1] / "mcp" / "mia_os_mcp" / "server.py"

# Endpunkte, die der MCP-Server absichtlich NICHT anfasst. Wer hier etwas
# eintraegt, muss den Grund danebenschreiben.
BEWUSST_AUSSEN = {
    "/api/sammlung/{entry_id}": "DELETE fehlt mit Absicht: kein Loeschen ueber den Assistenten",
    "/api/aufgaben/{task_id}": "dito",
    "/api/seiten/{page_id}": "dito",
    "/api/eigenschaften": "Eigenschaften legt Mia in der Oberflaeche an",
    "/api/eigenschaften/{key}": "dito",
    "/api/collect": "Sammellauf gehoert dem Cron, nicht dem Assistenten",
    "/api/einstellungen": "Vorlieben aendert nur Mia selbst",
    "/api/gesundheit": "laeuft ueber notiz(), nicht ueber eigene Werkzeuge",
    "/api/gesundheit/essen": "dito",
    "/api/gesundheit/gewicht": "dito",
    "/api/gesundheit/heute": "dito",
    "/api/gesundheit/zutaten": "dito",
    "/api/documents": "Dokumente laufen ueber /api/dokumente",
    "/api/documents/stats": "reine Anzeige",
    "/api/categories": "alte Kategorieansicht",
    "/api/categories/{key}": "dito",
    "/api/history/{category}/{key}": "reine Anzeige",
    "/api/homelab": "eigene Seite, kein Assistentenfall",
    "/api/firmware/neueste": (
        "Fragt das Display selbst ab, alle zwei Minuten. Ein Assistent, der "
        "Firmware-Staende abruft, haette nichts davon."
    ),
    "/api/firmware/datei": "Binaerdatei fuers Geraet, nichts zum Lesen",
    "/api/geraete": (
        "Zeigt die Homelab-Seite an. Fuer den Assistenten waere es eine Liste ohne Handlung."
    ),
    "/api/geraete/einstellungen": (
        "Long-Polling fuers Display, haelt bis 60 s offen. Einstellen geht ueber /api/einstellungen."
    ),
    "/api/hinweise/{hinweis_id}/{antwort}": "antwortet das Display per Tippen, nicht der Assistent",
    "/api/regeln": "Regel 62. Es gibt keine Kammer.",
    "/api/onlyoffice/callback/{doc_id}": "spricht der Document Server, nicht der Assistent",
    "/api/sammlung/{entry_id}/beleg": (
        "Datei-Upload: der Assistent hat keine Datei in der Hand. Er verknuepft "
        "ueber dokument_anhaengen, hochladen macht Mia in der Oberflaeche."
    ),
    "/api/scan/vorschau": (
        "Bildaufbereitung mit Vorschau: braucht Mias Auge und ihre Finger an "
        "den Ecken, dafuer gibt es keinen sinnvollen Assistentenweg."
    ),
    "/api/dokumente/verschieben": (
        "Aufraeumen in Mias Ablage entscheidet Mia. Der Vorschlag trifft in 88 % "
        "der Faelle, und in jedem achten schoebe ein Assistent, der ihn selbst "
        "annimmt, ein Blatt an eine Stelle, an der Mia es nicht sucht. Der Klick "
        "in der Oberflaeche ist die Zustimmung, und die laesst sich nicht "
        "delegieren."
    ),
    "/api/dokumente/umbenennen": (
        "Wie ein Beleg heisst, entscheidet Mia. Der Name kommt aus OCR-Text, "
        "und der ist genau das, was ueber den MCP-Weg das Haus verlaesst: "
        "ein Assistent, der den Vorschlag selbst annimmt, muesste ihn erst "
        "gelesen haben. Der Klick in der Oberflaeche ist die Zustimmung."
    ),
    "/api/termin/{uid}": "Termindetails kommen ueber /api/termine mit",
    "/api/termin/{uid}/notiz": "noch offen, bewusst spaeter",
    "/api/ueber": "reine Anzeige: Version und Aenderungsverlauf fuer Mias Augen",
    "/api/uebersicht": "reine Anzeige",
    "/api/aufgaben/{task_id}/uid": "intern",
}


def _mcp_pfade() -> set[str]:
    """Alle API-Pfade, die im MCP-Serverquelltext stehen."""
    text = MCP_SERVER.read_text(encoding="utf-8")
    roh = set(re.findall(r'"(/api/[^"]*)"', text))
    # f-Strings wie f"/api/sammlung/{entry_id}" auf die Schablone bringen
    return {re.sub(r"\{[a-z_]+\}", "{id}", p) for p in roh}


def _api_pfade() -> set[str]:
    from src.api import router

    pfade = set()
    for route in router.routes:
        pfad = getattr(route, "path", "")
        if not pfad.startswith("/"):
            continue
        # Der Router traegt sein /api-Praefix schon selbst, je nach
        # FastAPI-Fassung mal in route.path, mal erst beim Einhaengen.
        pfade.add(pfad if pfad.startswith("/api/") else "/api" + pfad)
    return pfade


@pytest.mark.skipif(not MCP_SERVER.exists(), reason="MCP-Server nicht im Baum")
def test_mcp_kennt_jeden_endpunkt_oder_nennt_den_grund() -> None:
    """Neue Endpunkte muessen ins MCP oder in die Ausnahmeliste."""
    genutzt = {re.sub(r"\{[a-z_]+\}", "{id}", p) for p in _mcp_pfade()}
    ausgenommen = {re.sub(r"\{[a-z_]+\}", "{id}", p) for p in BEWUSST_AUSSEN}

    fehlend = sorted(
        p
        for p in _api_pfade()
        if re.sub(r"\{[a-z_]+\}", "{id}", p) not in genutzt
        and re.sub(r"\{[a-z_]+\}", "{id}", p) not in ausgenommen
    )
    assert not fehlend, (
        "Diese API-Endpunkte kennt der MCP-Server nicht. Entweder ein Werkzeug "
        "in mcp/mia_os_mcp/server.py ergaenzen oder mit Begruendung in "
        f"BEWUSST_AUSSEN eintragen: {fehlend}"
    )


@pytest.mark.skipif(not MCP_SERVER.exists(), reason="MCP-Server nicht im Baum")
def test_mcp_ruft_keine_toten_pfade_auf() -> None:
    """Umbenannte Endpunkte fallen hier auf, nicht erst im Gespraech."""
    vorhanden = {re.sub(r"\{[a-z_]+\}", "{id}", p) for p in _api_pfade()}
    tot = sorted(p for p in _mcp_pfade() if p not in vorhanden)
    assert not tot, f"Der MCP-Server ruft Pfade auf, die es nicht mehr gibt: {tot}"


@pytest.mark.skipif(not MCP_SERVER.exists(), reason="MCP-Server nicht im Baum")
def test_mcp_kann_nichts_loeschen() -> None:
    """Die wichtigste Zusage: der Assistent zerstoert nichts."""
    text = MCP_SERVER.read_text(encoding="utf-8")
    assert "DELETE" not in text.upper().replace("DELETED", ""), (
        "Im MCP-Server steht ein DELETE. Loeschen bleibt draussen."
    )


@pytest.mark.skipif(not MCP_SERVER.exists(), reason="MCP-Server nicht im Baum")
def test_mcp_reicht_keinen_dokumenttext_durch() -> None:
    """Die zweite Zusage: der Assistent bekommt keine Dokumentinhalte.

    Seit dem OCR liefert ``/api/dokumente`` zu einem Treffer die Fundstelle im
    gelesenen Text mit. Fuer Mia am Bildschirm ist das richtig, es ist ihr
    Blatt. Ueber den MCP-Weg ginge derselbe Text an einen Assistenten und
    damit aus dem Haus, und das ist etwas anderes.

    Geprueft wird der Quelltext, weil genau das die Stelle ist, an der ein
    kuenftiges Werkzeug es vergessen wuerde: wer ``/api/dokumente`` oder
    ``/api/suche`` aufruft, muss ``stelle`` entfernen.
    """
    text = MCP_SERVER.read_text(encoding="utf-8")
    for endpunkt in ("/api/dokumente", "/api/suche"):
        assert endpunkt in text, f"{endpunkt} wird gar nicht mehr aufgerufen, Test veraltet"
    assert text.count('pop("stelle", None)') >= 2, (
        "Ein Werkzeug ruft /api/dokumente oder /api/suche auf, ohne die "
        "Fundstelle im OCR-Text zu entfernen. Dokumentinhalte bleiben draussen."
    )
