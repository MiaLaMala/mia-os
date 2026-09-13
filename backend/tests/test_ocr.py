"""OCR: Text aus selbst gescannten Belegen lesen und durchsuchbar machen.

Der wichtigste Test in dieser Datei ist ``test_bestand_bekommt_keinen_text``.
Alles andere ist Bequemlichkeit, das ist die Zusage an Mia: in ihren Ordnern
liegen Ausweise, Geburtsurkunden und Unterlagen Dritter, und von denen darf
kein Wort in der Datenbank landen. Die Grenze wird deshalb im Store geprueft
und nicht beim Aufrufer, und genau das prueft der Test.

**Echtes Tesseract laeuft nur in den Tests mit ``echtes_tesseract``.** Der Rest
mockt, aus zwei Gruenden: der CI-Runner hat kein Tesseract installiert, und
ein Testlauf, der je Fall eine Sekunde OCR wartet, ist eine Minute langsamer.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src import ocr
from src.store import Store

JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 40


# --- Der Text darf nur von selbst gescannten Belegen kommen ---------------


def test_bestand_bekommt_keinen_text(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    """Eine Datei ausserhalb des Belegordners bekommt keinen Text. Nie.

    Das ist Mias Zusage, keine Bequemlichkeit. In ``/Dokumente/01
    Persoenliches`` liegen Ausweis und Geburtsurkunde, in ``02 Medizinisch``
    medizinische Unterlagen Dritter. Die Grenze steht im Store, damit
    sie auch dann haelt, wenn spaeter jemand eine bequeme Sammelfunktion
    darueber baut und die Regel nur in der Dokumentation nachliest.
    """
    monkeypatch.setattr(ocr.settings, "belege_ordner", "/Dokumente/00 Belege")
    import src.store as store_modul

    monkeypatch.setattr(store_modul.settings, "belege_ordner", "/Dokumente/00 Belege")

    pfad = "/Dokumente/01 Persönliches/Personalausweis.pdf"
    store.upsert_document({"path": pfad, "name": "Personalausweis.pdf", "source": "nextcloud"})

    assert store.set_document_text("nextcloud", pfad, "Ausweisnummer L01X00T47") is False
    assert store.document_text("nextcloud", pfad) == ""


def test_beleg_bekommt_text(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    """Im Belegordner ist das Speichern erlaubt: Mia hatte das Blatt in der Hand."""
    import src.store as store_modul

    monkeypatch.setattr(store_modul.settings, "belege_ordner", "/Dokumente/00 Belege")

    pfad = "/Dokumente/00 Belege/2026-09-03 Meldebescheinigung.jpg"
    store.upsert_document({"path": pfad, "name": "2026-09-03 Meldebescheinigung.jpg"})

    assert store.set_document_text("nextcloud", pfad, "Aktenzeichen 43-044-26211") is True
    assert "43-044" in store.document_text("nextcloud", pfad)


def test_leerer_belegordner_verbietet_alles(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ohne konfigurierten Belegordner wird gar nichts geschrieben.

    Sonst waere eine leere Einstellung dasselbe wie \"alles erlaubt\": der
    Praefix ``\"\"`` passt auf jeden Pfad. Fehlkonfiguration muss zur
    strengeren Seite kippen, nicht zur laxeren.
    """
    import src.store as store_modul

    monkeypatch.setattr(store_modul.settings, "belege_ordner", "")
    store.upsert_document({"path": "/beliebig.jpg", "name": "beliebig.jpg"})

    assert store.set_document_text("nextcloud", "/beliebig.jpg", "Text") is False


def test_crawl_loescht_den_text_nicht(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    """Der stuendliche Sammellauf darf den gelesenen Text nicht wegwischen.

    ``replace_documents`` aktualisiert bekannte Pfade. Stuende ``ocr_text`` in
    seiner UPDATE-Liste, waere der Text nach spaetestens einer Stunde weg und
    die Suche im Beleg stillschweigend kaputt. Der Beleg selbst liegt ja
    weiter in Nextcloud und wird beim Crawl wiedergefunden.
    """
    import src.store as store_modul

    monkeypatch.setattr(store_modul.settings, "belege_ordner", "/Dokumente/00 Belege")
    pfad = "/Dokumente/00 Belege/2026-09-03 Bescheid.jpg"
    store.upsert_document({"path": pfad, "name": "2026-09-03 Bescheid.jpg"})
    store.set_document_text("nextcloud", pfad, "Widerspruchsfrist ein Monat")

    store.replace_documents(
        "nextcloud",
        [{"path": pfad, "name": "2026-09-03 Bescheid.jpg", "folder": "/Dokumente/00 Belege"}],
    )

    assert "Widerspruchsfrist" in store.document_text("nextcloud", pfad)


# --- Suche ----------------------------------------------------------------


@pytest.fixture
def belegordner(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.store as store_modul

    monkeypatch.setattr(store_modul.settings, "belege_ordner", "/Dokumente/00 Belege")


def test_suche_findet_woerter_im_text(store: Store, belegordner: None) -> None:
    """Das Aktenzeichen steht nur auf dem Blatt, nicht im Dateinamen.

    Genau das ist der Grund fuer die ganze Runde: ``2026-09-03
    Meldebescheinigung.jpg`` ist unter \"Meldebescheinigung\" auffindbar, aber
    wer nach dem Aktenzeichen sucht, fand bisher nichts.
    """
    pfad = "/Dokumente/00 Belege/2026-09-03 Meldebescheinigung.jpg"
    store.upsert_document({"path": pfad, "name": "2026-09-03 Meldebescheinigung.jpg"})
    store.set_document_text("nextcloud", pfad, "Aktenzeichen: 43-044-26211-000896\nBuxtehude")

    treffer = store.search_documents("43-044-26211-000896")
    assert [t["path"] for t in treffer] == [pfad]


def test_name_schlaegt_fliesstext(store: Store, belegordner: None) -> None:
    """Wer den Dateinamen kennt, will ihn oben sehen.

    Ohne Gewichtung gewinnt das Dokument, in dem das Wort oft vorkommt: FTS5
    belohnt Haeufigkeit, und ein Dateiname hat je Wort genau ein Vorkommen.
    """
    treffer_pfad = "/Dokumente/00 Belege/2026-09-01 Buxtehude.jpg"
    store.upsert_document({"path": treffer_pfad, "name": "2026-09-01 Buxtehude.jpg"})

    anderer = "/Dokumente/00 Belege/2026-09-02 Sonstiges.jpg"
    store.upsert_document({"path": anderer, "name": "2026-09-02 Sonstiges.jpg"})
    store.set_document_text("nextcloud", anderer, "Buxtehude " * 40)

    treffer = store.search_documents("Buxtehude")
    assert treffer[0]["path"] == treffer_pfad


def test_fundstelle_nur_bei_texttreffer(store: Store, belegordner: None) -> None:
    """Bei einem reinen Namenstreffer steht keine Fundstelle darunter.

    ``snippet()`` liefert sonst den Textanfang, und der stuende ohne Bezug zur
    Suche unter der Kachel: \"Hansestadt Buxtehude, Buergeramt…\" bei einer
    Suche nach \"Meldebescheinigung\" sieht aus wie ein Fehler.
    """
    pfad = "/Dokumente/00 Belege/2026-09-03 Meldebescheinigung.jpg"
    store.upsert_document({"path": pfad, "name": "2026-09-03 Meldebescheinigung.jpg"})
    store.set_document_text("nextcloud", pfad, "Hansestadt Buxtehude, Bürgeramt, Breite Straße 2")

    per_name = store.search_documents("Meldebescheinigung")
    assert per_name[0]["stelle"] == ""

    per_text = store.search_documents("Bürgeramt")
    assert "[Bürgeramt]" in per_text[0]["stelle"]


def test_fundstelle_ist_einzeilig(store: Store, belegordner: None) -> None:
    """Der Ausschnitt geht über Zeilengrenzen, die Anzeige hat eine Zeile.

    Am gerenderten Bild aufgefallen: im JSON sah die Fundstelle in Ordnung
    aus, unter der Kachel riss sie das Layout auf.
    """
    pfad = "/Dokumente/00 Belege/2026-09-03 Bescheid.jpg"
    store.upsert_document({"path": pfad, "name": "2026-09-03 Bescheid.jpg"})
    store.set_document_text(
        "nextcloud", pfad, "Buxtehude, den 03.09.2026\nAktenzeichen: 43-044-26211-000896"
    )

    stelle = store.search_documents("Aktenzeichen")[0]["stelle"]
    assert "\n" not in stelle
    assert "[Aktenzeichen]" in stelle


def test_das_gesuchte_steht_vorn(store: Store, belegordner: None) -> None:
    """Der Anlauf vor dem Treffer darf ihn nicht aus dem Bild schieben.

    Am gerenderten Bild gefunden: auf der Kachel stand ``… 03.09.2026 |
    [Aktenzeic…`` und die Nummer, wegen der jemand sucht, war abgeschnitten.
    Der Wert steht fast immer *hinter* dem Suchwort, also wird vorne gekürzt.
    """
    pfad = "/Dokumente/00 Belege/2026-09-03 Bescheid.jpg"
    store.upsert_document({"path": pfad, "name": "2026-09-03 Bescheid.jpg"})
    store.set_document_text(
        "nextcloud",
        pfad,
        "Hansestadt Buxtehude Bürgeramt Breite Straße zwei Buxtehude den dritten "
        "September Aktenzeichen: 43-044-26211-000896 Meldebescheinigung",
    )

    stelle = store.search_documents("Aktenzeichen")[0]["stelle"]
    assert stelle.index("[Aktenzeichen]") <= 24, f"Treffer steht zu weit hinten: {stelle!r}"
    assert "43-044-26211-000896" in stelle


def test_kurzer_vorlauf_bleibt_ganz(store: Store, belegordner: None) -> None:
    """Steht der Treffer ohnehin vorn, wird nichts abgeschnitten.

    Sonst stünde vor jedem Treffer eine Ellipse, auch wenn es davor gar nichts
    zu verstecken gibt.
    """
    pfad = "/Dokumente/00 Belege/2026-09-03 Bescheid.jpg"
    store.upsert_document({"path": pfad, "name": "2026-09-03 Bescheid.jpg"})
    store.set_document_text("nextcloud", pfad, "Aktenzeichen: 43-044 und weiterer Text dahinter")

    assert store.search_documents("Aktenzeichen")[0]["stelle"].startswith("[Aktenzeichen]")


def test_bestand_ohne_text_hat_keine_fundstelle(store: Store, belegordner: None) -> None:
    """Der Bestand hat keinen Text, also auch keine Fundstelle."""
    pfad = "/Dokumente/01 Persönliches/Meldebescheinigung.pdf"
    store.upsert_document({"path": pfad, "name": "Meldebescheinigung.pdf"})

    treffer = store.search_documents("Meldebescheinigung")
    assert treffer[0]["stelle"] == ""
    assert treffer[0]["ocr_text"] == ""


# --- Die alte Datenbank muss weiterlaufen ---------------------------------


def test_alte_fts_tabelle_wird_neu_gebaut(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Auf dem LXC liegt eine Datenbank mit der alten zweispaltigen Suchtabelle.

    ``CREATE VIRTUAL TABLE IF NOT EXISTS`` fasst sie nicht an und FTS5 kennt
    kein ``ALTER TABLE ADD COLUMN``. Ohne den Neubau liefe der Container
    weiter und jedes Schreiben in ``documents`` stuerbe in den Triggern an
    ``no such column: ocr_text``. Genau die Sorte Fehler, die lokal nie
    auftritt, weil hier eine frische Datei liegt.
    """
    import sqlite3

    import src.store as store_modul

    monkeypatch.setattr(store_modul.settings, "belege_ordner", "/Dokumente/00 Belege")
    pfad = tmp_path / "alt.db"

    # Die Fassung vor dieser Runde, so wie sie auf dem LXC steht.
    conn = sqlite3.connect(pfad)
    conn.executescript(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL, path TEXT NOT NULL, name TEXT NOT NULL,
            folder TEXT NOT NULL DEFAULT '', ext TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            modified_at TEXT NOT NULL DEFAULT '', file_id TEXT NOT NULL DEFAULT '',
            seen_at TEXT NOT NULL, UNIQUE(source, path)
        );
        CREATE VIRTUAL TABLE documents_fts USING fts5(
            name, folder, content='documents', content_rowid='id', tokenize='unicode61');
        CREATE TRIGGER documents_ai AFTER INSERT ON documents BEGIN
            INSERT INTO documents_fts(rowid, name, folder) VALUES (new.id, new.name, new.folder);
        END;
        INSERT INTO documents (source, path, name, folder, seen_at)
        VALUES ('nextcloud', '/Dokumente/01 Persönliches/Meldebescheinigung.pdf',
                'Meldebescheinigung.pdf', '/Dokumente/01 Persönliches', '2026-09-01');
        INSERT INTO documents_fts(rowid, name, folder)
        SELECT id, name, folder FROM documents;
        """
    )
    conn.commit()
    conn.close()

    store = Store(str(pfad))

    # Der Bestand ist noch da und weiter auffindbar: der Neubau der Suchtabelle
    # liest aus ``documents`` zurueck, dort liegen die eigentlichen Daten.
    assert [t["name"] for t in store.search_documents("Meldebescheinigung")] == [
        "Meldebescheinigung.pdf"
    ]

    # Und Schreiben geht wieder, ohne dass die Trigger stolpern.
    neu = "/Dokumente/00 Belege/2026-09-09 Bescheid.jpg"
    store.upsert_document({"path": neu, "name": "2026-09-09 Bescheid.jpg"})
    store.set_document_text("nextcloud", neu, "Widerspruchsfrist ein Monat")
    assert [t["path"] for t in store.search_documents("Widerspruchsfrist")] == [neu]


# --- Aufraeumen -----------------------------------------------------------


def test_aufraeumen_wirft_randreste_weg() -> None:
    """Tesseract macht aus Flecken am Blattrand Zeilen mit einem Zeichen.

    Die blaehen den Index auf, ohne dass jemand danach sucht.
    """
    roh = "Hansestadt Buxtehude\n|\n\n\n\nAktenzeichen: 43-044\n.\n\x0c"
    assert ocr.aufraeumen(roh) == "Hansestadt Buxtehude\n\nAktenzeichen: 43-044"


def test_aufraeumen_deckelt_die_laenge() -> None:
    """Ein Fehlgriff darf kein ganzes Buch in die Datenbank schreiben."""
    assert len(ocr.aufraeumen("Wort " * 20000)) <= ocr.MAX_ZEICHEN


# --- Kauderwelsch-Zeilen aussortieren -------------------------------------


def _tsv(*zeilen: tuple[float, str]) -> str:
    """Eine TSV-Ausgabe bauen, wie Tesseract sie liefert. Eine Zeile je Eintrag."""
    kopf = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    raus = [kopf]
    for nr, (konfidenz, text) in enumerate(zeilen, start=1):
        for wort_nr, wort in enumerate(text.split(), start=1):
            raus.append(f"5\t1\t1\t1\t{nr}\t{wort_nr}\t0\t0\t0\t0\t{konfidenz}\t{wort}")
    return "\n".join(raus)


def test_schattenkante_fliegt_raus() -> None:
    """Die Zeile, die Tesseract aus dem Handyschatten gemacht hat, gehört weg.

    Am gerenderten Beleg gemessen: sie kam auf 22 von 100, jede echte Zeile
    auf über 82. Ohne den Filter stand ``| a kia. a See SS en, Bie orn`` als
    erste Zeile im Index.
    """
    tsv = _tsv(
        (22.1, "| a kia. a See SS en, Bie orn Sete ae Seen NEE"),
        (88.2, "Hansestadt Buxtehude"),
        (89.1, "Aktenzeichen: 43-044-26211-000896"),
    )
    assert ocr._aus_tsv(tsv) == "Hansestadt Buxtehude\nAktenzeichen: 43-044-26211-000896"


def test_kurze_echte_zeile_bleibt() -> None:
    """Eine echte Zeile wegzuwerfen ist der teurere Fehler.

    ``Meldebescheinigung nach 5 18 Abs. 1 BMG`` sieht nach Wortlängen wie
    Kauderwelsch aus: viele kurze Bruchstücke. Tesseract selbst ist sich
    sicher, und darauf hört der Filter.
    """
    tsv = _tsv((93.3, "Meldebescheinigung nach 5 18 Abs. 1 BMG"), (96.0, "Frau"))
    assert ocr._aus_tsv(tsv) == "Meldebescheinigung nach 5 18 Abs. 1 BMG\nFrau"


def test_unerwartetes_format_wirft_nicht_alles_weg() -> None:
    """Bei kaputter TSV-Ausgabe gilt der Klartext, nicht die Leere.

    Der Filter ist Komfort, das Lesen der Zweck. Eine künftige
    Tesseract-Fassung mit anderer Spaltenzahl darf das OCR nicht abschalten,
    sondern höchstens ungefiltert lassen.
    """
    assert ocr._aus_tsv("völlig anderes Format\nohne Tabulatoren") == ""


@pytest.mark.asyncio
async def test_klartext_wenn_tsv_nichts_hergibt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Liefert der TSV-Weg nichts, wird die Ausgabe unverändert genommen."""
    monkeypatch.setattr(ocr, "verfuegbar", lambda: True)

    class Prozess:
        returncode = 0

        async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
            return b"Aktenzeichen: 43-044", b""

    async def start(*args: Any, **kwargs: Any) -> Prozess:
        return Prozess()

    monkeypatch.setattr(ocr.asyncio, "create_subprocess_exec", start)
    assert await ocr.text_lesen(JPG) == "Aktenzeichen: 43-044"


# --- Verhalten, wenn Tesseract fehlt oder klemmt --------------------------


@pytest.mark.asyncio
async def test_ohne_tesseract_leerer_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fehlt Tesseract, gibt es keinen Text und keinen Fehler.

    Der Beleg liegt zu dem Zeitpunkt bereits in Nextcloud. Ein fehlendes OCR
    darf ihn nicht nachtraeglich zum Problem machen.
    """
    monkeypatch.setattr(ocr.settings, "ocr_binary", "gibtesnicht-xyz")
    assert ocr.verfuegbar() is False
    assert await ocr.text_lesen(JPG) == ""


@pytest.mark.asyncio
async def test_zeitgrenze_beendet_den_prozess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ein haengender Tesseract darf den Upload nicht offen stehen lassen.

    Auf einem sehr feinstrukturierten Bild kann die Layout-Analyse minutenlang
    laufen. Der Test stellt einen Prozess, der nie antwortet, und prueft, dass
    er beendet wird statt gewartet.
    """
    monkeypatch.setattr(ocr, "verfuegbar", lambda: True)
    monkeypatch.setattr(ocr.settings, "ocr_timeout", 1)
    beendet: list[str] = []

    class HaengenderProzess:
        returncode = None

        async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
            await asyncio.sleep(30)
            return b"", b""

        def terminate(self) -> None:
            beendet.append("terminate")

        def kill(self) -> None:  # pragma: no cover - hier nicht erreicht
            beendet.append("kill")

        async def wait(self) -> int:
            return 0

    async def start(*args: Any, **kwargs: Any) -> HaengenderProzess:
        return HaengenderProzess()

    monkeypatch.setattr(ocr.asyncio, "create_subprocess_exec", start)

    assert await ocr.text_lesen(JPG) == ""
    assert beendet == ["terminate"]


@pytest.mark.asyncio
async def test_fehlercode_liefert_leeren_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ein abgestuerztes Tesseract endet in einem leeren Text, nicht in 500."""
    monkeypatch.setattr(ocr, "verfuegbar", lambda: True)

    class KaputterProzess:
        returncode = 1

        async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
            return b"", b"Error in pixReadStream"

    async def start(*args: Any, **kwargs: Any) -> KaputterProzess:
        return KaputterProzess()

    monkeypatch.setattr(ocr.asyncio, "create_subprocess_exec", start)
    assert await ocr.text_lesen(JPG) == ""


def test_umgebung_bleibt_im_container_leer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Im Container liegen Sprachdateien und Bibliotheken an der Standardstelle.

    Ein gesetztes ``TESSDATA_PREFIX`` auf einen Pfad, den es dort nicht gibt,
    waere schlimmer als gar keines: Tesseract findet dann ``deu`` nicht mehr.
    """
    monkeypatch.setattr(ocr.settings, "ocr_tessdata", "")
    monkeypatch.setattr(ocr.settings, "ocr_lib_path", "")
    umgebung = ocr._umgebung()

    assert "TESSDATA_PREFIX" not in umgebung
    assert "LD_LIBRARY_PATH" not in umgebung
    # Ohne die Bremse greift sich Tesseract alle Kerne fuer eine Seite und der
    # Webserver antwortet daneben nicht mehr.
    assert umgebung["OMP_THREAD_LIMIT"] == "1"


# --- Der Weg durch die API ------------------------------------------------


def _upload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    scannen: bool,
    text: str = "Aktenzeichen",
    pdf: bytes | None = b"%PDF-1.5\nfake",
    abgelegt: list[tuple[bytes, str]] | None = None,
    ocr_eingaben: list[bytes] | None = None,
) -> dict[str, Any]:
    """Einen Beleg hochladen, mit gestelltem Nextcloud und gestelltem OCR.

    ``abgelegt`` sammelt, was tatsaechlich nach Nextcloud ginge, ``pdf`` stellt
    die PDF-Erzeugung (``None`` = sie scheitert), ``ocr_eingaben`` haelt fest,
    womit das OCR gefuettert wurde.
    """
    import src.api as api_modul
    import src.belege as belege_modul

    async def ablegen_stub(inhalt: bytes, name: str) -> tuple[str, str]:
        if abgelegt is not None:
            abgelegt.append((inhalt, name))
        return f"/Dokumente/00 Belege/{name}", "42"

    monkeypatch.setattr(belege_modul, "ablegen", ablegen_stub)
    monkeypatch.setattr(api_modul.belege, "ablegen", ablegen_stub)

    async def lesen(bild: bytes, sprache: str = "") -> str:
        if ocr_eingaben is not None:
            ocr_eingaben.append(bild)
        return text

    async def pdf_stub(bild: bytes, sprache: str = "") -> bytes | None:
        return pdf

    monkeypatch.setattr(api_modul.ocr, "verfuegbar", lambda: True)
    monkeypatch.setattr(api_modul.ocr, "text_lesen", lesen)
    monkeypatch.setattr(api_modul.ocr, "als_pdf", pdf_stub)

    # Der Scanner ist hier nicht der Prueffall, und ein echtes Bild dafuer zu
    # bauen kostet nur Zeit.
    monkeypatch.setattr(api_modul.scanner, "verarbeiten", lambda *a, **k: (JPG, True))

    eintrag = client.post("/api/sammlung", json={"titel": "Widerspruch Kasse"}).json()["eintrag"]
    antwort = client.post(
        f"/api/sammlung/{eintrag['id']}/beleg",
        files={"datei": ("IMG_4711.jpg", JPG, "image/jpeg")},
        data={"scannen": str(scannen).lower()},
    )
    assert antwort.status_code == 200, antwort.text
    return dict(antwort.json())


def test_gescannter_beleg_wird_gelesen(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Wer den Scanner anhakt, bekommt den Text dazu."""
    daten = _upload(client, monkeypatch, scannen=True)
    assert daten["ocr_zeichen"] > 0

    treffer = client.get("/api/dokumente", params={"q": "Aktenzeichen"}).json()["treffer"]
    assert any("Widerspruch Kasse" in t["name"] for t in treffer)


# --- Gescanntes wird als PDF abgelegt -------------------------------------


def test_gescanntes_wird_pdf(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ein Bescheid ist ein Dokument, kein Foto.

    Als PDF laesst er sich ueberall oeffnen, drucken und weiterleiten, und
    Tesseract legt den gelesenen Text als unsichtbare Ebene darunter.
    """
    abgelegt: list[tuple[bytes, str]] = []
    _upload(client, monkeypatch, scannen=True, pdf=b"%PDF-1.5\nfake", abgelegt=abgelegt)

    inhalt, name = abgelegt[-1]
    assert name.endswith(".pdf"), f"als {name} abgelegt statt als PDF"
    assert inhalt.startswith(b"%PDF")


def test_ocr_liest_vom_bild_nicht_vom_pdf(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tesseract nimmt kein PDF als Eingabe.

    Wenn der Upload ab jetzt ein PDF ablegt, muss das OCR trotzdem das
    aufbereitete **Bild** bekommen. Sonst laeuft es auf einer Datei, mit der
    es nichts anfangen kann, und der Text in der Datenbank bleibt leer.
    """
    gelesen: list[bytes] = []
    daten = _upload(client, monkeypatch, scannen=True, pdf=b"%PDF-1.5\nfake", ocr_eingaben=gelesen)

    assert gelesen, "OCR wurde gar nicht aufgerufen"
    assert not gelesen[0].startswith(b"%PDF"), "OCR bekam das PDF statt des Bildes"
    assert daten["ocr_zeichen"] > 0


def test_ohne_pdf_bleibt_es_beim_bild(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scheitert die PDF-Erzeugung, wird das Bild abgelegt.

    Ein abgelegter Beleg ist mehr wert als ein sauberes Format. Der Fall
    tritt auf, wenn Tesseract fehlt oder in die Zeitgrenze laeuft.
    """
    abgelegt: list[tuple[bytes, str]] = []
    _upload(client, monkeypatch, scannen=True, pdf=None, abgelegt=abgelegt)

    _, name = abgelegt[-1]
    assert name.endswith(".jpg")


def test_kaputtes_pdf_wird_nicht_abgelegt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Was nicht mit %PDF anfaengt, ist keins.

    Lieber das Bild ablegen als eine Datei, die sich nirgends oeffnen laesst.
    """
    monkeypatch.setattr(ocr, "verfuegbar", lambda: True)

    class Prozess:
        returncode = 0

        async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
            return b"kein pdf, nur text", b""

    async def start(*args: Any, **kwargs: Any) -> Prozess:
        return Prozess()

    monkeypatch.setattr(ocr.asyncio, "create_subprocess_exec", start)
    assert asyncio.run(ocr.als_pdf(JPG)) is None


def test_ungescanntes_original_wird_nicht_gelesen(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ohne Haken beim Scanner wird kein Text gelesen.

    \"Original ohne Scan\" ist der Ausweg fuer den Fall, dass die Aufbereitung
    ein Foto verschlimmert. Es ist zugleich der Weg, auf dem Mia ein Foto
    ablegen kann, ohne dass sein Inhalt in der Datenbank landet.
    """
    daten = _upload(client, monkeypatch, scannen=False)
    assert daten["ocr_zeichen"] == 0

    treffer = client.get("/api/dokumente", params={"q": "Aktenzeichen"}).json()["treffer"]
    assert treffer == []


# --- Mit echtem Tesseract, wenn eines da ist ------------------------------


def _tesseract_da() -> bool:
    from tests.conftest import ECHTES_OCR_BINARY

    return shutil.which(ECHTES_OCR_BINARY) is not None


@pytest.fixture
def echtes_tesseract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Die beiden Sperren aus ``conftest`` fuer diesen Test aufheben.

    ``kein_echtes_ocr`` leert den Programmnamen und ``kein_echtes_ssh``
    ersetzt den Prozessstart. Beide sind autouse und beide muessen hier weg,
    sonst prueft der Test die Attrappe statt Tesseract.
    """
    from tests.conftest import ECHTER_PROZESSSTART, ECHTES_OCR_BINARY

    monkeypatch.setattr(ocr.settings, "ocr_binary", ECHTES_OCR_BINARY)
    monkeypatch.setattr(ocr.asyncio, "create_subprocess_exec", ECHTER_PROZESSSTART)


@pytest.mark.skipif(not _tesseract_da(), reason="Tesseract ist hier nicht installiert")
@pytest.mark.asyncio
async def test_echtes_tesseract_liest_deutschen_text(echtes_tesseract: None) -> None:
    """Ein Durchlauf mit dem echten Programm, damit der Aufruf stimmt.

    Prueft die Umlaute mit: ohne ``tesseract-ocr-deu`` faellt Tesseract still
    auf Englisch zurueck, und dann wird aus \"Gebühr\" ein \"Gebuhr\". Ein Test
    auf reinen ASCII-Text haette das nie gemerkt.
    """
    # Ein Blatt mit Text, gerendert statt gemalt: gemalte Buchstaben treffen
    # nie die Formen, auf die Tesseract trainiert ist.
    bild = _blatt_mit_text("Gebühr in Höhe von 9,00 Euro\nAktenzeichen: 43-044-26211")
    text = await ocr.text_lesen(bild)

    assert "43-044-26211" in text
    assert "Gebühr" in text


def _blatt_mit_text(text: str) -> bytes:
    """Ein weisses Blatt mit echtem gerendertem Text als JPEG."""
    import cv2
    import numpy as np

    hoehe, breite = 400, 1400
    blatt = np.full((hoehe, breite, 3), 255, dtype=np.uint8)
    # Hershey ist die einzige Schrift, die OpenCV ohne Fontdatei kann. Sie ist
    # eine Strichschrift und damit fuer OCR eher schwer als leicht: was hier
    # erkannt wird, wird auf echtem Papier erst recht erkannt.
    for i, zeile in enumerate(text.splitlines()):
        cv2.putText(blatt, zeile, (40, 120 + i * 130), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (0, 0, 0), 4)
    ok, puffer = cv2.imencode(".png", blatt)
    assert ok
    return bytes(puffer.tobytes())


@pytest.mark.skipif(not _tesseract_da(), reason="Tesseract ist hier nicht installiert")
def test_deutsche_sprachdatei_ist_da(echtes_tesseract: None) -> None:
    """Ohne ``deu`` liest Tesseract deutsche Post still schlechter.

    Es faellt dann nicht aus, sondern auf Englisch zurueck: Umlaute werden zu
    Grundbuchstaben und das ``ß`` zu einem ``B``. Ein Fehler, den man an der
    Ausgabe erst sieht, wenn man genau hinsieht.
    """
    umgebung = ocr._umgebung()
    ergebnis = subprocess.run(
        [ocr.settings.ocr_binary, "--list-langs"],
        capture_output=True,
        text=True,
        env={**umgebung, "PATH": "/usr/bin:/bin"},
    )
    assert "deu" in ergebnis.stdout.split()
