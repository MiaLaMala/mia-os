"""Tests fuer die HTTP-Schnittstelle."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    """Muss trotz der Weiterleitungen fuer alte Seiten erreichbar bleiben."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_unknown_category_is_404(client: TestClient) -> None:
    assert client.get("/k/gibtsnicht").status_code == 404


def test_alte_kategorieadresse_leitet_in_die_app(client: TestClient) -> None:
    """``/k/homelab`` war die Jinja-Seite. Der Weg fuehrt in die App."""
    antwort = client.get("/k/homelab", follow_redirects=False)
    assert antwort.status_code == 307
    assert antwort.headers["location"] == "/#/homelab"
    for weg in ("/k/ausbildung", "/k/behoerden"):
        assert client.get(weg).status_code == 404


def test_wurzel_liefert_die_app(client: TestClient) -> None:
    """Seit 07.09.2026 ist ``/`` das Svelte-Frontend, nicht mehr Jinja."""
    from pathlib import Path

    import src.main as m

    if not (Path(m.GEBAUT) / "index.html").is_file():
        assert client.get("/").status_code == 503
        return
    text = client.get("/").text
    assert '<div id="app">' in text


def test_wurzel_wird_nicht_zwischengespeichert(client: TestClient) -> None:
    """Die Huelle traegt die Dateinamen der Buendel und muss frisch kommen.

    Am 09.09.2026 hielt Safari auf Mias iPhone das alte ``app.js`` fest, das
    neue Berichtsheft fehlte dort im Menue, obwohl der Server es lieferte.
    """
    from pathlib import Path

    import src.main as m

    if not (Path(m.GEBAUT) / "index.html").is_file():
        return
    antwort = client.get("/")
    assert "no-store" in antwort.headers.get("cache-control", "")


def test_gebaute_dateien_tragen_eine_pruefsumme() -> None:
    """Feste Namen wie ``app.js`` sind der Grund, warum Zwischenspeicher kleben.

    Die Pruefsumme steht in der Vite-Konfiguration, nicht im Python-Code:
    hier faellt auf, wenn sie jemand wieder herausnimmt.
    """
    from pathlib import Path

    # Zwei Ebenen hoch: seit der Trennung von Backend und Frontend liegen die
    # Tests unter backend/tests, das Frontend daneben.
    config = Path(__file__).resolve().parents[2] / "frontend" / "vite.config.ts"
    text = config.read_text(encoding="utf-8")
    assert "app-[hash].js" in text
    # Nur die Konfigurationszeile pruefen, nicht den Fliesstext: der Kommentar
    # darueber erwaehnt den alten Namen absichtlich als Begruendung.
    assert 'entryFileNames: "app.js"' not in text


def test_uebersicht_api_zeigt_keine_emojis(client: TestClient) -> None:
    """Inter hat keine Emoji-Glyphen. Die API liefert bereinigte Texte."""
    import src.main as m

    m.get_store().record("termine", "anzahl_heute", 2.0)
    m.get_store().record("termine", "naechster", text_value="📚 Berufsschule, morgen 07:30")
    daten = client.get("/api/uebersicht").json()
    termine = next(k for k in daten["kacheln"] if k["key"] == "termine")
    assert "Berufsschule" in termine["caption"]["display"]
    assert "📚" not in termine["caption"]["display"]


def test_frontend_quellen_ohne_emojis() -> None:
    """Harte Design-Zusage: gezeichnete Icons, keine Unicode-Platzhalter."""
    from pathlib import Path

    wurzel = Path(__file__).resolve().parents[1] / "frontend" / "src"
    verboten = ("❤️", "📅", "🖥️", "💚", "⚠️", "📚", "📁", "✅", "🔴", "🟢")
    for datei in wurzel.rglob("*.svelte"):
        text = datei.read_text(encoding="utf-8")
        for e in verboten:
            assert e not in text, f"{datei.name} enthaelt {e}"


def test_nur_kategorien_mit_daten(client: TestClient) -> None:
    """Ausbildung und Behörden sind raus (Mias Ansage 06.09.2026).

    Beide standen seit Wochen als tote Kacheln mit "bald" da: Moodle ist
    laut Mia unbrauchbar gepflegt, für Behörden gibt es keine Quelle. Eine
    Kachel, die nie etwas zeigt, ist schlechter als gar keine.
    """
    resp = client.get("/api/categories")
    assert resp.status_code == 200
    keys = [c["key"] for c in resp.json()]
    # Termine zuerst: handlungsrelevant, siehe DESIGN.md
    assert keys == ["termine", "gesundheit", "dokumente", "homelab"]
    assert "ausbildung" not in keys
    assert "behoerden" not in keys


def test_single_category_endpoint(client: TestClient) -> None:
    resp = client.get("/api/categories/homelab")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Homelab"
    assert client.get("/api/categories/quatsch").status_code == 404


def test_history_endpoint_empty(client: TestClient) -> None:
    resp = client.get("/api/history/gesundheit/gewicht")
    assert resp.status_code == 200
    assert resp.json() == []


def test_collect_without_config_is_graceful(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ohne Zugangsdaten muss /api/collect sauber False melden, nicht 500 werfen.

    Der Kuma-Zugang muss dafür ausdrücklich abgeschaltet werden: ``kuma_ssh_host``
    hat mit "pve" eine feste Vorgabe, der Collector gilt also immer als
    konfiguriert und würde hier echtes SSH starten. Auf einem CI-Runner gibt
    es keine Route ins Heimnetz, und der Testlauf hing 25 Minuten daran fest.
    """
    import src.collectors.kuma as kuma

    monkeypatch.setattr(kuma.settings, "kuma_ssh_host", "")

    resp = client.post("/api/collect")
    assert resp.status_code == 200
    assert all(v is False for v in resp.json().values())


def test_kuma_ohne_zugang_ist_nicht_konfiguriert(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kein Host, kein Versuch: sonst laufen Tests in echtes SSH."""
    import src.collectors.kuma as kuma

    monkeypatch.setattr(kuma.settings, "kuma_ssh_host", "")
    assert kuma.KumaCollector(store=None).is_configured() is False  # type: ignore[arg-type]


# --- Dokumente ------------------------------------------------------------


def test_preview_unknown_document_is_404(client: TestClient) -> None:
    """Kein 500, wenn die ID nicht existiert."""
    assert client.get("/vorschau/999999").status_code == 404


def test_preview_needs_fileid(client: TestClient) -> None:
    """Ein Dokument ohne fileid (etwa lokal erzeugt) hat keine Vorschau."""
    import src.main as m

    m.get_store().replace_documents(
        "jana",
        [
            {
                "path": "/Brief.docx",
                "name": "Brief.docx",
                "folder": "/",
                "ext": ".docx",
                "size_bytes": 10,
                "modified_at": "2026-09-05T00:00:00+00:00",
                "file_id": "",
            }
        ],
    )
    doc_id = m.get_store().list_documents()[0]["id"]
    assert client.get(f"/vorschau/{doc_id}").status_code == 404


def test_preview_without_nextcloud_config(client: TestClient) -> None:
    """Mit fileid, aber ohne Zugangsdaten: sauberes 503 statt Absturz."""
    import src.main as m

    m.get_store().replace_documents(
        "nextcloud",
        [
            {
                "path": "/Ausweis.pdf",
                "name": "Ausweis.pdf",
                "folder": "/",
                "ext": ".pdf",
                "size_bytes": 10,
                "modified_at": "2026-09-05T00:00:00+00:00",
                "file_id": "9426",
            }
        ],
    )
    doc_id = m.get_store().list_documents()[0]["id"]
    assert client.get(f"/vorschau/{doc_id}").status_code == 503


def test_nur_ordner_zeigt_keine_dateinamen(client: TestClient) -> None:
    """Die Festlegung aus ``docs/apple-zuschnitt.md``, hier als Test.

    Ohne Suchbegriff darf ``nur_ordner=1`` keinen einzigen Dateinamen
    liefern, nur Ordner und Anzahl. Das ist der Weg, den die Apple-Apps
    ausschliesslich nehmen: in den Ordnern liegen Ausweise und medizinische
    Unterlagen, auch von anderen Menschen, und ein Telefon liegt auf Tischen.

    ``search_documents`` hielt sich ohne Suchbegriff schon daran,
    ``list_documents`` nicht. Genau diese Luecke schliesst der Schalter.
    """
    import src.main as m

    m.get_store().replace_documents(
        "nextcloud",
        [
            {
                "path": "/Dokumente/02 Medizinisch/Befund.pdf",
                "name": "Befund.pdf",
                "folder": "/Dokumente/02 Medizinisch",
                "ext": ".pdf",
                "size_bytes": 10,
                "modified_at": "2026-09-05T00:00:00+00:00",
                "file_id": "1",
            }
        ],
    )

    daten = client.get("/api/dokumente?nur_ordner=1").json()
    assert daten["treffer"] == []
    assert daten["gesamt"] == 1
    # Die Ordner kommen weiterhin: sie sind der Einstieg und verraten nur
    # Struktur ("02 Medizinisch, 1 Dokument"), keinen einzelnen Befund.
    assert daten["ordner"]

    # Der Name steht nirgends in der Antwort, auch nicht in einem Nebenfeld.
    assert "Befund.pdf" not in client.get("/api/dokumente?nur_ordner=1").text


def test_nur_ordner_sucht_trotzdem(client: TestClient) -> None:
    """Mit Suchbegriff greift der Schalter nicht: wer sucht, will finden."""
    import src.main as m

    m.get_store().replace_documents(
        "nextcloud",
        [
            {
                "path": "/Dokumente/Meldebescheinigung.pdf",
                "name": "Meldebescheinigung.pdf",
                "folder": "/Dokumente",
                "ext": ".pdf",
                "size_bytes": 10,
                "modified_at": "2026-09-05T00:00:00+00:00",
                "file_id": "1",
            }
        ],
    )

    daten = client.get("/api/dokumente?nur_ordner=1&q=meldebesch").json()
    assert [t["name"] for t in daten["treffer"]] == ["Meldebescheinigung.pdf"]


def test_web_blaettert_weiterhin(client: TestClient) -> None:
    """Ohne den Schalter bleibt die Weboberflaeche, wie sie war.

    Der Browser laeuft auf Mias Rechner, das Telefon liegt auf Tischen. Der
    Schalter ist deshalb ein Schalter und keine neue Vorgabe fuer alle.
    """
    import src.main as m

    m.get_store().replace_documents(
        "nextcloud",
        [
            {
                "path": "/Dokumente/Brief.pdf",
                "name": "Brief.pdf",
                "folder": "/Dokumente",
                "ext": ".pdf",
                "size_bytes": 10,
                "modified_at": "2026-09-05T00:00:00+00:00",
                "file_id": "1",
            }
        ],
    )

    daten = client.get("/api/dokumente").json()
    assert [t["name"] for t in daten["treffer"]] == ["Brief.pdf"]


# --- Dogfood-Befunde ------------------------------------------------------


def test_langer_leitwert_bekommt_die_kleine_stufe(client: TestClient) -> None:
    """H1: 'Homepage nicht erreichbar' lief 111px über die Kachel hinaus.

    Der Leitwert ist als Zahl gedacht und wird in 26 Pixeln ohne Umbruch
    gesetzt. Ein Satz sprengt damit die Kachel, und die ganze Seite wurde
    seitlich scrollbar (Körper 481px bei 390px Fenster).
    """
    from src.categories import BY_KEY
    from src.presenter import build_card

    lang = build_card(
        BY_KEY["homelab"],
        {"dienste_lage": {"key": "dienste_lage", "text_value": "Homepage nicht erreichbar"}},
    )
    assert lang["lead"]["lang"] is True

    kurz = build_card(
        BY_KEY["homelab"],
        {"dienste_lage": {"key": "dienste_lage", "text_value": "Alles läuft"}},
    )
    assert kurz["lead"]["lang"] is False


def test_zahlen_bleiben_gross(client: TestClient) -> None:
    """Eine Zahl ist der Normalfall und behält die große Stufe."""
    from src.categories import BY_KEY
    from src.presenter import build_card

    karte = build_card(
        BY_KEY["gesundheit"], {"gewicht": {"key": "gewicht", "value": 88.7, "unit": "kg"}}
    )
    assert karte["lead"].get("lang") is not True


def test_unbekannte_seite_hat_einen_weg_zurueck(client: TestClient) -> None:
    """N1: Die 404 zeigte FastAPIs nacktes JSON, 22 Zeichen ohne Navigation."""
    antwort = client.get("/gibtsnichtdiese-seite")
    assert antwort.status_code == 404
    assert "Seite nicht gefunden" in antwort.text
    assert 'href="/"' in antwort.text, "kein Weg zurück"


def test_unbekannte_kategorie_ebenso(client: TestClient) -> None:
    antwort = client.get("/k/quatsch")
    assert antwort.status_code == 404
    assert "Seite nicht gefunden" in antwort.text
