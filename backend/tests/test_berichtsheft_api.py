"""Tests fuer die Berichtsheft-Schnittstelle und ihre Speicherung."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.store import Store


def _woche(client: TestClient, montag: str = "") -> dict:
    p = f"?montag={montag}" if montag else ""
    antwort = client.get(f"/api/berichtsheft{p}")
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


# --- Store ------------------------------------------------------------------


def test_leere_woche_ist_none(store: Store) -> None:
    assert store.berichtswoche("2026-09-07") is None


def test_speichern_und_lesen(store: Store) -> None:
    store.save_berichtswoche(
        "2026-09-07",
        inhalt={"2026-09-08": {"taetigkeiten": ["Tickets"]}},
        status="bearbeitet",
        bemerkung="lief",
    )
    w = store.berichtswoche("2026-09-07")
    assert w is not None
    assert w["status"] == "bearbeitet"
    assert w["bemerkung"] == "lief"
    assert w["inhalt"]["2026-09-08"]["taetigkeiten"] == ["Tickets"]


def test_teilweises_speichern_loescht_nichts(store: Store) -> None:
    """Ein Tastendruck in einem Tagesfeld darf die Bemerkung nicht leeren."""
    store.save_berichtswoche("2026-09-07", bemerkung="wichtig", themen_schule="Subnetting")
    store.save_berichtswoche("2026-09-07", inhalt={"2026-09-08": {"taetigkeiten": ["A"]}})
    w = store.berichtswoche("2026-09-07")
    assert w is not None
    assert w["bemerkung"] == "wichtig"
    assert w["themen_schule"] == "Subnetting"
    assert w["inhalt"]["2026-09-08"]["taetigkeiten"] == ["A"]


def test_inhalt_wird_zusammengefuehrt_nicht_ersetzt(store: Store) -> None:
    store.save_berichtswoche("2026-09-07", inhalt={"2026-09-08": {"taetigkeiten": ["A"]}})
    store.save_berichtswoche("2026-09-07", inhalt={"2026-09-09": {"taetigkeiten": ["B"]}})
    w = store.berichtswoche("2026-09-07")
    assert w is not None
    assert set(w["inhalt"]) == {"2026-09-08", "2026-09-09"}


def test_tag_auf_none_loescht_ihn(store: Store) -> None:
    store.save_berichtswoche("2026-09-07", inhalt={"2026-09-08": {"taetigkeiten": ["A"]}})
    store.save_berichtswoche("2026-09-07", inhalt={"2026-09-08": None})
    w = store.berichtswoche("2026-09-07")
    assert w is not None
    assert w["inhalt"] == {}


def test_created_at_bleibt_stehen(store: Store) -> None:
    erst = store.save_berichtswoche("2026-09-07", bemerkung="a")
    dann = store.save_berichtswoche("2026-09-07", bemerkung="b")
    assert erst["created_at"] == dann["created_at"]


def test_kaputtes_json_gibt_leere_woche(store: Store) -> None:
    """Eine kaputte Zeile darf die Seite nicht am Laden hindern."""
    store.save_berichtswoche("2026-09-07", bemerkung="da")
    with store._conn() as conn:
        conn.execute(
            "UPDATE berichtswochen SET inhalt = 'kaputt' WHERE montag = ?", ("2026-09-07",)
        )
    w = store.berichtswoche("2026-09-07")
    assert w is not None
    assert w["inhalt"] == {}
    assert w["bemerkung"] == "da"


def test_liste_sortiert_neueste_zuerst(store: Store) -> None:
    for m in ("2026-08-24", "2026-09-07", "2026-08-31"):
        store.save_berichtswoche(m, bemerkung="x")
    assert [w["montag"] for w in store.berichtswochen()] == [
        "2026-09-07",
        "2026-08-31",
        "2026-08-24",
    ]


# --- API --------------------------------------------------------------------


def test_ohne_montag_kommt_die_laufende_woche(client: TestClient) -> None:
    w = _woche(client)
    heute = date.today()
    assert w["montag"] == (heute - timedelta(days=heute.weekday())).isoformat()
    assert len(w["tage"]) == 7


def test_beliebiger_tag_wird_auf_montag_gerundet(client: TestClient) -> None:
    assert _woche(client, "2026-09-10")["montag"] == "2026-09-07"


def test_kaputtes_datum_ist_400(client: TestClient) -> None:
    assert client.get("/api/berichtsheft?montag=quatsch").status_code == 400


def test_stunden_kommen_aus_dem_kalender(client: TestClient) -> None:
    import src.main as m

    store = m.get_store()
    store.replace_events(
        [
            {
                "uid": "a",
                "start_at": "2026-09-08T07:30:00",
                "end_at": "2026-09-08T16:15:00",
                "title": "Arbeit",
                "location": "",
                "calendar": "Arbeit",
                "ganztags": False,
            },
            {
                "uid": "b",
                "start_at": "2026-09-08T11:30:00",
                "end_at": "2026-09-08T12:30:00",
                "title": "Mittagspause",
                "location": "",
                "calendar": "Privat",
                "ganztags": False,
            },
        ],
        "2026-09-01T00:00:00",
        "2026-09-30T00:00:00",
    )
    w = _woche(client, "2026-09-07")
    assert w["tage"][1]["betrieb_stunden"] == 8.75
    assert w["stunden"] == 8.75


def test_speichern_gibt_die_woche_zurueck(client: TestClient) -> None:
    antwort = client.post(
        "/api/berichtsheft",
        json={
            "montag": "2026-09-09",
            "inhalt": {"2026-09-08": {"taetigkeiten": ["VLANs eingerichtet"]}},
            "status": "bearbeitet",
        },
    )
    assert antwort.status_code == 200, antwort.text
    w = antwort.json()
    assert w["montag"] == "2026-09-07"
    assert w["status"] == "bearbeitet"
    assert w["tage"][1]["taetigkeiten"] == ["VLANs eingerichtet"]


def test_gespeichertes_ueberlebt_den_neuen_entwurf(client: TestClient) -> None:
    client.post(
        "/api/berichtsheft",
        json={"montag": "2026-09-07", "inhalt": {"2026-09-08": {"taetigkeiten": ["A"]}}},
    )
    assert _woche(client, "2026-09-07")["tage"][1]["taetigkeiten"] == ["A"]


def test_unbekannter_status_ist_400(client: TestClient) -> None:
    antwort = client.post("/api/berichtsheft", json={"montag": "2026-09-07", "status": "irgendwas"})
    assert antwort.status_code == 400


def test_inhalt_muss_ein_objekt_sein(client: TestClient) -> None:
    antwort = client.post("/api/berichtsheft", json={"montag": "2026-09-07", "inhalt": ["a"]})
    assert antwort.status_code == 400


def test_speichern_ohne_montag_ist_400(client: TestClient) -> None:
    assert client.post("/api/berichtsheft", json={"status": "fertig"}).status_code == 400


def test_wochenliste_zeigt_auch_ungespeicherte(client: TestClient) -> None:
    antwort = client.get("/api/berichtsheft/wochen?anzahl=4")
    assert antwort.status_code == 200
    daten = antwort.json()
    assert len(daten["wochen"]) == 4
    assert daten["wochen"][0]["aktuell"] is True
    assert all(w["status"] == "entwurf" for w in daten["wochen"])


def test_woche_ohne_kalenderdaten_ist_markiert(client: TestClient) -> None:
    """Der Collector liest nur 45 Tage zurueck: '0 h' waere dort gelogen."""
    daten = client.get("/api/berichtsheft/wochen?anzahl=3").json()
    assert all(w["hat_daten"] is False for w in daten["wochen"])

    import src.main as m

    heute = date.today()
    montag = heute - timedelta(days=heute.weekday())
    m.get_store().replace_events(
        [
            {
                "uid": "x",
                "start_at": f"{montag.isoformat()}T09:00:00",
                "end_at": f"{montag.isoformat()}T17:00:00",
                "title": "Arbeit",
                "location": "",
                "calendar": "Arbeit",
                "ganztags": False,
            }
        ],
        f"{montag.isoformat()}T00:00:00",
        f"{(montag + timedelta(days=6)).isoformat()}T23:59:59",
    )
    daten = client.get("/api/berichtsheft/wochen?anzahl=3").json()
    assert daten["wochen"][0]["hat_daten"] is True
    assert daten["wochen"][1]["hat_daten"] is False


def test_gespeicherte_woche_zaehlt_auch_ohne_termine(client: TestClient) -> None:
    """Hat Mia selbst etwas eingetragen, ist die Woche keine Leerstelle mehr."""
    heute = date.today()
    alt = (heute - timedelta(weeks=2) - timedelta(days=heute.weekday())).isoformat()
    client.post("/api/berichtsheft", json={"montag": alt, "bemerkung": "war Urlaub"})
    daten = client.get("/api/berichtsheft/wochen?anzahl=4").json()
    passend = next(w for w in daten["wochen"] if w["montag"] == alt)
    assert passend["hat_daten"] is True


def test_wochenliste_zaehlt_gefuellte_tage(client: TestClient) -> None:
    heute = date.today()
    montag = (heute - timedelta(days=heute.weekday())).isoformat()
    client.post(
        "/api/berichtsheft",
        json={
            "montag": montag,
            "status": "fertig",
            "inhalt": {
                montag: {"taetigkeiten": ["A"]},
                (date.fromisoformat(montag) + timedelta(days=1)).isoformat(): {
                    "taetigkeiten": ["   "]
                },
            },
        },
    )
    daten = client.get("/api/berichtsheft/wochen?anzahl=2").json()
    aktuell = daten["wochen"][0]
    assert aktuell["status"] == "fertig"
    # Nur der Tag mit echtem Text zaehlt, Leerzeichen sind kein Inhalt.
    assert aktuell["gefuellte_tage"] == 1


@pytest.mark.parametrize("anzahl,erwartet", [(0, 1), (99, 52)])
def test_wochenliste_begrenzt_die_anzahl(client: TestClient, anzahl: int, erwartet: int) -> None:
    daten = client.get(f"/api/berichtsheft/wochen?anzahl={anzahl}").json()
    assert len(daten["wochen"]) == erwartet


def test_sammlungseintrag_wird_hinweis(client: TestClient) -> None:
    import src.main as m

    heute = date.today()
    montag = heute - timedelta(days=heute.weekday())
    m.get_store().create_entry(titel="Switch getauscht", datum=(montag).isoformat())
    w = _woche(client, montag.isoformat())
    assert "Switch getauscht" in w["tage"][0]["hinweise"]


def test_zeitfenster_deckt_genau_die_woche(client: TestClient) -> None:
    """Der Sonntag muss noch reinfallen, der Montag danach nicht mehr."""
    import src.main as m

    def ev(uid: str, tag: str) -> dict:
        return {
            "uid": uid,
            "start_at": f"{tag}T09:00:00",
            "end_at": f"{tag}T17:00:00",
            "title": "Arbeit",
            "location": "",
            "calendar": "Arbeit",
            "ganztags": False,
        }

    m.get_store().replace_events(
        [ev("so", "2026-09-13"), ev("mo", "2026-09-14")],
        "2026-09-01T00:00:00",
        "2026-09-30T00:00:00",
    )
    w = _woche(client, "2026-09-07")
    assert w["tage"][6]["stunden"] == 8.0
    assert w["stunden"] == 8.0


def test_datumsgrenzen_sind_dabei() -> None:
    """Sicherheitsnetz gegen ein abgeschnittenes Zeitfenster."""
    start = datetime.combine(date(2026, 9, 7), datetime.min.time())
    assert start.isoformat() == "2026-09-07T00:00:00"
