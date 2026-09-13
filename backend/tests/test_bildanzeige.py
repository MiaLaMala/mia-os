"""Bilder gross ansehen.

Anlass ist Mias Frage vom 09.09.2026: „Wieso kann ich eigentlich keine jpegs
oeffnen?" Die Antwort war ein Konstruktionsfehler. Die Liste, die entschied ob
eine Datei anklickbar ist, war ``editor.ANZEIGBAR``, und das ist die Liste
dessen, was OnlyOffice kann. Ein Dokumenteneditor faengt mit einem JPEG nichts
an, also standen Bilder nirgends und der Klick ging ins Leere. Ausgerechnet
ein abfotografierter Beleg war damit das Einzige, was sich nicht oeffnen liess.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 40


def _dokument(client: TestClient, name: str, ext: str, pfad: str | None = None) -> int:
    """Eine Datei in den Index legen und ihre ID liefern."""
    from src.main import get_store

    return get_store().upsert_document(
        {
            "source": "nextcloud",
            "path": pfad or f"/Dokumente/00 Belege/{name}",
            "name": name,
            "folder": "/Dokumente/00 Belege",
            "ext": ext,
            "size_bytes": len(JPG),
            "modified_at": "2026-09-09T20:00:00+00:00",
            "file_id": "42",
        }
    )


def test_bild_ist_anklickbar(client: TestClient) -> None:
    """Ein Bild bekommt einen Link. Das war der eigentliche Fehler.

    Vorher stand hier ein leerer String, weil Bilder in keiner Liste
    auftauchten, und die Kachel war tot.
    """
    _dokument(client, "2026-09-03 Bescheid.jpg", ".jpg")

    treffer = client.get("/api/dokumente", params={"q": "Bescheid"}).json()["treffer"]
    assert treffer, "Dokument nicht gefunden"
    assert treffer[0]["link"] == f"/bild/{treffer[0]['id']}"
    assert treffer[0]["anzeigbar"] is True


def test_pdf_geht_weiter_in_den_editor(client: TestClient) -> None:
    """Der neue Weg darf den alten nicht kapern.

    PDFs und Office-Dateien gehoeren weiter zu OnlyOffice, nur Bilder nehmen
    die eigene Anzeige.
    """
    _dokument(client, "2026-09-03 Bescheid.pdf", ".pdf")

    treffer = client.get("/api/dokumente", params={"q": "Bescheid"}).json()["treffer"]
    assert treffer[0]["link"] == f"/bearbeiten/{treffer[0]['id']}"


def test_heic_bleibt_ohne_link(client: TestClient) -> None:
    """HEIC zeigt kein Browser an.

    Ein Klick, der zu einem leeren Kasten fuehrt, ist schlechter als kein
    Klick: Mia sucht dann den Fehler bei sich.
    """
    _dokument(client, "IMG_4711.heic", ".heic")

    treffer = client.get("/api/dokumente", params={"q": "IMG"}).json()["treffer"]
    assert treffer[0]["link"] == ""
    assert treffer[0]["anzeigbar"] is False


def test_bildseite_zeigt_das_bild(client: TestClient) -> None:
    """Die Seite laedt und verweist auf die Datei."""
    doc_id = _dokument(client, "2026-09-03 Bescheid.jpg", ".jpg")

    antwort = client.get(f"/bild/{doc_id}")
    assert antwort.status_code == 200
    assert f"/bilddatei/{doc_id}" in antwort.text
    assert "2026-09-03 Bescheid.jpg" in antwort.text


def test_bildseite_lehnt_nicht_bilder_ab(client: TestClient) -> None:
    """Ein PDF durch die Bildanzeige zu schicken ergibt einen leeren Kasten."""
    doc_id = _dokument(client, "2026-09-03 Bescheid.pdf", ".pdf")

    assert client.get(f"/bild/{doc_id}").status_code == 415
    assert client.get(f"/bilddatei/{doc_id}").status_code == 415


def test_unbekanntes_dokument_ist_404(client: TestClient) -> None:
    assert client.get("/bild/999999").status_code == 404
    assert client.get("/bilddatei/999999").status_code == 404


def test_bilddatei_liefert_die_volle_aufloesung(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nicht ueber /vorschau: das ist auf 256 Pixel gedeckelt.

    Wer ein Blatt lesen will, braucht die volle Aufloesung, sonst ist das
    Aktenzeichen ein grauer Fleck.
    """
    import src.main as main_modul

    geholt: list[str] = []

    async def holen(pfad: str) -> tuple[bytes, str]:
        geholt.append(pfad)
        return JPG, "image/jpeg"

    monkeypatch.setattr(main_modul.editor, "datei_holen", holen)
    doc_id = _dokument(client, "2026-09-03 Bescheid.jpg", ".jpg")

    antwort = client.get(f"/bilddatei/{doc_id}")
    assert antwort.status_code == 200
    assert antwort.content == JPG
    assert antwort.headers["content-type"].startswith("image/")
    assert geholt == ["/Dokumente/00 Belege/2026-09-03 Bescheid.jpg"]


def test_nextcloud_weg_ist_kein_500(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ist Nextcloud nicht erreichbar, sagt die Seite das, statt zu sterben."""
    import src.main as main_modul

    async def kaputt(pfad: str) -> tuple[bytes, str]:
        raise httpx.ConnectError("weg")

    monkeypatch.setattr(main_modul.editor, "datei_holen", kaputt)
    doc_id = _dokument(client, "2026-09-03 Bescheid.jpg", ".jpg")

    assert client.get(f"/bilddatei/{doc_id}").status_code == 502


def test_zurueck_weg_bleibt_erhalten(client: TestClient) -> None:
    """Der Zurueck-Knopf soll wieder in die gefilterte Liste fuehren.

    Ohne das landet Mia nach jedem Beleg auf der ungefilterten Startseite und
    muss ihre Suche neu tippen.
    """
    doc_id = _dokument(client, "2026-09-03 Bescheid.jpg", ".jpg")

    antwort = client.get(f"/bild/{doc_id}", params={"zurueck": "#/dokumente?q=Bescheid"})
    assert "#/dokumente?q=Bescheid" in antwort.text


def test_ohne_zurueck_geht_es_zu_den_dokumenten(client: TestClient) -> None:
    """Ein direkter Aufruf ohne Zustand darf keinen leeren Link erzeugen."""
    doc_id = _dokument(client, "2026-09-03 Bescheid.jpg", ".jpg")

    antwort = client.get(f"/bild/{doc_id}")
    assert "#/dokumente" in antwort.text


def test_name_wird_escaped(client: TestClient) -> None:
    """Der Dateiname kommt aus Nextcloud und darf kein HTML einschleusen.

    Eine Datei, die jemand ``<script>...</script>.jpg`` nennt, waere sonst ein
    Loch. Jinja escaped von selbst, der Test haelt das fest.
    """
    doc_id = _dokument(client, "<script>alert(1)</script>.jpg", ".jpg")

    antwort = client.get(f"/bild/{doc_id}")
    assert "<script>alert(1)</script>" not in antwort.text
    assert "&lt;script&gt;" in antwort.text


def test_beleg_landet_klickbar_am_eintrag(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Der ganze Weg: Foto rein, als PDF abgelegt, am Eintrag anklickbar.

    Das ist der Fall, den Mia tatsaechlich hat. Vorher endete er in einer
    Kachel, die sich nicht oeffnen liess.
    """
    import src.api as api_modul

    async def ablegen(inhalt: bytes, name: str) -> tuple[str, str]:
        return f"/Dokumente/00 Belege/{name}", "42"

    async def lesen(bild: bytes, sprache: str = "") -> str:
        return "Aktenzeichen 43-044"

    async def als_pdf(bild: bytes, sprache: str = "") -> bytes | None:
        return b"%PDF-1.5\nfake"

    monkeypatch.setattr(api_modul.belege, "ablegen", ablegen)
    monkeypatch.setattr(api_modul.ocr, "verfuegbar", lambda: True)
    monkeypatch.setattr(api_modul.ocr, "text_lesen", lesen)
    monkeypatch.setattr(api_modul.ocr, "als_pdf", als_pdf)
    monkeypatch.setattr(api_modul.scanner, "verarbeiten", lambda *a, **k: (JPG, True))

    eintrag = client.post("/api/sammlung", json={"titel": "Widerspruch Kasse"}).json()["eintrag"]
    antwort = client.post(
        f"/api/sammlung/{eintrag['id']}/beleg",
        files={"datei": ("IMG_4711.jpg", JPG, "image/jpeg")},
        data={"scannen": "true"},
    )

    anhaenge: list[dict[str, Any]] = antwort.json()["dokumente"]
    assert anhaenge[0]["name"].endswith(".pdf")
    assert anhaenge[0]["link"], "Der Beleg am Eintrag ist nicht anklickbar"
