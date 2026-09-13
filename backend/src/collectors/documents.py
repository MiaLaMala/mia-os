"""Dokumente: Index ueber Nextcloud und die von Jana erstellten Dateien.

**Nur Metadaten.** Name, Pfad, Groesse, Datum. Nie Dateiinhalte: in Mias
Nextcloud liegen Ausweise, Geburtsurkunden und Recovery-Codes. Fuer die Frage
"welches Dokument liegt wo" reicht der Name vollstaendig aus.

Der WebDAV-Teil folgt der harten Lehre aus ``nextcloud-dokumentensuche``:
``PROPFIND`` liefert ``<d:href>`` URL-kodiert zurueck. Wer diesen Wert direkt
als naechsten Pfad weiterreicht und nochmal kodiert, bekommt 404 und die
Rekursion stirbt still bei der ersten Datei mit Umlaut. Deshalb: intern immer
DEKODIERTE Pfade halten, genau einmal beim Request kodieren.
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

from src.collectors.base import Collector
from src.config import settings

# Rauschen, das nie indiziert werden muss.
SKIP_DIRS = {
    ".obsidian",
    ".omc",
    "node_modules",
    ".git",
    ".cache",
    ".thumbnails",
    "__pycache__",
    ".venv",
}
MAX_DEPTH = 6

# Was als "Dokument" zaehlt. Bilder und Videos gehoeren nicht in einen
# Dokumenten-Index, die machen ihn nur unbrauchbar.
DOC_EXTS = {
    ".pdf",
    ".doc",
    ".docx",
    ".odt",
    ".rtf",
    ".txt",
    ".md",
    ".xls",
    ".xlsx",
    ".ods",
    ".csv",
    ".ppt",
    ".pptx",
    ".odp",
    ".html",
}

# Bilder gehoeren nicht in einen Dokumenten-Index: Mias Nextcloud haette dann
# jedes Urlaubsfoto drin und die Suche waere unbrauchbar. Im **Belegordner**
# ist ein Foto aber genau der Punkt, deshalb gelten dort diese Endungen
# zusaetzlich.
#
# Ohne diese Ausnahme faellt jeder fotografierte Beleg beim naechsten Crawl
# aus dem Index, und die Verknuepfung am Eintrag steht danach auf
# "nicht mehr am alten Ort", obwohl die Datei unveraendert daliegt.
BELEG_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}

RESPONSE_RE = re.compile(r"<d:response>(.*?)</d:response>", re.S)
HREF_RE = re.compile(r"<d:href>(.*?)</d:href>")
SIZE_RE = re.compile(r"<d:getcontentlength>(\d+)</d:getcontentlength>")
MTIME_RE = re.compile(r"<d:getlastmodified>(.*?)</d:getlastmodified>")
FILEID_RE = re.compile(r"<oc:fileid>(\d+)</oc:fileid>")

# PROPFIND-Rumpf: ohne den liefert Nextcloud nur die DAV-Standardfelder und
# keine oc:fileid. Die brauchen wir fuer die Vorschaubilder.
PROPFIND_BODY = (
    '<?xml version="1.0"?>'
    '<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
    "<d:prop>"
    "<d:resourcetype/><d:getcontentlength/><d:getlastmodified/><oc:fileid/>"
    "</d:prop></d:propfind>"
)

# Wovon Nextcloud ein Vorschaubild rendern kann. Bei allem anderen zeigt die
# Kachel das Kuerzel, statt auf ein 404-Bild zu warten.
PREVIEWABLE = {
    ".pdf",
    ".docx",
    ".doc",
    ".odt",
    ".xlsx",
    ".ods",
    ".pptx",
    ".odp",
    ".txt",
    ".md",
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
    ".webp",
}


def ist_beleg(pfad: str) -> bool:
    """Liegt die Datei in dem Ordner, in den Mia OS selbst schreibt?"""
    ordner = (settings.belege_ordner or "").rstrip("/")
    return bool(ordner) and pfad.startswith(ordner + "/")


def zaehlt_als_dokument(pfad: str) -> bool:
    """Gehoert diese Datei in den Index?

    Ueberall die Dokumentendungen, im Belegordner zusaetzlich Bilder.
    """
    ext = Path(pfad).suffix.lower()
    if ext in DOC_EXTS:
        return True
    return ext in BELEG_EXTS and ist_beleg(pfad)


def _entry(path: str, size: int, modified: str, source: str, file_id: str = "") -> dict[str, Any]:
    """Einen Fund in die Form bringen, die der Store erwartet."""
    name = path.rstrip("/").rsplit("/", 1)[-1]
    folder = path.rstrip("/").rsplit("/", 1)[0] or "/"
    ext = Path(name).suffix.lower()
    return {
        "source": source,
        "path": path,
        "name": name,
        "folder": folder,
        "ext": ext,
        "size_bytes": size,
        "modified_at": _iso(modified),
        "file_id": file_id,
    }


def _iso(http_date: str) -> str:
    """RFC-822 aus WebDAV in ISO umrechnen.

    Ohne das sortiert ``ORDER BY modified_at DESC`` alphabetisch: "Tue, 19 May"
    laendet dann vor "Mon, 03 Aug". Faellt das Parsen aus, lieber leer lassen
    als eine falsche Reihenfolge vortaeuschen.
    """
    if not http_date:
        return ""
    try:
        return parsedate_to_datetime(http_date).astimezone(UTC).isoformat()
    except (TypeError, ValueError):
        return ""


class DocumentCollector(Collector):
    """Baut den Dokumenten-Index aus Nextcloud plus lokalem Ablageordner."""

    name = "dokumente"
    category = "dokumente"

    def is_configured(self) -> bool:
        return bool(
            settings.nextcloud_url and settings.nextcloud_user and settings.nextcloud_password
        )

    async def collect(self) -> None:
        docs = await self._crawl_nextcloud()

        # Sicherung gegen einen halb abgebrochenen Crawl: lieber den alten
        # Index behalten als ihn durch eine Handvoll Dateien ersetzen.
        # Die Zahl stammt aus dem realen Bestand (1527 Dateien, Stand 09/2026).
        if len(docs) < settings.documents_min_expected:
            raise RuntimeError(
                f"Crawl lieferte nur {len(docs)} Dokumente, erwartet mindestens "
                f"{settings.documents_min_expected}. Index bleibt unveraendert."
            )

        self.store.replace_documents("nextcloud", docs)

        eigene = self._scan_local()
        if eigene:
            self.store.replace_documents("jana", eigene)

        stats = self.store.document_stats()
        self.store.record("dokumente", "gesamt", float(stats["gesamt"]))
        self.store.record("dokumente", "nextcloud_anzahl", float(len(docs)))
        self.store.record("dokumente", "eigene_anzahl", float(len(eigene)))

        typen = ", ".join(f"{t['ext'].lstrip('.').upper()} {t['n']}" for t in stats["typen"][:4])
        self.store.record("dokumente", "typen", text_value=typen)

        # Bewusst die Ordnerzahl statt des neuesten Dateinamens: der Leitwert
        # steht auf der Startseite, und dort haben Titel von Arztberichten
        # nichts verloren.
        ordner = len(self.store.document_folders(limit=100))
        self.store.record(
            "dokumente",
            "ordner_anzahl",
            text_value=f"in {ordner} Ordnern" if ordner else "",
        )

    # --- Nextcloud --------------------------------------------------------

    async def _crawl_nextcloud(self) -> list[dict[str, Any]]:
        base = settings.nextcloud_url.rstrip("/")
        root = f"{base}/remote.php/dav/files/{settings.nextcloud_user}"
        auth = (settings.nextcloud_user, settings.nextcloud_password)

        found: list[dict[str, Any]] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=30, auth=auth) as client:
            await self._walk(client, root, "/", 0, found, seen)
        return found

    async def _walk(
        self,
        client: httpx.AsyncClient,
        root: str,
        path: str,
        depth: int,
        found: list[dict[str, Any]],
        seen: set[str],
    ) -> None:
        if depth > MAX_DEPTH or path in seen:
            return
        seen.add(path)

        for rel, isdir, size, modified, file_id in await self._list(client, root, path):
            name = rel.rstrip("/").rsplit("/", 1)[-1]
            if isdir:
                if name not in SKIP_DIRS:
                    await self._walk(client, root, rel, depth + 1, found, seen)
            elif zaehlt_als_dokument(rel):
                found.append(_entry(rel, size, modified, "nextcloud", file_id))

    async def _list(
        self, client: httpx.AsyncClient, root: str, path: str
    ) -> list[tuple[str, bool, int, str, str]]:
        """Ein Verzeichnis auflisten. ``path`` ist dekodiert, hier wird kodiert."""
        resp = await client.request(
            "PROPFIND",
            root + urllib.parse.quote(path),
            headers={"Depth": "1", "Content-Type": "application/xml"},
            content=PROPFIND_BODY.encode(),
        )
        resp.raise_for_status()

        user = settings.nextcloud_user
        out: list[tuple[str, bool, int, str, str]] = []
        for block in RESPONSE_RE.findall(resp.text):
            href = HREF_RE.search(block)
            if not href:
                continue
            rel = urllib.parse.unquote(href.group(1)).split(f"/files/{user}", 1)[-1]
            if rel.rstrip("/") == path.rstrip("/"):
                continue  # der Ordner selbst
            isdir = "<d:collection/>" in block or "<d:collection />" in block
            size = SIZE_RE.search(block)
            mtime = MTIME_RE.search(block)
            fid = FILEID_RE.search(block)
            out.append(
                (
                    rel,
                    isdir,
                    int(size.group(1)) if size else 0,
                    mtime.group(1) if mtime else "",
                    fid.group(1) if fid else "",
                )
            )
        return out

    # --- Eigene Dokumente -------------------------------------------------

    def _scan_local(self) -> list[dict[str, Any]]:
        """Was ich selbst fuer Mia erstellt habe.

        Faellt still aus, wenn der Ordner nicht existiert: im Container ist er
        nur eingehaengt, wenn er auch gebraucht wird.
        """
        root_setting = settings.documents_local_path
        if not root_setting:
            return []
        root = Path(root_setting)
        if not root.is_dir():
            return []

        out: list[dict[str, Any]] = []
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in DOC_EXTS:
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            try:
                stat = p.stat()
            except OSError:
                continue
            rel = "/" + str(p.relative_to(root))
            out.append(
                _entry(
                    rel,
                    stat.st_size,
                    _http_date(stat.st_mtime),
                    "jana",
                )
            )
        return out


def _http_date(ts: float) -> str:
    """Lokalen Zeitstempel in dasselbe Format bringen, das WebDAV liefert."""
    return datetime.fromtimestamp(ts, UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
