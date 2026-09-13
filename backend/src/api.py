"""JSON-Schnittstelle fuer das Svelte-Frontend.

Getrennt von main.py, damit die Zustaendigkeit klar bleibt: hier steht, WAS
das Frontend bekommt, nicht wie es aussieht.

Die Aufbereitung selbst (Kalenderfarben, Dienstzustaende, Kennzahlen) liegt
weiter in main.py und wird von hier benutzt, statt sie ein zweites Mal zu
schreiben.
"""

from __future__ import annotations

import logging
import re
from base64 import b64encode
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from src import belege, namen, ocr, ordner, scanner
from src import ueber as ueber_modul
from src.categories import CATEGORIES
from src.config import settings
from src.einstellungen import EINSTELLUNGEN, als_schalter, als_zahl, mit_vorgaben

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/uebersicht")
async def uebersicht() -> dict[str, Any]:
    """Alle Kacheln fuer die Startseite."""
    from src.main import _card, _stamp

    return {
        "kacheln": [_card(c.key) for c in CATEGORIES],
        "stand": _stamp(),
        "owner": _owner(),
    }


@router.get("/termine")
async def termine(von: str, bis: str, kalender: str = "") -> dict[str, Any]:
    """Termine im Zeitfenster, in der Form die FullCalendar erwartet.

    ``von`` und ``bis`` kommen als ISO-Datum. FullCalendar fragt beim
    Blaettern selbst nach, deshalb keine feste Spanne.
    """
    from src.main import _kalenderfarbe, _termin_ansicht, get_store
    from src.sammlung import props_anlegen

    beginn = _pflichtdatum(von, "von")
    ende = _pflichtdatum(bis, "bis")
    if ende < beginn:
        raise HTTPException(status_code=400, detail="bis liegt vor von")
    if (ende - beginn).days > 400:
        raise HTTPException(status_code=400, detail="Zeitraum zu groß")

    store = get_store()
    # Sonst haben Sammlungseintraege keine Statusfarbe, wenn der Kalender vor
    # der Sammlungsseite geladen wird.
    props_anlegen(store)
    roh = store.events(
        datetime.combine(beginn, dtime.min).isoformat(),
        datetime.combine(ende, dtime.max).isoformat(),
        limit=1200,
    )
    if kalender:
        roh = [e for e in roh if e["calendar"] == kalender]

    # In EINER Abfrage holen, woran Notizen und Aufgaben haengen: sonst
    # kaeme pro Termin eine eigene Abfrage.
    uids = [str(e["uid"]) for e in roh]
    notizen = store.notes_for(uids)
    mit_aufgaben: dict[str, int] = {}
    for uid in set(uids):
        offen = [t for t in store.tasks_for_event(uid) if not t["erledigt"]]
        if offen:
            mit_aufgaben[uid] = len(offen)

    heute = date.today()
    termine = []
    for e in roh:
        ansicht = _termin_ansicht(e, heute)
        uid = str(e["uid"])
        termine.append(
            {
                "id": uid,
                "title": ansicht["titel"],
                "start": e["start_at"],
                "end": e["end_at"] or None,
                "allDay": bool(e["ganztags"]),
                "kalender": e["calendar"],
                "ort": e["location"] or "",
                "farbe": _kalenderfarbe(e["calendar"]),
                # Damit das Blatt zeigen kann, wo etwas dranhaengt.
                "hat_notiz": uid in notizen,
                "offene_aufgaben": mit_aufgaben.get(uid, 0),
            }
        )

    # Eintraege aus der Sammlung mit Datum gehoeren MIT ins Kalenderblatt.
    # Das ist der Kern des Notion-Modells: der Kalender ist eine ANSICHT auf
    # die Sammlung, kein getrenntes Werkzeug. Ein Eintrag mit Datum steht
    # gleichzeitig in Liste, Board, Tabelle und hier.
    for e in store.list_entries(von=beginn.isoformat(), bis=ende.isoformat(), nur_mit_datum=True):
        zeit = e["zeit"] or ""
        beginnt = f"{e['datum']}T{zeit}" if zeit else e["datum"]
        termine.append(
            {
                "id": f"eintrag-{e['id']}",
                "title": e["titel"],
                "start": beginnt,
                "end": None,
                "allDay": not zeit,
                "kalender": "Sammlung",
                "ort": "",
                "farbe": _eintragsfarbe(e, store),
                "hat_notiz": bool(e["inhalt"]),
                "offene_aufgaben": 0,
                # Damit die Oberflaeche weiss: das ist ein eigener Eintrag,
                # kein iCloud-Termin, und gehoert ins Eintragsblatt.
                "eintrag_id": e["id"],
            }
        )

    # Aufgaben mit Faelligkeit gehoeren ins Kalenderblatt: sie sind der
    # Grund, warum ein Tag voll ist, auch wenn kein Termin darauf liegt.
    return {
        "termine": termine,
        "kalender": store.event_calendars(),
        "aufgaben_je_tag": store.tasks_by_day(beginn.isoformat(), ende.isoformat()),
    }


def _eintragsfarbe(eintrag: dict[str, Any], store: Any) -> str:
    """Die Farbe eines Sammlungseintrags kommt aus seiner Statusfarbe.

    So sieht "fertig" im Kalender genauso aus wie im Board: dieselbe Sache,
    derselbe Farbton.
    """
    farbnamen = {
        "grau": "#8e8e93",
        "blau": "#0a84ff",
        "gruen": "#30d158",
        "gelb": "#ffd60a",
        "rot": "#ff453a",
        "lila": "#bf5af2",
        "rosa": "#ff375f",
        "orange": "#ff9f0a",
    }
    for prop in store.list_props():
        if prop["art"] != "auswahl":
            continue
        wert = eintrag["eigenschaften"].get(prop["key"])
        if not wert:
            continue
        for option in prop["optionen"]:
            if option.get("wert") == wert:
                return farbnamen.get(option.get("farbe", "grau"), "#8e8e93")
    return "#8e8e93"


def _zahl(roh: str | None) -> int:
    """Eine Zahl aus der Anfrage, 0 wenn keine da ist."""
    try:
        return max(0, int(roh or 0))
    except (TypeError, ValueError):
        return 0


@router.post("/kopplung/code")
async def kopplung_code() -> dict[str, Any]:
    """Einen Kopplungscode erzeugen.

    Erreichbar nur, wer schon drin ist: aus dem Heimnetz oder mit einem
    Schluessel. Genau das macht den Code sicher, obwohl er nur sechs Ziffern
    hat. Wer ihn ablesen kann, koennte die Daten ohnehin sehen.
    """
    from src.zugang import hole_kopplung

    code, bis = hole_kopplung().anlegen()
    return {"code": code, "gilt_bis": bis.isoformat()}


@router.post("/kopplung/einloesen")
async def kopplung_einloesen(request: Request) -> dict[str, Any]:
    """Einen Code gegen einen Geraeteschluessel tauschen.

    Der einzige Endpunkt unter ``/api``, der ohne Nachweis antwortet: er ist
    der Weg herein und kann ihn nicht voraussetzen. Statt eines Nachweises
    steht der Code davor, der zehn Minuten gilt und genau einmal.

    Der Schluessel wird hier **einmal** zurueckgegeben und danach nie wieder:
    gespeichert ist nur sein Abdruck. Verliert die App ihn, koppelt sie neu.
    """
    from src.main import get_store
    from src.zugang import abdruck as zugang_abdruck
    from src.zugang import hole_kopplung, neuer_schluessel

    daten = await request.json() if await request.body() else {}
    code = str(daten.get("code", "")).strip()
    if not hole_kopplung().einloesen(code):
        # Bewusst dieselbe Antwort fuer "gibt es nicht", "abgelaufen" und
        # "zu oft falsch": jede Unterscheidung waere ein Hinweis fuer den,
        # der raet.
        raise HTTPException(status_code=403, detail="Code gilt nicht")

    schluessel = neuer_schluessel()
    name = str(daten.get("name", "")).strip()[:64] or "Unbenanntes Gerät"
    plattform = str(daten.get("plattform", "")).strip()[:32]
    zugang_id = get_store().geraetezugang_anlegen(zugang_abdruck(schluessel), name, plattform)
    log.info("Gerät gekoppelt: %s (%s), id %d", name, plattform or "?", zugang_id)
    return {"schluessel": schluessel, "id": zugang_id, "name": name}


@router.get("/kopplung/geraete")
async def kopplung_geraete() -> dict[str, Any]:
    """Welche Apps gekoppelt sind."""
    from src.main import get_store

    return {"geraete": get_store().geraetezugaenge()}


@router.delete("/kopplung/geraete/{zugang_id}")
async def kopplung_loeschen(zugang_id: int) -> dict[str, Any]:
    """Eine App abmelden. Ihr Schluessel gilt ab dem naechsten Aufruf nicht mehr."""
    from src.main import get_store

    if not get_store().geraetezugang_loeschen(zugang_id):
        raise HTTPException(status_code=404, detail="Kein solches Gerät")
    return {"ok": True}


@router.get("/handgelenk")
async def handgelenk() -> dict[str, Any]:
    """Der Tag in der kleinstmöglichen Form, für die Uhr.

    Bewusst ein eigener Endpunkt und nicht ``/api/briefing``: eine
    Komplikation auf dem Zifferblatt wacht den ganzen Tag über alle paar
    Minuten auf, und das Briefing trägt Hinweise, Geräte-Einstellungen und
    einen fertigen Fließtext mit. Das sind mehrere Kilobyte für zwei Zahlen
    und eine Zeile Text, und auf einer Uhr ist jedes übertragene Byte
    Akkulaufzeit.

    Der Unterschied zum Briefing steckt in ``jetzt``: das Briefing zeigt den
    ganzen Tag, die Uhr zeigt, was **noch kommt**. Ein Termin um neun ist um
    halb elf keine nützliche Anzeige mehr.
    """
    from src.main import _termin_ansicht, get_store

    store = get_store()
    jetzt = datetime.now()
    heute = jetzt.date()

    # Von jetzt bis Mitternacht. Ganztägige Termine bleiben den ganzen Tag
    # stehen: sie haben keine Uhrzeit, die vergehen könnte.
    roh = store.events(
        datetime.combine(heute, dtime.min).isoformat(),
        datetime.combine(heute, dtime.max).isoformat(),
        limit=50,
    )
    offen_heute = [
        e for e in roh if e["ganztags"] or datetime.fromisoformat(str(e["start_at"])) >= jetzt
    ]

    naechster: dict[str, Any] | None = None
    if offen_heute:
        ansicht = _termin_ansicht(offen_heute[0], heute)
        naechster = {
            "titel": ansicht["titel"],
            "zeit": ansicht["beginn"] if not offen_heute[0]["ganztags"] else "",
            "ort": ansicht["ort"],
        }

    eintraege = store.list_entries()
    offene = [e for e in eintraege if e["eigenschaften"].get("status") != "fertig"]
    faellig = [e for e in offene if e["datum"] and e["datum"] <= heute.isoformat()]

    return {
        "naechster": naechster,
        "spaeter_heute": max(0, len(offen_heute) - 1),
        "faellig": len(faellig),
        "offen": len(offene),
        # Wann diese Zahlen entstanden sind. Die Uhr zeigt notfalls den
        # letzten bekannten Stand an und muss sagen können, wie alt er ist:
        # eine Komplikation, die stumm veraltete Zahlen zeigt, ist schlimmer
        # als eine leere.
        "stand": jetzt.isoformat(timespec="seconds"),
    }


@router.get("/app/neueste")
async def app_neueste() -> dict[str, Any]:
    """Welche Fassung der Apps bereitsteht.

    Die App fragt beim Start und danach höchstens täglich. Sie vergleicht
    selbst mit ihrer eigenen Nummer: der Server weiß nicht, was auf welchem
    Gerät läuft, und soll es auch nicht wissen müssen.
    """
    from src.apps import hole_apps

    stand = hole_apps().stand()
    return {
        "version": stand.get("version", ""),
        "gebaut_am": stand.get("gebaut_am", ""),
        "mac": stand.get("mac", {}),
        "ios": stand.get("ios", {}),
    }


@router.get("/app/datei/{art}")
async def app_datei(art: str) -> FileResponse:
    """Die App selbst. ``art`` ist ``mac`` oder ``ios``."""
    from src.apps import hole_apps

    datei = hole_apps().datei(art)
    if datei is None:
        raise HTTPException(status_code=404, detail="Keine App für diese Art")
    return FileResponse(
        datei,
        media_type="application/octet-stream",
        # Ohne den Namen lädt der Browser eine Datei, die "art" heißt und
        # sich nicht öffnen lässt.
        filename=datei.name,
    )


@router.get("/firmware/neueste")
async def firmware_neueste(request: Request) -> dict[str, Any]:
    """Welche Fassung bereitsteht, und nebenbei: wer hat gefragt.

    Das Gerät schickt seine Kennung und die laufende Version mit. Damit
    weiß der Server, was auf dem Schreibtisch steht, ohne dass es dafür
    einen eigenen Abruf braucht.
    """
    from src.firmware import hole_firmware

    fw = hole_firmware()
    kennung = str(request.query_params.get("kennung", "")).strip()[:64]
    if kennung:
        fw.melden(
            kennung=kennung,
            name=str(request.query_params.get("name", "")).strip()[:64],
            version=str(request.query_params.get("version", "")).strip()[:32],
            adresse=request.client.host if request.client else "",
            bild_us=_zahl(request.query_params.get("bild_us")),
            heap=_zahl(request.query_params.get("heap")),
        )

    stand = fw.stand()
    return {
        "version": stand.get("version", ""),
        "groesse": stand.get("groesse", 0),
        "sha256": stand.get("sha256", ""),
        "gebaut_am": stand.get("gebaut_am", ""),
    }


@router.get("/firmware/datei")
async def firmware_datei() -> FileResponse:
    """Die Binärdatei selbst, durchgereicht aus dem Zweig."""
    from src.firmware import hole_firmware

    datei = hole_firmware().datei()
    if datei is None:
        raise HTTPException(status_code=404, detail="Keine Firmware da")
    return FileResponse(datei, media_type="application/octet-stream")


@router.get("/geraete")
async def geraete() -> dict[str, Any]:
    """Welche Geräte sich gemeldet haben und was darauf läuft."""
    from src.firmware import hole_firmware

    return {"geraete": hole_firmware().geraete()}


def _geraet_einstellungen() -> dict[str, str]:
    """Die display_* Einstellungen ohne Vorsilbe, so wie das Gerät sie liest."""
    from src.main import get_store

    werte = mit_vorgaben(get_store().get_settings())
    return {k[len("display_") :]: v for k, v in werte.items() if k.startswith("display_")}


@router.get("/geraete/einstellungen")
async def geraete_einstellungen(request: Request) -> dict[str, Any]:
    """Einstellungen für das Display, mit Warten auf Änderung.

    ``seit`` ist der Stand, den das Gerät zuletzt gesehen hat. Ist er noch
    aktuell, hält die Anfrage bis zu ``warten`` Sekunden offen und kommt
    in dem Moment zurück, in dem Mia etwas speichert. So wirkt eine
    Änderung in unter einer Sekunde, ohne dass der Server das Gerät hinter
    dem NAT des Pi erreichen müsste.
    """
    from src.firmware import hole_firmware

    fw = hole_firmware()
    seit = _zahl(request.query_params.get("seit"))
    warten = min(_zahl(request.query_params.get("warten")), 60)
    if warten:
        await fw.warten(seit, warten)
    return {"stand": fw.einstellungs_stand, "geraet": _geraet_einstellungen()}


@router.get("/seiten")
async def seiten() -> dict[str, Any]:
    """Alle Seiten flach. Den Baum baut die Oberflaeche daraus."""
    from src.main import get_store
    from src.sammlung import startseiten_anlegen

    store = get_store()
    startseiten_anlegen(store)
    return {"seiten": store.list_pages()}


@router.post("/seiten")
async def seite_anlegen(daten: dict[str, Any]) -> dict[str, Any]:
    """Neue Seite, optional unter einer anderen."""
    from src.main import get_store

    titel = str(daten.get("titel", "")).strip() or "Neue Seite"
    if len(titel) > 200:
        raise HTTPException(status_code=400, detail="Titel zu lang")

    eltern = daten.get("parent_id")
    store = get_store()
    if eltern is not None and not store.get_page(int(eltern)):
        raise HTTPException(status_code=400, detail="Übergeordnete Seite fehlt")

    neue_id = store.create_page(
        titel,
        parent_id=None if eltern is None else int(eltern),
        symbol=str(daten.get("symbol", "document")),
        hat_sammlung=bool(daten.get("hat_sammlung", False)),
    )
    return {"seite": store.get_page(neue_id)}


@router.get("/seiten/{page_id}")
async def seite_lesen(page_id: int) -> dict[str, Any]:
    """Eine Seite samt ihrer Eintraege und dem Weg dorthin."""
    from src.main import get_store
    from src.sammlung import props_anlegen

    store = get_store()
    seite = store.get_page(page_id)
    if not seite:
        raise HTTPException(status_code=404, detail="Seite nicht gefunden")

    props_anlegen(store)
    alle = {p["id"]: p for p in store.list_pages()}

    # Der Weg von ganz oben bis hierher, fuer die Brotkrumen.
    weg: list[dict[str, Any]] = []
    aktuell: dict[str, Any] | None = seite
    while aktuell:
        weg.insert(0, {"id": aktuell["id"], "titel": aktuell["titel"]})
        eltern_id = aktuell.get("parent_id")
        aktuell = alle.get(eltern_id) if eltern_id else None

    # Eine Sammelseite zeigt alles, egal wo es liegt. Sonst nur das Eigene.
    eintraege: list[dict[str, Any]] = []
    if seite["hat_sammlung"]:
        eintraege = store.list_entries(page_id=None if seite["sammelt_alles"] else page_id)

    return {
        "seite": seite,
        "weg": weg,
        "unterseiten": [p for p in alle.values() if p["parent_id"] == page_id],
        "eintraege": eintraege,
        "eigenschaften": store.list_props(),
        # Damit die Oberflaeche einen Eintrag von "Alles" aus seiner Seite
        # zuordnen kann, ohne jede Seite einzeln zu laden.
        "seitentitel": {p["id"]: p["titel"] for p in alle.values()},
        "anhaenge": {str(k): v for k, v in store.document_counts().items()},
    }


@router.patch("/seiten/{page_id}")
async def seite_aendern(page_id: int, daten: dict[str, Any]) -> dict[str, Any]:
    from src.main import get_store

    store = get_store()
    if not store.get_page(page_id):
        raise HTTPException(status_code=404, detail="Seite nicht gefunden")

    if "titel" in daten and not str(daten["titel"]).strip():
        raise HTTPException(status_code=400, detail="Titel darf nicht leer sein")

    # Eine Seite darf nicht unter sich selbst haengen: das erzeugt einen
    # Kreis, den der Baum nicht mehr zeichnen kann.
    if "parent_id" in daten and daten["parent_id"] is not None:
        ziel = int(daten["parent_id"])
        if ziel == page_id:
            raise HTTPException(status_code=400, detail="Seite kann nicht in sich selbst")
        alle = {p["id"]: p for p in store.list_pages()}
        lauf: int | None = ziel
        while lauf:
            if lauf == page_id:
                raise HTTPException(status_code=400, detail="Das würde einen Kreis erzeugen")
            lauf = alle.get(lauf, {}).get("parent_id")

    store.update_page(page_id, **daten)
    return {"seite": store.get_page(page_id)}


@router.delete("/seiten/{page_id}")
async def seite_loeschen(page_id: int) -> dict[str, Any]:
    """Seite loeschen. Unterseiten und ihre Eintraege gehen mit."""
    from src.main import get_store

    if not get_store().delete_page(page_id):
        raise HTTPException(status_code=404, detail="Seite nicht gefunden")
    return {"ok": True}


@router.get("/sammlung")
async def sammlung(
    von: str = "",
    bis: str = "",
    suche: str = "",
    archiv: bool = False,
) -> dict[str, Any]:
    """Alle Eintraege plus die Eigenschaften.

    EINE Abfrage fuer alle Ansichten: Kalender, Tabelle, Board und Liste
    zeigen dieselben Zeilen, nur anders angeordnet. Genau das ist der
    Unterschied zu vier getrennten Werkzeugen.
    """
    from src.main import get_store
    from src.sammlung import props_anlegen

    store = get_store()
    props_anlegen(store)

    return {
        "eintraege": store.list_entries(von=von, bis=bis, suche=suche, mit_archiv=archiv),
        "eigenschaften": store.list_props(),
        # Wie viele Dokumente an welchem Eintrag haengen, in einem Rutsch.
        # Die Oberflaeche zeichnet daraus die Bueroklammer.
        "anhaenge": {str(k): v for k, v in store.document_counts().items()},
    }


@router.post("/sammlung")
async def eintrag_anlegen(daten: dict[str, Any]) -> dict[str, Any]:
    """Neuer Eintrag. Wie eine neue Seite in Notion."""
    from src.main import get_store
    from src.sammlung import startseiten_anlegen

    titel = str(daten.get("titel", "")).strip()
    if not titel:
        raise HTTPException(status_code=400, detail="Titel fehlt")
    if len(titel) > 300:
        raise HTTPException(status_code=400, detail="Titel zu lang")

    datum = str(daten.get("datum", ""))
    if datum:
        _pflichtdatum(datum, "datum")

    store = get_store()
    startseiten_anlegen(store)
    page_id = int(daten.get("page_id") or 0)
    # Auf einer Sammelseite angelegt heisst: ohne eigene Seite. Sonst
    # wuerde "Alles" zu einem Ordner, in dem Eintraege verschwinden.
    seite = store.get_page(page_id) if page_id else None
    if seite and seite["sammelt_alles"]:
        page_id = 0
    neue_id = store.create_entry(
        titel=titel,
        inhalt=str(daten.get("inhalt", "")),
        eigenschaften=daten.get("eigenschaften") or {},
        datum=datum,
        zeit=str(daten.get("zeit", "")),
        event_uid=str(daten.get("event_uid", "")),
        page_id=page_id,
    )
    eintrag = store.get_entry(neue_id)
    return {"eintrag": eintrag}


@router.get("/sammlung/{entry_id}")
async def eintrag_lesen(entry_id: int) -> dict[str, Any]:
    from src.main import get_store

    eintrag = get_store().get_entry(entry_id)
    if not eintrag:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    return {"eintrag": eintrag}


@router.patch("/sammlung/{entry_id}")
async def eintrag_aendern(entry_id: int, daten: dict[str, Any]) -> dict[str, Any]:
    """Felder aendern. Auch einzelne Eigenschaften.

    ``eigenschaft`` setzt einen einzelnen Wert, ohne die anderen zu
    ueberschreiben: sonst wuerde ein Klick auf "Status" die Tags loeschen.
    """
    from src.main import get_store

    store = get_store()
    vorher = store.get_entry(entry_id)
    if not vorher:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    felder: dict[str, Any] = {}
    for name in ("titel", "inhalt", "datum", "zeit", "event_uid", "archiviert", "page_id"):
        if name in daten:
            felder[name] = daten[name]

    if felder.get("datum"):
        _pflichtdatum(str(felder["datum"]), "datum")
    if "titel" in felder and not str(felder["titel"]).strip():
        raise HTTPException(status_code=400, detail="Titel darf nicht leer sein")

    if "eigenschaften" in daten:
        felder["eigenschaften"] = daten["eigenschaften"]
    elif "eigenschaft" in daten:
        schluessel = str(daten["eigenschaft"])
        neue = dict(vorher["eigenschaften"])
        wert = daten.get("wert")
        # Leerer Wert entfernt die Eigenschaft, statt "" zu speichern.
        if wert in (None, "", []):
            neue.pop(schluessel, None)
        else:
            neue[schluessel] = wert
        felder["eigenschaften"] = neue

    if not felder:
        raise HTTPException(status_code=400, detail="Nichts zu ändern")

    store.update_entry(entry_id, **felder)
    return {"eintrag": store.get_entry(entry_id)}


@router.get("/sammlung/{entry_id}/dokumente")
async def eintrag_dokumente(entry_id: int) -> dict[str, Any]:
    """Welche Dokumente an diesem Eintrag haengen."""
    from src.main import get_store

    store = get_store()
    if not store.get_entry(entry_id):
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    return {"dokumente": _anhaenge(store, entry_id)}


@router.post("/sammlung/{entry_id}/dokumente")
async def eintrag_dokument_anhaengen(entry_id: int, daten: dict[str, Any]) -> dict[str, Any]:
    """Ein Dokument aus dem Index an den Eintrag haengen.

    Angesprochen wird es ueber die Index-ID, gespeichert wird der Pfad: die ID
    wechselt, wenn eine Datei aus dem Index faellt und wiederkommt.
    """
    from src.main import get_store

    store = get_store()
    if not store.get_entry(entry_id):
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    doc_id = int(daten.get("dokument_id") or 0)
    doc = store.document_by_id(doc_id) if doc_id else None
    if not doc:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    store.link_document(entry_id, doc["source"], doc["path"], doc["name"])
    return {"dokumente": _anhaenge(store, entry_id)}


@router.delete("/sammlung/{entry_id}/dokumente")
async def eintrag_dokument_loesen(entry_id: int, source: str, path: str) -> dict[str, Any]:
    """Die Verknuepfung loesen. Die Datei in Nextcloud bleibt unberuehrt.

    Bewusst ueber ``source`` und ``path`` statt ueber die Index-ID: eine
    verschwundene Datei muss sich auch dann noch abhaengen lassen, wenn sie
    gar nicht mehr im Index steht.
    """
    from src.main import get_store

    store = get_store()
    if not store.unlink_document(entry_id, source, path):
        raise HTTPException(status_code=404, detail="Verknüpfung nicht gefunden")
    return {"ok": True}


@router.post("/scan/vorschau")
async def scan_vorschau(
    datei: Annotated[UploadFile, File()],
    staerke: Annotated[str, Form()] = "weich",
    ecken: Annotated[str, Form()] = "",
) -> dict[str, Any]:
    """Ein Foto aufbereiten und zurueckzeigen, ohne etwas zu speichern.

    Zwei Schritte statt einem, weil die Kantenerkennung scheitern darf:
    weisses Blatt auf hellem Tisch, geknicktes Papier, schlechtes Licht. Ein
    Bescheid, der so beschnitten wurde, dass das Aktenzeichen fehlt, waere
    schlimmer als ein unbearbeitetes Foto. Also sieht Mia erst das Ergebnis
    und kann die Ecken ziehen, bevor irgendwas nach Nextcloud geht.

    Das Original bleibt im Browser. Es ein zweites Mal hochzuladen ist im
    Heimnetz billiger, als es serverseitig zwischenzulagern: eine Halde
    halbfertiger Fotos von Ausweisen will hier niemand.
    """
    inhalt = await datei.read()
    try:
        vorgabe = scanner.ecken_aus_text(ecken)
        bild, gefunden, groesse = scanner.vorschau(inhalt, vorgabe, staerke)
    except ValueError as fehler:
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler

    return {
        "bild": "data:image/jpeg;base64," + b64encode(bild).decode(),
        "ecken": scanner.ecken_finden(inhalt) if vorgabe is None else vorgabe,
        "automatisch": gefunden,
        "breite": groesse[0],
        "hoehe": groesse[1],
    }


@router.post("/sammlung/{entry_id}/beleg")
async def eintrag_beleg_hochladen(
    entry_id: int,
    datei: Annotated[UploadFile, File()],
    scannen: Annotated[bool, Form()] = False,
    staerke: Annotated[str, Form()] = "weich",
    ecken: Annotated[str, Form()] = "",
) -> dict[str, Any]:
    """Ein Foto oder PDF hochladen, ablegen und gleich an den Eintrag haengen.

    Der bisherige Weg setzte voraus, dass die Datei schon in Nextcloud liegt.
    Der haeufigere Fall ist der andere: Mia hat einen Bescheid in der Hand,
    fotografiert ihn, und danach liegt das Bild in der Kamerarolle statt bei
    dem Vorgang, zu dem es gehoert.

    Der Name kommt aus dem Eintrag, nicht vom Handy: ``IMG_4711.jpg`` findet
    im Index niemand wieder, dort wird ueber Dateinamen gesucht.
    """
    from src.main import _als_datum, get_store

    store = get_store()
    eintrag = store.get_entry(entry_id)
    if not eintrag:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    inhalt = await datei.read()
    gescannt = False
    # Der aufbereitete Scan als Bild. Das PDF traegt ihn als Seite, aber OCR
    # liest vom Bild: Tesseract nimmt kein PDF als Eingabe.
    scanbild = b""
    try:
        endung = belege.endung_pruefen(datei.filename or "", inhalt)

        # Scannen nur bei Bildern. Ein PDF ist bereits ein Dokument, es durch
        # die Bildaufbereitung zu schicken wuerde es in ein Foto verwandeln.
        if scannen and endung != ".pdf":
            inhalt, _ = scanner.verarbeiten(inhalt, scanner.ecken_aus_text(ecken), staerke)
            # Der Scanner liefert immer JPEG, egal was hereinkam. Ohne das
            # traegt eine gescannte HEIC-Aufnahme weiter ihre alte Endung und
            # niemand kann sie oeffnen.
            endung = ".jpg"
            gescannt = True
            scanbild = inhalt

            # Ein Bescheid ist ein Dokument, kein Foto. Als PDF laesst er sich
            # ueberall oeffnen, drucken und weiterleiten, und Tesseract legt
            # den gelesenen Text als unsichtbare Ebene darunter: im Betrachter
            # findet Mia damit das Aktenzeichen per Strg+F.
            #
            # Kostet nichts extra, Tesseract liest ohnehin. Scheitert es,
            # bleibt es beim Bild: ein abgelegter Beleg ist mehr wert als ein
            # sauberes Format.
            pdf = await ocr.als_pdf(scanbild)
            if pdf:
                inhalt = pdf
                endung = ".pdf"

        # Das Datum des Eintrags, nicht das von heute: ein Bescheid vom 3.
        # wird oft erst am 9. fotografiert, und im Index soll stehen, worum
        # es geht, nicht wann Mia dazu kam.
        tag = _als_datum(eintrag.get("datum", "")) or date.today()
        name = belege.zielname(eintrag["titel"], endung, tag)
        pfad, file_id = await belege.ablegen(inhalt, name)
    except belege.BelegError as fehler:
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler
    except ValueError as fehler:
        raise HTTPException(status_code=400, detail=f"Bild nicht lesbar: {fehler}") from fehler
    except httpx.HTTPError as fehler:
        raise HTTPException(status_code=502, detail="Nextcloud nicht erreichbar") from fehler

    # Sofort in den Index, nicht erst beim naechsten Crawl: sonst stuende der
    # frische Beleg bis zu einer Stunde als "nicht mehr am alten Ort" da.
    echter_name = pfad.rsplit("/", 1)[-1]
    store.upsert_document(
        {
            "source": "nextcloud",
            "path": pfad,
            "name": echter_name,
            "folder": pfad.rsplit("/", 1)[0] or "/",
            "ext": endung,
            "size_bytes": len(inhalt),
            "modified_at": datetime.now(UTC).isoformat(),
            "file_id": file_id,
        }
    )
    store.link_document(entry_id, "nextcloud", pfad, echter_name)

    # Text lesen, aber nur bei dem, was gerade durch den Scanner gelaufen ist.
    # Ein durchgereichtes PDF oder ein Originalfoto wird nicht gelesen: Mia
    # hat den Scanner bewusst angehakt, und daran haengt die Zusage, dass
    # Textinhalte nur von selbst gescannten Blaettern in die Datenbank kommen.
    #
    # Gelesen wird vom **Bild**, nicht von dem, was abgelegt wurde: Tesseract
    # nimmt kein PDF als Eingabe. Und der Text hier ist ein anderer als der im
    # PDF: dieser hier ist auf Konfidenz gefiltert, weil er durchsucht wird.
    #
    # Der Beleg liegt zu diesem Zeitpunkt bereits in Nextcloud und am Eintrag.
    # Ein fehlgeschlagenes OCR kostet also die Suche im Text, sonst nichts.
    gelesen = 0
    if gescannt and scanbild and ocr.verfuegbar():
        text = await ocr.text_lesen(scanbild)
        if text and store.set_document_text("nextcloud", pfad, text):
            gelesen = len(text)

    return {
        "dokumente": _anhaenge(store, entry_id),
        "ocr_zeichen": gelesen,
        "vorschlag": await _ordnervorschlag(store, pfad, echter_name),
        "namensvorschlag": _namensvorschlag(pfad, echter_name, endung),
    }


def _namensvorschlag(pfad: str, name: str, endung: str) -> dict[str, str] | None:
    """Wie der Beleg heißen könnte, nach dem was auf ihm steht.

    Nur für gerade Gescanntes: der Text steht ohnehin schon in der Datenbank,
    und für alles andere gibt es keinen. Kein Aufruf nach außen, keine
    Wartezeit, reine Mustererkennung auf einem Text, der bereits da ist.

    ``None``, wenn der Vorschlag nichts Neues brächte. Ein Vorschlag, der
    genauso heißt wie die Datei, ist ein Knopf ohne Wirkung.
    """
    from src.main import get_store

    text = get_store().document_text("nextcloud", pfad)
    if not text:
        return None
    vorschlag = namen.name_bauen(text, endung)
    if not vorschlag or vorschlag == name:
        return None
    return {"pfad": pfad, "name": vorschlag}


async def _ordnervorschlag(store: Any, pfad: str, name: str) -> dict[str, Any] | None:
    """Wohin der frische Beleg gehoert, oder ``None``.

    Steht bewusst hinter dem Upload und nicht darin: der Beleg liegt zu diesem
    Zeitpunkt in Nextcloud, am Eintrag und im Index. Der Vorschlag ist eine
    Zugabe, und ein Embedding-Server, der nicht antwortet, darf sie nicht mit
    sich reissen.
    """
    if not ordner.verfuegbar():
        return None
    try:
        zentren = ordner.zentren(
            [
                {"folder": d["folder"], "vektor": ordner.auspacken(d["embed"])}
                for d in store.documents_mit_embed()
            ]
        )
        if len(zentren) < 2:
            return None
        text = ordner.dokumenttext(name, store.document_text("nextcloud", pfad))
        vektoren = await ordner.einbetten([text])
        if not vektoren:
            return None
        treffer = ordner.vorschlagen(vektoren[0], zentren)
    except (ValueError, KeyError, TypeError):
        log.exception("Ordnervorschlag fehlgeschlagen")
        return None
    if treffer:
        # Der Pfad gehoert dazu, sonst muesste das Frontend raten, fuer welchen
        # der Anhaenge der Vorschlag gilt. Bei Vorder- und Rueckseite am selben
        # Eintrag waere das eine Verwechslung, die niemand bemerkt.
        treffer["pfad"] = pfad
    return treffer


@router.post("/dokumente/verschieben")
async def dokument_verschieben(daten: dict[str, Any]) -> dict[str, Any]:
    """Eine Datei in einen anderen Ordner schieben, auf Mias Klick.

    Verschoben wird nur, was im Belegordner liegt. Mia OS legt dort ab, und
    genau das darf es auch wieder wegräumen. Alles andere in Mias Ablage
    bleibt unangetastet: ein Endpunkt, der jede Datei irgendwohin schieben
    kann, ist ein Schreibrecht auf die ganze Nextcloud, und den Vorschlag
    braucht es dafür nicht.
    """
    from src.main import get_store

    pfad = str(daten.get("pfad", "")).strip()
    ziel = str(daten.get("ordner", "")).strip()
    if not (pfad and ziel):
        raise HTTPException(status_code=400, detail="Pfad und Ordner fehlen")

    belegordner = (settings.belege_ordner or "").rstrip("/")
    if not belegordner or not pfad.startswith(belegordner + "/"):
        raise HTTPException(status_code=400, detail="Nur Belege lassen sich verschieben")

    try:
        neu = await belege.verschieben(pfad, ziel)
    except belege.BelegError as fehler:
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler
    except httpx.HTTPError as fehler:
        raise HTTPException(status_code=502, detail="Nextcloud nicht erreichbar") from fehler

    store = get_store()
    store.move_document("nextcloud", pfad, neu, neu.rsplit("/", 1)[0] or "/")
    return {"ok": True, "pfad": neu, "ordner": neu.rsplit("/", 1)[0]}


@router.post("/dokumente/umbenennen")
async def dokument_umbenennen(daten: dict[str, Any]) -> dict[str, Any]:
    """Einen Beleg umbenennen, auf Mias Klick.

    Dieselbe Grenze wie beim Verschieben: nur der Belegordner. Mia OS legt
    dort ab und darf dort aufräumen, in ihrer gewachsenen Ablage benennt es
    nichts um.

    Der gelesene Text geht **nicht** mit: er hängt am Dokument, nicht am
    Dateinamen, und die Suche im Beleg soll nach dem Umbenennen weiter
    funktionieren. ``move_document`` zieht Index und Verknüpfungen nach,
    ``ocr_text`` steht in keiner seiner UPDATE-Listen.
    """
    from src.main import get_store

    pfad = str(daten.get("pfad", "")).strip()
    name = str(daten.get("name", "")).strip()
    if not (pfad and name):
        raise HTTPException(status_code=400, detail="Pfad und Name fehlen")

    belegordner = (settings.belege_ordner or "").rstrip("/")
    if not belegordner or not pfad.startswith(belegordner + "/"):
        raise HTTPException(status_code=400, detail="Nur Belege lassen sich umbenennen")

    try:
        neu = await belege.umbenennen(pfad, name)
    except belege.BelegError as fehler:
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler
    except httpx.HTTPError as fehler:
        raise HTTPException(status_code=502, detail="Nextcloud nicht erreichbar") from fehler

    echter_name = neu.rsplit("/", 1)[-1]
    store = get_store()
    store.move_document("nextcloud", pfad, neu, neu.rsplit("/", 1)[0] or "/")
    store.rename_document("nextcloud", neu, echter_name)
    return {"ok": True, "pfad": neu, "name": echter_name}


@router.get("/ueber")
async def ueber() -> dict[str, Any]:
    """Version, Änderungsverlauf und Zahlen zum Bestand.

    Die Zahlen kommen aus der echten Datenbank, nicht aus einer gepflegten
    Liste: eine Aufzählung, die von Hand aktuell gehalten werden muss, ist
    nach zwei Wochen falsch.
    """
    from src.main import GESTARTET, get_store

    store = get_store()
    quellen = [
        {
            "name": r["collector"],
            "ok": bool(r["ok"]),
            "fehler": r["error"] or "",
            "wann": r["ran_at"],
        }
        for r in store.last_runs()
    ]
    return ueber_modul.ueberblick(store, quellen, GESTARTET)


def _anhaenge(store: Any, entry_id: int) -> list[dict[str, Any]]:
    """Die Anhaenge eines Eintrags, fertig fuer die Anzeige."""
    mit_vorschau = als_schalter(mit_vorgaben(store.get_settings()), "dokumente_vorschau")
    return [_anhang_ansicht(d, mit_vorschau) for d in store.documents_for_entry(entry_id)]


def _anhang_ansicht(doc: dict[str, Any], mit_vorschau: bool) -> dict[str, Any]:
    """Ein angehaengtes Dokument fuer die Anzeige.

    Fehlt die Datei im Index, taeuscht ``_doc_view`` sonst eine funktionierende
    Vorschau und einen Editor-Link vor, die beide ins Leere gehen.
    """
    from src.main import _doc_view

    fehlt = bool(doc.get("fehlt"))
    ansicht = _doc_view(doc, mit_vorschau and not fehlt)
    ansicht["fehlt"] = fehlt
    ansicht["source"] = doc["source"]
    if fehlt:
        ansicht["link"] = ""
        ansicht["vorschau"] = ""
        ansicht["anzeigbar"] = False
        ansicht["bearbeitbar"] = False
    return ansicht


@router.delete("/sammlung/{entry_id}")
async def eintrag_loeschen(entry_id: int) -> dict[str, Any]:
    from src.main import get_store

    if not get_store().delete_entry(entry_id):
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    return {"ok": True}


# --- Eigenschaften verwalten ---------------------------------------------


@router.post("/eigenschaften")
async def eigenschaft_anlegen(daten: dict[str, Any]) -> dict[str, Any]:
    """Eine neue Spalte in der Sammlung."""
    from src.main import get_store

    name = str(daten.get("name", "")).strip()
    art = str(daten.get("art", "auswahl"))
    if not name:
        raise HTTPException(status_code=400, detail="Name fehlt")
    if art not in ("auswahl", "mehrfach", "text", "zahl", "datum", "haken"):
        raise HTTPException(status_code=400, detail=f"Unbekannte Art: {art}")

    # Schluessel aus dem Namen ableiten, damit Mia keinen erfinden muss.
    key = str(daten.get("key") or "").strip() or _schluessel(name)
    if not key:
        raise HTTPException(status_code=400, detail="Kein gültiger Schlüssel")

    store = get_store()
    store.set_prop(
        key,
        name,
        art,
        daten.get("optionen") or [],
        int(daten.get("sortierung") or len(store.list_props()) + 1),
    )
    return {"eigenschaften": store.list_props()}


@router.delete("/eigenschaften/{key}")
async def eigenschaft_loeschen(key: str) -> dict[str, Any]:
    from src.main import get_store

    if not get_store().delete_prop(key):
        raise HTTPException(status_code=404, detail="Eigenschaft nicht gefunden")
    return {"ok": True}


def _schluessel(name: str) -> str:
    """Aus 'Nächster Schritt' wird 'naechster_schritt'."""
    ersatz = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
    klein = name.lower()
    for alt, neu in ersatz.items():
        klein = klein.replace(alt, neu)
    return re.sub(r"[^a-z0-9]+", "_", klein).strip("_")[:40]


@router.get("/termin/{uid}")
async def termin_details(uid: str) -> dict[str, Any]:
    """Alles, was zu einem Termin gehoert: Notiz und Aufgaben."""
    from src.main import get_store

    store = get_store()
    return {
        "uid": uid,
        "notiz": store.get_note(uid),
        "aufgaben": [_task_view(t) for t in store.tasks_for_event(uid)],
        # Eintraege aus der Sammlung, die an diesem Termin haengen.
        "eintraege": store.entries_for_event(uid),
    }


@router.put("/termin/{uid}/notiz")
async def notiz_sichern(uid: str, daten: dict[str, Any]) -> dict[str, Any]:
    """Notiz zu einem Termin sichern."""
    from src.main import get_store

    text = str(daten.get("notiz", ""))
    if len(text) > 20_000:
        raise HTTPException(status_code=400, detail="Notiz zu lang")

    get_store().set_note(uid, text)
    return {"ok": True}


@router.get("/aufgaben")
async def aufgaben(offen: bool = False, frei: bool = False) -> dict[str, Any]:
    """Alle Aufgaben.

    ``frei`` blendet die aus, die an einem Termin haengen: die stehen dort
    schon und wuerden die Liste doppeln.
    """
    from src.main import get_store

    posten = get_store().list_tasks(nur_offen=offen, ohne_termin=frei)
    return {
        "aufgaben": [_task_view(t) for t in posten],
        "offen": sum(1 for t in posten if not t["erledigt"]),
    }


@router.post("/aufgaben")
async def aufgabe_anlegen(daten: dict[str, Any]) -> dict[str, Any]:
    """Neue Aufgabe."""
    from src.main import get_store

    titel = str(daten.get("titel", "")).strip()
    if not titel:
        raise HTTPException(status_code=400, detail="Titel fehlt")
    if len(titel) > 300:
        raise HTTPException(status_code=400, detail="Titel zu lang")

    faellig = str(daten.get("faellig_am", ""))
    if faellig:
        _pflichtdatum(faellig, "faellig_am")

    store = get_store()
    neue_id = store.add_task(titel, str(daten.get("event_uid", "")), faellig)
    passend = [t for t in store.list_tasks() if t["id"] == neue_id]
    return {"aufgabe": _task_view(passend[0])} if passend else {"id": neue_id}


@router.patch("/aufgaben/{task_id}")
async def aufgabe_aendern(task_id: int, daten: dict[str, Any]) -> dict[str, Any]:
    """Aufgabe abhaken, umbenennen oder datieren."""
    from src.main import get_store

    titel = daten.get("titel")
    if titel is not None and not str(titel).strip():
        raise HTTPException(status_code=400, detail="Titel darf nicht leer sein")

    faellig = daten.get("faellig_am")
    if faellig:
        _pflichtdatum(str(faellig), "faellig_am")

    ok = get_store().update_task(
        task_id,
        titel=None if titel is None else str(titel),
        erledigt=None if daten.get("erledigt") is None else bool(daten["erledigt"]),
        faellig_am=None if faellig is None else str(faellig),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Aufgabe nicht gefunden")
    return {"ok": True}


@router.delete("/aufgaben/{task_id}")
async def aufgabe_loeschen(task_id: int) -> dict[str, Any]:
    from src.main import get_store

    if not get_store().delete_task(task_id):
        raise HTTPException(status_code=404, detail="Aufgabe nicht gefunden")
    return {"ok": True}


def _task_view(t: dict[str, Any]) -> dict[str, Any]:
    """Eine Aufgabe so, wie das Frontend sie braucht."""
    return {
        "id": t["id"],
        "titel": t["titel"],
        "erledigt": bool(t["erledigt"]),
        "event_uid": t["event_uid"],
        "faellig_am": t["faellig_am"],
    }


@router.get("/homelab")
async def homelab() -> dict[str, Any]:
    """Dienstzustaende und Kennzahlen."""
    from src.main import (
        _card,
        _dienste_ansicht,
        _kennzahlen,
        _lage,
        _stamp,
        _stoerungen,
        get_store,
    )

    store = get_store()
    werte = mit_vorgaben(store.get_settings())
    # Die Lage muss ALLE Dienste sehen, sonst zaehlt sie bei aktivem Filter
    # nur die Stoerungen und meldet "1 von 1 erreichbar".
    alle = _dienste_ansicht(store, werte, ungefiltert=True)

    return {
        "lage": _lage(alle),
        "stoerungen": _stoerungen(alle),
        "dienste": _dienste_ansicht(store, werte),
        "kennzahlen": _kennzahlen(_card("homelab"), ohne={"Dienste"}),
        "stand": _stamp(),
    }


@router.get("/dokumente")
async def dokumente(q: str = "", ordner: str = "", seite: int = 1) -> dict[str, Any]:
    """Dokumente mit Suche, Ordnerfilter und Seitenzahl.

    Die Suche geht ueber einen eigenen Weg im Store und liefert eine Liste
    ohne Seiten: bei einem Suchbegriff will man Treffer sehen, nicht
    blaettern.
    """
    from src.main import _doc_view, get_store

    store = get_store()
    werte = mit_vorgaben(store.get_settings())
    seite = max(1, seite)
    pro_seite = als_zahl(werte, "dokumente_pro_seite")

    if q:
        treffer = store.search_documents(q, limit=120)
        gesamt, seiten = len(treffer), 1
    else:
        gesamt = store.count_documents(ordner)
        seiten = max(1, -(-gesamt // pro_seite))
        seite = min(seite, seiten)
        treffer = store.list_documents(ordner, pro_seite, (seite - 1) * pro_seite)

    mit_vorschau = als_schalter(werte, "dokumente_vorschau")
    # An welchen Eintraegen die gezeigten Dateien haengen. Eine Abfrage fuer
    # die ganze Seite, sonst kostet jede Kachel eine eigene.
    zugehoerig = store.entries_for_documents([(d["source"], d["path"]) for d in treffer])
    return {
        "treffer": [
            {
                **_doc_view(d, mit_vorschau),
                "eintraege": zugehoerig.get((d["source"], d["path"]), []),
            }
            for d in treffer
        ],
        "gesamt": gesamt,
        "seite": seite,
        "seiten": seiten,
        "ordner": store.document_folders(),
    }


@router.get("/einstellungen")
async def einstellungen() -> dict[str, Any]:
    """Alle Einstellungen samt aktueller Werte."""
    from src.main import get_store

    return {
        "posten": [
            {
                "key": e.key,
                "titel": e.titel,
                "hilfe": e.hilfe,
                "art": e.art,
                "gruppe": e.gruppe,
                "vorgabe": e.vorgabe,
                "minimum": e.minimum,
                "maximum": e.maximum,
                "optionen": list(e.optionen) if e.optionen else None,
            }
            for e in EINSTELLUNGEN
        ],
        "werte": mit_vorgaben(get_store().get_settings()),
        "owner": _owner(),
    }


@router.get("/gesundheit")
async def gesundheit() -> dict[str, Any]:
    """Gewicht und Ernaehrung als Karte plus Verlauf."""
    from src.main import _card, _stamp, get_store

    store = get_store()
    return {
        "karte": _card("gesundheit"),
        "verlauf": store.history("gesundheit", "gewicht", days=60),
        "stand": _stamp(),
    }


def _owner() -> str:
    from src.main import OWNER

    return str(OWNER)


# --- Schnelleingabe ----------------------------------------------------------


@router.post("/schnell")
async def schnelleingabe(daten: dict[str, Any]) -> dict[str, Any]:
    """Ein Feld, Enter. Der Text wird gelesen, nicht nur gespeichert.

    "AU abgeben Freitag" wird ein Eintrag mit Datum, "88,4 kg" ein Gewicht
    in wger, "Skyr 200g" eine Mahlzeit, wenn die Zutat eindeutig ist.
    Alles andere wird ein Eintrag auf der Hauptsammlung.
    """
    from src import gesundheit
    from src.main import get_store
    from src.schnell import deute

    text = str(daten.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text fehlt")
    if len(text) > 300:
        raise HTTPException(status_code=400, detail="Zu lang")

    deutung = deute(text)

    if deutung.art == "gewicht" and gesundheit.konfiguriert():
        try:
            await gesundheit.gewicht_eintragen(float(deutung.zahl or 0))
        except gesundheit.WgerError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail="wger nicht erreichbar") from e
        return {"art": "gewicht", "kg": deutung.zahl, "meldung": f"{_kg(deutung.zahl)} eingetragen"}

    if deutung.art == "essen" and gesundheit.konfiguriert():
        try:
            treffer = await gesundheit.zutaten_suchen(deutung.titel, limit=5)
            if len(treffer) == 1:
                await gesundheit.essen_eintragen(int(treffer[0]["id"]), float(deutung.zahl or 0))
                return {
                    "art": "essen",
                    "meldung": f"{int(deutung.zahl or 0)} g {treffer[0]['name']} eingetragen",
                }
            if treffer:
                # Mehrdeutig: die Oberflaeche laesst waehlen.
                return {"art": "essen_wahl", "gramm": deutung.zahl, "zutaten": treffer}
        except gesundheit.WgerError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail="wger nicht erreichbar") from e
        # Keine Zutat gefunden: dann ist es eben ein normaler Eintrag.

    store = get_store()
    page_id = int(daten.get("page_id") or 0)
    neue_id = store.create_entry(
        titel=deutung.titel or text,
        datum=deutung.datum or "",
        zeit=deutung.zeit or "",
        page_id=page_id,
    )
    eintrag = store.get_entry(neue_id)
    return {"art": "eintrag", "eintrag": eintrag, "meldung": "Eintrag angelegt"}


def _kg(wert: float | None) -> str:
    return f"{wert:.1f}".replace(".", ",") + " kg" if wert is not None else ""


# --- Gesundheit schreiben ------------------------------------------------------


@router.post("/gesundheit/gewicht")
async def gewicht_setzen(daten: dict[str, Any]) -> dict[str, Any]:
    from src import gesundheit

    try:
        kg = float(str(daten.get("kg", "")).replace(",", "."))
    except ValueError as e:
        raise HTTPException(status_code=400, detail="kg ist keine Zahl") from e
    tag = _pflichtdatum(str(daten["datum"]), "datum") if daten.get("datum") else None
    try:
        await gesundheit.gewicht_eintragen(kg, tag)
    except gesundheit.WgerError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail="wger nicht erreichbar") from e
    return {"ok": True, "kg": kg}


@router.get("/gesundheit/zutaten")
async def zutaten(q: str = "") -> dict[str, Any]:
    from src import gesundheit

    if not gesundheit.konfiguriert():
        return {"zutaten": []}
    try:
        return {"zutaten": await gesundheit.zutaten_suchen(q)}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail="wger nicht erreichbar") from e


@router.get("/gesundheit/heute")
async def gegessen_heute() -> dict[str, Any]:
    from src import gesundheit

    if not gesundheit.konfiguriert():
        return {"eintraege": [], "kcal": 0}
    try:
        liste = await gesundheit.heute_gegessen()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail="wger nicht erreichbar") from e
    return {"eintraege": liste, "kcal": sum(int(e["kcal"]) for e in liste)}


@router.post("/gesundheit/essen")
async def essen_setzen(daten: dict[str, Any]) -> dict[str, Any]:
    from src import gesundheit

    try:
        zutat = int(daten.get("zutat_id") or 0)
        gramm = float(str(daten.get("gramm", "")).replace(",", "."))
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Zutat oder Menge fehlt") from e
    if not zutat:
        raise HTTPException(status_code=400, detail="Zutat fehlt")
    try:
        await gesundheit.essen_eintragen(zutat, gramm)
    except gesundheit.WgerError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail="wger nicht erreichbar") from e
    return {"ok": True}


# --- Suche ueber alles ---------------------------------------------------------


@router.get("/suche")
async def suche(q: str = "") -> dict[str, Any]:
    """Ein Feld fuer Seiten, Eintraege, Termine und Dokumente.

    Dokumente erscheinen nur auf Suche, nie als Vorschlag: im Index stehen
    Arztberichte und Ausweise.
    """
    from src.main import _doc_view, _kalenderfarbe, get_store
    from src.presenter import ohne_emoji

    q = q.strip()
    if len(q) < 2:
        return {"seiten": [], "eintraege": [], "termine": [], "dokumente": []}

    store = get_store()
    return {
        "seiten": [
            {"id": p["id"], "titel": p["titel"], "symbol": p["symbol"]}
            for p in store.search_pages(q, limit=8)
        ],
        "eintraege": [
            {
                "id": e["id"],
                "titel": e["titel"],
                "datum": e["datum"],
                "page_id": e["page_id"],
                "status": e["eigenschaften"].get("status", ""),
            }
            for e in store.list_entries(suche=q)[:10]
        ],
        "termine": [
            {
                "id": t["uid"],
                "titel": ohne_emoji(t["title"]),
                "start": t["start_at"],
                "ganztags": bool(t["ganztags"]),
                "kalender": t["calendar"],
                "farbe": _kalenderfarbe(t["calendar"]),
            }
            for t in store.search_events(q, limit=8)
        ],
        "dokumente": [
            {
                "id": d["id"],
                "name": d["name"],
                "folder": d["folder"],
                "ext": d["ext"],
                # Bei einem Treffer im gelesenen Text steht die Fundstelle
                # neben dem Namen, sonst der Ordner. Wer nach einem
                # Aktenzeichen sucht, will sehen, dass es auf dem Blatt steht.
                "stelle": d["stelle"],
            }
            for d in (_doc_view(x, False) for x in store.search_documents(q, limit=8))
        ],
    }


# --- Briefing --------------------------------------------------------------------


@router.get("/briefing")
async def briefing() -> dict[str, Any]:
    """Der Tag als Text, fuer die Morgen-Nachricht.

    Dieselben Daten wie die Heute-Seite, nur als Zeilen. Wer die Nachricht
    verschickt, entscheidet der Aufrufer (ntfy, Telegram), nicht Mia OS.
    """
    from src.main import _termin_ansicht, get_store

    store = get_store()
    heute = date.today()
    morgen = heute + timedelta(days=1)

    def tag(t: date) -> list[dict[str, Any]]:
        roh = store.events(
            datetime.combine(t, dtime.min).isoformat(),
            datetime.combine(t, dtime.max).isoformat(),
            limit=50,
        )
        return [
            {
                "titel": _termin_ansicht(e, heute)["titel"],
                "zeit": "" if e["ganztags"] else str(e["start_at"])[11:16],
                "ende": "" if e["ganztags"] or not e["end_at"] else str(e["end_at"])[11:16],
                "ort": e["location"] or "",
                "kalender": e["calendar"],
            }
            for e in roh
        ]

    offene = [
        {
            "id": e["id"],
            "titel": e["titel"],
            "datum": e["datum"],
            "status": e["eigenschaften"].get("status", ""),
        }
        for e in store.list_entries()
        if e["eigenschaften"].get("status") != "fertig"
    ]
    faellig = [e for e in offene if e["datum"] and e["datum"] <= heute.isoformat()]

    zeilen: list[str] = []
    heute_liste = tag(heute)
    if heute_liste:
        zeilen.append(f"Heute, {len(heute_liste)} Termine:" if len(heute_liste) > 1 else "Heute:")
        for t in heute_liste:
            zeit = f"{t['zeit']} " if t["zeit"] else ""
            ort = f" ({t['ort']})" if t["ort"] else ""
            zeilen.append(f"  {zeit}{t['titel']}{ort}")
    else:
        zeilen.append("Heute keine Termine.")
    if faellig:
        zeilen.append(f"Fällig: {', '.join(e['titel'] for e in faellig[:5])}")
    elif offene:
        zeilen.append(f"Offen: {len(offene)} Einträge, nichts fällig.")
    morgen_liste = tag(morgen)
    if morgen_liste:
        erster = morgen_liste[0]
        zeit = f" ab {erster['zeit']}" if erster["zeit"] else ""
        zeilen.append(
            f"Morgen{zeit}: {erster['titel']}"
            + (f" und {len(morgen_liste) - 1} weitere" if len(morgen_liste) > 1 else "")
        )

    # Was das Display sonst noch zeigen soll: Zettel von Jana, und die
    # Regeln fuer die Kammer. Beides haengt am Briefing, weil das Geraet
    # ohnehin alle zwei Minuten danach fragt.
    from src.hinweise import hole_hinweise

    # Die Einstellungen fuer das Geraet, als Fallnetz: die schnelle Strecke
    # ist /api/geraete/einstellungen.
    geraet = _geraet_einstellungen()

    return {
        "datum": heute.isoformat(),
        "heute": heute_liste,
        "morgen": morgen_liste,
        "faellig": faellig,
        "offen": len(offene),
        "hinweise": hole_hinweise().offen(),
        "geraet": geraet,
        "text": "\n".join(zeilen),
    }


# --- Hinweise fuer die Geraete ------------------------------------------------


@router.get("/hinweise")
async def hinweise_lesen() -> dict[str, Any]:
    """Alle Hinweise, neueste zuerst. Fuer Jana, um Fame und Shame zu lesen."""
    from src.hinweise import hole_hinweise

    return {"hinweise": hole_hinweise().alle()}


@router.post("/hinweise")
async def hinweis_anlegen(daten: dict[str, Any]) -> dict[str, Any]:
    """Einen Zettel auf den Tisch legen. ``text`` ist Pflicht, ``von`` optional."""
    from src.hinweise import hole_hinweise

    try:
        h = hole_hinweise().anlegen(str(daten.get("text", "")), str(daten.get("von", "Jana")))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"hinweis": h.__dict__}


@router.post("/hinweise/{hinweis_id}/{antwort}")
async def hinweis_antworten(hinweis_id: int, antwort: str) -> dict[str, Any]:
    """Was das Geraet zurueckmeldet: ok, spaeter, fame oder shame."""
    from src.hinweise import hole_hinweise

    try:
        h = hole_hinweise().antworten(hinweis_id, antwort)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if h is None:
        raise HTTPException(status_code=404, detail="Hinweis nicht gefunden")
    return {"hinweis": h.__dict__}


@router.get("/regeln")
async def regeln() -> dict[str, Any]:
    """Die Regeln des Servers, fuer die Kammer auf dem Display.

    Regel 62: die Existenz der Kammer wird nach aussen geleugnet. Dieser
    Endpunkt hat deshalb keine Dokumentation, die ueber diesen Satz
    hinausgeht.
    """
    import json as _json
    from pathlib import Path as _Path

    datei = _Path(__file__).with_name("regeln.json")
    try:
        return {"regeln": _json.loads(datei.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return {"regeln": []}


# --- Berichtsheft ----------------------------------------------------------------


@router.get("/berichtsheft")
async def berichtsheft_woche(montag: str = "") -> dict[str, Any]:
    """Ein Wochenblatt: frisch aus dem Kalender, mit Mias Korrekturen darueber.

    Ohne ``montag`` die laufende Woche. Der Entwurf wird jedes Mal neu
    gerechnet, damit ein nachtraeglich eingetragener Termin die Stunden
    korrigiert, ohne Mias Text anzufassen.
    """
    from src.berichtsheft import entwurf, wochenanfang, zusammenfuehren
    from src.main import get_store

    start = wochenanfang(_als_datum_oder_heute(montag))
    ende = start + timedelta(days=6)
    store = get_store()

    roh = store.events(
        datetime.combine(start, dtime.min).isoformat(),
        datetime.combine(ende, dtime.max).isoformat(),
        limit=400,
    )
    eintraege = [
        e
        for e in store.list_entries()
        if e["datum"] and start.isoformat() <= e["datum"] <= ende.isoformat()
    ]
    woche = entwurf(start, roh, eintraege)
    woche = zusammenfuehren(woche, store.berichtswoche(start.isoformat()))
    return woche.as_dict()


@router.get("/berichtsheft/wochen")
async def berichtsheft_liste(anzahl: int = 12) -> dict[str, Any]:
    """Die letzten Wochen mit Status, fuer die Uebersicht.

    Zeigt auch Wochen, die noch nie gespeichert wurden: genau die sind ja die
    offenen. Ohne das waere die Liste leer und nichts erinnerte an sie.
    """
    from src.berichtsheft import entwurf, wochenanfang
    from src.main import get_store

    anzahl = max(1, min(anzahl, 52))
    store = get_store()
    diese = wochenanfang(date.today())
    gespeichert = {w["montag"]: w for w in store.berichtswochen()}

    wochen: list[dict[str, Any]] = []
    for i in range(anzahl):
        start = diese - timedelta(weeks=i)
        ende = start + timedelta(days=6)
        roh = store.events(
            datetime.combine(start, dtime.min).isoformat(),
            datetime.combine(ende, dtime.max).isoformat(),
            limit=400,
        )
        w = entwurf(start, roh)
        eigene = gespeichert.get(start.isoformat())
        gefuellt = 0
        if eigene:
            gefuellt = sum(
                1
                for werte in eigene["inhalt"].values()
                if isinstance(werte, dict)
                and any(str(z).strip() for z in werte.get("taetigkeiten") or [])
            )
        wochen.append(
            {
                "montag": w.montag,
                "sonntag": w.sonntag,
                "kw": w.kw,
                "jahr": w.jahr,
                "stunden": w.stunden,
                "arbeitstage": sum(1 for t in w.tage if t.stunden > 0),
                "status": eigene["status"] if eigene else "entwurf",
                "gefuellte_tage": gefuellt,
                "aktuell": start == diese,
                # Der Kalender-Collector liest nur 45 Tage zurueck. Aeltere
                # Wochen haben deshalb keine Termine, und "0 h" waere dort
                # eine falsche Aussage statt einer fehlenden.
                "hat_daten": bool(roh) or bool(eigene),
            }
        )
    return {"wochen": wochen, "diese_woche": diese.isoformat()}


@router.post("/berichtsheft")
async def berichtsheft_speichern(daten: dict[str, Any]) -> dict[str, Any]:
    """Mias Korrekturen an einer Woche speichern.

    Nur die mitgeschickten Felder werden angefasst, damit ein Tastendruck in
    einem Tagesfeld nicht die Bemerkung leert.
    """
    from src.berichtsheft import wochenanfang
    from src.main import get_store

    montag = wochenanfang(_pflichtdatum(str(daten.get("montag") or ""), "montag")).isoformat()

    inhalt = daten.get("inhalt")
    if inhalt is not None and not isinstance(inhalt, dict):
        raise HTTPException(status_code=400, detail="inhalt muss ein Objekt sein")

    status = daten.get("status")
    if status is not None:
        if status not in ("entwurf", "bearbeitet", "fertig"):
            raise HTTPException(status_code=400, detail="unbekannter Status")
        status = str(status)

    get_store().save_berichtswoche(
        montag,
        inhalt=inhalt,
        status=status,
        themen_schule=_optionaler_text(daten, "themen_schule"),
        bemerkung=_optionaler_text(daten, "bemerkung"),
    )
    return await berichtsheft_woche(montag)


def _optionaler_text(daten: dict[str, Any], feld: str) -> str | None:
    """Text nur uebernehmen, wenn er wirklich mitgeschickt wurde."""
    if feld not in daten:
        return None
    wert = daten[feld]
    return "" if wert is None else str(wert)


def _als_datum_oder_heute(wert: str) -> date:
    if not wert:
        return date.today()
    return _pflichtdatum(wert, "montag")


def _pflichtdatum(wert: str, name: str) -> date:
    """Ein Datum, das dasein MUSS. Fehlt es, ist die Anfrage kaputt."""
    from src.main import _als_datum

    tag = _als_datum(wert)
    if tag is None:
        raise HTTPException(status_code=400, detail=f"{name} ist kein gültiges Datum")
    return tag
