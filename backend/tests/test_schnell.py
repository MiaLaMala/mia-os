"""Schnelleingabe, Suche ueber alles, Sammelseite, Briefing.

Das, was Mia OS von Notion unterscheidet: der Assistent kann schreiben,
und ein Feld reicht.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from src import gesundheit
from src.schnell import deute
from src.store import Store

MONTAG = date(2026, 9, 7)


# --- Der Deuter -----------------------------------------------------------


def test_gewicht_wird_erkannt() -> None:
    d = deute("88,4 kg")
    assert d.art == "gewicht"
    assert d.zahl == 88.4
    assert deute("90kg").art == "gewicht"
    assert deute("88.4 kilo").zahl == 88.4


def test_essen_wird_erkannt_in_beiden_reihenfolgen() -> None:
    d = deute("Skyr 200g")
    assert d.art == "essen"
    assert d.titel == "Skyr"
    assert d.zahl == 200
    d = deute("150 g Haferflocken")
    assert d.art == "essen"
    assert d.titel == "Haferflocken"
    assert d.zahl == 150


def test_wochentag_wird_zum_naechsten_datum() -> None:
    d = deute("AU abgeben Freitag", heute=MONTAG)
    assert d.art == "eintrag"
    assert d.titel == "AU abgeben"
    assert d.datum == "2026-09-11"
    # Der heutige Wochentag ist heute, nicht in einer Woche.
    assert deute("Sport Montag", heute=MONTAG).datum == "2026-09-07"


def test_relative_tage_und_uhrzeit() -> None:
    d = deute("Zahnarzt morgen um 9:30", heute=MONTAG)
    assert d.titel == "Zahnarzt"
    assert d.datum == "2026-09-08"
    assert d.zeit == "09:30"
    d = deute("Anruf Amt übermorgen 14 Uhr", heute=MONTAG)
    assert d.datum == "2026-09-09"
    assert d.zeit == "14:00"
    assert d.titel == "Anruf Amt"


def test_datum_mit_punkt_und_jahreswechsel() -> None:
    d = deute("Zahnarzt 14.10. 9 Uhr", heute=MONTAG)
    assert d.datum == "2026-10-14"
    assert d.zeit == "09:00"
    assert d.titel == "Zahnarzt"
    # Ein Datum, das dieses Jahr schon vorbei ist, meint naechstes Jahr.
    assert deute("Geburtstag 3.1.", heute=MONTAG).datum == "2027-01-03"
    # Mit Jahr bleibt es, wie es ist.
    assert deute("Frist 3.1.2026", heute=MONTAG).datum == "2026-01-03"


def test_haengendes_am_oder_bis_verschwindet() -> None:
    assert deute("Bericht abgeben bis Freitag", heute=MONTAG).titel == "Bericht abgeben"
    assert deute("Termin am Mittwoch", heute=MONTAG).titel == "Termin"


def test_ohne_alles_bleibt_der_text() -> None:
    d = deute("Anna fragen wegen Küche")
    assert d.art == "eintrag"
    assert d.titel == "Anna fragen wegen Küche"
    assert d.datum is None
    assert d.zeit is None


# --- Die Schnelleingabe ueber die API ---------------------------------------


def test_schnelleingabe_legt_eintrag_mit_datum_an(client: TestClient) -> None:
    r = client.post("/api/schnell", json={"text": "AU abgeben 11.9."})
    assert r.status_code == 200, r.text
    daten = r.json()
    assert daten["art"] == "eintrag"
    assert daten["eintrag"]["titel"] == "AU abgeben"
    assert daten["eintrag"]["datum"] == "2026-09-11" or daten["eintrag"]["datum"].endswith("-09-11")


def test_schnelleingabe_ohne_text(client: TestClient) -> None:
    assert client.post("/api/schnell", json={"text": "  "}).status_code == 400


def test_schnelleingabe_gewicht_ohne_wger_wird_eintrag(client: TestClient) -> None:
    """Ohne wger-Konfiguration faellt das Gewicht nicht ins Leere."""
    r = client.post("/api/schnell", json={"text": "88,4 kg"})
    assert r.status_code == 200
    assert r.json()["art"] == "eintrag"


def test_schnelleingabe_gewicht_mit_wger(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    aufrufe: list[tuple[float, Any]] = []

    async def fake(kg: float, tag: Any = None) -> dict[str, Any]:
        aufrufe.append((kg, tag))
        return {"weight": kg}

    monkeypatch.setattr(gesundheit, "konfiguriert", lambda: True)
    monkeypatch.setattr(gesundheit, "gewicht_eintragen", fake)
    r = client.post("/api/schnell", json={"text": "88,4 kg"})
    assert r.status_code == 200, r.text
    assert r.json()["art"] == "gewicht"
    assert aufrufe == [(88.4, None)]
    assert "88,4 kg" in r.json()["meldung"]


def test_schnelleingabe_essen_eindeutig_und_mehrdeutig(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    gebucht: list[tuple[int, float]] = []

    async def suche(begriff: str, limit: int = 12) -> list[dict[str, Any]]:
        alle = [
            {"id": 4, "name": "Skyr natur", "kcal": 63, "protein": 11, "kh": 4, "fett": 0.2},
            {"id": 22, "name": "Skyr Erdbeere", "kcal": 80, "protein": 9, "kh": 9, "fett": 0.2},
        ]
        return [z for z in alle if begriff.lower() in z["name"].lower()][:limit]

    async def buchen(zutat_id: int, gramm: float, wann: Any = None) -> dict[str, Any]:
        gebucht.append((zutat_id, gramm))
        return {}

    monkeypatch.setattr(gesundheit, "konfiguriert", lambda: True)
    monkeypatch.setattr(gesundheit, "zutaten_suchen", suche)
    monkeypatch.setattr(gesundheit, "essen_eintragen", buchen)

    r = client.post("/api/schnell", json={"text": "Skyr 200g"})
    assert r.json()["art"] == "essen_wahl"
    assert len(r.json()["zutaten"]) == 2
    assert gebucht == []

    r = client.post("/api/schnell", json={"text": "Skyr natur 200g"})
    assert r.json()["art"] == "essen"
    assert gebucht == [(4, 200.0)]

    # Keine Zutat: dann ein normaler Eintrag, nichts geht verloren.
    r = client.post("/api/schnell", json={"text": "Döner 300g"})
    assert r.json()["art"] == "eintrag"


def test_schnelleingabe_meldet_wger_ausfall(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def kaputt(kg: float, tag: Any = None) -> dict[str, Any]:
        raise httpx.ConnectError("nein")

    monkeypatch.setattr(gesundheit, "konfiguriert", lambda: True)
    monkeypatch.setattr(gesundheit, "gewicht_eintragen", kaputt)
    r = client.post("/api/schnell", json={"text": "88 kg"})
    assert r.status_code == 502
    assert "wger" in r.json()["detail"]


# --- Gesundheit schreiben ----------------------------------------------------


def test_gewicht_endpunkt_prueft_zahl(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert client.post("/api/gesundheit/gewicht", json={"kg": "viel"}).status_code == 400

    async def fake(kg: float, tag: Any = None) -> dict[str, Any]:
        return {"weight": kg, "tag": tag}

    monkeypatch.setattr(gesundheit, "gewicht_eintragen", fake)
    r = client.post("/api/gesundheit/gewicht", json={"kg": "88,2", "datum": "2026-09-06"})
    assert r.status_code == 200
    assert r.json()["kg"] == 88.2


def test_zutaten_ohne_wger_leer(client: TestClient) -> None:
    assert client.get("/api/gesundheit/zutaten?q=skyr").json() == {"zutaten": []}
    assert client.get("/api/gesundheit/heute").json() == {"eintraege": [], "kcal": 0}


def test_essen_endpunkt_braucht_zutat(client: TestClient) -> None:
    assert client.post("/api/gesundheit/essen", json={"gramm": 100}).status_code == 400


@pytest.mark.asyncio
async def test_gewicht_eintragen_ersetzt_vorhandenes(monkeypatch: pytest.MonkeyPatch) -> None:
    """wger erlaubt ein Gewicht je Tag: ein zweites wird ein PATCH."""
    aufrufe: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        aufrufe.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json={"results": [{"id": 5, "weight": "88.70"}]})
        return httpx.Response(200, json={"id": 5, "weight": "88.20"})

    monkeypatch.setattr(gesundheit.settings, "wger_url", "http://wger.test")
    monkeypatch.setattr(gesundheit.settings, "wger_token", "abc")
    original = gesundheit._client

    def client_mit_mock() -> httpx.AsyncClient:
        c = original()
        c._transport = httpx.MockTransport(handler)
        return c

    monkeypatch.setattr(gesundheit, "_client", client_mit_mock)
    await gesundheit.gewicht_eintragen(88.2, date(2026, 9, 5))
    assert aufrufe == [("GET", "/api/v2/weightentry/"), ("PATCH", "/api/v2/weightentry/5/")]

    with pytest.raises(gesundheit.WgerError):
        await gesundheit.gewicht_eintragen(5.0)


# --- Sammelseite --------------------------------------------------------------


def test_alles_zeigt_eintraege_aller_seiten(client: TestClient) -> None:
    seiten = client.get("/api/seiten").json()["seiten"]
    alles = next(s for s in seiten if s["titel"] == "Alles")
    behoerden = next(s for s in seiten if s["titel"] == "Behörden")
    assert alles["sammelt_alles"] is True
    assert behoerden["sammelt_alles"] is False

    client.post("/api/sammlung", json={"titel": "Steuer-ID", "page_id": behoerden["id"]})
    client.post("/api/sammlung", json={"titel": "Ohne Seite"})

    auf_alles = client.get(f"/api/seiten/{alles['id']}").json()
    titel = {e["titel"] for e in auf_alles["eintraege"]}
    assert titel == {"Steuer-ID", "Ohne Seite"}
    assert auf_alles["seitentitel"][str(behoerden["id"])] == "Behörden"

    auf_behoerden = client.get(f"/api/seiten/{behoerden['id']}").json()
    assert [e["titel"] for e in auf_behoerden["eintraege"]] == ["Steuer-ID"]


def test_auf_alles_angelegt_bleibt_ohne_seite(client: TestClient) -> None:
    """Sonst wuerde "Alles" zum Ordner, in dem Eintraege verschwinden."""
    seiten = client.get("/api/seiten").json()["seiten"]
    alles = next(s for s in seiten if s["titel"] == "Alles")
    e = client.post("/api/sammlung", json={"titel": "X", "page_id": alles["id"]}).json()["eintrag"]
    assert e["page_id"] == 0


def test_eintrag_kann_seite_wechseln(client: TestClient) -> None:
    seiten = client.get("/api/seiten").json()["seiten"]
    ziel = next(s for s in seiten if s["titel"] == "Ausbildung")
    e = client.post("/api/sammlung", json={"titel": "Bericht"}).json()["eintrag"]
    r = client.patch(f"/api/sammlung/{e['id']}", json={"page_id": ziel["id"]})
    assert r.json()["eintrag"]["page_id"] == ziel["id"]


def test_alte_datenbank_bekommt_sammelseite(tmp_path: Path) -> None:
    """Bestand vom 06.09.: pages ohne sammelt_alles, "Alles" nur ein Ordner."""
    pfad = tmp_path / "alt.db"
    conn = sqlite3.connect(pfad)
    conn.executescript(
        """
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, parent_id INTEGER, titel TEXT NOT NULL DEFAULT '',
            symbol TEXT NOT NULL DEFAULT 'document', inhalt TEXT NOT NULL DEFAULT '',
            hat_sammlung INTEGER NOT NULL DEFAULT 0, ansicht TEXT NOT NULL DEFAULT 'liste',
            gruppe_nach TEXT NOT NULL DEFAULT 'status', sortierung REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        INSERT INTO pages (titel, hat_sammlung, created_at, updated_at) VALUES ('Alles', 1, 'x', 'x');
        INSERT INTO pages (titel, hat_sammlung, created_at, updated_at) VALUES ('Behörden', 1, 'x', 'x');
        """
    )
    conn.commit()
    conn.close()

    from src.sammlung import startseiten_anlegen

    store = Store(str(pfad))
    startseiten_anlegen(store)
    seiten = {p["titel"]: p for p in store.list_pages()}
    assert seiten["Alles"]["sammelt_alles"] is True
    assert seiten["Behörden"]["sammelt_alles"] is False
    # Kein zweiter Satz Startseiten.
    assert len(seiten) == 2


# --- Suche ueber alles -----------------------------------------------------------


def test_suche_findet_seiten_eintraege_termine(client: TestClient) -> None:
    from src.main import get_store

    client.post("/api/seiten", json={"titel": "Zahnarzt Unterlagen"})
    client.post("/api/sammlung", json={"titel": "Zahnarzt anrufen", "datum": "2026-09-20"})
    get_store().replace_events(
        [
            {
                "uid": "z1",
                "start_at": "2026-09-30T09:00:00",
                "end_at": "2026-09-30T10:00:00",
                "title": "Zahnarzt",
                "location": "",
                "calendar": "Privat",
                "ganztags": 0,
            },
            {
                "uid": "z0",
                "start_at": "2020-01-01T09:00:00",
                "end_at": "",
                "title": "Zahnarzt alt",
                "location": "",
                "calendar": "Privat",
                "ganztags": 0,
            },
        ],
        "2020-01-01T00:00:00",
        "2030-01-01T00:00:00",
    )

    r = client.get("/api/suche?q=zahn").json()
    assert [s["titel"] for s in r["seiten"]] == ["Zahnarzt Unterlagen"]
    assert [e["titel"] for e in r["eintraege"]] == ["Zahnarzt anrufen"]
    # Der kommende Termin steht vor dem vergangenen.
    assert [t["titel"] for t in r["termine"]] == ["Zahnarzt", "Zahnarzt alt"]
    assert r["termine"][0]["farbe"].startswith("#")
    assert r["dokumente"] == []


def test_suche_braucht_zwei_zeichen(client: TestClient) -> None:
    assert client.get("/api/suche?q=z").json() == {
        "seiten": [],
        "eintraege": [],
        "termine": [],
        "dokumente": [],
    }


# --- Briefing --------------------------------------------------------------------


def test_briefing_ohne_termine(client: TestClient) -> None:
    r = client.get("/api/briefing").json()
    assert r["heute"] == []
    assert "keine Termine" in r["text"]


def test_briefing_mit_tag(client: TestClient) -> None:
    from src.main import get_store

    heute = date.today().isoformat()
    get_store().replace_events(
        [
            {
                "uid": "b1",
                "start_at": f"{heute}T08:00:00",
                "end_at": f"{heute}T12:45:00",
                "title": "Berufsschule",
                "location": "Hamburg",
                "calendar": "Berufsschule",
                "ganztags": 0,
            }
        ],
        f"{heute}T00:00:00",
        f"{heute}T23:59:59",
    )
    client.post("/api/sammlung", json={"titel": "AU abgeben", "datum": heute})

    r = client.get("/api/briefing").json()
    assert r["heute"][0]["zeit"] == "08:00"
    assert r["faellig"][0]["titel"] == "AU abgeben"
    assert "08:00 Berufsschule (Hamburg)" in r["text"]
    assert "Fällig: AU abgeben" in r["text"]
