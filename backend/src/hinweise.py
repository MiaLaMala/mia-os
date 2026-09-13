"""Hinweise für die Geräte: kurze Zettel, die auf dem Display erscheinen.

Ein Hinweis ist ein Satz von jemandem (Jana, ein Cron-Job, Mia selbst),
der für kurze Zeit auf dem Tisch stehen soll: "Paket bei Nachbarin",
"Jellyfin seit 12 min wieder oben". Das Display zeigt den ältesten offenen
und bietet zwei Knöpfe, "ok" und "später". Ok heißt gesehen, der Hinweis
verschwindet. Später schiebt ihn eine Stunde nach hinten.

Warum kein Push zum Gerät: das Display fragt ohnehin alle zwei Minuten nach
dem Briefing. Die Hinweise kommen dort einfach mit. Ein HTTP-Server auf dem
ESP32 wäre ein zweiter Weg für dasselbe.

Die Liste lebt im Speicher und wird als JSON abgelegt, damit sie einen
Neustart übersteht. Eine Datenbanktabelle wäre für ein Dutzend Zeilen zu
viel Apparat.

**Hall of Fame und Shame.** Regel 39 des Discord-Servers: viermal Daumen
hoch, und die Nachricht kommt in die Hall of Fame. Das Display macht das
mit viermal Tippen auf "ok" (Fame) oder "später" (Shame). Beides landet in
einer eigenen Liste, die Jana lesen kann, um zu lernen, welche Hinweise
ankommen und welche nerven.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ABLAGE = Path("/var/lib/mia-os/hinweise.json")

# Länger zeigt das Display keinen Hinweis von selbst. Was nach einem Tag
# noch niemand gesehen hat, war nicht wichtig.
VERFALL = timedelta(hours=24)
SPAETER = timedelta(hours=1)
MAX_TEXT = 120


@dataclass
class Hinweis:
    id: int
    text: str
    von: str = "Jana"
    erstellt: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    # Ab wann der Hinweis wieder gezeigt werden darf (nach "später").
    ab: str = ""
    # "offen", "ok", "spaeter", "fame", "shame"
    zustand: str = "offen"
    erledigt: str = ""

    def sichtbar(self, jetzt: datetime) -> bool:
        if self.zustand not in ("offen", "spaeter"):
            return False
        if datetime.fromisoformat(self.erstellt) + VERFALL < jetzt:
            return False
        return not (self.ab and datetime.fromisoformat(self.ab) > jetzt)


class Hinweise:
    def __init__(self, ablage: Path = ABLAGE) -> None:
        self._ablage = ablage
        self._schloss = threading.Lock()
        self._liste: list[Hinweis] = []
        self._naechste_id = 1
        self._laden()

    def _laden(self) -> None:
        if not self._ablage.exists():
            return
        try:
            roh = json.loads(self._ablage.read_text(encoding="utf-8"))
            self._liste = [Hinweis(**h) for h in roh.get("hinweise", [])]
            self._naechste_id = int(roh.get("naechste_id", len(self._liste) + 1))
        except (OSError, ValueError, TypeError) as e:
            log.warning("Hinweise nicht lesbar, fange leer an: %s", e)

    def _sichern(self) -> None:
        self._ablage.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._ablage.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {"naechste_id": self._naechste_id, "hinweise": [asdict(h) for h in self._liste]},
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        tmp.replace(self._ablage)

    def anlegen(self, text: str, von: str = "Jana") -> Hinweis:
        text = " ".join(text.split())[:MAX_TEXT]
        if not text:
            raise ValueError("Hinweis ohne Text")
        with self._schloss:
            h = Hinweis(id=self._naechste_id, text=text, von=von[:32] or "Jana")
            self._naechste_id += 1
            self._liste.append(h)
            # Erledigtes älter als sieben Tage fliegt raus, sonst wächst die
            # Datei ewig. Fame und Shame bleiben, das ist ja der Sinn.
            grenze = datetime.now(UTC) - timedelta(days=7)
            self._liste = [
                x
                for x in self._liste
                if x.zustand in ("offen", "spaeter", "fame", "shame")
                or datetime.fromisoformat(x.erstellt) > grenze
            ]
            self._sichern()
            return h

    def offen(self) -> list[dict[str, Any]]:
        """Was das Display zeigen darf, ältester zuerst."""
        jetzt = datetime.now(UTC)
        with self._schloss:
            return [
                {"id": h.id, "text": h.text, "von": h.von, "erstellt": h.erstellt}
                for h in self._liste
                if h.sichtbar(jetzt)
            ]

    def antworten(self, hinweis_id: int, antwort: str) -> Hinweis | None:
        """Was das Gerät zurückmeldet: ok, spaeter, fame, shame."""
        if antwort not in ("ok", "spaeter", "fame", "shame"):
            raise ValueError(f"Unbekannte Antwort: {antwort}")
        with self._schloss:
            for h in self._liste:
                if h.id != hinweis_id:
                    continue
                jetzt = datetime.now(UTC)
                if antwort == "spaeter":
                    h.zustand = "spaeter"
                    h.ab = (jetzt + SPAETER).isoformat()
                else:
                    h.zustand = antwort
                    h.erledigt = jetzt.isoformat()
                self._sichern()
                return h
        return None

    def alle(self) -> list[dict[str, Any]]:
        with self._schloss:
            return [asdict(h) for h in reversed(self._liste)]


_hinweise: Hinweise | None = None


def hole_hinweise() -> Hinweise:
    global _hinweise
    if _hinweise is None:
        _hinweise = Hinweise()
    return _hinweise
