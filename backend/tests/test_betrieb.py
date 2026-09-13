"""Betriebsauskunft: Liveness, Readiness, Metriken.

Der Punkt dieser Tests ist nicht, dass die Endpunkte antworten. Es ist, dass
sie **unterschiedlich** antworten: eine Readiness, die immer gruen ist, ist
dasselbe wie keine.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src import betrieb
from src.store import Store


def test_liveness_bleibt_schlicht(client: TestClient) -> None:
    """``/health`` darf nichts anfassen, was ausfallen kann.

    Geprueft ueber die Groesse: sobald jemand dort Datenbankzahlen
    hineinlegt, waechst die Antwort, und damit waere die Liveness von der
    Datenbank abhaengig. Genau das soll sie nie sein.
    """
    antwort = client.get("/health")
    assert antwort.status_code == 200
    assert antwort.json()["status"] == "ok"
    assert len(antwort.content) < 120


def test_bereitschaft_ist_gruen_wenn_alles_steht(client: TestClient) -> None:
    antwort = client.get("/health/bereit")
    assert antwort.status_code == 200
    daten = antwort.json()
    assert daten["bereit"] is True
    assert daten["datenbank"]["ok"] is True
    assert daten["datenbank"]["schreibbar"] is True
    assert daten["sammelschleife"] is True


def test_bereitschaft_wird_rot_ohne_sammelschleife(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Stirbt die Hintergrundschleife still, muss das nach aussen sichtbar sein.

    Das ist der Ausfall, den man ohne Readiness nie bemerkt: der Dienst
    antwortet weiter, die Zahlen altern, und irgendwann faellt jemandem auf,
    dass der Kalender seit Tagen derselbe ist.
    """
    import src.main as m

    monkeypatch.setattr(m, "sammelschleife_laeuft", lambda: False)
    antwort = client.get("/health/bereit")
    assert antwort.status_code == 503
    assert antwort.json()["bereit"] is False


def test_bereitschaft_wird_rot_ohne_datenbank(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import src.main as m

    def kaputt(store: Store) -> dict[str, object]:
        return {"ok": False, "schreibbar": False, "dauer_ms": 0, "fehler": "OperationalError"}

    monkeypatch.setattr(m.betrieb, "db_pruefen", kaputt)
    antwort = client.get("/health/bereit")
    assert antwort.status_code == 503
    assert antwort.json()["datenbank"]["fehler"] == "OperationalError"


def test_alte_daten_faerben_nicht_rot_aber_warnen(store: Store) -> None:
    """Stundenalte Zahlen sind kein Grund, den Verkehr abzudrehen.

    Mia kann mit alten Werten Termine ansehen, suchen und schreiben. Ein
    503 waere ein selbstgebauter Ausfall. Sichtbar muss es trotzdem sein,
    deshalb steht es als Warnung in der Antwort.
    """
    store.record_run("kuma", True, None, 12)
    with store._conn() as conn:
        alt = (datetime.now(UTC) - timedelta(hours=9)).isoformat()
        conn.execute("UPDATE collector_runs SET ran_at = ?", (alt,))

    stand = betrieb.bereitschaft(store, sammelschleife_laeuft=True)
    assert stand["bereit"] is True
    assert stand["sammler"]["ok"] is False
    assert stand["warnungen"]


def test_nicht_eingerichtete_quelle_ist_kein_fehler(store: Store) -> None:
    """Moodle ist bewusst nicht eingerichtet. Das darf nichts rot faerben.

    Ein Monitor, der dauerhaft rot leuchtet, wird nach drei Tagen ignoriert.
    Dann ist er schlechter als keiner.
    """
    store.record_run("moodle", False, "nicht konfiguriert", 0)
    store.record_run("kalender", True, None, 30)

    stand = betrieb.bereitschaft(store, sammelschleife_laeuft=True)
    assert stand["sammler"]["fehlerhafte_quellen"] == 0
    namen = {q["name"]: q for q in stand["sammler"]["quellen"]}
    assert namen["moodle"]["eingerichtet"] is False
    assert namen["kalender"]["eingerichtet"] is True


def test_echter_quellenfehler_wird_gezaehlt(store: Store) -> None:
    store.record_run("kuma", False, "TimeoutError: ssh", 8000)
    stand = betrieb.bereitschaft(store, sammelschleife_laeuft=True)
    assert stand["sammler"]["fehlerhafte_quellen"] == 1


def test_metriken_tragen_keine_persoenlichen_label(client: TestClient) -> None:
    """Der Fehler, den man in echten Systemen dauernd sieht.

    Ein Dokumentname als Label landet in einer Zeitreihe, die laenger lebt
    als das Dokument. Hier stehen nur Collector-Namen, und die sind
    technische Bezeichner.
    """
    import src.main as m

    store = m.get_store()
    store.record_run("dokumente", True, None, 40)
    store.create_entry(titel="Arztbericht Endokrinologie", datum="2026-09-14")

    text = client.get("/metrics").text
    assert "Arztbericht" not in text
    assert "Endokrinologie" not in text
    # Ein Label gibt es, und zwar genau eines, mit technischen Namen.
    for zeile in text.splitlines():
        if zeile.startswith("#") or "{" not in zeile:
            continue
        assert zeile.startswith("mia_os_quelle_ok{quelle=")


def test_metriken_haben_das_prometheus_format(client: TestClient) -> None:
    antwort = client.get("/metrics")
    assert antwort.status_code == 200
    assert antwort.headers["content-type"].startswith("text/plain")
    text = antwort.text
    for name in ("mia_os_bereit", "mia_os_laufzeit_sekunden", "mia_os_db_erreichbar"):
        assert f"# HELP {name} " in text
        assert f"# TYPE {name} " in text
        # Jede Metrik braucht eine Wertzeile, nicht nur Kopfzeilen.
        assert any(
            z.startswith(f"{name} ") and z.split(" ")[1].replace(".", "", 1).isdigit()
            for z in text.splitlines()
        ), f"{name} hat keinen Wert"


def test_betriebsendpunkte_sind_nicht_offen(fremder: TestClient) -> None:
    """Von aussen gibt es keine Landkarte des Systems.

    ``/health`` bleibt offen, weil Uptime Kuma es braucht und es nur "ok"
    sagt. Alles Weitere verlangt dieselbe Kopplung wie die Schnittstelle.
    """
    assert fremder.get("/health").status_code == 200
    assert fremder.get("/health/bereit").status_code == 401
    assert fremder.get("/metrics").status_code == 401


@pytest.mark.parametrize("pfad", ["/health/bereit", "/metrics"])
def test_betriebsendpunkte_antworten_auch_leer(client: TestClient, pfad: str) -> None:
    """Frisch aufgesetzt, ohne einen einzigen Sammellauf.

    Der Zustand, in dem eine Gesundheitsauskunft am ehesten in eine Ausnahme
    laeuft: es gibt noch nichts zu berichten.
    """
    antwort = client.get(pfad)
    assert antwort.status_code in (200, 503)
    assert antwort.content
