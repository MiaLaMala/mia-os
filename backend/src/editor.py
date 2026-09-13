"""Dokumente bearbeiten: Bruecke zwischen Mia OS, OnlyOffice und Nextcloud.

Der Ablauf, wenn Mia auf eine Kachel tippt:

1. Der Browser oeffnet ``/bearbeiten/<id>`` in Mia OS.
2. Die Seite laedt die OnlyOffice-Oberfläche und uebergibt ihr eine
   Konfiguration mit zwei Adressen: woher die Datei kommt und wohin
   Aenderungen gemeldet werden. Beide zeigen auf Mia OS.
3. Der **Document Server** (nicht der Browser) holt die Datei unter
   ``/datei/<id>``. Mia OS laedt sie in dem Moment mit Mias App-Passwort aus
   Nextcloud und reicht sie durch.
4. Schliesst Mia den Editor nach einer Aenderung, ruft der Document Server
   ``/api/onlyoffice/callback/<id>`` auf. Mia OS holt die bearbeitete Fassung
   und legt sie per WebDAV zurueck an ihren Platz in Nextcloud.

Damit bleibt Nextcloud der einzige Speicherort. Mia OS haelt nie eine Kopie.

Warum eigene Signaturen statt eines Logins: der Document Server ruft ohne
Sitzung an. Jede Adresse traegt deshalb ein kurzlebiges, an die Dokument-ID
gebundenes Merkmal (``signiere``/``pruefe``). Ohne gueltige Signatur gibt es
weder Datei noch Rueckschreiben, auch nicht fuer jemanden, der die ID errraet.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any

import httpx

from src.config import settings

# Was OnlyOffice bearbeiten kann, nach Editor-Typ.
WORD = {".docx", ".doc", ".odt", ".rtf", ".txt"}
CELL = {".xlsx", ".xls", ".ods", ".csv"}
SLIDE = {".pptx", ".ppt", ".odp"}
# PDFs oeffnet OnlyOffice zum Lesen, nicht zum Bearbeiten.
NUR_LESEN = {".pdf"}

BEARBEITBAR = WORD | CELL | SLIDE
ANZEIGBAR = BEARBEITBAR | NUR_LESEN

# Wie lange eine Adresse gilt. Grosszuegig, weil ein Dokument auch mal
# eine Weile offen liegt, aber nicht unbegrenzt.
GUELTIG_SEKUNDEN = 12 * 3600


def editor_typ(ext: str) -> str:
    """Welchen Editor OnlyOffice laden soll."""
    if ext in CELL:
        return "cell"
    if ext in SLIDE:
        return "slide"
    return "word"


def _geheimnis() -> bytes:
    """Schluessel fuer die eigenen Signaturen.

    Bewusst derselbe wie fuer OnlyOffice: wer den kennt, kann ohnehin alles.
    Ein zweites Geheimnis waere nur eine weitere Sache, die vergessen wird.
    """
    return (settings.onlyoffice_jwt_secret or "mia-os-ohne-geheimnis").encode()


def signiere(doc_id: int) -> str:
    """Kurzlebiges Merkmal fuer genau dieses Dokument."""
    ablauf = int(time.time()) + GUELTIG_SEKUNDEN
    roh = f"{doc_id}:{ablauf}"
    sig = hmac.new(_geheimnis(), roh.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{ablauf}.{sig}"


def pruefe(doc_id: int, merkmal: str) -> bool:
    """Gehoert das Merkmal zu diesem Dokument und gilt es noch?"""
    try:
        ablauf_text, sig = merkmal.split(".", 1)
        ablauf = int(ablauf_text)
    except (ValueError, AttributeError):
        return False
    if ablauf < time.time():
        return False
    erwartet = hmac.new(_geheimnis(), f"{doc_id}:{ablauf}".encode(), hashlib.sha256).hexdigest()[
        :32
    ]
    return hmac.compare_digest(sig, erwartet)


# --- JWT fuer OnlyOffice ---------------------------------------------------


def _b64(roh: bytes) -> str:
    return urlsafe_b64encode(roh).rstrip(b"=").decode()


def jwt_signieren(nutzlast: dict[str, Any]) -> str:
    """Minimales HS256-JWT.

    Bewusst von Hand statt mit einer Bibliothek: es sind zwanzig Zeilen, und
    eine Abhaengigkeit weniger im Container ist eine Angriffsflaeche weniger.
    """
    kopf = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    koerper = _b64(json.dumps(nutzlast, separators=(",", ":"), sort_keys=True).encode())
    zu_signieren = f"{kopf}.{koerper}".encode()
    sig = hmac.new(settings.onlyoffice_jwt_secret.encode(), zu_signieren, hashlib.sha256)
    return f"{kopf}.{koerper}.{_b64(sig.digest())}"


def jwt_pruefen(token: str) -> dict[str, Any] | None:
    """Ein JWT des Document Servers pruefen. ``None``, wenn etwas nicht stimmt."""
    try:
        kopf, koerper, sig = token.split(".")
    except ValueError:
        return None
    erwartet = _b64(
        hmac.new(
            settings.onlyoffice_jwt_secret.encode(), f"{kopf}.{koerper}".encode(), hashlib.sha256
        ).digest()
    )
    if not hmac.compare_digest(sig, erwartet):
        return None
    fehlend = "=" * (-len(koerper) % 4)
    try:
        daten: dict[str, Any] = json.loads(urlsafe_b64decode(koerper + fehlend))
    except (ValueError, TypeError):
        return None
    return daten


# --- Nextcloud -------------------------------------------------------------


def _webdav_url(pfad: str) -> str:
    basis = settings.nextcloud_url.rstrip("/")
    return f"{basis}/remote.php/dav/files/{settings.nextcloud_user}{urllib.parse.quote(pfad)}"


async def datei_holen(pfad: str) -> tuple[bytes, str]:
    """Eine Datei aus Nextcloud laden. Gibt Inhalt und Medientyp zurueck."""
    auth = (settings.nextcloud_user, settings.nextcloud_password)
    # follow_redirects, weil Nextcloud WebDAV-Anfragen umleitet und httpx von
    # sich aus keiner Weiterleitung folgt.
    async with httpx.AsyncClient(timeout=60, auth=auth, follow_redirects=True) as client:
        antwort = await client.get(_webdav_url(pfad))
        antwort.raise_for_status()
        typ = antwort.headers.get("content-type", "application/octet-stream")
        return antwort.content, typ


async def datei_schreiben(pfad: str, inhalt: bytes) -> None:
    """Eine bearbeitete Datei zurueck nach Nextcloud legen."""
    auth = (settings.nextcloud_user, settings.nextcloud_password)
    async with httpx.AsyncClient(timeout=120, auth=auth, follow_redirects=True) as client:
        antwort = await client.put(_webdav_url(pfad), content=inhalt)
        antwort.raise_for_status()


def dokument_schluessel(doc: dict[str, Any]) -> str:
    """Kennung, die OnlyOffice zum Zwischenspeichern nutzt.

    Muss sich aendern, sobald sich die Datei aendert, sonst zeigt der Server
    eine veraltete Fassung aus seinem Zwischenspeicher. Deshalb steckt der
    Aenderungszeitpunkt mit drin.
    """
    roh = f"{doc['id']}:{doc.get('modified_at', '')}:{doc.get('size_bytes', 0)}"
    return hashlib.sha256(roh.encode()).hexdigest()[:20]
