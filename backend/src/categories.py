"""Kategorien-Registry.

Eine Kategorie hinzufuegen heisst: hier einen Eintrag ergaenzen und einen
Collector schreiben. Navigation, Routen und Uebersicht entstehen daraus von
selbst. Das ist die Modularitaet, die Mia gefordert hat.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Field:
    """Ein angezeigter Wert."""

    key: str
    label: str
    # Leitwert: die eine Zahl, die in der Uebersicht steht. Genau einer je Kategorie.
    lead: bool = False
    # Kurzer Kontext direkt darunter.
    caption: bool = False
    # Als Trend darstellen: Pfeil statt Vorzeichen.
    trend: bool = False


@dataclass(frozen=True)
class Category:
    """Ein Lebensbereich mit eigener Seite."""

    key: str
    title: str
    icon: str
    # Kurzsatz auf der Kategorieseite, sagt was hier zu sehen ist.
    subtitle: str = ""
    # False = in Navigation und Uebersicht sichtbar, aber noch ohne Collector.
    live: bool = True
    # Eigene Seite statt der generischen Kategorieansicht. Fuer Bereiche, die
    # mehr sind als eine Liste von Zahlen (Dokumente brauchen eine Suche).
    route: str = ""
    fields: list[Field] = field(default_factory=list)

    @property
    def path(self) -> str:
        return self.route or f"/k/{self.key}"

    @property
    def lead(self) -> Field | None:
        return next((f for f in self.fields if f.lead), None)

    @property
    def caption(self) -> Field | None:
        return next((f for f in self.fields if f.caption), None)

    @property
    def details(self) -> list[Field]:
        return [f for f in self.fields if not f.lead and not f.caption]


CATEGORIES: list[Category] = [
    Category(
        key="termine",
        title="Termine",
        icon="calendar",
        subtitle="Was heute, morgen und diese Woche ansteht",
        route="/termine",
        fields=[
            Field("anzahl_heute", "Heute", lead=True),
            Field("naechster", "", caption=True),
            Field("anzahl_morgen", "Morgen"),
            Field("anzahl_woche", "Diese Woche"),
            Field("kalender_anzahl", "Kalender angebunden"),
        ],
    ),
    Category(
        key="gesundheit",
        title="Gesundheit",
        icon="heart",
        subtitle="Gewicht, Verlauf und Ernährungstagebuch",
        fields=[
            Field("gewicht", "Gewicht", lead=True),
            Field("gewicht_delta", "", caption=True, trend=True),
            Field("gewicht_datum", "Zuletzt gewogen"),
            Field("gewicht_eintraege", "Messungen gesamt"),
            Field("ernaehrung_eintraege", "Einträge im Tagebuch"),
            Field("ernaehrung_zuletzt", "Zuletzt geloggt"),
        ],
    ),
    Category(
        key="dokumente",
        title="Dokumente",
        icon="document",
        subtitle="Alles aus der Cloud und was ich für dich erstellt habe",
        route="/dokumente",
        fields=[
            Field("gesamt", "Dokumente", lead=True),
            Field("ordner_anzahl", "", caption=True),
            Field("nextcloud_anzahl", "Aus Nextcloud"),
            Field("eigene_anzahl", "Von mir erstellt"),
            Field("typen", "Häufigste Formate"),
        ],
    ),
    Category(
        key="homelab",
        title="Homelab",
        icon="server",
        subtitle="Auslastung und Zustand der Maschinen",
        route="/homelab",
        fields=[
            Field("dienste_lage", "Dienste", lead=True),
            Field("uptime_24h", "Verfügbarkeit 24 h"),
            Field("gaeste_laufend", "Gäste laufen"),
            Field("gaeste_gesamt", "Gäste gesamt"),
            Field("pve_ram_prozent", "Arbeitsspeicher"),
            Field("pve_cpu_prozent", "Prozessor"),
            Field("antwortzeit_ms", "Antwortzeit"),
            Field("storage_vollster_prozent", "Vollster Speicher"),
            Field("storage_vollster_name", "Speicher"),
        ],
    ),
]

BY_KEY = {c.key: c for c in CATEGORIES}
LIVE = [c for c in CATEGORIES if c.live]
