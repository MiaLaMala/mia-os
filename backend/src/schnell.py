"""Die Schnelleingabe verstehen.

Ein Feld, ein Satz. Hier wird entschieden, was der Satz ist: ein Eintrag mit
Datum, ein Gewicht, eine Mahlzeit. Bewusst ohne Sprachmodell: die Muster
sind wenige, und sie muessen jedes Mal gleich reagieren.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

WOCHENTAGE = {
    "montag": 0, "mo": 0,
    "dienstag": 1, "di": 1,
    "mittwoch": 2, "mi": 2,
    "donnerstag": 3, "do": 3,
    "freitag": 4, "fr": 4,
    "samstag": 5, "sa": 5,
    "sonntag": 6, "so": 6,
}  # fmt: skip

RELATIV = {"heute": 0, "morgen": 1, "übermorgen": 2, "uebermorgen": 2}

_GEWICHT = re.compile(r"^\s*(\d{2,3}(?:[.,]\d{1,2})?)\s*(?:kg|kilo)\s*$", re.I)
_ESSEN = re.compile(r"^\s*(.+?)\s+(\d{1,4}(?:[.,]\d)?)\s*(?:g|gr|gramm)\s*$", re.I)
_ESSEN_VORN = re.compile(r"^\s*(\d{1,4}(?:[.,]\d)?)\s*(?:g|gr|gramm)\s+(.+?)\s*$", re.I)
_ZEIT = re.compile(
    r"\b(?:um\s+)?(\d{1,2})(?::(\d{2}))?\s*uhr\b|\b(?:um\s+)(\d{1,2}):(\d{2})\b", re.I
)
_DATUM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.?(?:(\d{4}))?\b")


@dataclass
class Deutung:
    art: str  # eintrag | gewicht | essen
    titel: str = ""
    datum: str | None = None
    zeit: str | None = None
    zahl: float | None = None


def deute(text: str, heute: date | None = None) -> Deutung:
    heute = heute or date.today()
    text = text.strip()

    if m := _GEWICHT.match(text):
        return Deutung("gewicht", zahl=float(m.group(1).replace(",", ".")))

    if m := _ESSEN.match(text):
        return Deutung("essen", titel=m.group(1).strip(), zahl=float(m.group(2).replace(",", ".")))
    if m := _ESSEN_VORN.match(text):
        return Deutung("essen", titel=m.group(2).strip(), zahl=float(m.group(1).replace(",", ".")))

    rest = text
    datum: str | None = None
    zeit: str | None = None

    if m := _ZEIT.search(rest):
        stunde = m.group(1) or m.group(3)
        minute = m.group(2) or m.group(4) or "00"
        if stunde and 0 <= int(stunde) < 24 and 0 <= int(minute) < 60:
            zeit = f"{int(stunde):02d}:{minute}"
            rest = (rest[: m.start()] + rest[m.end() :]).strip()

    if m := _DATUM.search(rest):
        tag, monat = int(m.group(1)), int(m.group(2))
        jahr = int(m.group(3)) if m.group(3) else heute.year
        try:
            d = date(jahr, monat, tag)
            # Ohne Jahr und schon vorbei: gemeint ist naechstes Jahr.
            if not m.group(3) and d < heute - timedelta(days=1):
                d = date(jahr + 1, monat, tag)
            datum = d.isoformat()
            rest = (rest[: m.start()] + rest[m.end() :]).strip()
        except ValueError:
            pass

    if datum is None:
        woerter = rest.split()
        for i in range(len(woerter) - 1, -1, -1):
            w = woerter[i].lower().strip(",.")
            if w in RELATIV:
                datum = (heute + timedelta(days=RELATIV[w])).isoformat()
            elif w in WOCHENTAGE:
                # "Freitag" heisst der naechste Freitag, heute eingeschlossen.
                delta = (WOCHENTAGE[w] - heute.weekday()) % 7
                datum = (heute + timedelta(days=delta)).isoformat()
            elif w in ("am", "bis") and i == len(woerter) - 1:
                pass
            else:
                continue
            del woerter[i]
            # Ein haengendes "am" oder "bis" davor mitnehmen.
            if i > 0 and woerter[i - 1].lower() in ("am", "bis"):
                del woerter[i - 1]
            rest = " ".join(woerter)
            break

    titel = rest.strip(" ,.:;") or text
    return Deutung("eintrag", titel=titel, datum=datum, zeit=zeit)
