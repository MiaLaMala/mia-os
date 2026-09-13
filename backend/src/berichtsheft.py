"""Berichtsheft: aus den Kalendern einen Wochenentwurf bauen.

Der Ausbildungsnachweis ist Pflicht, und er ist genau die Sorte Arbeit, die
liegen bleibt: jede Woche dasselbe abtippen, was ohnehin im Kalender steht.
Mia OS kennt die sieben Kalender, also baut es den Entwurf und Mia korrigiert
ihn nur noch.

Was hier **nicht** passiert: Taetigkeiten erfinden. Der Kalender sagt
"Arbeit 09:00 bis 11:30", nicht was in der Zeit passiert ist. Der Entwurf
liefert deshalb Tage, Stunden und Anhaltspunkte aus der Sammlung, die
Themenzeilen bleiben leer, bis Mia sie fuellt. Ein erfundener Eintrag im
Berichtsheft waere schlimmer als ein leerer.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")

# Kalender, die zur Ausbildung gehoeren, und wohin sie zaehlen.
SCHULE_KALENDER = {"berufsschule"}
BETRIEB_KALENDER = {"arbeit", "berufsbildungswerk hamburg"}

# Was im Kalender steht, aber keine Ausbildungszeit ist. Pausen sind laut
# Arbeitszeitgesetz unbezahlt und gehoeren nicht in die Stundensumme, der Weg
# zur Arbeit ebenfalls nicht.
KEINE_ARBEITSZEIT = re.compile(
    r"pause|fr[uü]hst[uü]ck|mittagessen|heimweg|anfahrt|hinweg|r[uü]ckweg|feierabend",
    re.IGNORECASE,
)

# Ganztaegige Marker, die den ganzen Tag umwidmen.
#
# Bewusst eng gefasst. "AU abgeben" ist eine Aufgabe und kein Fehltag: das
# Muster hat den Montag der KW 37 auf null Stunden gesetzt, obwohl Mia
# gearbeitet hat. Ein zu eifriges Muster faelscht den Nachweis, also lieber
# einen Fehltag uebersehen als einen erfinden.
ABWESENHEIT = (
    ("krank", re.compile(r"\bkrank\b|krankgemeldet|krankmeldung|arbeitsunf[aä]hig", re.IGNORECASE)),
    ("urlaub", re.compile(r"\burlaub\b|frei genommen", re.IGNORECASE)),
    ("feiertag", re.compile(r"feiertag", re.IGNORECASE)),
)

# Ganztagseintraege aus der Sammlung sind Mias eigene Aufgaben, keine
# Kalendermarker. Sie taugen als Anhaltspunkt, nie als Fehltag.
KEIN_KALENDER = {"sammlung", ""}


@dataclass
class Block:
    """Ein Zeitblock an einem Tag, so wie er im Kalender steht."""

    von: str
    bis: str
    titel: str
    kalender: str
    stunden: float


@dataclass
class Tag:
    """Ein Tag im Berichtsheft."""

    datum: str
    wochentag: str
    # betrieb | schule | krank | urlaub | feiertag | frei
    art: str = "frei"
    stunden: float = 0.0
    schule_stunden: float = 0.0
    betrieb_stunden: float = 0.0
    # Was Mia eintraegt. Der Entwurf laesst das leer, ausser es gibt Belege.
    taetigkeiten: list[str] = field(default_factory=list)
    # Woher die Vorschlaege kommen, damit Mia sie einordnen kann.
    hinweise: list[str] = field(default_factory=list)
    bloecke: list[Block] = field(default_factory=list)


@dataclass
class Woche:
    """Ein Wochenblatt."""

    montag: str
    sonntag: str
    kw: int
    jahr: int
    tage: list[Tag] = field(default_factory=list)
    betrieb_stunden: float = 0.0
    schule_stunden: float = 0.0
    stunden: float = 0.0
    # entwurf | bearbeitet | fertig
    status: str = "entwurf"
    # Freitext, den Mia zusaetzlich schreibt.
    bemerkung: str = ""
    themen_schule: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def wochenanfang(tag: date) -> date:
    """Der Montag der Woche, in der ``tag`` liegt."""
    return tag - timedelta(days=tag.weekday())


def _stunden(von: str, bis: str) -> float:
    """Dauer in Stunden, auf eine Viertelstunde gerundet."""
    if not von or not bis:
        return 0.0
    try:
        a = datetime.fromisoformat(von)
        b = datetime.fromisoformat(bis)
    except ValueError:
        return 0.0
    minuten = (b - a).total_seconds() / 60
    if minuten <= 0:
        return 0.0
    return round(round(minuten / 15) * 15 / 60, 2)


def _art(kalender: str, titel: str) -> str:
    """Zaehlt der Block zur Schule, zum Betrieb oder zu gar nichts?"""
    k = (kalender or "").strip().lower()
    if KEINE_ARBEITSZEIT.search(titel or ""):
        return ""
    if k in SCHULE_KALENDER:
        return "schule"
    if k in BETRIEB_KALENDER:
        return "betrieb"
    # "Betrieb (Nachmittag)" liegt im Kalender Arbeit, faengt der obere Zweig.
    # Alles andere (Privat, Lernort-Wohnen) ist keine Ausbildungszeit.
    return ""


def entwurf(
    montag: date,
    termine: list[dict[str, Any]],
    eintraege: list[dict[str, Any]] | None = None,
) -> Woche:
    """Aus Terminen einer Woche das Wochenblatt bauen.

    ``termine`` sind die Zeilen aus ``store.events``: ``start_at``, ``end_at``,
    ``title``, ``calendar``, ``ganztags``.
    ``eintraege`` sind Sammlungseintraege mit ``datum`` und ``titel``; sie
    liefern Anhaltspunkte, keine fertigen Saetze.
    """
    montag = wochenanfang(montag)
    sonntag = montag + timedelta(days=6)
    iso = montag.isocalendar()

    tage = {
        (montag + timedelta(days=i)).isoformat(): Tag(
            datum=(montag + timedelta(days=i)).isoformat(),
            wochentag=WOCHENTAGE[i],
        )
        for i in range(7)
    }

    for t in termine:
        start = str(t.get("start_at") or "")
        tag = tage.get(start[:10])
        if tag is None:
            continue
        titel = str(t.get("title") or "").strip()
        kalender = str(t.get("calendar") or "")

        if t.get("ganztags"):
            if kalender.strip().lower() in KEIN_KALENDER:
                if titel:
                    tag.hinweise.append(titel)
                continue
            for art, muster in ABWESENHEIT:
                if muster.search(titel):
                    tag.art = art
                    tag.hinweise.append(titel)
                    break
            else:
                if titel:
                    tag.hinweise.append(titel)
            continue

        art = _art(kalender, titel)
        if not art:
            continue
        h = _stunden(start, str(t.get("end_at") or ""))
        tag.bloecke.append(
            Block(
                von=start[11:16],
                bis=str(t.get("end_at") or "")[11:16],
                titel=titel,
                kalender=kalender,
                stunden=h,
            )
        )
        if art == "schule":
            tag.schule_stunden = round(tag.schule_stunden + h, 2)
        else:
            tag.betrieb_stunden = round(tag.betrieb_stunden + h, 2)

    for e in eintraege or []:
        tag = tage.get(str(e.get("datum") or "")[:10])
        if tag is None:
            continue
        titel = str(e.get("titel") or "").strip()
        if titel:
            tag.hinweise.append(titel)

    for tag in tage.values():
        tag.stunden = round(tag.schule_stunden + tag.betrieb_stunden, 2)
        if tag.art in ("krank", "urlaub", "feiertag"):
            # Ein Krankheitstag hat keine Stunden, auch wenn der Kalender die
            # Regeltermine weiter zeigt. Sonst stimmt die Summe nicht.
            tag.stunden = tag.schule_stunden = tag.betrieb_stunden = 0.0
            tag.bloecke = []
            continue
        if tag.stunden == 0:
            tag.art = "frei"
        elif tag.schule_stunden and tag.betrieb_stunden:
            tag.art = "schule+betrieb"
        elif tag.schule_stunden:
            tag.art = "schule"
        else:
            tag.art = "betrieb"

    liste = [tage[(montag + timedelta(days=i)).isoformat()] for i in range(7)]
    woche = Woche(
        montag=montag.isoformat(),
        sonntag=sonntag.isoformat(),
        kw=iso.week,
        jahr=iso.year,
        tage=liste,
    )
    woche.betrieb_stunden = round(sum(t.betrieb_stunden for t in liste), 2)
    woche.schule_stunden = round(sum(t.schule_stunden for t in liste), 2)
    woche.stunden = round(woche.betrieb_stunden + woche.schule_stunden, 2)
    return woche


def zusammenfuehren(entwurf_woche: Woche, gespeichert: dict[str, Any] | None) -> Woche:
    """Gespeicherte Korrekturen ueber den frischen Entwurf legen.

    Der Kalender bleibt die Quelle fuer Tage und Stunden, Mias Text gewinnt
    ueber den Vorschlag. So aendert ein nachtraeglich eingetragener Termin die
    Stundensumme, ohne ihre Saetze zu ueberschreiben.
    """
    if not gespeichert:
        return entwurf_woche
    woche = entwurf_woche
    woche.status = str(gespeichert.get("status") or "entwurf")
    woche.bemerkung = str(gespeichert.get("bemerkung") or "")
    woche.themen_schule = str(gespeichert.get("themen_schule") or "")
    inhalt = gespeichert.get("inhalt") or {}
    for tag in woche.tage:
        eigene = inhalt.get(tag.datum)
        if not eigene:
            continue
        zeilen = eigene.get("taetigkeiten")
        if isinstance(zeilen, list):
            tag.taetigkeiten = [str(z) for z in zeilen if str(z).strip()]
        art = eigene.get("art")
        if isinstance(art, str) and art:
            tag.art = art
        stunden = eigene.get("stunden")
        if isinstance(stunden, int | float):
            # Mia korrigiert die Stunden von Hand: dann gilt ihre Zahl.
            tag.stunden = float(stunden)
    woche.stunden = round(sum(t.stunden for t in woche.tage), 2)
    return woche
