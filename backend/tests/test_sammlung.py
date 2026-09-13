"""Die Eintragssammlung: eine Datenbank, viele Ansichten.

Das Notion-Modell. Kalender, Tabelle, Board und Liste sind Blicke auf
dieselben Zeilen, nicht getrennte Werkzeuge.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _anlegen(client: TestClient, titel: str, **rest: object) -> dict:
    antwort = client.post("/api/sammlung", json={"titel": titel, **rest})
    assert antwort.status_code == 200, antwort.text
    return antwort.json()["eintrag"]


# --- Grundlagen -----------------------------------------------------------


def test_sammlung_startet_mit_eigenschaften(client: TestClient) -> None:
    """Eine leere Sammlung ohne Spalten wäre ratlos."""
    daten = client.get("/api/sammlung").json()
    namen = [p["name"] for p in daten["eigenschaften"]]
    assert "Status" in namen
    assert "Bereich" in namen


def test_eintrag_anlegen_und_lesen(client: TestClient) -> None:
    e = _anlegen(
        client,
        "Steuer-ID beantragen",
        eigenschaften={"status": "dran", "prio": "hoch"},
        datum="2026-09-10",
    )
    assert e["titel"] == "Steuer-ID beantragen"
    assert e["eigenschaften"]["status"] == "dran"
    assert e["datum"] == "2026-09-10"

    gelesen = client.get(f"/api/sammlung/{e['id']}").json()["eintrag"]
    assert gelesen["titel"] == e["titel"]


def test_eintrag_ohne_titel_wird_abgewiesen(client: TestClient) -> None:
    assert client.post("/api/sammlung", json={"titel": "  "}).status_code == 400
    assert client.post("/api/sammlung", json={}).status_code == 400


def test_kaputtes_datum_wird_abgewiesen(client: TestClient) -> None:
    r = client.post("/api/sammlung", json={"titel": "Test", "datum": "irgendwann"})
    assert r.status_code == 400


def test_unbekannter_eintrag_gibt_404(client: TestClient) -> None:
    assert client.get("/api/sammlung/9999").status_code == 404
    assert client.patch("/api/sammlung/9999", json={"titel": "x"}).status_code == 404
    assert client.delete("/api/sammlung/9999").status_code == 404


# --- Eigenschaften --------------------------------------------------------


def test_einzelne_eigenschaft_loescht_die_anderen_nicht(client: TestClient) -> None:
    """Der wichtigste Test: ein Klick auf Status darf die Tags nicht wegwerfen."""
    e = _anlegen(
        client,
        "Wohnung ummelden",
        eigenschaften={"status": "offen", "bereich": "Behörden", "prio": "hoch"},
    )
    r = client.patch(f"/api/sammlung/{e['id']}", json={"eigenschaft": "status", "wert": "fertig"})
    props = r.json()["eintrag"]["eigenschaften"]
    assert props == {"status": "fertig", "bereich": "Behörden", "prio": "hoch"}


def test_leerer_wert_entfernt_die_eigenschaft(client: TestClient) -> None:
    """Nicht als leerer Text speichern: dann steht ein leeres Feld im Board."""
    e = _anlegen(client, "Test", eigenschaften={"status": "offen", "prio": "hoch"})
    r = client.patch(f"/api/sammlung/{e['id']}", json={"eigenschaft": "prio", "wert": ""})
    assert r.json()["eintrag"]["eigenschaften"] == {"status": "offen"}


def test_eigene_spalte_anlegen(client: TestClient) -> None:
    r = client.post("/api/eigenschaften", json={"name": "Nächster Schritt", "art": "text"})
    assert r.status_code == 200
    keys = [p["key"] for p in r.json()["eigenschaften"]]
    # Umlaute werden umgeschrieben, sonst taugt der Schlüssel nicht.
    assert "naechster_schritt" in keys


def test_unbekannte_art_wird_abgewiesen(client: TestClient) -> None:
    r = client.post("/api/eigenschaften", json={"name": "Kaputt", "art": "zauberei"})
    assert r.status_code == 400


def test_spalte_loeschen(client: TestClient) -> None:
    client.post("/api/eigenschaften", json={"name": "Weg damit", "art": "text"})
    assert client.delete("/api/eigenschaften/weg_damit").status_code == 200
    assert client.delete("/api/eigenschaften/weg_damit").status_code == 404


# --- Die Ansichten teilen sich die Daten ---------------------------------


def test_alle_ansichten_sehen_dieselben_zeilen(client: TestClient) -> None:
    """Der Kern des Notion-Modells.

    Ein Eintrag mit Datum steht im Kalender UND in Tabelle, Board und Liste.
    Es gibt nicht vier getrennte Sammlungen.
    """
    _anlegen(client, "Mit Datum", datum="2026-09-10", eigenschaften={"status": "offen"})
    _anlegen(client, "Ohne Datum", eigenschaften={"status": "offen"})

    alle = client.get("/api/sammlung").json()["eintraege"]
    assert len(alle) == 2, "Tabelle/Board/Liste sehen alles"

    # Der Kalender fragt nach einem Zeitraum.
    im_zeitraum = client.get(
        "/api/sammlung", params={"von": "2026-09-01", "bis": "2026-09-30"}
    ).json()["eintraege"]
    assert [e["titel"] for e in im_zeitraum] == ["Mit Datum"]


def test_undatierte_stehen_hinten(client: TestClient) -> None:
    """Was keine Frist hat, drängt nicht."""
    _anlegen(client, "ohne")
    _anlegen(client, "spät", datum="2026-09-20")
    _anlegen(client, "früh", datum="2026-09-01")

    titel = [e["titel"] for e in client.get("/api/sammlung").json()["eintraege"]]
    assert titel == ["früh", "spät", "ohne"], titel


def test_suche(client: TestClient) -> None:
    _anlegen(client, "Krankmeldung faxen")
    _anlegen(client, "Zeugnis abholen", inhalt="liegt im Sekretariat")

    treffer = client.get("/api/sammlung", params={"suche": "Sekretariat"}).json()
    assert [e["titel"] for e in treffer["eintraege"]] == ["Zeugnis abholen"]


def test_archiviertes_ist_weg_aber_nicht_geloescht(client: TestClient) -> None:
    e = _anlegen(client, "Erledigt und weg")
    client.patch(f"/api/sammlung/{e['id']}", json={"archiviert": True})

    assert client.get("/api/sammlung").json()["eintraege"] == []
    mit = client.get("/api/sammlung", params={"archiv": True}).json()["eintraege"]
    assert [x["titel"] for x in mit] == ["Erledigt und weg"]


def test_eintrag_am_termin(client: TestClient) -> None:
    """Ein Eintrag kann an einem iCloud-Termin hängen."""
    e = _anlegen(client, "Zeugnis mitbringen", event_uid="uid-42")
    assert e["event_uid"] == "uid-42"

    am_termin = client.get("/api/termin/uid-42").json()
    assert [x["titel"] for x in am_termin["eintraege"]] == ["Zeugnis mitbringen"]


def test_kaputte_eigenschaften_killen_die_ansicht_nicht(client: TestClient) -> None:
    """Steht Unsinn in der JSON-Spalte, fehlen die Eigenschaften, nicht die Zeile."""
    import src.main as m

    e = _anlegen(client, "Wird kaputtgemacht")
    with m.get_store()._conn() as conn:
        conn.execute("UPDATE entries SET eigenschaften = 'kein json' WHERE id = ?", (e["id"],))

    alle = client.get("/api/sammlung").json()["eintraege"]
    assert [x["titel"] for x in alle] == ["Wird kaputtgemacht"]
    assert alle[0]["eigenschaften"] == {}


def test_eintrag_mit_datum_steht_im_kalender(client: TestClient) -> None:
    """Der Kern: der Kalender ist eine ANSICHT auf die Sammlung.

    Ein Eintrag mit Datum taucht dort auf, ohne dass ihn jemand kopiert.
    """
    _anlegen(client, "Steuer-ID nachfragen", datum="2026-09-10", eigenschaften={"status": "dran"})
    _anlegen(client, "Irgendwann mal")  # ohne Datum, gehört nicht in den Kalender

    daten = client.get("/api/termine", params={"von": "2026-09-01", "bis": "2026-09-30"}).json()
    aus_sammlung = [t for t in daten["termine"] if t.get("eintrag_id")]
    assert [t["title"] for t in aus_sammlung] == ["Steuer-ID nachfragen"]
    assert aus_sammlung[0]["allDay"] is True


def test_eintragsfarbe_kommt_vom_status(client: TestClient) -> None:
    """Fertig sieht im Kalender aus wie im Board: dieselbe Sache, dieselbe Farbe."""
    _anlegen(client, "Grün", datum="2026-09-11", eigenschaften={"status": "fertig"})
    daten = client.get("/api/termine", params={"von": "2026-09-01", "bis": "2026-09-30"}).json()
    eintrag = next(t for t in daten["termine"] if t.get("eintrag_id"))
    assert eintrag["farbe"] == "#30d158", "grün wie die Statusoption"


def test_eintrag_mit_zeit_ist_nicht_ganztags(client: TestClient) -> None:
    _anlegen(client, "Mit Uhrzeit", datum="2026-09-12", zeit="14:30")
    daten = client.get("/api/termine", params={"von": "2026-09-01", "bis": "2026-09-30"}).json()
    eintrag = next(t for t in daten["termine"] if t.get("eintrag_id"))
    assert eintrag["allDay"] is False
    assert eintrag["start"] == "2026-09-12T14:30"


# --- Seiten: Mias eigener Baum -------------------------------------------


def test_startseiten_werden_angelegt(client: TestClient) -> None:
    """Eine leere Seitenleiste wäre ratlos."""
    seiten = client.get("/api/seiten").json()["seiten"]
    assert [s["titel"] for s in seiten] == ["Alles", "Ausbildung", "Behörden", "Notizen"]


def test_unterseite_und_weg(client: TestClient) -> None:
    eltern = client.get("/api/seiten").json()["seiten"][1]
    kind = client.post(
        "/api/seiten", json={"titel": "Berufsschule", "parent_id": eltern["id"]}
    ).json()["seite"]

    daten = client.get(f"/api/seiten/{kind['id']}").json()
    assert [w["titel"] for w in daten["weg"]] == ["Ausbildung", "Berufsschule"]
    assert daten["unterseiten"] == []

    oben = client.get(f"/api/seiten/{eltern['id']}").json()
    assert [u["titel"] for u in oben["unterseiten"]] == ["Berufsschule"]


def test_seite_kann_nicht_in_sich_selbst(client: TestClient) -> None:
    """Sonst entsteht ein Kreis, den der Baum nicht mehr zeichnen kann."""
    s = client.post("/api/seiten", json={"titel": "Test"}).json()["seite"]
    assert client.patch(f"/api/seiten/{s['id']}", json={"parent_id": s["id"]}).status_code == 400


def test_kein_kreis_ueber_umwege(client: TestClient) -> None:
    a = client.post("/api/seiten", json={"titel": "A"}).json()["seite"]
    b = client.post("/api/seiten", json={"titel": "B", "parent_id": a["id"]}).json()["seite"]
    # A unter B hängen wäre ein Kreis: A -> B -> A
    r = client.patch(f"/api/seiten/{a['id']}", json={"parent_id": b["id"]})
    assert r.status_code == 400
    assert "Kreis" in r.json()["detail"]


def test_seite_loeschen_nimmt_unterseiten_mit(client: TestClient) -> None:
    a = client.post("/api/seiten", json={"titel": "Oben", "hat_sammlung": True}).json()["seite"]
    b = client.post("/api/seiten", json={"titel": "Drunter", "parent_id": a["id"]}).json()["seite"]
    _anlegen(client, "Eintrag drin", page_id=a["id"])

    assert client.delete(f"/api/seiten/{a['id']}").status_code == 200
    uebrig = [s["id"] for s in client.get("/api/seiten").json()["seiten"]]
    assert a["id"] not in uebrig
    assert b["id"] not in uebrig, "Unterseite hängt sonst im Nichts"
    # Der Eintrag der gelöschten Seite ist auch weg.
    assert client.get("/api/sammlung").json()["eintraege"] == []


def test_eintraege_gehoeren_zu_ihrer_seite(client: TestClient) -> None:
    a = client.post("/api/seiten", json={"titel": "A", "hat_sammlung": True}).json()["seite"]
    b = client.post("/api/seiten", json={"titel": "B", "hat_sammlung": True}).json()["seite"]
    _anlegen(client, "Auf A", page_id=a["id"])
    _anlegen(client, "Auf B", page_id=b["id"])

    assert [e["titel"] for e in client.get(f"/api/seiten/{a['id']}").json()["eintraege"]] == [
        "Auf A"
    ]
    assert [e["titel"] for e in client.get(f"/api/seiten/{b['id']}").json()["eintraege"]] == [
        "Auf B"
    ]


def test_seite_ohne_sammlung_liefert_keine_eintraege(client: TestClient) -> None:
    s = client.post("/api/seiten", json={"titel": "Nur Text"}).json()["seite"]
    assert client.get(f"/api/seiten/{s['id']}").json()["eintraege"] == []


def test_unbekannte_seite_gibt_404(client: TestClient) -> None:
    assert client.get("/api/seiten/9999").status_code == 404
    assert client.delete("/api/seiten/9999").status_code == 404


def test_alte_datenbank_bekommt_neue_spalte(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Der Fehler, an dem der Deploy starb.

    SCHEMA enthält einen Index auf entries(page_id). Fehlt die Spalte in
    einer bestehenden Datenbank, scheitert executescript, BEVOR die
    Migration überhaupt läuft. Lokal fiel das nie auf, weil jeder Test mit
    einer frischen Datei startet.
    """
    import sqlite3

    from src.store import Store

    pfad = tmp_path / "alt.db"
    conn = sqlite3.connect(pfad)
    conn.execute(
        "CREATE TABLE entries (id INTEGER PRIMARY KEY, titel TEXT NOT NULL DEFAULT '',"
        " inhalt TEXT NOT NULL DEFAULT '', eigenschaften TEXT NOT NULL DEFAULT '{}',"
        " datum TEXT NOT NULL DEFAULT '', zeit TEXT NOT NULL DEFAULT '',"
        " event_uid TEXT NOT NULL DEFAULT '', sortierung REAL NOT NULL DEFAULT 0,"
        " archiviert INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,"
        " updated_at TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO entries (titel, created_at, updated_at) VALUES ('Alt', 'x', 'x')")
    conn.commit()
    conn.close()

    store = Store(str(pfad))
    # Kein Absturz, und die alten Daten sind noch da.
    assert [e["titel"] for e in store.list_entries()] == ["Alt"]
    # Die neue Spalte ist ergänzt.
    assert store.create_page("Neu") > 0


def test_store_zweimal_starten_ist_harmlos(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Bei jedem Containerstart läuft die Migration erneut."""
    from src.store import Store

    pfad = str(tmp_path / "doppelt.db")
    erst = Store(pfad)
    erst.create_page("Bleibt")
    zweit = Store(pfad)
    assert [p["titel"] for p in zweit.list_pages()] == ["Bleibt"]
