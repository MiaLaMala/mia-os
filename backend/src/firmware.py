"""Firmware für die Geräte und wer sich gemeldet hat.

Zwei Dinge, die zusammengehören:

**Die Firmware.** Die CI legt sie in den Zweig ``firmware`` des Repos
``jana-desktop``, zusammen mit einer kleinen JSON-Datei. Mia OS holt sich
beides mit dem vorhandenen Deploy-Key und reicht es an die Geräte weiter.

*Warum der Umweg über den Server:* Das Repo ist privat, ein Download
bräuchte also einen Schlüssel. Ein ESP32 liegt offen auf dem Schreibtisch,
wer ihn mitnimmt liest den Flash aus. Ein Schlüssel im Gerät liesse sich
ausserdem nur wechseln, indem man genau das Gerät flasht, das man gerade
aus der Ferne erreichen wollte. Der Server hat den Zugang ohnehin.

*Warum ein Zweig statt eines Releases:* Release-Dateien hängen an der
GitHub-API und brauchen ein Token. Ein Zweig kommt über SSH, und dafür gibt
es schon einen Deploy-Key mit Leserecht.

**Die Geräteliste.** Geräte melden sich beim Start und bei jedem Abruf. Der
Server weiß dadurch, was es gibt, welche Fassung läuft und wann er zuletzt
gehört hat. Das ist die Voraussetzung dafür, ein Gerät von sich aus
anzustupsen, statt zu warten, bis es das nächste Mal fragt.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Der Zweig, in den die CI baut. Nur die aktuelle Datei, keine Historie.
REPO = "git@github-jana-desktop:MiaLaMala/jana-desktop.git"
ZWEIG = "firmware"
ABLAGE = Path("/var/lib/mia-os/firmware")

# Wie oft nachgesehen wird, ob die CI etwas Neues gebaut hat. Zehn Minuten
# ist derselbe Takt wie beim Deploy von Mia OS selbst.
NACHSEHEN_SEKUNDEN = 600

# Ab wann ein Gerät als verschwunden gilt. Das Display meldet sich alle zwei
# Minuten, drei verpasste Meldungen sind also ein echtes Schweigen.
STILL_SEKUNDEN = 420


@dataclass
class Geraet:
    """Was der Server über ein Gerät weiß."""

    kennung: str
    name: str = ""
    version: str = ""
    adresse: str = ""
    # Was das Gerät sonst noch über sich sagt: Bildzeit der Augen in
    # Mikrosekunden, freier Heap in Bytes. Gemessen auf dem Gerät, nicht
    # gerechnet, deshalb steht es hier und nicht in einer Doku.
    bild_us: int = 0
    heap: int = 0
    zuletzt: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def still_seit(self) -> int:
        return int((datetime.now(UTC) - self.zuletzt).total_seconds())

    @property
    def erreichbar(self) -> bool:
        return self.still_seit < STILL_SEKUNDEN

    def als_dict(self) -> dict[str, Any]:
        return {
            "kennung": self.kennung,
            "name": self.name,
            "version": self.version,
            "adresse": self.adresse,
            "bild_us": self.bild_us,
            "heap": self.heap,
            "zuletzt": self.zuletzt.isoformat(),
            "still_seit": self.still_seit,
            "erreichbar": self.erreichbar,
        }


class Firmware:
    """Holt die gebaute Firmware und merkt sich, wer sich gemeldet hat."""

    def __init__(self) -> None:
        self._geraete: dict[str, Geraet] = {}
        self._schloss = threading.Lock()
        self._stand: dict[str, Any] = {}
        self._geholt: datetime | None = None
        # Stand der Geraete-Einstellungen. Zaehlt bei jeder Aenderung hoch;
        # wer wartet, bekommt in dem Moment eine Antwort. Das Display haelt
        # dafuer dauerhaft eine Anfrage offen (Long-Polling), weil der Server
        # es hinter dem NAT des Pi nicht von sich aus erreichen kann.
        self.einstellungs_stand = 1
        self._geaendert: asyncio.Event | None = None

    def _ereignis(self) -> asyncio.Event:
        if self._geaendert is None:
            self._geaendert = asyncio.Event()
        return self._geaendert

    def einstellungen_geaendert(self) -> None:
        """Von der Einstellungsseite aufgerufen, wenn ein display_* Wert neu ist."""
        self.einstellungs_stand += 1
        ereignis = self._ereignis()
        ereignis.set()
        ereignis.clear()

    async def warten(self, seit: int, sekunden: float) -> bool:
        """Bis sich etwas aendert oder die Zeit um ist. True bei Aenderung."""
        if seit != self.einstellungs_stand:
            return True
        try:
            await asyncio.wait_for(self._ereignis().wait(), timeout=sekunden)
            return True
        except TimeoutError:
            return False

    # --- Firmware ---------------------------------------------------------

    def _holen(self) -> None:
        """Den Zweig holen oder aktualisieren.

        Ein flacher Klon reicht: der Zweig hat bewusst keine Historie, und
        die CI schreibt ihn mit ``--force`` neu. Deshalb bei jedem Abruf
        neu klonen statt zu ziehen, ein ``pull`` würde an der ersetzten
        Historie scheitern.
        """
        ABLAGE.parent.mkdir(parents=True, exist_ok=True)
        ziel = ABLAGE.with_suffix(".neu")
        if ziel.exists():
            subprocess.run(["rm", "-rf", str(ziel)], check=False)

        subprocess.run(
            ["git", "clone", "--quiet", "--depth", "1", "--branch", ZWEIG, REPO, str(ziel)],
            check=True,
            capture_output=True,
            timeout=120,
            # HOME muss gesetzt sein, sonst findet git die ssh/config nicht
            # und damit auch nicht den Schluessel. Der Container laeuft als
            # "mia", nicht als root: derselbe Stolperstein wie beim
            # Kuma-Zugriff.
            env={"HOME": "/home/mia", "PATH": "/usr/bin:/bin"},
        )

        # Erst prüfen, dann übernehmen. Eine halb geholte Firmware wäre
        # schlimmer als eine veraltete.
        beschreibung = json.loads((ziel / "firmware.json").read_text(encoding="utf-8"))
        datei = ziel / "firmware.bin"
        echte = hashlib.sha256(datei.read_bytes()).hexdigest()
        if echte != beschreibung["sha256"]:
            subprocess.run(["rm", "-rf", str(ziel)], check=False)
            raise ValueError(f"Prüfsumme weicht ab: {echte} statt {beschreibung['sha256']}")

        if ABLAGE.exists():
            subprocess.run(["rm", "-rf", str(ABLAGE)], check=False)
        ziel.rename(ABLAGE)
        self._stand = beschreibung
        self._geholt = datetime.now(UTC)
        log.info("Firmware %s geholt (%d Bytes)", beschreibung["version"], beschreibung["groesse"])

    def stand(self) -> dict[str, Any]:
        """Was gerade bereitsteht. Holt nach, wenn es zu lange her ist."""
        veraltet = (
            self._geholt is None
            or (datetime.now(UTC) - self._geholt).total_seconds() > NACHSEHEN_SEKUNDEN
        )
        if veraltet:
            try:
                self._holen()
            except (subprocess.SubprocessError, OSError, ValueError, KeyError) as fehler:
                # Kein Netz, kein Schlüssel, kaputte Datei: dann gilt der
                # letzte bekannte Stand weiter. Ein Gerät, das wegen eines
                # Fehlers hier nicht mehr nach Terminen fragt, wäre schlimmer
                # als eines, das ein Update später erfährt.
                log.warning("Firmware nicht geholt: %s", fehler)
        return dict(self._stand)

    def datei(self) -> Path | None:
        pfad = ABLAGE / "firmware.bin"
        return pfad if pfad.exists() else None

    # --- Geräte -----------------------------------------------------------

    def melden(
        self,
        kennung: str,
        name: str,
        version: str,
        adresse: str,
        bild_us: int = 0,
        heap: int = 0,
    ) -> None:
        """Ein Gerät hat sich gemeldet."""
        with self._schloss:
            vorher = self._geraete.get(kennung)
            self._geraete[kennung] = Geraet(
                kennung=kennung,
                name=name or (vorher.name if vorher else ""),
                version=version,
                adresse=adresse,
                bild_us=bild_us,
                heap=heap,
                zuletzt=datetime.now(UTC),
            )
            if vorher and vorher.version != version:
                log.info("%s: %s -> %s", kennung, vorher.version or "?", version)

    def geraete(self) -> list[dict[str, Any]]:
        with self._schloss:
            liste = sorted(self._geraete.values(), key=lambda g: g.name or g.kennung)
        return [g.als_dict() for g in liste]


_firmware: Firmware | None = None


def hole_firmware() -> Firmware:
    global _firmware
    if _firmware is None:
        _firmware = Firmware()
    return _firmware
