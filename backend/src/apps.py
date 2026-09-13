"""Die gebauten Apps für Mac und iPhone.

Derselbe Weg wie bei der Display-Firmware in ``firmware.py``, und aus
denselben Gründen: die CI legt die fertigen Dateien in den Zweig ``apps``,
Mia OS holt sie mit dem vorhandenen Deploy-Key und reicht sie weiter.

*Warum der Umweg über den Server statt eines Downloads von GitHub:* das Repo
ist privat, ein direkter Abruf bräuchte also ein Token in der App. Ein Token
auf einem Gerät, das verloren gehen kann, ist ein Token zu viel. Der Server
hat den Zugang ohnehin, und die App redet mit ihm sowieso schon.

*Warum ein Zweig und kein Release:* Release-Dateien hängen an der GitHub-API
und brauchen ein Token. Ein Zweig kommt über SSH, und dafür gibt es bereits
einen Deploy-Key mit Leserecht.

**Was hier bewusst NICHT passiert: automatisch aktualisieren.** Die App
erfährt, dass es etwas Neues gibt, und sagt es. Das Ersetzen einer laufenden
Anwendung ist der Punkt, an dem ein Fehler die App unbrauchbar macht, und
dann steht Mia ohne das Werkzeug da, mit dem sie das Problem melden würde.
Derselbe Gedanke wie beim Umbenennen von Belegen: der Klick ist die
Zustimmung.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Derselbe Deploy-Key wie für die Firmware, deshalb derselbe SSH-Aliasname.
REPO = "git@github-mia-os:MiaLaMala/mia-os.git"
ZWEIG = "apps"
ABLAGE = Path("/var/lib/mia-os/apps")

# Wie oft nachgesehen wird. Zehn Minuten, derselbe Takt wie bei der Firmware
# und beim Deploy von Mia OS selbst.
NACHSEHEN_SEKUNDEN = 600

# Welche Dateien es gibt. Der Schlüssel ist das, was die App als ``art``
# mitschickt.
ARTEN = {
    "mac": "MiaOS-Mac.zip",
    "ios": "MiaOS-iOS.ipa",
}


class Apps:
    """Holt die gebauten Apps und sagt, was bereitsteht."""

    def __init__(self) -> None:
        self._stand: dict[str, Any] = {}
        self._geholt: datetime | None = None
        # Der Abruf läuft in einem Thread-Pool von Starlette: zwei Anfragen
        # gleichzeitig würden sonst beide klonen und sich in dasselbe
        # Verzeichnis schreiben.
        self._schloss = threading.Lock()

    def _holen(self) -> None:
        """Den Zweig frisch klonen und die Prüfsummen nachrechnen."""
        ABLAGE.parent.mkdir(parents=True, exist_ok=True)
        ziel = ABLAGE.with_suffix(".neu")
        subprocess.run(["rm", "-rf", str(ziel)], check=False)

        subprocess.run(
            ["git", "clone", "--quiet", "--depth", "1", "--branch", ZWEIG, REPO, str(ziel)],
            check=True,
            capture_output=True,
            timeout=300,
            # HOME muss gesetzt sein, sonst findet git die ssh/config nicht.
            # Der Container läuft als "mia", nicht als root: derselbe
            # Stolperstein wie bei Kuma und bei der Firmware.
            env={"HOME": "/home/mia", "PATH": "/usr/bin:/bin"},
        )

        beschreibung = json.loads((ziel / "apps.json").read_text(encoding="utf-8"))

        # Erst prüfen, dann übernehmen. Eine halb geholte App wäre schlimmer
        # als eine veraltete: sie ließe sich herunterladen und nicht öffnen.
        for art, datei in ARTEN.items():
            teil = beschreibung.get(art)
            if not teil:
                continue
            pfad = ziel / datei
            echte = hashlib.sha256(pfad.read_bytes()).hexdigest()
            if echte != teil["sha256"]:
                subprocess.run(["rm", "-rf", str(ziel)], check=False)
                raise ValueError(f"{datei}: Prüfsumme weicht ab ({echte} statt {teil['sha256']})")

        subprocess.run(["rm", "-rf", str(ABLAGE)], check=False)
        ziel.rename(ABLAGE)
        self._stand = beschreibung
        self._geholt = datetime.now(UTC)
        log.info("Apps %s geholt", beschreibung.get("version", "?"))

    def stand(self) -> dict[str, Any]:
        """Was bereitsteht. Holt nach, wenn es zu lange her ist."""
        veraltet = (
            self._geholt is None
            or (datetime.now(UTC) - self._geholt).total_seconds() > NACHSEHEN_SEKUNDEN
        )
        if veraltet and self._schloss.acquire(blocking=False):
            try:
                self._holen()
            except (subprocess.SubprocessError, OSError, ValueError, KeyError) as fehler:
                # Kein Netz, kein Schlüssel, kaputte Datei: dann gilt der
                # letzte bekannte Stand weiter. Eine App, die wegen eines
                # Fehlers hier nicht mehr startet, wäre schlimmer als eine,
                # die ein Update später erfährt.
                log.warning("Apps nicht geholt: %s", fehler)
            finally:
                self._schloss.release()
        return dict(self._stand)

    def datei(self, art: str) -> Path | None:
        """Die Datei zu einer Art, wenn es sie gibt."""
        name = ARTEN.get(art)
        if name is None:
            return None
        pfad = ABLAGE / name
        return pfad if pfad.exists() else None


_apps: Apps | None = None


def hole_apps() -> Apps:
    global _apps
    if _apps is None:
        _apps = Apps()
    return _apps
