"""Termine aus dem iCloud-CalDAV.

Speichert die Termine selbst, nicht nur Zaehlwerte: eine Terminseite braucht
Uhrzeit, Ort und Kalender. Bewusst **nicht** gespeichert werden Beschreibung
und Teilnehmer, das ist Inhalt fremder Leute.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
from typing import Any

import caldav

from src.collectors.base import Collector
from src.config import settings

# Wie weit gelesen wird. Rueckwaerts, damit man im Kalenderblatt auch
# zurueckblaettern kann, vorwaerts fuer die Planung.
TAGE_ZURUECK = 45
TAGE_VORAUS = 120


class CalendarCollector(Collector):
    name = "termine"
    category = "termine"

    def is_configured(self) -> bool:
        return bool(settings.caldav_url and settings.caldav_user and settings.caldav_password)

    async def collect(self) -> None:
        # caldav ist synchron: in einen Thread auslagern, damit der Server nicht blockiert.
        await asyncio.to_thread(self._collect_sync)

    def _collect_sync(self) -> None:
        client = caldav.DAVClient(  # type: ignore[operator]
            url=settings.caldav_url,
            username=settings.caldav_user,
            password=settings.caldav_password,
        )
        principal = client.principal()
        calendars = principal.calendars()

        heute = date.today()
        start = datetime.combine(heute - timedelta(days=TAGE_ZURUECK), time.min)
        ende = datetime.combine(heute + timedelta(days=TAGE_VORAUS), time.max)

        termine: list[dict[str, Any]] = []
        for cal in calendars:
            name = _kalendername(cal)
            try:
                gefunden = cal.search(start=start, end=ende, event=True, expand=True)
            except Exception:
                # Ein hakender Kalender darf die anderen nicht mitreissen.
                continue
            for ev in gefunden:
                eintrag = _als_termin(ev, name)
                if eintrag:
                    termine.append(eintrag)

        termine.sort(key=lambda t: t["start_at"])
        self.store.replace_events(termine, start.isoformat(), ende.isoformat())

        # Kennzahlen fuer die Uebersichtskachel.
        morgen = heute + timedelta(days=1)
        heute_liste = [t for t in termine if t["start_at"][:10] == heute.isoformat()]
        morgen_liste = [t for t in termine if t["start_at"][:10] == morgen.isoformat()]
        woche = [
            t for t in termine if t["start_at"][:10] <= (heute + timedelta(days=7)).isoformat()
        ]

        self.store.record(self.category, "anzahl_heute", float(len(heute_liste)))
        self.store.record(self.category, "anzahl_morgen", float(len(morgen_liste)))
        self.store.record(self.category, "anzahl_woche", float(len(woche)))
        self.store.record(self.category, "kalender_anzahl", float(len(calendars)))

        # Der naechste Termin ist die eigentliche Aussage, nicht die Anzahl.
        jetzt = datetime.now().isoformat()
        naechster = next((t for t in termine if t["start_at"] >= jetzt), None)
        if naechster:
            self.store.record(self.category, "naechster", text_value=_kurzfassung(naechster, heute))

        for label, liste in (("heute", heute_liste), ("morgen", morgen_liste)):
            self.store.record(
                self.category,
                f"liste_{label}",
                text_value=" | ".join(t["title"] for t in liste[:6]),
            )


def _kalendername(cal: Any) -> str:
    """Anzeigename, ohne an der veralteten ``name``-Eigenschaft zu haengen."""
    for zugriff in ("get_display_name", "name"):
        try:
            wert = getattr(cal, zugriff)
            return str(wert() if callable(wert) else wert).strip()
        except Exception:
            continue
    return ""


def _als_termin(event: Any, kalender: str) -> dict[str, Any] | None:
    """Ein VEVENT in die Form bringen, die die Anzeige braucht."""
    try:
        comp = event.icalendar_component
    except Exception:
        return None

    titel = str(comp.get("summary", "")).strip()
    if not titel:
        return None

    beginn = getattr(comp.get("dtstart"), "dt", None)
    if beginn is None:
        return None

    # Ganztaegige Termine kommen als date, nicht als datetime.
    ganztags = not isinstance(beginn, datetime)
    if ganztags:
        beginn = datetime.combine(beginn, time.min)
    elif beginn.tzinfo is not None:
        # Auf lokale Zeit bringen und die Zonenangabe abstreifen: sonst
        # vergleicht sich der Text nicht mehr mit dem Tagesdatum.
        beginn = beginn.astimezone().replace(tzinfo=None)

    schluss = getattr(comp.get("dtend"), "dt", None)
    if schluss is not None:
        if not isinstance(schluss, datetime):
            schluss = datetime.combine(schluss, time.min)
        elif schluss.tzinfo is not None:
            schluss = schluss.astimezone().replace(tzinfo=None)

    return {
        "uid": str(comp.get("uid", "")) or f"{kalender}:{titel}:{beginn.isoformat()}",
        "start_at": beginn.isoformat(),
        "end_at": schluss.isoformat() if schluss else "",
        "title": titel,
        "location": str(comp.get("location", "")).strip()[:120],
        "calendar": kalender,
        "ganztags": ganztags,
    }


def _kurzfassung(termin: dict[str, Any], heute: date) -> str:
    """Der naechste Termin in einem Satz, so wie man ihn sagen wuerde."""
    beginn = datetime.fromisoformat(termin["start_at"])
    tag = beginn.date()

    if termin["ganztags"]:
        wann = "heute" if tag == heute else _tagwort(tag, heute)
        return f"{termin['title']}, {wann}"

    uhr = beginn.strftime("%H:%M")
    if tag == heute:
        return f"{termin['title']}, {uhr}"
    return f"{termin['title']}, {_tagwort(tag, heute)} {uhr}"


WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def _tagwort(tag: date, heute: date) -> str:
    """'morgen' statt 'Montag', wenn es morgen ist. So spricht man."""
    abstand = (tag - heute).days
    if abstand == 0:
        return "heute"
    if abstand == 1:
        return "morgen"
    if abstand < 7:
        return WOCHENTAGE[tag.weekday()]
    return tag.strftime("%d.%m.")
