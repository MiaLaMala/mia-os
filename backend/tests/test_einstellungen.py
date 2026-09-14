"""Einstellungen, Dienste und die Live-Schnittstelle."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from src.einstellungen import EINSTELLUNGEN, NACH_KEY, als_zahl, gruppen, mit_vorgaben
from src.store import Store


def _dienst(name: str, **kw: Any) -> dict[str, Any]:
    return {
        "name": name,
        "status": kw.get("status", 1),
        "msg": kw.get("msg", "200 - OK"),
        "ping": kw.get("ping", 42),
        "uptime24": kw.get("uptime24", 99.9),
        "uptime30": kw.get("uptime30", 99.5),
        "seit": "2026-09-05 23:00:00",
    }


# --- Werte pruefen --------------------------------------------------------


def test_zahl_ausserhalb_des_bereichs_wird_abgelehnt() -> None:
    """Ein kaputtes Sammelintervall wuerde den Hintergrundlauf lahmlegen."""
    e = NACH_KEY["sammel_minuten"]
    assert e.pruefe("15") == "15"
    assert e.pruefe("2") is None, "unter dem Minimum"
    assert e.pruefe("9999") is None, "ueber dem Maximum"
    assert e.pruefe("abc") is None
    assert e.pruefe("") is None


def test_auswahl_nimmt_nur_bekannte_werte() -> None:
    e = NACH_KEY["dienste_uptime_zeitraum"]
    assert e.pruefe("24") == "24"
    assert e.pruefe("30") == "30"
    assert e.pruefe("999") is None


def test_schalter_versteht_die_ueblichen_formen() -> None:
    e = NACH_KEY["dokumente_vorschau"]
    assert e.pruefe("on") == "1"
    assert e.pruefe("1") == "1"
    assert e.pruefe("") == "0"


def test_vorgaben_fuellen_luecken() -> None:
    """Kein Aufrufer soll mit fehlenden Schluesseln rechnen muessen."""
    werte = mit_vorgaben({})
    assert set(werte) == {e.key for e in EINSTELLUNGEN}
    assert als_zahl(werte, "sammel_minuten") == 15


def test_kaputter_gespeicherter_wert_faellt_auf_die_vorgabe(store: Store) -> None:
    """Auch wenn jemand direkt in die Datenbank schreibt."""
    werte = mit_vorgaben({"sammel_minuten": "-5", "dienste_uptime_zeitraum": "lila"})
    assert werte["sammel_minuten"] == "15"
    assert werte["dienste_uptime_zeitraum"] == "24"


def test_gruppen_behalten_die_reihenfolge() -> None:
    namen = [g for g, _ in gruppen()]
    assert namen == list(dict.fromkeys(e.gruppe for e in EINSTELLUNGEN))


# --- Dienste im Store -----------------------------------------------------


def test_dienste_stoerungen_zuerst(store: Store) -> None:
    """Was nicht laeuft, gehoert nach oben."""
    store.replace_services(
        [
            _dienst("Alpha"),
            _dienst("Zeta", status=0, msg="timeout"),
            _dienst("Beta", status=3),
        ]
    )
    assert [d["name"] for d in store.services()] == ["Zeta", "Beta", "Alpha"]


def test_dienst_ids_bleiben_stabil(store: Store) -> None:
    store.replace_services([_dienst("Nextcloud")])
    vorher = store.services()[0]["id"]
    store.replace_services([_dienst("Nextcloud", status=0)])
    nachher = store.services()[0]
    assert nachher["id"] == vorher
    assert nachher["status"] == 0


def test_verschwundene_dienste_fliegen_raus(store: Store) -> None:
    store.replace_services([_dienst("Alt"), _dienst("Neu")])
    store.replace_services([_dienst("Neu")])
    assert [d["name"] for d in store.services()] == ["Neu"]


def test_einstellungen_ueberleben(store: Store) -> None:
    store.set_setting("sammel_minuten", "30")
    store.set_setting("sammel_minuten", "45")
    assert store.get_settings()["sammel_minuten"] == "45"


# --- Seiten und Schnittstelle ---------------------------------------------


def test_api_homelab_liefert_dienste(client: TestClient) -> None:
    import src.main as m

    m.get_store().replace_services([_dienst("Vaultwarden", uptime24=98.5)])
    daten = client.get("/api/homelab").json()
    assert daten["dienste"][0]["name"] == "Vaultwarden"
    assert daten["dienste"][0]["uptime"] == 98.5
    assert "stand" in daten


def test_nur_stoerungen_blendet_laufende_aus(client: TestClient) -> None:
    import src.main as m

    m.get_store().replace_services([_dienst("Laeuft"), _dienst("Kaputt", status=0)])
    m.get_store().set_setting("dienste_nur_stoerungen", "1")
    namen = [d["name"] for d in client.get("/api/homelab").json()["dienste"]]
    assert namen == ["Kaputt"]


def test_ohne_messwerte_kein_null_prozent(client: TestClient) -> None:
    """-1 heisst 'noch nichts gemessen', nicht '0 Prozent verfuegbar'."""
    import src.main as m

    m.get_store().replace_services([_dienst("Neu", uptime24=-1)])
    assert client.get("/api/homelab").json()["dienste"][0]["uptime"] is None


def test_zeitraum_wechselt_die_zahl(client: TestClient) -> None:
    import src.main as m

    m.get_store().replace_services([_dienst("X", uptime24=99.9, uptime30=95.0)])
    assert client.get("/api/homelab").json()["dienste"][0]["uptime"] == 99.9
    m.get_store().set_setting("dienste_uptime_zeitraum", "30")
    assert client.get("/api/homelab").json()["dienste"][0]["uptime"] == 95.0


def test_vorschau_abschaltbar(client: TestClient) -> None:
    """Wichtig, weil Vorschauen lesbare Arztunterlagen zeigen koennen."""
    import src.main as m

    m.get_store().replace_documents(
        "nextcloud",
        [
            {
                "path": "/Befund.pdf",
                "name": "Befund.pdf",
                "folder": "/",
                "ext": ".pdf",
                "size_bytes": 10,
                "modified_at": "2026-09-05T00:00:00+00:00",
                "file_id": "1",
            }
        ],
    )
    m.get_store().set_setting("dokumente_vorschau", "0")
    daten = client.get("/api/dokumente").json()
    assert all(not d["vorschau"] for d in daten["treffer"])


def test_kennzahlen_kommen_wirklich_an(client: TestClient) -> None:
    """Die Karte liefert lead + details, nicht 'fields'.

    Beim ersten Wurf war die Liste deshalb still leer: kein Fehler, nur
    nichts zu sehen. Genau das soll dieser Test verhindern.
    """
    import src.main as m

    store = m.get_store()
    store.record("homelab", "gaeste_laufend", 37.0)
    store.record("homelab", "uptime_24h", 99.5, unit="%")
    store.record("homelab", "dienste_lage", text_value="alle erreichbar")

    daten = client.get("/api/homelab").json()
    assert daten["kennzahlen"], "keine Kennzahlen geliefert"
    beschriftungen = [k["label"] for k in daten["kennzahlen"]]
    assert "Gäste laufen" in beschriftungen

    # "Dienste" gehoert NICHT dazu: derselbe Satz steht schon als Lage oben,
    # daneben als Kachel liest er sich wie eine zweite Fehlermeldung.
    assert "Dienste" not in beschriftungen


# --- Lagemeldung ----------------------------------------------------------


def test_lage_meldet_alles_laeuft(client: TestClient) -> None:
    import src.main as m

    m.get_store().replace_services([_dienst("A"), _dienst("B")])
    lage = client.get("/api/homelab").json()["lage"]
    assert lage["satz"] == "Alles läuft"
    assert lage["zustand"] == "oben"
    assert lage["oben"] == 2


def test_lage_nennt_den_einen_kaputten_dienst_beim_namen(client: TestClient) -> None:
    """Bei genau einer Störung ist der Name die Information, nicht die Zahl."""
    import src.main as m

    m.get_store().replace_services([_dienst("A"), _dienst("Homepage", status=0)])
    lage = client.get("/api/homelab").json()["lage"]
    assert lage["satz"] == "Homepage ist nicht erreichbar"
    assert lage["zustand"] == "unten"
    assert lage["oben"] == 1


def test_lage_zaehlt_bei_mehreren_stoerungen(client: TestClient) -> None:
    import src.main as m

    m.get_store().replace_services([_dienst("A", status=0), _dienst("B", status=0), _dienst("C")])
    assert client.get("/api/homelab").json()["lage"]["satz"] == "2 Dienste gestört"


def test_lage_ignoriert_den_stoerungsfilter(client: TestClient) -> None:
    """Sonst meldet sie bei aktivem Filter '1 von 1 erreichbar'."""
    import src.main as m

    m.get_store().replace_services([_dienst("A"), _dienst("B"), _dienst("Kaputt", status=0)])
    m.get_store().set_setting("dienste_nur_stoerungen", "1")

    daten = client.get("/api/homelab").json()
    assert daten["lage"]["gesamt"] == 3, "Lage muss alle Dienste zaehlen"
    assert daten["lage"]["oben"] == 2
    # Die Liste selbst bleibt gefiltert.
    assert [d["name"] for d in daten["dienste"]] == ["Kaputt"]


def test_pending_ist_keine_stoerung(client: TestClient) -> None:
    """Status 2 heisst 'wird gerade geprüft', nicht 'kaputt'.

    Steht zum Beispiel eine Minute lang da, während Mia OS selbst neu
    startet. Als Störung gemeldet wäre das ein Fehlalarm bei jedem Deploy.
    """
    import src.main as m

    m.get_store().replace_services(
        [_dienst("A"), _dienst("mia-os", status=2), _dienst("Echt kaputt", status=0)]
    )
    namen = [s["name"] for s in client.get("/api/homelab").json()["stoerungen"]]
    assert namen == ["Echt kaputt"]


# --- Automatisch speichern ------------------------------------------------


def test_einzelne_einstellung_sichern(client: TestClient) -> None:
    """Kein Speichern-Knopf: jede Änderung geht sofort raus."""
    antwort = client.post(
        "/api/einstellungen", json={"key": "dienste_uptime_zeitraum", "wert": "30"}
    )
    assert antwort.status_code == 200
    assert antwort.json()["wert"] == "30"

    import src.main as m

    assert m.get_store().get_settings()["dienste_uptime_zeitraum"] == "30"


def test_entfernte_einstellung_wird_abgewiesen(client: TestClient) -> None:
    """Die Einstellung "thema" gab es bis zum 14.09.2026 (Akzent Blau oder Rot).

    Seit die Palette aus farben.json kommt, hat Mia OS genau einen Akzent,
    und das Auswahlfeld bewirkte nichts mehr. Der Schlüssel darf jetzt nicht
    mehr durchgehen: eine alte App-Fassung, die ihn noch schickt, soll eine
    klare Absage bekommen statt einen Wert in die Datenbank zu legen, den
    niemand liest.
    """
    antwort = client.post("/api/einstellungen", json={"key": "thema", "wert": "rot"})
    assert antwort.status_code == 400


def test_unbekannter_schluessel_wird_abgewiesen(client: TestClient) -> None:
    """Sonst könnte man über die Schnittstelle beliebige Werte ablegen."""
    antwort = client.post("/api/einstellungen", json={"key": "admin", "wert": "1"})
    assert antwort.status_code == 400

    import src.main as m

    assert "admin" not in m.get_store().get_settings()


def test_ungueltiger_wert_wird_nicht_gespeichert(client: TestClient) -> None:
    """Eine kaputte Zahl im Sammelintervall würde den Hintergrundlauf lahmlegen."""
    import src.main as m

    for wert in ("null", "-5", "99999", ""):
        antwort = client.post("/api/einstellungen", json={"key": "sammel_minuten", "wert": wert})
        assert antwort.status_code == 400, f"{wert!r} wurde angenommen"

    assert "sammel_minuten" not in m.get_store().get_settings()


def test_api_einstellungen_liefert_alle_posten(client: TestClient) -> None:
    """Das Frontend baut die Seite aus dieser Liste, nicht aus festem HTML."""
    daten = client.get("/api/einstellungen").json()
    keys = {p["key"] for p in daten["posten"]}
    assert keys == {e.key for e in EINSTELLUNGEN}
    for e in EINSTELLUNGEN:
        assert e.key in daten["werte"]


def test_api_homelab_zeigt_stoerung_getrennt(client: TestClient) -> None:
    """Was kaputt ist, steht in einer eigenen Liste vor allen Diensten."""
    import src.main as m

    m.get_store().replace_services([_dienst("Laeuft"), _dienst("Kaputt", status=0, msg="400")])
    daten = client.get("/api/homelab").json()
    assert [d["name"] for d in daten["stoerungen"]] == ["Kaputt"]
    assert {d["name"] for d in daten["dienste"]} == {"Laeuft", "Kaputt"}


def test_alte_seiten_leiten_in_die_app(client: TestClient) -> None:
    for pfad in ("/homelab", "/einstellungen", "/dokumente", "/gesundheit"):
        antwort = client.get(pfad, follow_redirects=False)
        assert antwort.status_code == 307, pfad
        assert antwort.headers["location"] == f"/#{pfad}"
