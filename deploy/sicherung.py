#!/usr/bin/env python3
"""Sicherung der Mia-OS-Datenbank, mit anschliessender Rueckspiel-Probe.

Der Punkt des Ganzen steht im zweiten Teil: eine Sicherung, die nie
zurueckgespielt wurde, ist keine Sicherung, sondern eine Datei. Deshalb
macht dieses Skript beides in einem Lauf und meldet erst dann Erfolg, wenn
die Kopie nachweislich wieder aufgeht.

Warum ``sqlite3.Connection.backup`` und nicht ``cp``:
    Die Datenbank wird waehrend der Sicherung beschrieben (Collector-Lauf,
    ein Klick von Mia). Ein ``cp`` erwischt dann eine Datei mitten in einer
    Transaktion, und der Schaden faellt erst auf, wenn man sie braucht. Die
    Backup-API von SQLite nimmt die noetigen Sperren selbst und liefert
    einen in sich stimmigen Stand, ohne den Dienst anzuhalten.

Warum kein ``sqlite3``-Kommandozeilenwerkzeug:
    Auf dem LXC ist es nicht installiert, das Python-Modul dagegen schon.
    Ein Paket nachzuinstallieren waere mehr Angriffsflaeche fuer nichts.

Aufruf:
    python3 sicherung.py                      # sichern und pruefen
    python3 sicherung.py --nur-pruefen DATEI  # eine vorhandene Sicherung pruefen

Rueckgabewert 0 heisst: Sicherung liegt da UND sie laesst sich oeffnen.
Alles andere heisst, dass niemand sich auf diese Sicherung verlassen darf.
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Vorgaben passen zum LXC 141. Beide lassen sich per Argument ueberschreiben,
# damit dasselbe Skript auch lokal gegen eine Kopie laufen kann.
QUELLE = Path("/var/lib/docker/volumes/mia-os_mia-os-data/_data/mia-os.db")
ZIEL = Path("/var/backups/mia-os")

# Wie viele Sicherungen liegen bleiben. Die Datenbank ist wenige Megabyte
# gross, 14 Staende kosten also kaum Platz, decken aber zwei Wochen ab: lang
# genug, um einen Fehler zu bemerken, der sich langsam einschleicht.
BEHALTEN = 14

# Tabellen, ohne die Mia OS nicht arbeiten kann. Fehlt eine davon in der
# zurueckgespielten Kopie, ist die Sicherung unbrauchbar, auch wenn die
# Datei sich oeffnen laesst.
PFLICHTTABELLEN = {"metrics", "collector_runs", "events", "entries"}


def _menschlich(bytes_: int) -> str:
    """Byte-Zahlen so, dass man sie im Vorbeigehen liest."""
    if bytes_ < 1024 * 1024:
        return f"{bytes_ / 1024:.0f} KB"
    return f"{bytes_ / 1024 / 1024:.1f} MB"


def sichern(quelle: Path, ziel_ordner: Path) -> Path:
    """Einen stimmigen Stand der Datenbank ablegen, gzip-gepackt.

    Erst wird in eine unkomprimierte Zwischendatei gesichert, dann gepackt.
    Der Umweg ist noetig, weil die Backup-API in eine echte SQLite-Datei
    schreibt und nicht in einen Datenstrom.
    """
    if not quelle.exists():
        raise FileNotFoundError(f"Datenbank nicht gefunden: {quelle}")

    ziel_ordner.mkdir(parents=True, exist_ok=True)
    stempel = datetime.now().strftime("%Y-%m-%d_%H%M")
    ziel = ziel_ordner / f"mia-os_{stempel}.db.gz"

    with tempfile.TemporaryDirectory() as tmp:
        roh = Path(tmp) / "kopie.db"
        # ``uri=True`` mit ``mode=ro``: die Quelle wird nur gelesen. Selbst
        # ein Fehler in diesem Skript kann die laufende Datenbank dann nicht
        # veraendern.
        with (
            sqlite3.connect(f"file:{quelle}?mode=ro", uri=True) as auf,
            sqlite3.connect(roh) as ab,
        ):
            auf.backup(ab)
        with roh.open("rb") as ein, gzip.open(ziel, "wb", compresslevel=6) as aus:
            shutil.copyfileobj(ein, aus)

    return ziel


def pruefen(sicherung: Path) -> dict[str, int]:
    """Die Sicherung in eine Wegwerf-Datenbank zurueckspielen und nachzaehlen.

    Bewusst in einem eigenen Verzeichnis, das danach verschwindet: es soll
    kein Weg existieren, auf dem diese Probe versehentlich die echte
    Datenbank beruehrt.
    """
    with tempfile.TemporaryDirectory() as tmp:
        wieder = Path(tmp) / "wegwerf.db"
        with gzip.open(sicherung, "rb") as ein, wieder.open("wb") as aus:
            shutil.copyfileobj(ein, aus)

        with sqlite3.connect(wieder) as db:
            # SQLites eigene Pruefung zuerst. Sie liest jede Seite und meldet
            # kaputte Indizes und abgeschnittene Dateien, die ein blosses
            # "laesst sich oeffnen" durchwinken wuerde.
            ergebnis = db.execute("PRAGMA integrity_check").fetchone()[0]
            if ergebnis != "ok":
                raise ValueError(f"integrity_check meldet: {ergebnis}")

            tabellen = [
                z[0]
                for z in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            fehlend = PFLICHTTABELLEN - set(tabellen)
            if fehlend:
                raise ValueError(f"Pflichttabellen fehlen: {', '.join(sorted(fehlend))}")

            zeilen = {}
            for name in tabellen:
                # Tabellennamen kommen aus sqlite_master, also aus der Datei
                # selbst, und lassen sich nicht als Parameter binden. Der
                # Name wird deshalb in Anfuehrungszeichen gesetzt.
                zeilen[name] = db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]

    return zeilen


def aufraeumen(ziel_ordner: Path, behalten: int) -> list[Path]:
    """Alte Staende loeschen, den neuesten nie.

    Sortiert ueber den Dateinamen, nicht ueber die Aenderungszeit: ein
    Kopiervorgang setzt die Zeit neu, der Zeitstempel im Namen bleibt.
    """
    alle = sorted(ziel_ordner.glob("mia-os_*.db.gz"))
    zuviel = alle[:-behalten] if len(alle) > behalten else []
    for datei in zuviel:
        datei.unlink()
    return zuviel


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--quelle", type=Path, default=QUELLE)
    p.add_argument("--ziel", type=Path, default=ZIEL)
    p.add_argument("--behalten", type=int, default=BEHALTEN)
    p.add_argument(
        "--nur-pruefen",
        type=Path,
        help="Eine vorhandene Sicherung pruefen, ohne eine neue anzulegen.",
    )
    args = p.parse_args()

    try:
        if args.nur_pruefen:
            datei = args.nur_pruefen
            print(f"Pruefe vorhandene Sicherung: {datei}")
        else:
            datei = sichern(args.quelle, args.ziel)
            print(f"Gesichert: {datei} ({_menschlich(datei.stat().st_size)})")

        zeilen = pruefen(datei)
    except Exception as fehler:  # noqa: BLE001 - hier ist jede Ursache gleich schlimm
        print(f"FEHLGESCHLAGEN: {fehler}", file=sys.stderr)
        return 1

    gesamt = sum(zeilen.values())
    print(f"Rueckspiel-Probe bestanden: {len(zeilen)} Tabellen, {gesamt} Zeilen")
    for name, anzahl in sorted(zeilen.items(), key=lambda z: -z[1]):
        print(f"  {name:<24} {anzahl:>8}")

    if not args.nur_pruefen:
        geloescht = aufraeumen(args.ziel, args.behalten)
        if geloescht:
            print(f"Alte Staende entfernt: {len(geloescht)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
