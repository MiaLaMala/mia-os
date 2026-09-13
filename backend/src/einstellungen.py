"""Was Mia selbst einstellen kann.

Bewusst getrennt von ``config.py``: dort stehen Zugangsdaten und Adressen, die
beim Start aus der Umgebung kommen. Hier stehen Vorlieben, die sich im Betrieb
aendern duerfen und in der Datenbank liegen.

Jede Einstellung ist hier **einmal** beschrieben: Typ, Vorgabe, erlaubter
Bereich. Die Seite baut sich daraus selbst, und die Pruefung beim Speichern
benutzt dieselbe Liste. So kann die Anzeige nicht von dem abweichen, was
wirklich angenommen wird.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Einstellung:
    key: str
    titel: str
    hilfe: str
    art: Literal["schalter", "zahl", "auswahl"]
    vorgabe: str
    gruppe: str
    minimum: int = 0
    maximum: int = 0
    optionen: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def pruefe(self, roh: str) -> str | None:
        """Einen eingegebenen Wert pruefen. ``None``, wenn er nicht taugt."""
        if self.art == "schalter":
            return "1" if roh in {"1", "on", "true", "ja"} else "0"
        if self.art == "zahl":
            try:
                zahl = int(roh)
            except (TypeError, ValueError):
                return None
            if not self.minimum <= zahl <= self.maximum:
                return None
            return str(zahl)
        if self.art == "auswahl":
            gueltig = {wert for wert, _ in self.optionen}
            return roh if roh in gueltig else None
        return None


EINSTELLUNGEN: tuple[Einstellung, ...] = (
    Einstellung(
        key="sammel_minuten",
        titel="Wie oft gesammelt wird",
        hilfe="Abstand zwischen zwei Durchläufen. Kürzer heißt frischere Zahlen "
        "und mehr Last auf Proxmox und Nextcloud.",
        art="zahl",
        vorgabe="15",
        gruppe="Aktualisierung",
        minimum=5,
        maximum=240,
    ),
    Einstellung(
        key="live_sekunden",
        titel="Live-Aktualisierung",
        hilfe="Abstand, in dem die Homelab-Seite ihre Zahlen im Hintergrund "
        "nachlädt. 0 schaltet es ab.",
        art="zahl",
        vorgabe="20",
        gruppe="Aktualisierung",
        minimum=0,
        maximum=300,
    ),
    Einstellung(
        key="dokumente_vorschau",
        titel="Vorschaubilder zeigen",
        hilfe="Aus heißt: nur Dateikürzel statt Seitenbild. Sinnvoll, wenn "
        "jemand mitliest, denn Vorschauen sind lesbar.",
        art="schalter",
        vorgabe="1",
        gruppe="Dokumente",
    ),
    Einstellung(
        key="dokumente_pro_seite",
        titel="Dokumente je Seite",
        hilfe="Mehr Kacheln heißt weniger blättern, aber längeres Laden.",
        art="zahl",
        vorgabe="48",
        gruppe="Dokumente",
        minimum=12,
        maximum=120,
    ),
    Einstellung(
        key="dienste_nur_stoerungen",
        titel="Nur Störungen zeigen",
        hilfe="Blendet alles aus, was normal läuft. Ruhiger, wenn dich nur "
        "interessiert was klemmt.",
        art="schalter",
        vorgabe="0",
        gruppe="Homelab",
    ),
    Einstellung(
        key="dienste_uptime_zeitraum",
        titel="Verfügbarkeit über",
        hilfe="Welcher Zeitraum bei den Diensten angezeigt wird.",
        art="auswahl",
        vorgabe="24",
        gruppe="Homelab",
        optionen=(("24", "24 Stunden"), ("30", "30 Tage")),
    ),
    Einstellung(
        key="thema",
        titel="Farbe",
        hilfe="Der Akzent für aktive Auswahl, Fokus und Markierungen. Gilt auf allen Geräten.",
        art="auswahl",
        vorgabe="standard",
        gruppe="Darstellung",
        optionen=(("standard", "Blau"), ("rot", "Rot")),
    ),
    # --- Jana Desktop: das Display auf dem Schreibtisch ---------------------
    # Kommt mit dem Briefing zum Geraet, das die Werte im NVS ablegt. Gilt
    # damit auch, wenn Mia OS gerade nicht erreichbar ist.
    Einstellung(
        key="display_theme",
        titel="Ansicht",
        hilfe="Gesicht: zwei Augen und ein Satz. Seiten: Uhr, Termine, Kästen.",
        art="auswahl",
        vorgabe="gesicht",
        gruppe="Jana Desktop",
        optionen=(("gesicht", "Gesicht"), ("seiten", "Seiten")),
    ),
    Einstellung(
        key="display_augenfarbe",
        titel="Augenfarbe",
        hilfe="Bei Störung werden sie ohnehin orange.",
        art="auswahl",
        vorgabe="hellblau",
        gruppe="Jana Desktop",
        optionen=(("hellblau", "Hellblau"), ("gruen", "Grün"), ("lila", "Lila"), ("rot", "Rot")),
    ),
    Einstellung(
        key="display_blinzeln",
        titel="Blinzeln",
        hilfe="Alle vier bis fünf Sekunden.",
        art="schalter",
        vorgabe="1",
        gruppe="Jana Desktop",
    ),
    Einstellung(
        key="display_umherschauen",
        titel="Umherschauen",
        hilfe="Die Pupillen wandern alle paar Sekunden. Aus heißt: Blick geradeaus.",
        art="schalter",
        vorgabe="1",
        gruppe="Jana Desktop",
    ),
    Einstellung(
        key="display_feierabend_ab",
        titel="Feierabend ab",
        hilfe="Volle Stunde. Ab dann schaut das Gesicht müde und der Satz sagt Feierabend.",
        art="zahl",
        vorgabe="16",
        gruppe="Jana Desktop",
        minimum=12,
        maximum=23,
    ),
    Einstellung(
        key="display_feierabend_bis",
        titel="Feierabend bis",
        hilfe="Volle Stunde am Morgen, ab dann ist es wieder wach.",
        art="zahl",
        vorgabe="7",
        gruppe="Jana Desktop",
        minimum=0,
        maximum=12,
    ),
)

NACH_KEY = {e.key: e for e in EINSTELLUNGEN}


def mit_vorgaben(gespeichert: dict[str, str]) -> dict[str, Any]:
    """Gespeicherte Werte auf die vollstaendige Liste legen.

    Alles, was nicht gesetzt ist, bekommt seine Vorgabe. So muss kein Aufrufer
    mit fehlenden Schluesseln rechnen.
    """
    werte: dict[str, Any] = {}
    for e in EINSTELLUNGEN:
        roh = gespeichert.get(e.key, e.vorgabe)
        geprueft = e.pruefe(roh)
        werte[e.key] = geprueft if geprueft is not None else e.vorgabe
    return werte


def als_zahl(werte: dict[str, Any], key: str) -> int:
    return int(werte.get(key, NACH_KEY[key].vorgabe))


def als_schalter(werte: dict[str, Any], key: str) -> bool:
    return werte.get(key) == "1"


def gruppen() -> list[tuple[str, list[Einstellung]]]:
    """Fuer die Anzeige: Einstellungen nach Gruppe, Reihenfolge wie oben."""
    raus: list[tuple[str, list[Einstellung]]] = []
    for e in EINSTELLUNGEN:
        if not raus or raus[-1][0] != e.gruppe:
            raus.append((e.gruppe, []))
        raus[-1][1].append(e)
    return raus
