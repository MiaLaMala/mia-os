"""Notizen und Aufgaben: die schreibende Seite von Mia OS."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient


def _ev(uid: str, titel: str) -> dict[str, Any]:
    beginn = datetime(2026, 9, 15, 9, 0)
    return {
        "uid": uid,
        "calendar": "Privat",
        "title": titel,
        "start_at": beginn.isoformat(),
        "end_at": beginn.replace(hour=10).isoformat(),
        "ganztags": 0,
        "location": "",
    }


# --- Notizen --------------------------------------------------------------


def test_notiz_schreiben_und_lesen(client: TestClient) -> None:
    r = client.put("/api/termin/uid-1/notiz", json={"notiz": "Zeugnis mitbringen"})
    assert r.status_code == 200
    assert client.get("/api/termin/uid-1").json()["notiz"] == "Zeugnis mitbringen"


def test_leere_notiz_loescht(client: TestClient) -> None:
    """Eine leere Notiz soll verschwinden, nicht als leere Zeile bleiben."""
    client.put("/api/termin/uid-2/notiz", json={"notiz": "erstmal was"})
    client.put("/api/termin/uid-2/notiz", json={"notiz": "   "})
    assert client.get("/api/termin/uid-2").json()["notiz"] == ""


def test_zu_lange_notiz_wird_abgewiesen(client: TestClient) -> None:
    r = client.put("/api/termin/uid-3/notiz", json={"notiz": "x" * 20_001})
    assert r.status_code == 400


def test_unbekannter_termin_gibt_leere_details(client: TestClient) -> None:
    """Kein 404: eine Notiz darf angelegt werden, bevor es sie gibt."""
    daten = client.get("/api/termin/gibtsnicht").json()
    assert daten["notiz"] == ""
    assert daten["aufgaben"] == []


# --- Aufgaben -------------------------------------------------------------


def test_aufgabe_anlegen_und_abhaken(client: TestClient) -> None:
    r = client.post("/api/aufgaben", json={"titel": "Krankmeldung faxen"})
    assert r.status_code == 200
    a = r.json()["aufgabe"]
    assert a["titel"] == "Krankmeldung faxen"
    assert a["erledigt"] is False

    assert client.patch(f"/api/aufgaben/{a['id']}", json={"erledigt": True}).status_code == 200
    alle = client.get("/api/aufgaben").json()["aufgaben"]
    assert [t["erledigt"] for t in alle if t["id"] == a["id"]] == [True]


def test_aufgabe_ohne_titel_wird_abgewiesen(client: TestClient) -> None:
    assert client.post("/api/aufgaben", json={"titel": "   "}).status_code == 400
    assert client.post("/api/aufgaben", json={}).status_code == 400


def test_aufgabe_mit_kaputtem_datum(client: TestClient) -> None:
    r = client.post("/api/aufgaben", json={"titel": "Test", "faellig_am": "morgen"})
    assert r.status_code == 400


def test_aufgabe_am_termin(client: TestClient) -> None:
    """Aufgaben am Termin tauchen dort auf, nicht in der freien Liste."""
    client.post("/api/aufgaben", json={"titel": "Unterlagen", "event_uid": "uid-5"})
    client.post("/api/aufgaben", json={"titel": "Frei stehend"})

    am_termin = client.get("/api/termin/uid-5").json()["aufgaben"]
    assert [t["titel"] for t in am_termin] == ["Unterlagen"]

    frei = client.get("/api/aufgaben", params={"frei": True}).json()["aufgaben"]
    assert [t["titel"] for t in frei] == ["Frei stehend"]


def test_erledigte_wandern_nach_unten(client: TestClient) -> None:
    ids = []
    for titel in ("erste", "zweite", "dritte"):
        ids.append(client.post("/api/aufgaben", json={"titel": titel}).json()["aufgabe"]["id"])
    client.patch(f"/api/aufgaben/{ids[0]}", json={"erledigt": True})

    titel = [t["titel"] for t in client.get("/api/aufgaben").json()["aufgaben"]]
    assert titel[-1] == "erste", f"Erledigte nicht unten: {titel}"


def test_faellige_zuerst_ohne_datum_zuletzt(client: TestClient) -> None:
    """Eine Aufgabe ohne Frist drängt nicht und steht hinten."""
    client.post("/api/aufgaben", json={"titel": "irgendwann"})
    client.post("/api/aufgaben", json={"titel": "am 8.", "faellig_am": "2026-09-08"})
    client.post("/api/aufgaben", json={"titel": "am 1.", "faellig_am": "2026-09-01"})

    titel = [t["titel"] for t in client.get("/api/aufgaben").json()["aufgaben"]]
    assert titel == ["am 1.", "am 8.", "irgendwann"], titel


def test_aufgabe_loeschen(client: TestClient) -> None:
    a = client.post("/api/aufgaben", json={"titel": "weg damit"}).json()["aufgabe"]
    assert client.delete(f"/api/aufgaben/{a['id']}").status_code == 200
    assert client.delete(f"/api/aufgaben/{a['id']}").status_code == 404


def test_unbekannte_aufgabe_gibt_404(client: TestClient) -> None:
    assert client.patch("/api/aufgaben/9999", json={"erledigt": True}).status_code == 404


# --- Verbindung zum Kalender ---------------------------------------------


def test_termine_zeigen_woran_etwas_haengt(client: TestClient) -> None:
    """Das Blatt muss sehen, wo eine Notiz oder Aufgabe dranhängt."""
    import src.main as m

    m.get_store().replace_events(
        [_ev("uid-7", "Zahnarzt"), _ev("uid-8", "Ohne alles")],
        "2026-09-01T00:00:00",
        "2026-09-30T23:59:59",
    )
    client.put("/api/termin/uid-7/notiz", json={"notiz": "Karte mitnehmen"})
    client.post("/api/aufgaben", json={"titel": "Rezept holen", "event_uid": "uid-7"})

    daten = client.get("/api/termine", params={"von": "2026-09-01", "bis": "2026-09-30"}).json()
    nach_id = {t["id"]: t for t in daten["termine"]}
    assert nach_id["uid-7"]["hat_notiz"] is True
    assert nach_id["uid-7"]["offene_aufgaben"] == 1
    assert nach_id["uid-8"]["hat_notiz"] is False
    assert nach_id["uid-8"]["offene_aufgaben"] == 0


def test_erledigte_aufgabe_zaehlt_nicht_mehr(client: TestClient) -> None:
    import src.main as m

    m.get_store().replace_events(
        [_ev("uid-9", "Termin")], "2026-09-01T00:00:00", "2026-09-30T23:59:59"
    )
    a = client.post(
        "/api/aufgaben", json={"titel": "erledigt gleich", "event_uid": "uid-9"}
    ).json()["aufgabe"]
    client.patch(f"/api/aufgaben/{a['id']}", json={"erledigt": True})

    daten = client.get("/api/termine", params={"von": "2026-09-01", "bis": "2026-09-30"}).json()
    assert daten["termine"][0]["offene_aufgaben"] == 0


def test_faellige_aufgaben_je_tag(client: TestClient) -> None:
    """Ein Tag mit offener Aufgabe zählt, auch ohne Termin darauf."""
    client.post("/api/aufgaben", json={"titel": "A", "faellig_am": "2026-09-08"})
    client.post("/api/aufgaben", json={"titel": "B", "faellig_am": "2026-09-08"})

    daten = client.get("/api/termine", params={"von": "2026-09-01", "bis": "2026-09-30"}).json()
    assert daten["aufgaben_je_tag"]["2026-09-08"] == 2
