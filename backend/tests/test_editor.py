"""Editor-Bruecke: Signaturen, JWT und Rueckschreiben.

Der Rueckruf ueberschreibt echte Dateien in Mias Nextcloud. Deshalb ist hier
mehr Sorgfalt angebracht als bei einer Anzeige-Route.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest

from src import editor


@pytest.fixture(autouse=True)
def _geheimnis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(editor.settings, "onlyoffice_jwt_secret", "test-geheimnis")


# --- Eigene Signaturen ----------------------------------------------------


def test_signatur_gilt_fuer_ihr_dokument() -> None:
    merkmal = editor.signiere(42)
    assert editor.pruefe(42, merkmal) is True


def test_signatur_gilt_nicht_fuer_andere_dokumente() -> None:
    """Wer eine gueltige Adresse hat, kommt damit nicht an alles andere."""
    merkmal = editor.signiere(42)
    assert editor.pruefe(43, merkmal) is False


def test_signatur_laeuft_ab(monkeypatch: pytest.MonkeyPatch) -> None:
    merkmal = editor.signiere(42)
    # Echten Zeitwert vorher festhalten: ein Lambda, das time.time() aufruft,
    # waehrend es time.time() ersetzt, ruft sich selbst auf.
    spaeter = time.time() + editor.GUELTIG_SEKUNDEN + 60
    monkeypatch.setattr(time, "time", lambda: spaeter)
    assert editor.pruefe(42, merkmal) is False


@pytest.mark.parametrize("murks", ["", "kaputt", "123.abc", "abc.def", "999999999"])
def test_signatur_weist_unsinn_ab(murks: str) -> None:
    assert editor.pruefe(42, murks) is False


def test_signatur_haengt_am_geheimnis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wechselt das Geheimnis, werden alte Adressen ungueltig."""
    merkmal = editor.signiere(42)
    monkeypatch.setattr(editor.settings, "onlyoffice_jwt_secret", "anderes")
    assert editor.pruefe(42, merkmal) is False


# --- JWT ------------------------------------------------------------------


def test_jwt_hin_und_zurueck() -> None:
    nutzlast = {"status": 2, "url": "https://beispiel/datei.docx"}
    geprueft = editor.jwt_pruefen(editor.jwt_signieren(nutzlast))
    assert geprueft == nutzlast


def test_jwt_mit_falscher_signatur_faellt_durch() -> None:
    token = editor.jwt_signieren({"status": 2})
    kopf, koerper, _ = token.split(".")
    assert editor.jwt_pruefen(f"{kopf}.{koerper}.gefaelscht") is None


@pytest.mark.parametrize("murks", ["", "a.b", "kein-jwt", "a.b.c.d"])
def test_jwt_weist_unsinn_ab(murks: str) -> None:
    assert editor.jwt_pruefen(murks) is None


# --- Editor-Typen ---------------------------------------------------------


@pytest.mark.parametrize(
    ("ext", "erwartet"),
    [(".docx", "word"), (".xlsx", "cell"), (".pptx", "slide"), (".pdf", "word")],
)
def test_editor_typ(ext: str, erwartet: str) -> None:
    assert editor.editor_typ(ext) == erwartet


def test_pdf_ist_anzeigbar_aber_nicht_bearbeitbar() -> None:
    """OnlyOffice zeigt PDFs, bearbeitet sie aber nicht."""
    assert ".pdf" in editor.ANZEIGBAR
    assert ".pdf" not in editor.BEARBEITBAR


def test_schluessel_aendert_sich_mit_der_datei() -> None:
    """Sonst zeigt OnlyOffice eine veraltete Fassung aus dem Zwischenspeicher."""
    a = {"id": 1, "modified_at": "2026-09-01T00:00:00+00:00", "size_bytes": 100}
    b = {"id": 1, "modified_at": "2026-09-05T00:00:00+00:00", "size_bytes": 100}
    assert editor.dokument_schluessel(a) != editor.dokument_schluessel(b)
    assert editor.dokument_schluessel(a) == editor.dokument_schluessel(dict(a))


# --- Nextcloud-Pfade ------------------------------------------------------


def test_webdav_pfad_kodiert_umlaute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(editor.settings, "nextcloud_url", "https://nas.example")
    monkeypatch.setattr(editor.settings, "nextcloud_user", "mia")
    url = editor._webdav_url("/Dokumente/01 Persönliches/Ausweis.pdf")
    assert "Pers%C3%B6nliches" in url
    assert "%20" in url
    assert url.startswith("https://nas.example/remote.php/dav/files/mia/")


# --- Routen ---------------------------------------------------------------


@pytest.fixture
def eingerichtet(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Ein Client mit vollstaendig konfiguriertem Editor und einem Dokument."""
    import src.main as m

    for modul in (m.settings, editor.settings):
        monkeypatch.setattr(modul, "onlyoffice_url", "https://office.example", raising=False)
        monkeypatch.setattr(
            modul, "public_base_url", "http://mia-os.example.invalid:8080", raising=False
        )
        monkeypatch.setattr(modul, "onlyoffice_jwt_secret", "test-geheimnis", raising=False)
        monkeypatch.setattr(modul, "nextcloud_url", "https://nas.example", raising=False)
        monkeypatch.setattr(modul, "nextcloud_user", "mia", raising=False)
        monkeypatch.setattr(modul, "nextcloud_password", "geheim", raising=False)

    m.get_store().replace_documents(
        "nextcloud",
        [
            {
                "path": "/Dokumente/Brief.docx",
                "name": "Brief.docx",
                "folder": "/Dokumente",
                "ext": ".docx",
                "size_bytes": 2048,
                "modified_at": "2026-09-05T00:00:00+00:00",
                "file_id": "9426",
            }
        ],
    )
    return m.get_store().list_documents()[0]["id"]


def test_editor_seite_baut_konfiguration(client: Any, eingerichtet: int) -> None:
    resp = client.get(f"/bearbeiten/{eingerichtet}")
    assert resp.status_code == 200
    assert "DocsAPI" in resp.text
    # Der Document Server muss Mia OS erreichen, nicht der Browser.
    assert "mia-os.example.invalid:8080/datei/" in resp.text
    assert "callbackUrl" in resp.text


def test_datei_braucht_gueltige_signatur(client: Any, eingerichtet: int) -> None:
    """Ohne Merkmal keine Datei, auch wenn jemand die ID kennt."""
    assert client.get(f"/datei/{eingerichtet}").status_code == 403
    assert client.get(f"/datei/{eingerichtet}?m=erfunden").status_code == 403


def test_callback_braucht_gueltige_signatur(client: Any, eingerichtet: int) -> None:
    resp = client.post(f"/api/onlyoffice/callback/{eingerichtet}", json={"status": 2})
    assert resp.status_code == 403


def test_callback_ignoriert_zwischenstaende(client: Any, eingerichtet: int) -> None:
    """Status 1 heisst 'wird gerade bearbeitet', da gibt es nichts zu speichern."""
    m = editor.signiere(eingerichtet)
    nutzlast = {"status": 1}
    resp = client.post(
        f"/api/onlyoffice/callback/{eingerichtet}?m={m}",
        json={"token": editor.jwt_signieren(nutzlast), **nutzlast},
    )
    assert resp.status_code == 200
    assert resp.json() == {"error": 0}


def test_callback_weist_gefaelschtes_jwt_ab(client: Any, eingerichtet: int) -> None:
    """Sonst koennte jemand mit erratener ID beliebige Inhalte einschleusen."""
    m = editor.signiere(eingerichtet)
    resp = client.post(
        f"/api/onlyoffice/callback/{eingerichtet}?m={m}",
        json={"status": 2, "url": "https://boese.example/schadcode.docx", "token": "a.b.c"},
    )
    assert resp.status_code == 403


def test_callback_schreibt_zurueck(
    client: Any, eingerichtet: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Der ganze Weg: Aenderung abholen und nach Nextcloud legen."""
    geschrieben: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            geschrieben["pfad"] = str(request.url)
            geschrieben["inhalt"] = request.content
            return httpx.Response(204)
        return httpx.Response(200, content=b"NEUER INHALT")

    transport = httpx.MockTransport(handler)
    echt = httpx.AsyncClient

    def gefaelscht(*a: Any, **kw: Any) -> httpx.AsyncClient:
        kw["transport"] = transport
        return echt(*a, **kw)

    monkeypatch.setattr("src.main.httpx.AsyncClient", gefaelscht)
    monkeypatch.setattr("src.editor.httpx.AsyncClient", gefaelscht)

    m = editor.signiere(eingerichtet)
    nutzlast = {"status": 2, "url": "https://office.example/fertig.docx"}
    resp = client.post(
        f"/api/onlyoffice/callback/{eingerichtet}?m={m}",
        json={"token": editor.jwt_signieren(nutzlast), **nutzlast},
    )

    assert resp.json() == {"error": 0}
    assert geschrieben["inhalt"] == b"NEUER INHALT"
    assert geschrieben["pfad"].endswith("/Dokumente/Brief.docx")


def test_callback_folgt_weiterleitungen(
    client: Any, eingerichtet: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Der Download der bearbeiteten Fassung kann eine Weiterleitung sein.

    httpx folgt von sich aus KEINER Weiterleitung. Ohne follow_redirects
    scheiterte das Speichern mit "Redirect response '303 See Other'", und Mia
    haette nur "konnte nicht gespeichert werden" gesehen. Am 05.09.2026 im
    Test gegen die echte Nextcloud aufgefallen, nicht im Code.
    """
    geschrieben: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            geschrieben["inhalt"] = request.content
            return httpx.Response(204)
        if "umgeleitet" not in str(request.url):
            return httpx.Response(303, headers={"location": "https://office.example/umgeleitet"})
        return httpx.Response(200, content=b"NACH DER WEITERLEITUNG")

    transport = httpx.MockTransport(handler)
    echt = httpx.AsyncClient

    def gefaelscht(*a: Any, **kw: Any) -> httpx.AsyncClient:
        kw["transport"] = transport
        return echt(*a, **kw)

    monkeypatch.setattr("src.main.httpx.AsyncClient", gefaelscht)
    monkeypatch.setattr("src.editor.httpx.AsyncClient", gefaelscht)

    m = editor.signiere(eingerichtet)
    nutzlast = {"status": 2, "url": "https://office.example/fertig.docx"}
    resp = client.post(
        f"/api/onlyoffice/callback/{eingerichtet}?m={m}",
        json={"token": editor.jwt_signieren(nutzlast), **nutzlast},
    )

    assert resp.json() == {"error": 0}
    assert geschrieben["inhalt"] == b"NACH DER WEITERLEITUNG"


def test_editor_lehnt_unbekanntes_format_ab(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.main as m

    monkeypatch.setattr(m.settings, "onlyoffice_url", "https://office.example")
    monkeypatch.setattr(m.settings, "public_base_url", "http://mia-os:8080")
    m.get_store().replace_documents(
        "nextcloud",
        [
            {
                "path": "/seite.html",
                "name": "seite.html",
                "folder": "/",
                "ext": ".html",
                "size_bytes": 10,
                "modified_at": "2026-09-05T00:00:00+00:00",
                "file_id": "1",
            }
        ],
    )
    doc_id = m.get_store().list_documents()[0]["id"]
    assert client.get(f"/bearbeiten/{doc_id}").status_code == 415


# --- Rueckweg -------------------------------------------------------------


def test_zurueck_behaelt_ordner_und_suche(client: Any, eingerichtet: int) -> None:
    """Nach dem Editor wieder im gefilterten Ordner landen, nicht bei 'Alle'.

    Mias Beobachtung am 05.09.2026: die Kategorieleiste sprang bei jedem
    geoeffneten Dokument auf den Ausgangszustand zurueck.
    """
    resp = client.get(
        f"/bearbeiten/{eingerichtet}",
        params={"zurueck": "ordner=/Dokumente/02 Medizinisch&seite=2"},
    )
    assert resp.status_code == 200
    assert "ordner=%2FDokumente%2F02+Medizinisch" in resp.text
    assert "seite=2" in resp.text


def test_zurueck_ohne_stand_geht_auf_uebersicht(client: Any, eingerichtet: int) -> None:
    resp = client.get(f"/bearbeiten/{eingerichtet}")
    assert 'href="/#/dokumente"' in resp.text


def test_zurueck_kann_nicht_auf_fremde_seite_zeigen(client: Any, eingerichtet: int) -> None:
    """Der Wert kommt aus der Adresszeile, darf also keine Weiterleitung sein."""
    boese = "https://boese.example/phishing"
    resp = client.get(f"/bearbeiten/{eingerichtet}", params={"zurueck": boese})
    assert resp.status_code == 200
    assert "boese.example" not in resp.text
    assert 'href="/#/dokumente"' in resp.text


def test_zurueck_ignoriert_unbekannte_parameter(client: Any, eingerichtet: int) -> None:
    resp = client.get(
        f"/bearbeiten/{eingerichtet}",
        params={"zurueck": "ordner=/Dokumente&schadcode=<script>&admin=1"},
    )
    assert "schadcode" not in resp.text
    assert "admin=1" not in resp.text
    assert "ordner=%2FDokumente" in resp.text
