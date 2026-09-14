"""Eine Wegwerf-Instanz mit erfundenen Daten, nur zum Ansehen im Simulator.

Warum nicht Mias echte Instanz: die Screenshots gehen ueber Telegram. Echte
Ordnernamen aus ihrer Ablage ("02 Medizinisch") und echte Termine haben dort
nichts verloren. Auch der Homelab-Bildschirm zeigt sonst die echten
Dienstnamen und damit die Struktur des Heimnetzes.

Also: leere Datenbank, ausgedachte Inhalte, leerer Ordner fuer den Schluessel.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ZIEL = Path("/tmp/miaos-demo")
ZIEL.mkdir(exist_ok=True)
DB = ZIEL / "demo.db"
if DB.exists():
    DB.unlink()

os.environ["DB_PATH"] = str(DB)
os.environ["PORT"] = "8099"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.store import Store  # noqa: E402

# Der Konstruktor legt Schema und Migrationen selbst an, ein eigenes init()
# gibt es nicht.
store = Store(str(DB))

heute = date.today()
jetzt = datetime.now(UTC)


def iso(tage: int, stunde: int, minute: int = 0) -> str:
    t = heute + timedelta(days=tage)
    return f"{t.isoformat()}T{stunde:02d}:{minute:02d}:00"


# --- Termine --------------------------------------------------------------
# ``replace_events`` leert nur das angegebene Fenster, deshalb von/bis.
store.replace_events(
    [
        {
            "uid": "demo-1",
            "title": "Berufsschule, LF8",
            "start_at": iso(0, 13, 30),
            "end_at": iso(0, 16, 0),
            "ganztags": 0,
            "location": "Raum 204",
            "calendar": "Ausbildung",
        },
        {
            "uid": "demo-2",
            "title": "Einkaufen mit Leni",
            "start_at": iso(0, 18, 0),
            "end_at": iso(0, 19, 0),
            "ganztags": 0,
            "location": "",
            "calendar": "Privat",
        },
        {
            "uid": "demo-3",
            "title": "Projektarbeit abgeben",
            "start_at": iso(1, 9, 0),
            "end_at": iso(1, 9, 30),
            "ganztags": 0,
            "location": "",
            "calendar": "Ausbildung",
        },
    ],
    von=iso(-7, 0),
    bis=iso(30, 23, 59),
)

# --- Sammlung -------------------------------------------------------------
for titel, status, tage in [
    ("Teileliste fertig machen", "dran", -1),
    ("Handout drucken", "offen", 0),
    ("Pitch ueben", "offen", 2),
    ("Ersatzteile bestellen", "fertig", -3),
]:
    store.create_entry(
        titel=titel,
        eigenschaften={"status": status},
        datum=(heute + timedelta(days=tage)).isoformat(),
    )

# --- Dokumente ------------------------------------------------------------
# Ausgedachte Ordner und Namen. Die Namen sieht man in der App ohnehin nur
# nach getippter Suche, aber im Index stehen duerfen sie trotzdem nicht echt.
dokumente = [
    ("/Demo/01 Papiere", "Musterbescheid.pdf"),
    ("/Demo/01 Papiere", "Beispielantrag.pdf"),
    ("/Demo/01 Papiere", "Vordruck leer.pdf"),
    ("/Demo/02 Schule", "Lernfeld 8 Skript.pdf"),
    ("/Demo/02 Schule", "Uebungsblatt JSON.pdf"),
    ("/Demo/02 Schule", "Uebungsblatt YAML.pdf"),
    ("/Demo/02 Schule", "Stundenplan.pdf"),
    ("/Demo/03 Technik", "Datenblatt Mikrofon.pdf"),
    ("/Demo/03 Technik", "Handbuch Messgeraet.pdf"),
    ("/Demo/04 Belege", "Beleg Beispiel 1.jpg"),
    ("/Demo/04 Belege", "Beleg Beispiel 2.jpg"),
]
store.replace_documents(
    "nextcloud",
    [
        {
            "path": f"{ordner}/{name}",
            "name": name,
            "folder": ordner,
            "ext": "." + name.rsplit(".", 1)[1],
            "size_bytes": 120_000 + i * 4_000,
            "modified_at": (jetzt - timedelta(days=i)).isoformat(),
            "file_id": str(1000 + i),
        }
        for i, (ordner, name) in enumerate(dokumente)
    ],
)

# --- Homelab --------------------------------------------------------------
dienste = [
    ("Beispieldienst A", 1, "200 - OK", 12.0, 99.9, 99.8),
    ("Beispieldienst B", 1, "200 - OK", 8.0, 100.0, 99.9),
    ("Beispieldienst C", 0, "connect ECONNREFUSED", 0.0, 41.2, 88.0),
    ("Beispieldienst D", 1, "200 - OK", 24.0, 99.5, 99.1),
    ("Beispieldienst E", 3, "wartung", 0.0, -1.0, -1.0),
]
store.replace_services(
    [
        {
            "name": n,
            "status": s,
            "msg": m,
            "ping": p,
            "uptime24": u24,
            "uptime30": u30,
        }
        for n, s, m, p, u24, u30 in dienste
    ]
)

print(f"Demo-Datenbank: {DB}")
print(f"  {len(dokumente)} Dokumente, {len(dienste)} Dienste")
