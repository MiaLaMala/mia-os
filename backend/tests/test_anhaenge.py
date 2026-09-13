"""Dokumente an Eintraegen.

Der Index kannte die Dateien, die Sammlung kannte die Eintraege, beide wussten
nichts voneinander. Diese Tests halten fest, was beim Verbinden schiefgehen
kann: der Crawl vergibt neue IDs, Dateien werden umbenannt, und ein geloeschter
Eintrag darf keine Waise hinterlassen.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from src.store import Store


def _doc(path: str, name: str = "", file_id: str = "42") -> dict[str, Any]:
    return {
        "path": path,
        "name": name or path.rsplit("/", 1)[-1],
        "folder": path.rsplit("/", 1)[0] or "/",
        "ext": "." + path.rsplit(".", 1)[-1],
        "size_bytes": 1024,
        "modified_at": "2026-09-01T10:00:00+00:00",
        "file_id": file_id,
    }


# --- Store ---------------------------------------------------------------


def test_anhaengen_und_lesen(store: Store) -> None:
    store.replace_documents("nextcloud", [_doc("/Dokumente/Bescheid.pdf")])
    eintrag = store.create_entry("Widerspruch Kasse")

    assert store.link_document(eintrag, "nextcloud", "/Dokumente/Bescheid.pdf", "Bescheid.pdf")

    haenge = store.documents_for_entry(eintrag)
    assert [d["name"] for d in haenge] == ["Bescheid.pdf"]
    assert haenge[0]["fehlt"] is False


def test_zweimal_anhaengen_ist_kein_fehler(store: Store) -> None:
    """Ein Doppelklick darf nicht in einen 500er laufen."""
    store.replace_documents("nextcloud", [_doc("/a.pdf")])
    eintrag = store.create_entry("Test")

    assert store.link_document(eintrag, "nextcloud", "/a.pdf", "a.pdf") is True
    assert store.link_document(eintrag, "nextcloud", "/a.pdf", "a.pdf") is False
    assert len(store.documents_for_entry(eintrag)) == 1


def test_verknuepfung_ueberlebt_neuen_crawl(store: Store) -> None:
    """Der Crawl vergibt neue IDs. Verknuepft wird deshalb ueber den Pfad.

    Genau daran ist frueher schon der Editor-Link gestorben: nach spaetestens
    15 Minuten zeigte er ins Leere.
    """
    store.replace_documents("nextcloud", [_doc("/Bescheid.pdf")])
    eintrag = store.create_entry("Widerspruch")
    store.link_document(eintrag, "nextcloud", "/Bescheid.pdf", "Bescheid.pdf")
    alte_id = store.documents_for_entry(eintrag)[0]["id"]

    # Ein zweiter Lauf, bei dem die Datei kurz weg war und wiederkam.
    store.replace_documents("nextcloud", [])
    store.replace_documents("nextcloud", [_doc("/Bescheid.pdf")])

    haenge = store.documents_for_entry(eintrag)
    assert len(haenge) == 1
    assert haenge[0]["fehlt"] is False
    assert haenge[0]["id"] != alte_id


def test_verschwundene_datei_bleibt_sichtbar(store: Store) -> None:
    """Eine verschobene Datei darf nicht still aus der Anzeige fallen.

    Sonst sieht ein Behoerdeneintrag aus, als haette nie ein Bescheid
    danebengelegen.
    """
    store.replace_documents("nextcloud", [_doc("/Bescheid.pdf")])
    eintrag = store.create_entry("Widerspruch")
    store.link_document(eintrag, "nextcloud", "/Bescheid.pdf", "Bescheid.pdf")

    store.replace_documents("nextcloud", [_doc("/Archiv/Bescheid.pdf")])

    haenge = store.documents_for_entry(eintrag)
    assert len(haenge) == 1
    assert haenge[0]["fehlt"] is True
    assert haenge[0]["name"] == "Bescheid.pdf"


def test_abhaengen(store: Store) -> None:
    store.replace_documents("nextcloud", [_doc("/a.pdf")])
    eintrag = store.create_entry("Test")
    store.link_document(eintrag, "nextcloud", "/a.pdf", "a.pdf")

    assert store.unlink_document(eintrag, "nextcloud", "/a.pdf") is True
    assert store.documents_for_entry(eintrag) == []
    # Die Datei selbst bleibt im Index.
    assert store.count_documents() == 1


def test_geloeschter_eintrag_laesst_keine_waise(store: Store) -> None:
    """Ohne Aufraeumen erbt der naechste Eintrag mit derselben ID die Anhaenge."""
    store.replace_documents("nextcloud", [_doc("/a.pdf")])
    eintrag = store.create_entry("Weg damit")
    store.link_document(eintrag, "nextcloud", "/a.pdf", "a.pdf")

    store.delete_entry(eintrag)

    assert store.document_counts() == {}
    assert store.entries_for_document("nextcloud", "/a.pdf") == []


def test_geloeschte_seite_nimmt_anhaenge_mit(store: Store) -> None:
    store.replace_documents("nextcloud", [_doc("/a.pdf")])
    seite = store.create_page("Behörden", hat_sammlung=True)
    eintrag = store.create_entry("Antrag", page_id=seite)
    store.link_document(eintrag, "nextcloud", "/a.pdf", "a.pdf")

    store.delete_page(seite)

    assert store.document_counts() == {}


def test_zaehler_und_rueckrichtung(store: Store) -> None:
    store.replace_documents("nextcloud", [_doc("/a.pdf"), _doc("/b.pdf")])
    eins = store.create_entry("Eins")
    zwei = store.create_entry("Zwei")
    store.link_document(eins, "nextcloud", "/a.pdf", "a.pdf")
    store.link_document(eins, "nextcloud", "/b.pdf", "b.pdf")
    store.link_document(zwei, "nextcloud", "/a.pdf", "a.pdf")

    assert store.document_counts() == {eins: 2, zwei: 1}
    assert [e["titel"] for e in store.entries_for_document("nextcloud", "/a.pdf")] == [
        "Eins",
        "Zwei",
    ]

    gebuendelt = store.entries_for_documents([("nextcloud", "/a.pdf"), ("nextcloud", "/b.pdf")])
    assert {t["titel"] for t in gebuendelt[("nextcloud", "/a.pdf")]} == {"Eins", "Zwei"}
    assert [t["titel"] for t in gebuendelt[("nextcloud", "/b.pdf")]] == ["Eins"]


def test_gebuendelte_abfrage_ohne_dateien(store: Store) -> None:
    """Eine leere Dokumentenseite darf kein kaputtes SQL bauen."""
    assert store.entries_for_documents([]) == {}


# --- API -----------------------------------------------------------------


def _lege_dokument_an(client: TestClient, path: str = "/Dokumente/Bescheid.pdf") -> int:
    from src.main import get_store

    store = get_store()
    store.replace_documents("nextcloud", [_doc(path)])
    return int(store.list_documents()[0]["id"])


def test_api_anhaengen_lesen_loesen(client: TestClient) -> None:
    doc_id = _lege_dokument_an(client)
    eintrag = client.post("/api/sammlung", json={"titel": "Widerspruch"}).json()["eintrag"]

    antwort = client.post(f"/api/sammlung/{eintrag['id']}/dokumente", json={"dokument_id": doc_id})
    assert antwort.status_code == 200
    assert [d["name"] for d in antwort.json()["dokumente"]] == ["Bescheid.pdf"]

    gelesen = client.get(f"/api/sammlung/{eintrag['id']}/dokumente").json()["dokumente"]
    assert len(gelesen) == 1
    assert gelesen[0]["fehlt"] is False
    assert gelesen[0]["source"] == "nextcloud"

    weg = client.request(
        "DELETE",
        f"/api/sammlung/{eintrag['id']}/dokumente",
        params={"source": "nextcloud", "path": "/Dokumente/Bescheid.pdf"},
    )
    assert weg.status_code == 200
    assert client.get(f"/api/sammlung/{eintrag['id']}/dokumente").json()["dokumente"] == []


def test_api_unbekannter_eintrag_und_dokument(client: TestClient) -> None:
    doc_id = _lege_dokument_an(client)
    assert client.get("/api/sammlung/9999/dokumente").status_code == 404
    assert (
        client.post("/api/sammlung/9999/dokumente", json={"dokument_id": doc_id}).status_code == 404
    )

    eintrag = client.post("/api/sammlung", json={"titel": "X"}).json()["eintrag"]
    assert (
        client.post(
            f"/api/sammlung/{eintrag['id']}/dokumente", json={"dokument_id": 9999}
        ).status_code
        == 404
    )
    # Ohne Angabe ebenfalls 404 statt eines 500ers aus int(None).
    assert client.post(f"/api/sammlung/{eintrag['id']}/dokumente", json={}).status_code == 404


def test_api_loesen_ohne_verknuepfung(client: TestClient) -> None:
    eintrag = client.post("/api/sammlung", json={"titel": "X"}).json()["eintrag"]
    antwort = client.request(
        "DELETE",
        f"/api/sammlung/{eintrag['id']}/dokumente",
        params={"source": "nextcloud", "path": "/gibtsnicht.pdf"},
    )
    assert antwort.status_code == 404


def test_api_verschwundene_datei_hat_keinen_toten_link(client: TestClient) -> None:
    """Ohne das zeigt die Oberflaeche einen Editor-Link auf eine leere Seite."""
    from src.main import get_store

    doc_id = _lege_dokument_an(client)
    eintrag = client.post("/api/sammlung", json={"titel": "Widerspruch"}).json()["eintrag"]
    client.post(f"/api/sammlung/{eintrag['id']}/dokumente", json={"dokument_id": doc_id})

    get_store().replace_documents("nextcloud", [_doc("/woanders/Bescheid.pdf")])

    gelesen = client.get(f"/api/sammlung/{eintrag['id']}/dokumente").json()["dokumente"]
    assert gelesen[0]["fehlt"] is True
    assert gelesen[0]["link"] == ""
    assert gelesen[0]["vorschau"] == ""
    assert gelesen[0]["name"] == "Bescheid.pdf"


def test_sammlung_liefert_anhangzahlen(client: TestClient) -> None:
    doc_id = _lege_dokument_an(client)
    eintrag = client.post("/api/sammlung", json={"titel": "Widerspruch"}).json()["eintrag"]
    client.post(f"/api/sammlung/{eintrag['id']}/dokumente", json={"dokument_id": doc_id})

    daten = client.get("/api/sammlung").json()
    assert daten["anhaenge"][str(eintrag["id"])] == 1


def test_dokumentenliste_nennt_ihre_eintraege(client: TestClient) -> None:
    doc_id = _lege_dokument_an(client)
    eintrag = client.post("/api/sammlung", json={"titel": "Widerspruch Kasse"}).json()["eintrag"]
    client.post(f"/api/sammlung/{eintrag['id']}/dokumente", json={"dokument_id": doc_id})

    treffer = client.get("/api/dokumente").json()["treffer"]
    passend = [t for t in treffer if t["name"] == "Bescheid.pdf"]
    assert [e["titel"] for e in passend[0]["eintraege"]] == ["Widerspruch Kasse"]


def test_eintrag_loeschen_raeumt_ueber_die_api_auf(client: TestClient) -> None:
    doc_id = _lege_dokument_an(client)
    eintrag = client.post("/api/sammlung", json={"titel": "Weg"}).json()["eintrag"]
    client.post(f"/api/sammlung/{eintrag['id']}/dokumente", json={"dokument_id": doc_id})

    client.delete(f"/api/sammlung/{eintrag['id']}")

    assert client.get("/api/sammlung").json()["anhaenge"] == {}
