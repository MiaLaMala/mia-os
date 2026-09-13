"""MCP-Server fuer Mia OS.

Damit kann ein Assistent direkt in Mia OS schreiben und lesen, statt Mia
Sachen zu erzaehlen, die sie danach selbst eintippt.

Grundsatz: **schreiben ja, loeschen nein.** Es gibt bewusst kein Werkzeug
zum Loeschen von Eintraegen, Aufgaben oder Seiten. Ein Assistent, der eine
Anweisung falsch versteht, soll hoechstens Muell anlegen, nie etwas
vernichten. Aufraeumen macht Mia in der Oberflaeche.

Ebenfalls bewusst nicht drin: Dokumentinhalte. Im Index stehen Arztberichte
und Ausweise, deshalb liefert die Dokumentsuche nur Titel und Pfad.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer

BASIS = os.environ.get("MIA_OS_URL", "http://localhost:8080").rstrip("/")
ZEITLIMIT = float(os.environ.get("MIA_OS_TIMEOUT", "20"))

mcp = MCPServer("mia-os")


async def _hole(pfad: str, **params: Any) -> dict[str, Any]:
    sauber = {k: v for k, v in params.items() if v not in ("", None)}
    async with httpx.AsyncClient(timeout=ZEITLIMIT) as c:
        antwort = await c.get(f"{BASIS}{pfad}", params=sauber)
        antwort.raise_for_status()
        return antwort.json()


async def _sende(pfad: str, daten: dict[str, Any], methode: str = "POST") -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=ZEITLIMIT) as c:
        antwort = await c.request(methode, f"{BASIS}{pfad}", json=daten)
        if antwort.status_code >= 400:
            # Fehlertext durchreichen, sonst sieht der Aufrufer nur "400".
            raise RuntimeError(f"{antwort.status_code}: {antwort.text[:300]}")
        return antwort.json()


@mcp.tool()
async def briefing() -> dict[str, Any]:
    """Was heute ansteht: Termine, offene und faellige Eintraege, Aufgaben.

    Der schnellste Weg, den Stand zu sehen, bevor man etwas anlegt.
    """
    return await _hole("/api/briefing")


@mcp.tool()
async def notiz(text: str) -> dict[str, Any]:
    """Einen Satz eintragen, Mia OS deutet ihn selbst.

    "AU abgeben Freitag" wird ein Eintrag mit Datum, "88,4 kg" ein Gewicht,
    "Skyr 200g" eine Mahlzeit. Das ist der richtige Weg fuer alles, was Mia
    beilaeufig erzaehlt. Fuer strukturierte Sachen eintrag_anlegen nehmen.

    Args:
        text: Ein Satz, hoechstens 300 Zeichen.
    """
    return await _sende("/api/schnell", {"text": text})


@mcp.tool()
async def hinweis_aufs_display(text: str, von: str = "Jana") -> dict[str, Any]:
    """Einen kurzen Zettel auf Mias Tischdisplay legen.

    Erscheint beim naechsten Abruf (spaetestens nach zwei Minuten) als
    Kasten mit den Knoepfen "ok" und "spaeter". Fuer Dinge, die auf den
    Tisch gehoeren, nicht ins Handy: "Paket bei Nachbarin", "Jellyfin
    seit 12 min wieder oben". Nichts Privates, das Display steht offen
    am Arbeitsplatz.

    Args:
        text: Ein Satz, hoechstens 120 Zeichen.
        von: Wer den Zettel schreibt, z. B. "Jana" oder "Kuma".
    """
    return await _sende("/api/hinweise", {"text": text, "von": von})


@mcp.tool()
async def hinweise_liste() -> dict[str, Any]:
    """Alle Zettel mit Zustand, neueste zuerst.

    Zustand "fame" heisst: Mia hat viermal auf ok getippt, der Hinweis kam
    gut an. "shame" heisst viermal spaeter: so nie wieder formulieren.
    """
    return await _hole("/api/hinweise")


@mcp.tool()
async def eintrag_anlegen(
    titel: str,
    inhalt: str = "",
    datum: str = "",
    zeit: str = "",
    eigenschaften: dict[str, Any] | None = None,
    page_id: int = 0,
) -> dict[str, Any]:
    """Einen Eintrag mit Feldern anlegen.

    Args:
        titel: Pflicht, hoechstens 300 Zeichen.
        inhalt: Freitext.
        datum: ISO-Datum (2026-09-15), leer wenn undatiert.
        zeit: HH:MM.
        eigenschaften: z.B. {"Status": "offen", "Bereich": "Behörde"}.
        page_id: Seite, unter der er haengt. 0 = Hauptsammlung.
    """
    daten: dict[str, Any] = {"titel": titel, "inhalt": inhalt}
    if datum:
        daten["datum"] = datum
    if zeit:
        daten["zeit"] = zeit
    if eigenschaften:
        daten["eigenschaften"] = eigenschaften
    if page_id:
        daten["page_id"] = page_id
    return await _sende("/api/sammlung", daten)


@mcp.tool()
async def eintrag_aendern(
    entry_id: int,
    titel: str = "",
    inhalt: str = "",
    datum: str = "",
    eigenschaft_name: str = "",
    eigenschaft_wert: str = "",
    archiviert: bool | None = None,
) -> dict[str, Any]:
    """Einen bestehenden Eintrag aendern.

    Nur mitgegebene Felder werden angefasst. ``eigenschaft_name`` plus
    ``eigenschaft_wert`` setzt einen einzelnen Wert, ohne die anderen
    Eigenschaften zu ueberschreiben.

    Args:
        entry_id: ID aus eintraege_suchen oder briefing.
        archiviert: True legt den Eintrag ins Archiv (kein Loeschen).
    """
    daten: dict[str, Any] = {}
    if titel:
        daten["titel"] = titel
    if inhalt:
        daten["inhalt"] = inhalt
    if datum:
        daten["datum"] = datum
    if archiviert is not None:
        daten["archiviert"] = archiviert
    if eigenschaft_name:
        # Die API will den Namen als Zeichenkette und den Wert daneben.
        # Ein verschachteltes Objekt laeuft still durch, ohne etwas zu setzen.
        daten["eigenschaft"] = eigenschaft_name
        daten["wert"] = eigenschaft_wert
    if not daten:
        raise ValueError("Nichts zu aendern angegeben")
    return await _sende(f"/api/sammlung/{entry_id}", daten, methode="PATCH")


@mcp.tool()
async def eintraege_suchen(
    suche: str = "", von: str = "", bis: str = "", archiv: bool = False
) -> dict[str, Any]:
    """Eintraege durchsuchen oder einen Zeitraum abfragen.

    Args:
        suche: Suchbegriff, leer = alle.
        von: ISO-Datum ab wann.
        bis: ISO-Datum bis wann.
        archiv: True zeigt archivierte mit.
    """
    return await _hole("/api/sammlung", suche=suche, von=von, bis=bis, archiv=archiv)


@mcp.tool()
async def aufgabe_anlegen(titel: str, faellig_am: str = "") -> dict[str, Any]:
    """Eine Aufgabe anlegen.

    Args:
        titel: Pflicht.
        faellig_am: ISO-Datum, leer wenn ohne Frist.
    """
    daten: dict[str, Any] = {"titel": titel}
    if faellig_am:
        daten["faellig_am"] = faellig_am
    return await _sende("/api/aufgaben", daten)


@mcp.tool()
async def aufgabe_abhaken(task_id: int, erledigt: bool = True) -> dict[str, Any]:
    """Eine Aufgabe als erledigt markieren oder wieder oeffnen."""
    return await _sende(f"/api/aufgaben/{task_id}", {"erledigt": erledigt}, methode="PATCH")


@mcp.tool()
async def aufgaben() -> dict[str, Any]:
    """Alle Aufgaben mit Status und Frist."""
    return await _hole("/api/aufgaben")


@mcp.tool()
async def termine(von: str = "", bis: str = "") -> dict[str, Any]:
    """Termine aus Mias Kalendern.

    Args:
        von: ISO-Datum, leer = heute.
        bis: ISO-Datum, leer = 30 Tage nach ``von``.
    """
    # Die API verlangt beide Daten. Ohne Vorgabe kaeme ein 422 beim
    # Aufrufer an, obwohl "die naechsten Wochen" die normale Frage ist.
    beginn = date.fromisoformat(von) if von else date.today()
    ende = date.fromisoformat(bis) if bis else beginn + timedelta(days=30)
    return await _hole("/api/termine", von=beginn.isoformat(), bis=ende.isoformat())


@mcp.tool()
async def suche(q: str) -> dict[str, Any]:
    """Ueber alles suchen: Seiten, Eintraege, Termine, Dokumente.

    Dokumente kommen nur bei ausdruecklicher Suche und nur mit Titel und
    Pfad, nie mit Inhalt. Die Fundstelle im gelesenen Text faellt hier
    genauso raus wie bei ``dokumente_suchen``: sie gehoert auf Mias
    Bildschirm, nicht in eine Antwort, die das Haus verlaesst.

    Args:
        q: Mindestens zwei Zeichen.
    """
    antwort = await _hole("/api/suche", q=q)
    for treffer in antwort.get("dokumente", []):
        treffer.pop("stelle", None)
    return antwort


@mcp.tool()
async def seiten() -> dict[str, Any]:
    """Der Seitenbaum: welche Bereiche es gibt und ihre IDs.

    Vor eintrag_anlegen aufrufen, wenn der Eintrag unter eine bestimmte
    Seite soll.
    """
    return await _hole("/api/seiten")


@mcp.tool()
async def seite_anlegen(
    titel: str, parent_id: int | None = None, hat_sammlung: bool = False
) -> dict[str, Any]:
    """Eine neue Seite anlegen.

    Args:
        titel: Name der Seite.
        parent_id: Uebergeordnete Seite, None = oberste Ebene.
        hat_sammlung: True, wenn die Seite Eintraege sammeln soll.
    """
    daten: dict[str, Any] = {"titel": titel, "hat_sammlung": hat_sammlung}
    if parent_id is not None:
        daten["parent_id"] = parent_id
    return await _sende("/api/seiten", daten)


@mcp.tool()
async def dokumente_suchen(q: str = "", ordner: str = "") -> dict[str, Any]:
    """Dokumente im Index finden. Nur Titel und Pfad, nie Inhalte.

    Seit dem OCR liefert die Weboberflaeche zu einem Treffer die Fundstelle im
    gelesenen Text mit. **Die wird hier absichtlich weggeworfen.** Mia sieht
    sie auf ihrem Bildschirm, das ist ihr Blatt und ihre Entscheidung. Ueber
    diesen Weg ginge derselbe Text an einen Assistenten und damit aus dem Haus,
    und das ist etwas anderes.

    Args:
        q: Suchbegriff.
        ordner: Ordner eingrenzen.
    """
    antwort = await _hole("/api/dokumente", q=q, ordner=ordner)
    for treffer in antwort.get("treffer", []):
        treffer.pop("stelle", None)
        treffer.pop("hat_text", None)
    return antwort


@mcp.tool()
async def dokument_anhaengen(entry_id: int, dokument_id: int) -> dict[str, Any]:
    """Ein Dokument aus dem Index an einen Eintrag haengen.

    Der uebliche Weg: erst ``dokumente_suchen``, dann die ``id`` des richtigen
    Treffers hier eintragen. Verknuepft wird nur, die Datei selbst wird weder
    gelesen noch verschoben.

    Args:
        entry_id: ID des Eintrags, aus eintraege_suchen oder briefing.
        dokument_id: ID aus dokumente_suchen.
    """
    return await _sende(f"/api/sammlung/{entry_id}/dokumente", {"dokument_id": dokument_id})


@mcp.tool()
async def eintrag_dokumente(entry_id: int) -> dict[str, Any]:
    """Welche Dokumente an einem Eintrag haengen. Nur Titel und Pfad.

    Args:
        entry_id: ID des Eintrags.
    """
    return await _hole(f"/api/sammlung/{entry_id}/dokumente")


@mcp.tool()
async def berichtsheft(montag: str = "") -> dict[str, Any]:
    """Das Wochenblatt des Ausbildungsnachweises.

    Der Entwurf kommt aus den Kalendern: Tage, Stunden und Anhaltspunkte
    stehen schon drin, die Taetigkeiten sind leer. Der Kalender weiss WANN
    Mia gearbeitet hat, nicht WAS sie gemacht hat: **niemals Taetigkeiten
    erfinden**, nur eintragen, was Mia selbst sagt.

    Args:
        montag: Ein beliebiges Datum in der Woche, leer = laufende Woche.
    """
    return await _hole("/api/berichtsheft", montag=montag)


@mcp.tool()
async def berichtsheft_wochen(anzahl: int = 12) -> dict[str, Any]:
    """Welche Wochen noch offen sind.

    Args:
        anzahl: Wie viele Wochen zurueck, hoechstens 52.
    """
    return await _hole("/api/berichtsheft/wochen", anzahl=anzahl)


@mcp.tool()
async def berichtsheft_eintragen(
    tag: str,
    taetigkeiten: list[str],
    ersetzen: bool = False,
) -> dict[str, Any]:
    """Taetigkeiten fuer einen Tag ins Berichtsheft schreiben.

    Der uebliche Weg: Mia erzaehlt im Chat, was sie gemacht hat, und es
    landet direkt im richtigen Tag. Der passende Montag wird selbst
    ermittelt, Stunden bleiben unangetastet.

    Args:
        tag: ISO-Datum des Tages.
        taetigkeiten: Eine Zeile je Taetigkeit, in Mias eigenen Worten.
        ersetzen: True loescht vorhandene Zeilen, sonst wird angehaengt.
    """
    datum = date.fromisoformat(tag)
    montag = datum - timedelta(days=datum.weekday())

    zeilen = [z.strip() for z in taetigkeiten if z.strip()]
    if not ersetzen:
        woche = await _hole("/api/berichtsheft", montag=montag.isoformat())
        vorhanden = next(
            (t["taetigkeiten"] for t in woche["tage"] if t["datum"] == tag),
            [],
        )
        # Doppelte vermeiden: sonst steht dieselbe Taetigkeit dreimal da,
        # wenn Mia sie im Gespraech mehrfach erwaehnt.
        zeilen = [z for z in vorhanden if z.strip()] + [z for z in zeilen if z not in vorhanden]

    return await _sende(
        "/api/berichtsheft",
        {"montag": montag.isoformat(), "inhalt": {tag: {"taetigkeiten": zeilen}}},
    )
