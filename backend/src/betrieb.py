"""Betriebsauskunft: Liveness, Readiness und Metriken.

Warum drei Endpunkte statt einem
--------------------------------

``/health`` beantwortet eine einzige Frage: **laeuft der Prozess noch?**
Wird sie mit Nein beantwortet, ist Neustarten die richtige Antwort. Deshalb
fasst sie nichts an, was ausfallen kann: keine Datenbank, kein Netz. Eine
Liveness-Pruefung, die von der Datenbank abhaengt, startet den Container bei
einer langsamen Abfrage neu und macht das Problem groesser.

``/health/bereit`` beantwortet die andere Frage: **darf Verkehr hierhin?**
Sie darf rot sein, waehrend die Liveness gruen bleibt. Das ist genau der
Unterschied, an dem in echten Systemen die meiste Zeit verloren geht: rot
bei Readiness heisst "kein Verkehr", rot bei Liveness heisst "neu starten".

``/metrics`` liefert Zahlen im Prometheus-Textformat, ohne jede Bibliothek.
Das Format ist ein paar Zeilen Text, und eine Abhaengigkeit fuer etwas
einzuziehen, das in dreissig Zeilen passt, waere schlechter Tausch.

Was hier NICHT hineingehoert
----------------------------

Keine personenbezogenen Werte. Kein Dokumentname, kein Termintitel, keine
Dateipfade aus Mias Ablage, weder im Text noch als Label. Metriken landen in
Zeitreihen, die laenger leben als die Daten selbst, und ein Label ist eine
Speicherung. Gezaehlt wird deshalb, nicht benannt.
"""

from __future__ import annotations

import contextlib
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.store import Store

# Ab wann Sammeldaten als alt gelten.
#
# Der Takt liegt normal bei 60 Minuten. Drei verpasste Laeufe sind ein
# Muster und kein Ausrutscher, deshalb 180. Kuerzer waere Rauschen: eine
# einzelne langsame Quelle wuerde die Bereitschaft rot faerben, obwohl die
# App tadellos bedienbar ist.
DATEN_ALT_NACH_MINUTEN = 180

# Wie lange eine Bereitschaftspruefung dauern darf. Laenger heisst, dass die
# Datenbank haengt, und dann ist die Antwort "nicht bereit" richtiger als
# eine, die irgendwann kommt.
DB_ZEITLIMIT_SEKUNDEN = 5


def _jetzt() -> datetime:
    return datetime.now(UTC)


def _alter_minuten(zeitpunkt: str) -> float | None:
    """Wie viele Minuten seit einem ISO-Zeitpunkt vergangen sind."""
    try:
        gelesen = datetime.fromisoformat(zeitpunkt)
    except (TypeError, ValueError):
        return None
    if gelesen.tzinfo is None:
        gelesen = gelesen.replace(tzinfo=UTC)
    return (_jetzt() - gelesen).total_seconds() / 60


def db_pruefen(store: Store) -> dict[str, Any]:
    """Ist die Datenbank erreichbar und beschreibbar?

    Lesen allein reicht nicht: eine volle Platte laesst sich problemlos
    lesen, und der Ausfall faellt erst auf, wenn Mia etwas eintraegt. Es wird
    deshalb in einer Transaktion geschrieben, die sofort wieder zurueckgerollt
    wird. Der Stand bleibt unveraendert, der Schreibweg ist trotzdem geprueft.
    """
    begonnen = time.monotonic()
    ergebnis: dict[str, Any] = {"ok": False, "schreibbar": False}
    try:
        conn = sqlite3.connect(store.db_path, timeout=DB_ZEITLIMIT_SEKUNDEN)
        try:
            conn.execute("SELECT 1").fetchone()
            ergebnis["ok"] = True
            conn.execute("BEGIN IMMEDIATE")
            conn.rollback()
            ergebnis["schreibbar"] = True
        finally:
            conn.close()
    except Exception as fehler:
        # Jede Ursache heisst hier dasselbe: die Datenbank taugt gerade
        # nicht. Der Typname reicht als Hinweis, die Meldung selbst koennte
        # einen Pfad aus Mias Ablage enthalten und gehoert nicht nach aussen.
        ergebnis["fehler"] = type(fehler).__name__
    ergebnis["dauer_ms"] = int((time.monotonic() - begonnen) * 1000)
    # Eine fehlende Dateigroesse darf die ganze Auskunft nicht verhindern.
    with contextlib.suppress(OSError):
        ergebnis["groesse_mb"] = round(Path(store.db_path).stat().st_size / 1024 / 1024, 1)
    return ergebnis


def sammler_pruefen(store: Store) -> dict[str, Any]:
    """Wie alt sind die gesammelten Daten, und welche Quelle klemmt?

    Nicht konfigurierte Quellen zaehlen nicht als Fehler. Mia hat Moodle
    bewusst nicht eingerichtet, und ein Dashboard, das deswegen dauerhaft rot
    leuchtet, wird nach drei Tagen ignoriert. Genau so sterben Alarme.
    """
    quellen: list[dict[str, Any]] = []
    juengstes: float | None = None
    kaputt = 0

    with contextlib.suppress(Exception):
        for lauf in store.last_runs():
            alter = _alter_minuten(str(lauf.get("ran_at", "")))
            fehler = str(lauf.get("error") or "")
            nicht_eingerichtet = fehler == "nicht konfiguriert"
            ok = bool(lauf.get("ok"))
            if not ok and not nicht_eingerichtet:
                kaputt += 1
            if ok and alter is not None and (juengstes is None or alter < juengstes):
                juengstes = alter
            quellen.append(
                {
                    "name": lauf.get("collector"),
                    "ok": ok,
                    "eingerichtet": not nicht_eingerichtet,
                    "alter_minuten": round(alter) if alter is not None else None,
                    "dauer_ms": lauf.get("duration_ms"),
                }
            )

    veraltet = juengstes is None or juengstes > DATEN_ALT_NACH_MINUTEN
    return {
        "ok": not veraltet,
        "juengster_lauf_minuten": round(juengstes) if juengstes is not None else None,
        "fehlerhafte_quellen": kaputt,
        "quellen": quellen,
    }


def bereitschaft(store: Store, sammelschleife_laeuft: bool) -> dict[str, Any]:
    """Die vollstaendige Bereitschaftsauskunft.

    ``bereit`` haengt an der Datenbank und der Hintergrundschleife, **nicht**
    an alten Sammeldaten. Begruendung: Mia OS ist mit stundenalten Zahlen
    vollstaendig benutzbar, sie kann Termine ansehen, Dokumente suchen und
    Notizen schreiben. Den Verkehr deswegen abzudrehen waere ein Ausfall, den
    man sich selbst gebaut hat. Veraltete Daten stehen trotzdem in der
    Antwort, sichtbar, als Warnung.
    """
    db = db_pruefen(store)
    sammler = sammler_pruefen(store)
    bereit = bool(db["ok"] and db["schreibbar"] and sammelschleife_laeuft)

    warnungen: list[str] = []
    if not sammler["ok"]:
        alter = sammler["juengster_lauf_minuten"]
        warnungen.append(
            "Sammeldaten sind alt" if alter is None else f"Juengste Daten sind {alter} Minuten alt"
        )
    if sammler["fehlerhafte_quellen"]:
        warnungen.append(f"{sammler['fehlerhafte_quellen']} Quelle(n) melden Fehler")

    return {
        "bereit": bereit,
        "zeit": _jetzt().isoformat(),
        "datenbank": db,
        "sammler": sammler,
        "sammelschleife": sammelschleife_laeuft,
        "warnungen": warnungen,
    }


def _zeile(name: str, wert: float | int, hilfe: str, art: str = "gauge") -> str:
    """Eine Metrik mit Kopfzeilen, wie Prometheus sie erwartet."""
    return f"# HELP {name} {hilfe}\n# TYPE {name} {art}\n{name} {wert}\n"


def metriken(store: Store, sammelschleife_laeuft: bool, gestartet: datetime) -> str:
    """Der Inhalt von ``/metrics``.

    Bewusst ohne ``prometheus_client``: das Format sind drei Zeilen je Wert,
    und die Bibliothek braechte eine eigene Registry samt Prozess-Sammler mit.
    Fuer ein Dutzend Zahlen ist das mehr Bewegliches als Nutzen.
    """
    stand = bereitschaft(store, sammelschleife_laeuft)
    db = stand["datenbank"]
    teile = [
        _zeile(
            "mia_os_bereit",
            int(stand["bereit"]),
            "1 wenn der Dienst Verkehr annehmen kann",
        ),
        _zeile(
            "mia_os_laufzeit_sekunden",
            int((_jetzt() - gestartet).total_seconds()),
            "Sekunden seit dem Start des Prozesses",
            "counter",
        ),
        _zeile("mia_os_db_erreichbar", int(db["ok"]), "1 wenn die Datenbank antwortet"),
        _zeile(
            "mia_os_db_schreibbar",
            int(db["schreibbar"]),
            "1 wenn in die Datenbank geschrieben werden kann",
        ),
        _zeile(
            "mia_os_db_abfrage_ms",
            db["dauer_ms"],
            "Dauer der Bereitschaftsabfrage in Millisekunden",
        ),
        _zeile(
            "mia_os_sammler_fehler",
            stand["sammler"]["fehlerhafte_quellen"],
            "Eingerichtete Quellen, deren letzter Lauf fehlschlug",
        ),
    ]
    if db.get("groesse_mb") is not None:
        teile.append(
            _zeile("mia_os_db_groesse_mb", db["groesse_mb"], "Groesse der Datenbankdatei in MB")
        )
    alter = stand["sammler"]["juengster_lauf_minuten"]
    if alter is not None:
        teile.append(
            _zeile(
                "mia_os_daten_alter_minuten",
                alter,
                "Alter des juengsten erfolgreichen Sammellaufs in Minuten",
            )
        )

    # Je Quelle, ob ihr letzter Lauf geklappt hat. Der Name eines Collectors
    # ist ein technischer Bezeichner wie "kuma", kein personenbezogener Wert,
    # und darf deshalb als Label stehen.
    zeilen = [
        f'mia_os_quelle_ok{{quelle="{q["name"]}"}} {int(bool(q["ok"]))}'
        for q in stand["sammler"]["quellen"]
        if q["eingerichtet"]
    ]
    if zeilen:
        teile.append(
            "# HELP mia_os_quelle_ok Letzter Lauf je eingerichteter Quelle\n"
            "# TYPE mia_os_quelle_ok gauge\n" + "\n".join(zeilen) + "\n"
        )

    return "".join(teile)
