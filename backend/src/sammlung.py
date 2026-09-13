"""Die Eigenschaften, mit denen Mia OS startet.

In Notion legt man Spalten selbst an. Damit die Sammlung nicht leer und
ratlos startet, gibt es hier eine sinnvolle Grundausstattung. Mia kann sie
umbenennen, erweitern oder loeschen.
"""

from __future__ import annotations

from typing import Any

# Farbnamen statt Hexwerte: die Oberflaeche entscheidet, wie Blau aussieht,
# und im dunklen Thema anders als im hellen.
VORGABE_PROPS: list[dict[str, Any]] = [
    {
        "key": "status",
        "name": "Status",
        "art": "auswahl",
        "sortierung": 1,
        "optionen": [
            {"wert": "offen", "farbe": "grau"},
            {"wert": "dran", "farbe": "blau"},
            {"wert": "wartet", "farbe": "gelb"},
            {"wert": "fertig", "farbe": "gruen"},
        ],
    },
    {
        "key": "bereich",
        "name": "Bereich",
        "art": "auswahl",
        "sortierung": 2,
        "optionen": [
            {"wert": "Ausbildung", "farbe": "blau"},
            {"wert": "Behörden", "farbe": "rot"},
            {"wert": "Gesundheit", "farbe": "gruen"},
            {"wert": "Homelab", "farbe": "lila"},
            {"wert": "Privat", "farbe": "rosa"},
        ],
    },
    {
        "key": "prio",
        "name": "Priorität",
        "art": "auswahl",
        "sortierung": 3,
        "optionen": [
            {"wert": "hoch", "farbe": "rot"},
            {"wert": "mittel", "farbe": "gelb"},
            {"wert": "niedrig", "farbe": "grau"},
        ],
    },
]


def props_anlegen(store: Any) -> None:
    """Die Grundausstattung anlegen, falls noch keine da ist.

    Nur beim ersten Mal: sonst kaemen Mias eigene Aenderungen bei jedem
    Neustart zurueck auf die Vorgabe.
    """
    if store.list_props():
        return
    for p in VORGABE_PROPS:
        store.set_prop(p["key"], p["name"], p["art"], p["optionen"], p["sortierung"])


# Womit Mia OS startet. Ohne das ist die Seitenleiste leer und ratlos.
STARTSEITEN = [
    {"titel": "Alles", "symbol": "grid", "hat_sammlung": True, "sammelt_alles": True},
    {"titel": "Ausbildung", "symbol": "book", "hat_sammlung": True},
    {"titel": "Behörden", "symbol": "folder", "hat_sammlung": True},
    {"titel": "Notizen", "symbol": "document", "hat_sammlung": False},
]


def startseiten_anlegen(store: Any) -> None:
    """Ein paar Seiten zum Loslegen, nur beim ersten Mal.

    Sonst kaemen geloeschte Seiten bei jedem Neustart zurueck.
    """
    vorhandene = store.list_pages()
    if vorhandene:
        # Bestand von vor der Sammelseite: "Alles" hiess so, sammelte aber
        # nur seine eigenen Eintraege. Einmal umstellen, nicht bei jedem
        # Aufruf, damit Mia die Markierung auch wieder wegnehmen kann.
        if not any(p["sammelt_alles"] for p in vorhandene):
            for p in vorhandene:
                if p["titel"] == "Alles" and p["parent_id"] is None and p["hat_sammlung"]:
                    store.update_page(p["id"], sammelt_alles=True)
                    break
        return
    for s in STARTSEITEN:
        store.create_page(
            s["titel"],
            symbol=s["symbol"],
            hat_sammlung=s["hat_sammlung"],
            sammelt_alles=bool(s.get("sammelt_alles", False)),
        )
