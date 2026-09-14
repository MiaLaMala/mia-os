"""FastAPI-App: Zentrale mit Navigation, JSON-API und Sammel-Loop."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from src import betrieb, bonjour, editor, ueber
from src.api import router as api_router
from src.categories import BY_KEY, CATEGORIES, LIVE
from src.collectors import all_collectors
from src.collectors.documents import PREVIEWABLE
from src.config import settings
from src.einstellungen import (
    EINSTELLUNGEN,
    als_schalter,
    als_zahl,
    mit_vorgaben,
)
from src.icons import icon
from src.presenter import build_card, ohne_emoji
from src.store import Store
from src.torwache import torwache

log = logging.getLogger("mia-os")

# Bilder, die sich gross ansehen lassen.
#
# Bewusst getrennt von ``editor.ANZEIGBAR``: das ist die Liste dessen, was
# OnlyOffice kann, und ein Dokumenteneditor faengt mit einem JPEG nichts an.
# Bilder in diese Liste zu quetschen wuerde den Editor mit einer Datei
# starten, die er nicht oeffnen kann.
#
# HEIC fehlt mit Absicht: Firefox und Chrome zeigen es nicht an, und ein
# Klick, der zu einem leeren Kasten fuehrt, ist schlechter als kein Klick.
# Gescanntes ist ohnehin PDF oder JPEG.
BILD_ANZEIGBAR = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))
templates.env.globals["icon"] = icon
templates.env.globals["nav"] = CATEGORIES

OWNER = "Mia Grünwald"

_store: Store | None = None


def get_store() -> Store:
    """Store faul anlegen, nie beim Import.

    Sonst legt schon ein ``import src.main`` das DB-Verzeichnis an und
    scheitert dort, wo keine Schreibrechte auf ``/var/lib`` bestehen.
    """
    global _store
    if _store is None:
        _store = Store(settings.db_path)
    return _store


async def collect_once() -> dict[str, bool]:
    """Alle Collectors einmal laufen lassen."""
    results: dict[str, bool] = {}
    for collector in all_collectors(get_store()):
        results[collector.name] = await collector.run()
    return results


async def _collect_loop() -> None:
    """Hintergrundschleife. Faellt einer aus, laeuft der Rest weiter."""
    while True:
        with contextlib.suppress(Exception):
            await collect_once()
        # Takt bei jedem Durchlauf neu lesen: aendert Mia ihn in den
        # Einstellungen, gilt das ab dem naechsten Mal, ohne Neustart.
        minuten = settings.collect_interval_minutes
        with contextlib.suppress(Exception):
            minuten = als_zahl(mit_vorgaben(get_store().get_settings()), "sammel_minuten")
        await asyncio.sleep(minuten * 60)


# Die laufende Sammelschleife. Die Bereitschaftsauskunft muss wissen, ob sie
# noch lebt: stirbt sie still, laeuft der Dienst weiter und liefert auf ewig
# dieselben Zahlen. Von aussen sieht das aus wie Betrieb.
_sammel_task: asyncio.Task[None] | None = None

# Die Bonjour-Ankuendigung, damit die Apps den Server im Netz selbst finden.
_melder: bonjour.Melder | None = None


def sammelschleife_laeuft() -> bool:
    """Ob die Hintergrundschleife noch arbeitet."""
    return _sammel_task is not None and not _sammel_task.done()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _sammel_task, _melder
    _sammel_task = asyncio.create_task(_collect_loop())
    task = _sammel_task

    # Bonjour: scheitert es, laeuft Mia OS unveraendert weiter, nur muss die
    # Adresse in den Apps dann von Hand stehen. Eine Bequemlichkeit darf den
    # Start nicht verhindern.
    _melder = bonjour.Melder(
        bonjour.Ankuendigung(
            instanz="Mia OS",
            port=settings.port,
            version=ueber.version(),
            adresse=bonjour.eigene_adresse(),
        )
    )
    melder = _melder
    with contextlib.suppress(Exception):
        await melder.starten()

    yield

    if _melder is not None:
        with contextlib.suppress(Exception):
            await _melder.stoppen()
        _melder = None
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


# Wann der Dienst hochgekommen ist. Die About-Seite zeigt daraus die
# Laufzeit: "seit 3 Tagen" sagt mehr ueber die Gesundheit als jede Zahl.
GESTARTET = datetime.now(UTC)

app = FastAPI(
    title=OWNER,
    description="Persoenliche Zentrale",
    version=ueber.version(),
    lifespan=lifespan,
)

# Wer herein darf. Muss VOR dem Router stehen, sonst laeuft die Anfrage
# bereits in die Route und die Wache sieht sie nie.
app.middleware("http")(torwache)

# Eine native App hat keine Herkunft im Sinne des Browsers und schickt
# deshalb keinen Origin-Header: fuer sie ist das hier bedeutungslos. Es
# steht da fuer die Entwicklung, wo Vite auf 5173 laeuft und das Backend auf
# 8080, und fuer den Fall, dass die Oberflaeche einmal woanders liegt.
#
# ``allow_origin_regex`` statt einer festen Liste: die Adressen im Heimnetz
# aendern sich, die Form nicht. Bewusst KEIN "*": mit Anmeldedaten zusammen
# waere das der Fehler, den die Spezifikation selbst verbietet.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|172\.16\.\d+\.\d+|10\.42\.7\.\d+)(:\d+)?$|^https://[a-z0-9-]+\.mia-gruenwald\.dev$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JSON-Schnittstelle fuer das Svelte-Frontend.
app.include_router(api_router)

static_dir = BASE_DIR / "web" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Das gebaute Svelte-Frontend. Liegt unter static/gebaut und wird von dort
# ausgeliefert: kein CDN, alles kommt aus dem eigenen Container.
GEBAUT = static_dir / "gebaut"
if (GEBAUT / "assets").is_dir():  # pragma: no cover
    app.mount("/assets", StaticFiles(directory=str(GEBAUT / "assets")), name="assets")


@app.get("/", response_class=HTMLResponse)
@app.get("/app", response_class=HTMLResponse)
@app.get("/app/{rest:path}", response_class=HTMLResponse)
async def frontend(rest: str = "") -> HTMLResponse:
    """Liefert die Svelte-App aus.

    Der Router im Browser uebernimmt danach (Hash-Routen). Die alten
    Jinja-Seiten sind abgeloest: seit 07.09.2026 ist ``/`` die App, ``/app``
    bleibt nur fuer alte Lesezeichen erhalten.
    """
    datei = GEBAUT / "index.html"
    if not datei.is_file():
        raise HTTPException(status_code=503, detail="Frontend noch nicht gebaut")
    # Die Huelle selbst nie zwischenspeichern: sie enthaelt die Namen der
    # gebauten Dateien. Haelt Safari sie fest, laedt das iPhone weiter das
    # alte Buendel, obwohl der Server laengst ein neues hat. Genau das ist am
    # 09.09.2026 passiert, das Berichtsheft fehlte dort im Menue.
    # Die Buendel selbst tragen eine Pruefsumme im Namen und duerfen bleiben.
    return HTMLResponse(
        datei.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


# Alte Adressen der Jinja-Seiten fuehren in die App, an dieselbe Stelle.
# Bewusst einzeln statt als Catch-all: der haette /health mitgefangen.
for _alt in ("termine", "dokumente", "homelab", "einstellungen", "gesundheit"):

    def _weiterleitung(ziel: str = _alt) -> RedirectResponse:
        return RedirectResponse(f"/#/{ziel}", status_code=307)

    app.add_api_route(f"/{_alt}", _weiterleitung, methods=["GET"], include_in_schema=False)


@app.get("/k/{key}", response_class=RedirectResponse, include_in_schema=False)
async def alte_kategorie(key: str) -> RedirectResponse:
    if key not in BY_KEY:
        raise HTTPException(status_code=404, detail="Unbekannte Kategorie")
    return RedirectResponse(f"/#{BY_KEY[key].route or '/' + key}", status_code=307)


# --- Seiten ---------------------------------------------------------------


def _als_datum(wert: str) -> date | None:
    """Ein Datum aus der Adresszeile, oder nichts. Nie eine Ausnahme."""
    try:
        return date.fromisoformat(wert)
    except ValueError:
        return None


def _termin_ansicht(e: dict[str, Any], heute: date) -> dict[str, Any]:
    """Einen Termin fuer die Anzeige aufbereiten."""
    beginn = datetime.fromisoformat(e["start_at"])
    schluss = datetime.fromisoformat(e["end_at"]) if e["end_at"] else None
    jetzt = datetime.now()
    # Ganztaegige Termine "laufen" nicht: ein Geburtstag laeuft nicht von
    # 00:00 bis 23:59, er ist einfach an dem Tag.
    laeuft = bool(not e["ganztags"] and schluss and beginn <= jetzt <= schluss)
    vorbei = bool(not e["ganztags"] and (schluss or beginn) < jetzt)

    dauer = ""
    if schluss and not e["ganztags"]:
        minuten = int((schluss - beginn).total_seconds() // 60)
        if minuten >= 60:
            stunden, rest = divmod(minuten, 60)
            dauer = f"{stunden} h" if not rest else f"{stunden}:{rest:02d} h"
        elif minuten > 0:
            dauer = f"{minuten} min"

    return {
        "titel": ohne_emoji(e["title"]),
        "beginn": f"{beginn:%H:%M}",
        "ende": f"{schluss:%H:%M}" if schluss and not e["ganztags"] else "",
        "dauer": dauer,
        "ort": e["location"],
        "kalender": e["calendar"],
        "farbe": _kalenderfarbe(e["calendar"]),
        "ganztags": bool(e["ganztags"]),
        "laeuft": laeuft,
        "vorbei": vorbei,
        "tag": beginn.date().isoformat(),
        # Fuer die Zeitachse: die rohen Zeitpunkte. Ein Termin ohne Ende
        # bekommt eine Stunde, sonst waere sein Block hoehenlos.
        "_von": beginn,
        "_bis": schluss or beginn + timedelta(hours=1),
    }


# Gedaempfte Toene, damit mehrere nebeneinander nicht schreien. Bewusst nicht
# die Akzentfarbe: die gehoert der Auswahl im Raster, sonst waere unklar, was
# gerade angetippt ist.
_KALENDERFARBEN = (
    "#5b8def",
    "#3fa66a",
    "#d98a3f",
    "#a86fd1",
    "#3fa3a3",
    "#c8607f",
    "#7a86a8",
)


def _kalenderfarbe(name: str) -> str:
    """Jedem Kalender dieselbe Farbe geben, ueber Neustarts hinweg.

    Ueber den Namen statt ueber die Reihenfolge: sonst tauschen die Farben,
    sobald ein Kalender dazukommt oder wegfaellt.
    """
    if not name:
        return _KALENDERFARBEN[-1]
    stelle = int(hashlib.sha1(name.encode()).hexdigest()[:8], 16)
    return _KALENDERFARBEN[stelle % len(_KALENDERFARBEN)]


def _stoerungen(dienste: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Was wirklich klemmt.

    Status 2 heisst bei Kuma "pending", also gerade in Pruefung. Das steht
    zum Beispiel eine Minute lang da, waehrend Mia OS selbst neu startet, und
    ist keine Stoerung. Nur 0 (unten) und 3 (Wartung) gehoeren nach oben.
    """
    return [d for d in dienste if d["status"] in (0, 3)]


def _lage(dienste: list[dict[str, Any]]) -> dict[str, Any]:
    """Die eine Aussage, die oben steht.

    Ein Satz statt einer Zahl: "alles läuft" ist die Information, nicht "47".
    """
    gesamt = len(dienste)
    unten = [d for d in dienste if d["status"] == 0]
    wartung = [d for d in dienste if d["status"] == 3]
    gemessen = [d["uptime"] for d in dienste if d["uptime"] is not None]

    if unten:
        zustand = "unten"
        satz = unten[0]["name"] if len(unten) == 1 else f"{len(unten)} Dienste gestört"
        if len(unten) == 1:
            satz += " ist nicht erreichbar"
    elif wartung:
        zustand = "wartung"
        satz = f"{len(wartung)} in Wartung"
    elif gesamt:
        zustand = "oben"
        satz = "Alles läuft"
    else:
        zustand = "unklar"
        satz = "Noch keine Daten"

    return {
        "zustand": zustand,
        "satz": satz,
        "gesamt": gesamt,
        "oben": gesamt - len(unten),
        "uptime": round(sum(gemessen) / len(gemessen), 2) if gemessen else None,
    }


@app.get("/api/homelab")
async def api_homelab() -> dict[str, Any]:
    """Alles, was die Homelab-Seite zum Auffrischen braucht.

    Bewusst ein Aufruf statt drei: die Seite laedt das im Hintergrund, und
    drei parallele Anfragen auf einem Zwei-Kern-Container sind Verschwendung.
    """
    store = get_store()
    werte = mit_vorgaben(store.get_settings())
    runs = {r["collector"]: r for r in store.last_runs()}
    alle = _dienste_ansicht(store, werte, ungefiltert=True)
    kennzahlen = _kennzahlen(_card("homelab"), ohne={"Dienste"})

    return {
        "stand": _stamp(),
        "lage": _lage(alle),
        "stoerungen": _stoerungen(alle),
        # Die Karte liefert lead + details, nicht "fields".
        "kennzahlen": kennzahlen,
        "dienste": _dienste_ansicht(store, werte),
        "quellen": {
            name: {"ok": r["ok"], "fehler": r["error"]}
            for name, r in runs.items()
            if name in {"homelab", "kuma"}
        },
    }


def _kennzahlen(karte: dict[str, Any], ohne: set[str] | None = None) -> list[dict[str, Any]]:
    """Leitwert und Details als eine Liste, in Anzeigereihenfolge.

    ``ohne`` blendet Beschriftungen aus. Auf der Homelab-Seite faellt so
    "Dienste" heraus: derselbe Satz steht schon oben als Lagemeldung, und
    daneben als Kachel liest er sich wie eine zweite Fehlermeldung.
    """
    ohne = ohne or set()
    raus = []
    if karte.get("lead") and not karte["lead"]["empty"] and karte["lead"]["label"] not in ohne:
        raus.append(
            {"label": karte["lead"]["label"], "wert": karte["lead"]["display"], "leit": True}
        )
    raus += [
        {"label": d["label"], "wert": d["display"], "leit": False}
        for d in karte.get("details", [])
        if d["label"] not in ohne
    ]
    return raus


@app.post("/api/einstellungen")
async def einstellung_speichern(request: Request) -> dict[str, Any]:
    """Eine einzelne Einstellung sichern, ohne Seitenwechsel.

    Die Seite schickt bei jeder Änderung genau einen Wert hierher. Geprüft
    wird derselbe Weg wie beim Formular: unbekannte Schlüssel und ungültige
    Werte werden verworfen, nicht gespeichert.
    """
    daten = await request.json()
    key = str(daten.get("key", ""))
    wert = str(daten.get("wert", ""))

    posten = {e.key: e for e in EINSTELLUNGEN}
    if key not in posten:
        raise HTTPException(status_code=400, detail="Unbekannte Einstellung")

    sauber = posten[key].pruefe(wert)
    if sauber is None:
        raise HTTPException(status_code=400, detail="Ungültiger Wert")

    get_store().set_setting(key, sauber)
    if key.startswith("display_"):
        # Das Display wartet darauf. Sofort wecken statt zwei Minuten.
        from src.firmware import hole_firmware

        hole_firmware().einstellungen_geaendert()
    return {"ok": True, "key": key, "wert": sauber}


def _dienste_ansicht(
    store: Store, werte: dict[str, Any], ungefiltert: bool = False
) -> list[dict[str, Any]]:
    """Dienste fuer die Anzeige aufbereiten.

    ``ungefiltert`` uebergeht die Einstellung "nur Stoerungen": die
    Lagemeldung oben muss alle Dienste zaehlen, sonst meldet sie bei aktivem
    Filter "1 von 1 erreichbar".
    """
    zeitraum = werte["dienste_uptime_zeitraum"]
    nur_stoerungen = als_schalter(werte, "dienste_nur_stoerungen") and not ungefiltert

    raus = []
    for d in store.services():
        if nur_stoerungen and d["status"] == 1:
            continue
        uptime = d["uptime24"] if zeitraum == "24" else d["uptime30"]
        raus.append(
            {
                "name": d["name"],
                "status": d["status"],
                "zustand": {0: "unten", 1: "oben", 3: "wartung"}.get(d["status"], "unklar"),
                "meldung": d["msg"],
                "ping": d["ping"],
                # -1 heisst: noch keine Messwerte, nicht 0 Prozent.
                "uptime": None if uptime < 0 else uptime,
            }
        )
    return raus


# --- API ------------------------------------------------------------------


@app.exception_handler(404)
async def nicht_gefunden(request: Request, exc: Exception) -> Response:
    """Eine eigene 404-Seite statt FastAPIs nacktem JSON.

    Fuer die API bleibt es JSON, fuer alles andere eine kleine HTML-Seite
    mit Weg zurueck in die App.
    """
    if request.url.path.startswith("/api/"):
        return Response(
            json.dumps({"detail": "Nicht gefunden"}),
            status_code=404,
            media_type="application/json",
        )
    return templates.TemplateResponse(
        request,
        "fehler.html",
        {
            "owner": OWNER,
            "titel": "Seite nicht gefunden",
            "text": "Diese Adresse gibt es nicht. Vielleicht ein altes Lesezeichen?",
            "active": None,
            "now": _stamp(),
        },
        status_code=404,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness: laeuft der Prozess?

    Fasst bewusst nichts an, was ausfallen kann. Uptime Kuma fragt von
    aussen, und eine Antwort, die von der Datenbank abhaengt, wuerde den
    Container bei einer langsamen Abfrage neu starten. Die eigentliche
    Auskunft steht unter ``/health/bereit``.

    **Die Apps benutzen diesen Endpunkt zum Pruefen der Adresse.** Deshalb
    steht hier auch der Name und die Version: so kann die App sagen
    "Mia OS 0.3.10 erreichbar" statt nur "irgendwas hat geantwortet". Eine
    beliebige andere Webseite antwortet nicht mit diesem JSON.
    """
    return {
        "status": "ok",
        "dienst": "mia-os",
        "name": OWNER,
        "version": ueber.version(),
        "time": datetime.now(UTC).isoformat(),
    }


@app.get("/health/bereit")
async def health_bereit() -> Response:
    """Readiness: darf Verkehr hierhin?

    Antwortet 503, wenn Datenbank oder Sammelschleife fehlen. Der
    Statuscode ist der eigentliche Inhalt, weil jeder Load Balancer und
    jeder Monitor ihn lesen kann, ohne JSON zu verstehen.
    """
    stand = betrieb.bereitschaft(get_store(), sammelschleife_laeuft())
    return Response(
        json.dumps(stand, ensure_ascii=False),
        status_code=200 if stand["bereit"] else 503,
        media_type="application/json",
    )


@app.get("/metrics")
async def metrics() -> Response:
    """Zahlen im Prometheus-Textformat, ohne personenbezogene Label."""
    return Response(
        betrieb.metriken(get_store(), sammelschleife_laeuft(), GESTARTET),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/api/categories")
async def api_categories() -> list[dict[str, Any]]:
    return [_category_payload(c.key) for c in CATEGORIES]


@app.get("/api/categories/{key}")
async def api_category(key: str) -> dict[str, Any]:
    if key not in BY_KEY:
        raise HTTPException(status_code=404, detail="Unbekannte Kategorie")
    return _category_payload(key)


@app.get("/api/history/{category}/{key}")
async def api_history(category: str, key: str, days: int = 30) -> list[dict[str, Any]]:
    return get_store().history(category, key, days)


@app.get("/api/documents")
async def api_documents(q: str = "", limit: int = 50) -> dict[str, Any]:
    """Dokumentensuche als JSON.

    Gibt nur Metadaten heraus und ohne Suchbegriff gar nichts: der Index
    enthaelt Arztberichte und Unterlagen Dritter.
    """
    treffer = get_store().search_documents(q, limit=min(limit, 200))
    return {
        "query": q,
        "anzahl": len(treffer),
        "treffer": [_doc_view(d) for d in treffer],
    }


@app.get("/api/documents/stats")
async def api_document_stats() -> dict[str, Any]:
    """Kennzahlen ohne Dateinamen."""
    stats = get_store().document_stats()
    stats.pop("neuestes", None)
    stats["ordner"] = get_store().document_folders()
    return stats


@app.get("/bearbeiten/{doc_id}", response_class=HTMLResponse)
async def document_editor(request: Request, doc_id: int, zurueck: str = "") -> HTMLResponse:
    """Ein Dokument im eingebetteten OnlyOffice-Editor oeffnen.

    ``zurueck`` traegt den Zustand der Dokumentenseite (Ordner, Suche, Seite),
    damit der Zurueck-Weg wieder dort landet und nicht auf der ungefilterten
    Startseite.
    """
    store = get_store()
    doc = store.document_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Unbekanntes Dokument")

    ext = doc.get("ext", "")
    if ext not in editor.ANZEIGBAR:
        raise HTTPException(status_code=415, detail=f"{ext} kann ich nicht anzeigen")
    if not (settings.onlyoffice_url and settings.public_base_url):
        raise HTTPException(status_code=503, detail="Editor nicht konfiguriert")

    merkmal = editor.signiere(doc_id)
    basis = settings.public_base_url.rstrip("/")
    schreibbar = ext in editor.BEARBEITBAR and doc.get("source") == "nextcloud"

    # Kein "type": "mobile". Der Document Server haette dafuer eine eigene
    # Handy-Oberflaeche, die verlangt in der Community-Version aber eine
    # kommerzielle Lizenz ("nur schreibgeschuetzt oeffnen"). Die
    # Desktop-Oberflaeche ist am Handy enger, laesst sich aber bedienen und
    # vor allem bearbeiten. Am 05.09.2026 am Bild geprueft.
    konfig: dict[str, Any] = {
        "document": {
            "fileType": ext.lstrip("."),
            "key": editor.dokument_schluessel(doc),
            "title": doc["name"],
            # Diese Adresse ruft der Document Server auf, nicht der Browser.
            "url": f"{basis}/datei/{doc_id}?m={merkmal}",
            "permissions": {"edit": schreibbar, "download": True, "print": True},
        },
        "documentType": editor.editor_typ(ext),
        "editorConfig": {
            "lang": "de-DE",
            "mode": "edit" if schreibbar else "view",
            "user": {"id": "mia", "name": OWNER},
            "customization": {
                "autosave": True,
                "forcesave": True,
                "compactHeader": True,
                "hideRightMenu": True,
                # Kein Firmenlogo, das ins Nichts verlinkt.
                "logo": {"image": "", "url": ""},
            },
        },
    }
    if schreibbar:
        konfig["editorConfig"]["callbackUrl"] = (
            f"{basis}/api/onlyoffice/callback/{doc_id}?m={merkmal}"
        )
    if settings.onlyoffice_jwt_secret:
        konfig["token"] = editor.jwt_signieren(konfig)

    return templates.TemplateResponse(
        request,
        "editor.html",
        {
            "owner": OWNER,
            "doc": _doc_view(doc),
            "konfig_json": json.dumps(konfig),
            "api_url": f"{settings.onlyoffice_url.rstrip('/')}/web-apps/apps/api/documents/api.js",
            "schreibbar": schreibbar,
            "zurueck_url": _zurueck_url(zurueck),
            "active": "dokumente",
            "now": _stamp(),
        },
    )


@app.get("/datei/{doc_id}")
async def document_file(doc_id: int, m: str = "") -> Response:
    """Die Datei selbst, fuer den Document Server.

    Wird nicht vom Browser aufgerufen, sondern vom OnlyOffice-Container.
    Deshalb kein Login, sondern ein signiertes Merkmal in der Adresse.
    """
    if not editor.pruefe(doc_id, m):
        raise HTTPException(status_code=403, detail="Ungueltiger oder abgelaufener Zugriff")

    doc = get_store().document_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Unbekanntes Dokument")

    try:
        inhalt, typ = await editor.datei_holen(doc["path"])
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Datei nicht abrufbar") from exc

    return Response(
        content=inhalt,
        media_type=typ,
        headers={"Content-Disposition": f'inline; filename="{quote(doc["name"])}"'},
    )


@app.get("/bild/{doc_id}", response_class=HTMLResponse)
async def document_image(request: Request, doc_id: int, zurueck: str = "") -> HTMLResponse:
    """Ein Bild gross ansehen.

    OnlyOffice kann mit einem JPEG nichts anfangen, deshalb standen Bilder
    bisher gar nicht in ``editor.ANZEIGBAR`` und der Klick auf eine
    Bild-Kachel ging ins Leere. Ausgerechnet ein abfotografierter Beleg war
    damit das Einzige, was sich nicht oeffnen liess.

    Ein Bild braucht keinen Editor, nur eine Seite mit dem Bild darauf.
    """
    doc = get_store().document_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Unbekanntes Dokument")
    if doc.get("ext", "") not in BILD_ANZEIGBAR:
        raise HTTPException(status_code=415, detail="Das ist kein Bild")

    return templates.TemplateResponse(
        request,
        "bild.html",
        {
            "owner": OWNER,
            "titel": doc["name"],
            "quelle": f"/bilddatei/{doc_id}",
            "zurueck": zurueck or "#/dokumente",
        },
    )


@app.get("/bilddatei/{doc_id}")
async def document_image_file(doc_id: int) -> Response:
    """Das Bild selbst, in voller Aufloesung.

    Nicht ueber ``/vorschau``: das ist bewusst auf 256 Pixel gedeckelt, damit
    eine Kachelwand nicht 31 MB laedt. Wer ein Blatt lesen will, braucht die
    volle Aufloesung, sonst ist das Aktenzeichen ein grauer Fleck.
    """
    doc = get_store().document_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Unbekanntes Dokument")
    if doc.get("ext", "") not in BILD_ANZEIGBAR:
        raise HTTPException(status_code=415, detail="Das ist kein Bild")

    try:
        inhalt, typ = await editor.datei_holen(doc["path"])
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Datei nicht abrufbar") from exc

    return Response(
        content=inhalt,
        media_type=typ,
        headers={"Content-Disposition": f'inline; filename="{quote(doc["name"])}"'},
    )


@app.post("/api/onlyoffice/callback/{doc_id}")
async def onlyoffice_callback(request: Request, doc_id: int, m: str = "") -> dict[str, int]:
    """Rueckruf des Document Servers nach einer Aenderung.

    Muss **immer** ``{"error": 0}`` antworten, wenn nichts kaputt ist: bei
    allem anderen wiederholt der Document Server endlos und meldet Mia einen
    Speicherfehler.
    """
    if not editor.pruefe(doc_id, m):
        raise HTTPException(status_code=403, detail="Ungueltiger Zugriff")

    daten = await request.json()

    # Bei aktivem JWT steckt die echte Nutzlast im Token, der Rumpf ist nur
    # Beiwerk und darf nicht blind geglaubt werden.
    if settings.onlyoffice_jwt_secret:
        token = daten.get("token") or request.headers.get("authorization", "").removeprefix(
            "Bearer "
        )
        geprueft = editor.jwt_pruefen(token) if token else None
        if geprueft is None:
            raise HTTPException(status_code=403, detail="Signatur stimmt nicht")
        daten = geprueft.get("payload", geprueft)

    # 2 = fertig bearbeitet, 6 = Zwischenspeichern waehrend der Arbeit.
    if daten.get("status") not in (2, 6):
        return {"error": 0}

    doc = get_store().document_by_id(doc_id)
    if doc is None or not daten.get("url"):
        return {"error": 0}

    try:
        # follow_redirects: httpx folgt von sich aus KEINER Weiterleitung.
        # Der Document Server liefert seine Download-Adressen aber teils als
        # 302/303 aus. Ohne das schlaegt das Speichern fehl, und Mia sieht nur
        # "Dokument konnte nicht gespeichert werden".
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            antwort = await client.get(daten["url"])
            antwort.raise_for_status()
        await editor.datei_schreiben(doc["path"], antwort.content)
    except httpx.HTTPError:
        log.exception("Konnte %s nicht zurueckschreiben", doc["path"])
        return {"error": 1}

    log.info("Gespeichert: %s (%d Bytes)", doc["path"], len(antwort.content))
    return {"error": 0}


@app.get("/vorschau/{doc_id}")
async def document_preview(doc_id: int, groesse: int = 256) -> Response:
    """Vorschaubild eines Dokuments, serverseitig von Nextcloud geholt.

    Der Browser kann die Vorschau nicht selbst abrufen, dafuer braeuchte er
    Mias App-Passwort. Also holt Mia OS das Bild mit den eigenen Zugangsdaten
    und reicht es durch: so steht nie ein Passwort im HTML.
    """
    doc = get_store().document_by_id(doc_id)
    if doc is None or not doc.get("file_id"):
        raise HTTPException(status_code=404, detail="Keine Vorschau")

    if not (settings.nextcloud_url and settings.nextcloud_user and settings.nextcloud_password):
        raise HTTPException(status_code=503, detail="Nextcloud nicht konfiguriert")

    # Deckel bei 256: Nextcloud haelt sich oberhalb davon nicht an die
    # angefragte Kante und liefert die volle Seitenaufloesung. Gemessen an
    # einer echten Urkunde: x=256 -> 51 KB, x=400 -> 665 KB fuer dieselbe
    # Kachel. Bei 48 Kacheln je Seite ist das der Unterschied zwischen
    # 2,4 MB und 31 MB.
    kante = max(96, min(groesse, 256))
    url = f"{settings.nextcloud_url.rstrip('/')}/index.php/core/preview"
    try:
        async with httpx.AsyncClient(
            timeout=20,
            auth=(settings.nextcloud_user, settings.nextcloud_password),
        ) as client:
            resp = await client.get(
                url,
                params={"fileId": doc["file_id"], "x": kante, "y": kante, "a": 1},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Vorschau nicht erreichbar") from exc

    # Nicht jedes Dokument hat eine Vorschau. Das ist kein Fehler, die Kachel
    # zeigt dann ihr Kuerzel.
    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail="Keine Vorschau")

    return Response(
        content=resp.content,
        media_type=resp.headers.get("content-type", "image/png"),
        # Nur im Browser zwischenspeichern, nicht in Proxys: es sind private
        # Dokumentenseiten.
        headers={"Cache-Control": "private, max-age=86400"},
    )


@app.post("/api/collect")
async def api_collect() -> dict[str, bool]:
    return await collect_once()


# --- Intern ---------------------------------------------------------------


def _stamp() -> str:
    return datetime.now().strftime("%d.%m., %H:%M")


def _card(key: str) -> dict[str, Any]:
    latest = {row["key"]: row for row in get_store().latest(key)}
    return build_card(BY_KEY[key], latest)


def _zurueck_url(stand: str) -> str:
    """Aus dem mitgegebenen Zustand einen sicheren Rueckweg bauen.

    Der Wert kommt aus der Adresszeile, darf also nicht ungeprueft in ein
    ``href``. Nur bekannte Parameter werden uebernommen und neu
    zusammengesetzt: so kann daraus keine Weiterleitung auf eine fremde Seite
    werden, egal was jemand hineinschreibt.
    """
    erlaubt = {"q", "ordner", "seite"}
    felder = [
        (schluessel, wert)
        for schluessel, wert in parse_qsl(stand, keep_blank_values=False)
        if schluessel in erlaubt and wert
    ]
    return f"/#/dokumente?{urlencode(felder)}" if felder else "/#/dokumente"


def _doc_view(doc: dict[str, Any], mit_vorschau: bool = True) -> dict[str, Any]:
    """Einen Treffer fuer die Anzeige aufbereiten."""
    path = doc["path"]
    ext = doc.get("ext", "")
    eigene = doc.get("source") == "jana"
    ordner = doc.get("folder") or "/"

    # Der Klick bleibt in Mia OS: der Editor wird eingebettet, statt nach
    # Nextcloud abzuspringen. Nebenwirkung: der 421 ist weg, weil der Browser
    # gar nicht mehr auf nas. wechselt.
    #
    # Bilder gehen einen eigenen Weg. Sie standen vorher nirgends und waren
    # deshalb als Einzige nicht anklickbar, ausgerechnet die abfotografierten
    # Belege.
    ist_bild = ext in BILD_ANZEIGBAR
    anzeigbar = ext in editor.ANZEIGBAR or ist_bild
    if ist_bild:
        link = f"/bild/{doc['id']}"
    elif ext in editor.ANZEIGBAR:
        link = f"/bearbeiten/{doc['id']}"
    else:
        link = ""

    # Wo die Datei liegt, fuer den Fall dass Mia doch in Nextcloud will.
    ordner_link = ""
    if not eigene and settings.nextcloud_url:
        basis = settings.nextcloud_url.rstrip("/")
        ordner_link = f"{basis}/index.php/apps/files/?dir={quote(ordner)}"

    # Vorschau nur, wo Nextcloud eine rendern kann, und nur wenn Mia sie
    # eingeschaltet hat. Sonst zeigt die Kachel ihr Kuerzel.
    vorschau = ""
    if mit_vorschau and doc.get("file_id") and ext in PREVIEWABLE:
        vorschau = f"/vorschau/{doc['id']}"

    return {
        "id": doc.get("id"),
        "name": doc["name"],
        "folder": ordner,
        "ext": ext.lstrip("."),
        "groesse": _human_size(int(doc.get("size_bytes") or 0)),
        "datum": _human_date(doc.get("modified_at", "")),
        "quelle": "von mir" if eigene else "Nextcloud",
        "eigene": eigene,
        "bearbeitbar": ext in editor.BEARBEITBAR,
        "anzeigbar": anzeigbar,
        # Mia legt entpackte Archive neben dem Original ab. Ein zweiter Treffer
        # mit gleichem Namen ist dann kein Fehler, sieht aber so aus.
        "kopie": ordner.rstrip("/").rsplit("/", 1)[-1].lower()
        in {"uncompressed", "compressed", "unzip"},
        "vorschau": vorschau,
        "link": link,
        "ordner_link": ordner_link,
        "path": path,
        # Die Fundstelle im gelesenen Text, nur bei einem Treffer dort. Steht
        # ausschliesslich bei selbst gescannten Belegen zur Verfuegung, der
        # Bestand hat keinen gespeicherten Text.
        "stelle": doc.get("stelle") or "",
        "hat_text": bool(doc.get("ocr_text")),
    }


def _human_size(size: int) -> str:
    if size <= 0:
        return ""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _human_date(iso: str) -> str:
    """ISO in Mias Format. Leer statt Fehler, wenn nichts Brauchbares kommt."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y")
    except ValueError:
        return ""


def _category_payload(key: str) -> dict[str, Any]:
    """Kategorie flach, fuer die JSON-API."""
    cat = BY_KEY[key]
    latest = {row["key"]: row for row in get_store().latest(key)}
    values = [
        {
            "key": f.key,
            "label": f.label,
            "value": latest[f.key]["value"],
            "text": latest[f.key]["text_value"],
            "unit": latest[f.key]["unit"],
            "at": latest[f.key]["collected_at"],
        }
        for f in cat.fields
        if f.key in latest
    ]
    return {
        "key": cat.key,
        "title": cat.title,
        "icon": cat.icon,
        "live": cat.live,
        "values": values,
    }


def run() -> None:
    """Einstiegspunkt fuer ``mia-os``."""
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)


__all__ = ["LIVE", "app", "collect_once", "get_store", "run"]
