"""Die JSON-Schnittstelle fuer das Svelte-Frontend."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient


def _ev(titel: str, beginn: datetime, **rest: Any) -> dict[str, Any]:
    ende = rest.get("ende", beginn + timedelta(hours=1))
    return {
        "uid": f"uid-{titel}",
        "calendar": rest.get("kalender", "Privat"),
        "title": titel,
        "start_at": beginn.isoformat(),
        "end_at": ende.isoformat() if ende else "",
        "ganztags": int(rest.get("ganztags", False)),
        "location": rest.get("ort", ""),
    }


# --- Übersicht ------------------------------------------------------------


def test_uebersicht_liefert_alle_kacheln(client: TestClient) -> None:
    daten = client.get("/api/uebersicht").json()
    schluessel = [k["key"] for k in daten["kacheln"]]
    assert schluessel == ["termine", "gesundheit", "dokumente", "homelab"]
    assert daten["owner"]


def test_kachel_hat_die_felder_die_das_frontend_erwartet(client: TestClient) -> None:
    """Ändert sich das hier, bricht die Anzeige still. Deshalb festgenagelt."""
    kachel = client.get("/api/uebersicht").json()["kacheln"][0]
    for feld in ("key", "title", "icon", "route", "lead", "caption", "details", "has_data"):
        assert feld in kachel, f"{feld} fehlt"


# --- Termine --------------------------------------------------------------


def test_termine_in_fullcalendar_form(client: TestClient) -> None:
    """FullCalendar erwartet start/end/allDay, nicht unsere Store-Namen."""
    import src.main as m

    beginn = datetime(2026, 9, 15, 9, 0)
    m.get_store().replace_events(
        [_ev("Zahnarzt", beginn, ort="Buxtehude")],
        "2026-09-01T00:00:00",
        "2026-09-30T23:59:59",
    )

    daten = client.get("/api/termine", params={"von": "2026-09-01", "bis": "2026-09-30"}).json()
    assert len(daten["termine"]) == 1
    t = daten["termine"][0]
    assert t["title"] == "Zahnarzt"
    assert t["start"].startswith("2026-09-15T09:00")
    assert t["allDay"] is False
    assert t["ort"] == "Buxtehude"
    assert t["farbe"].startswith("#")


def test_termine_ohne_emoji(client: TestClient) -> None:
    """Inter hat keine Emoji-Glyphen, der Browser zeichnet Ersatzkästchen."""
    import src.main as m

    m.get_store().replace_events(
        [_ev("📚 Berufsschule", datetime(2026, 9, 15, 7, 30))],
        "2026-09-01T00:00:00",
        "2026-09-30T23:59:59",
    )
    daten = client.get("/api/termine", params={"von": "2026-09-01", "bis": "2026-09-30"}).json()
    assert daten["termine"][0]["title"] == "Berufsschule"


def test_kalenderfarbe_haengt_am_namen(client: TestClient) -> None:
    """Nicht an der Reihenfolge: sonst tauschen die Farben bei neuem Kalender."""
    from src.main import _kalenderfarbe

    assert _kalenderfarbe("Berufsschule") == _kalenderfarbe("Berufsschule")
    assert _kalenderfarbe("Arbeit") != _kalenderfarbe("Privat")


def test_termine_weisen_kaputte_daten_ab(client: TestClient) -> None:
    """Die Werte kommen aus der Adresszeile, da steht irgendwann Unsinn."""
    faelle = [
        {"von": "morgen", "bis": "2026-09-30"},
        {"von": "2026-13-99", "bis": "2026-09-30"},
        {"von": "2026-09-30", "bis": "2026-09-01"},  # bis vor von
        {"von": "2020-01-01", "bis": "2030-01-01"},  # zu großer Zeitraum
    ]
    for p in faelle:
        assert client.get("/api/termine", params=p).status_code == 400, p


def test_termine_brauchen_beide_daten(client: TestClient) -> None:
    assert client.get("/api/termine").status_code == 422


def test_kalenderfilter(client: TestClient) -> None:
    import src.main as m

    m.get_store().replace_events(
        [
            _ev("Schule", datetime(2026, 9, 15, 7, 30), kalender="Berufsschule"),
            _ev("Frei", datetime(2026, 9, 15, 18, 0), kalender="Privat"),
        ],
        "2026-09-01T00:00:00",
        "2026-09-30T23:59:59",
    )
    p = {"von": "2026-09-01", "bis": "2026-09-30", "kalender": "Privat"}
    daten = client.get("/api/termine", params=p).json()
    assert [t["title"] for t in daten["termine"]] == ["Frei"]
    # Die Kalenderliste bleibt vollständig, sonst verschwindet der Filter.
    assert "Berufsschule" in daten["kalender"]


# --- Homelab --------------------------------------------------------------


def test_homelab_felder(client: TestClient) -> None:
    daten = client.get("/api/homelab").json()
    for feld in ("lage", "stoerungen", "dienste", "kennzahlen", "stand"):
        assert feld in daten


def test_lage_zaehlt_immer_alle_dienste(client: TestClient) -> None:
    """Auch bei aktivem Filter: sonst meldet sie '1 von 1 erreichbar'."""
    import src.main as m

    store = m.get_store()
    store.replace_services(
        [
            {
                "name": "A",
                "status": 1,
                "msg": "",
                "uptime_24h": 100.0,
                "uptime_30d": 100.0,
                "ping": 10.0,
            },
            {
                "name": "B",
                "status": 0,
                "msg": "kaputt",
                "uptime_24h": 0.0,
                "uptime_30d": 50.0,
                "ping": None,
            },
        ]
    )
    store.set_setting("dienste_nur_stoerungen", "1")

    daten = client.get("/api/homelab").json()
    assert len(daten["dienste"]) == 1, "Filter greift nicht"
    assert daten["lage"]["gesamt"] == 2, "Lage zählt nur die gefilterten Dienste"
    assert daten["lage"]["oben"] == 1


# --- Dokumente ------------------------------------------------------------


def test_dokumente_seiten(client: TestClient) -> None:
    daten = client.get("/api/dokumente").json()
    for feld in ("treffer", "gesamt", "seite", "seiten", "ordner"):
        assert feld in daten


# --- Einstellungen --------------------------------------------------------


def test_einstellungen_liefern_posten_und_werte(client: TestClient) -> None:
    daten = client.get("/api/einstellungen").json()
    assert daten["posten"], "keine Einstellungen"
    schluessel = {p["key"] for p in daten["posten"]}
    assert schluessel <= set(daten["werte"]), "Werte fehlen für manche Posten"
    # Die Auswahlfelder brauchen ihre Optionen, sonst bleibt das Feld leer.
    for p in daten["posten"]:
        if p["art"] == "auswahl":
            assert p["optionen"], f"{p['key']} ohne Optionen"


def test_gesundheit_liefert_karte_und_verlauf(client: TestClient) -> None:
    daten = client.get("/api/gesundheit").json()
    assert "karte" in daten
    assert isinstance(daten["verlauf"], list)


# --- Frontend-Auslieferung ------------------------------------------------


def test_app_route_liefert_das_frontend(client: TestClient) -> None:
    """Der Router im Browser übernimmt: jede Unterseite bekommt dasselbe HTML."""
    from pathlib import Path

    import src.main as m

    gebaut = Path(m.GEBAUT)
    if not (gebaut / "index.html").is_file():
        # Ohne Build liefert die Route bewusst 503 statt einer leeren Seite.
        assert client.get("/app").status_code == 503
        return

    for weg in ("/app", "/app/termine", "/app/einstellungen"):
        antwort = client.get(weg)
        assert antwort.status_code == 200, weg
        assert '<div id="app">' in antwort.text


def test_frontend_laedt_nichts_von_fremden_servern(client: TestClient) -> None:
    """Kein CDN: auf einer Seite mit Ausweisen bleibt alles im eigenen Container.

    Das ist keine Stilfrage. Ein fremdes Skript auf dieser Seite sieht
    Dokumentnamen und Termine mit.
    """
    from pathlib import Path

    import src.main as m

    datei = Path(m.GEBAUT) / "index.html"
    if not datei.is_file():
        return

    text = datei.read_text(encoding="utf-8")
    for muster in ("//cdn.", "https://unpkg", "https://cdnjs", "googleapis.com"):
        assert muster not in text, f"fremde Quelle im HTML: {muster}"
