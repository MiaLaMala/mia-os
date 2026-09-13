"""Tests fuer den Dokumenten-Index.

Deckt vor allem die Stellen ab, an denen ich schon einmal falsch lag:
Umlaute in Pfaden, die Sortierung nach Datum und die Notbremse gegen einen
halb abgebrochenen Crawl.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.collectors.documents import DOC_EXTS, _entry, _iso
from src.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(str(tmp_path / "test.db"))


def _doc(name: str, folder: str = "/Dokumente", **kw: Any) -> dict[str, Any]:
    return _entry(
        f"{folder}/{name}",
        kw.get("size", 1024),
        kw.get("modified", "Mon, 03 Aug 2026 10:00:00 GMT"),
        kw.get("source", "nextcloud"),
        kw.get("file_id", ""),
    )


# --- Speichern und Suchen -------------------------------------------------


def test_replace_and_search(store: Store) -> None:
    store.replace_documents("nextcloud", [_doc("Meldebescheinigung.pdf")])
    treffer = store.search_documents("meldebescheinigung")
    assert len(treffer) == 1
    assert treffer[0]["name"] == "Meldebescheinigung.pdf"


def test_search_is_prefix_based(store: Store) -> None:
    """ "meld" muss "Meldebescheinigung" finden, sonst ist die Suche nutzlos."""
    store.replace_documents("nextcloud", [_doc("Meldebescheinigung.pdf")])
    assert len(store.search_documents("meld")) == 1


def test_search_matches_folder(store: Store) -> None:
    store.replace_documents(
        "nextcloud", [_doc("Bescheid.pdf", folder="/Dokumente/04 Arbeitsagentur")]
    )
    assert len(store.search_documents("arbeitsagentur")) == 1


def test_search_handles_umlauts(store: Store) -> None:
    """Mias Ordner heissen "01 Persoenliches" mit Umlaut."""
    store.replace_documents("nextcloud", [_doc("Ausweis.pdf", folder="/Dokumente/01 Persönliches")])
    assert len(store.search_documents("persönliches")) == 1


def test_search_empty_returns_nothing(store: Store) -> None:
    """Die Suche selbst liefert ohne Begriff nichts.

    Die Kachelwand holt ihre Dokumente ueber ``list_documents``, nicht hierueber.
    So bleibt die Suchfunktion eindeutig: leere Anfrage ist kein Treffer.
    """
    store.replace_documents(
        "nextcloud",
        [
            _doc("alt.pdf", modified="Tue, 19 May 2026 10:00:00 GMT"),
            _doc("neu.pdf", modified="Wed, 02 Sep 2026 10:00:00 GMT"),
        ],
    )
    assert store.search_documents("") == []
    assert store.search_documents("   ") == []


def test_list_documents_newest_first(store: Store) -> None:
    """Die Kachelwand zeigt die zuletzt geaenderten Dokumente zuerst."""
    store.replace_documents(
        "nextcloud",
        [
            _doc("alt.pdf", modified="Tue, 19 May 2026 10:00:00 GMT"),
            _doc("neu.pdf", modified="Wed, 02 Sep 2026 10:00:00 GMT"),
        ],
    )
    assert [d["name"] for d in store.list_documents()] == ["neu.pdf", "alt.pdf"]


def test_list_documents_paginates(store: Store) -> None:
    """Seitenweise, damit nicht 187 Vorschaubilder auf einmal laden."""
    store.replace_documents("nextcloud", [_doc(f"d{i:03}.pdf") for i in range(10)])
    erste = store.list_documents(limit=4, offset=0)
    zweite = store.list_documents(limit=4, offset=4)
    assert len(erste) == 4
    assert len(zweite) == 4
    assert {d["name"] for d in erste}.isdisjoint({d["name"] for d in zweite})
    assert store.count_documents() == 10


def test_list_documents_filters_by_folder(store: Store) -> None:
    """Ordnerfilter nimmt auch Unterordner mit."""
    store.replace_documents(
        "nextcloud",
        [
            _doc("a.pdf", folder="/Dokumente/02 Medizinisch"),
            _doc("b.pdf", folder="/Dokumente/02 Medizinisch/Dritte"),
            _doc("c.pdf", folder="/Dokumente/01 Persönliches"),
        ],
    )
    treffer = store.list_documents("/Dokumente/02 Medizinisch")
    assert {d["name"] for d in treffer} == {"a.pdf", "b.pdf"}
    assert store.count_documents("/Dokumente/02 Medizinisch") == 2


def test_document_by_id(store: Store) -> None:
    store.replace_documents("nextcloud", [_doc("Ausweis.pdf", file_id="9426")])
    doc = store.list_documents()[0]
    geholt = store.document_by_id(int(doc["id"]))
    assert geholt is not None
    assert geholt["file_id"] == "9426"
    assert store.document_by_id(999999) is None


def test_ids_ueberleben_einen_crawl(store: Store) -> None:
    """Editor-Links duerfen nach dem naechsten Crawl nicht ins Leere zeigen.

    Vorher wurde bei jedem Lauf alles geloescht und neu eingefuegt, wodurch
    dieselbe Datei eine neue ID bekam. Ein Lesezeichen war damit nach
    spaetestens 15 Minuten tot. Aufgefallen am 05.09.2026 am gerenderten
    Bild: der Editor zeigte "Unbekanntes Dokument".
    """
    store.replace_documents("nextcloud", [_doc("Brief.docx"), _doc("Notiz.pdf")])
    vorher = {d["name"]: d["id"] for d in store.list_documents()}

    # Zweiter Crawl, gleiche Dateien, eine davon geaendert.
    store.replace_documents(
        "nextcloud",
        [_doc("Brief.docx", size=9999), _doc("Notiz.pdf")],
    )
    nachher = {d["name"]: d["id"] for d in store.list_documents()}

    assert vorher == nachher, "IDs haben sich verschoben"
    geaendert = next(d for d in store.list_documents() if d["name"] == "Brief.docx")
    assert geaendert["size_bytes"] == 9999, "Aenderung wurde nicht uebernommen"


def test_geloeschte_dateien_verschwinden(store: Store) -> None:
    """Der Index darf keine Karteileichen behalten."""
    store.replace_documents("nextcloud", [_doc("bleibt.pdf"), _doc("weg.pdf")])
    store.replace_documents("nextcloud", [_doc("bleibt.pdf")])
    assert [d["name"] for d in store.list_documents()] == ["bleibt.pdf"]


def test_folders_show_structure_without_filenames(store: Store) -> None:
    """Der Einstieg ohne Suche zeigt Ordner und Anzahl, keine Namen."""
    store.replace_documents(
        "nextcloud",
        [
            _doc("Befund.pdf", folder="/Dokumente/02 Medizinisch"),
            _doc("Bericht.pdf", folder="/Dokumente/02 Medizinisch/Dritte"),
            _doc("Ausweis.pdf", folder="/Dokumente/01 Persönliches"),
        ],
    )
    ordner = store.document_folders()
    # Kein Dateiname taucht in der Struktur auf.
    roh = str(ordner)
    assert "Befund" not in roh and "Bericht" not in roh


def test_folders_skip_pointless_root(store: Store) -> None:
    """Schluckt ein Sammelordner fast alles, ist er als Einstieg wertlos.

    Genau so sah es am 05.09.2026 aus: "Dokumente 159" und sonst nichts.
    Dann muss eine Ebene tiefer gruppiert werden.
    """
    store.replace_documents(
        "nextcloud",
        [
            _doc("a.pdf", folder="/Dokumente/02 Medizinisch"),
            _doc("b.pdf", folder="/Dokumente/02 Medizinisch/Dritte"),
            _doc("c.pdf", folder="/Dokumente/01 Persönliches"),
            _doc("d.pdf", folder="/Dokumente/01 Persönliches"),
            _doc("e.pdf", folder="/Mac Downloads"),
        ],
    )
    namen = [o["top"].strip("/").split("/")[-1] for o in store.document_folders()]
    assert "02 Medizinisch" in namen
    assert "01 Persönliches" in namen
    assert "Dokumente" not in namen, "nicht auf dem Sammelordner stehenbleiben"


def test_folders_keep_real_top_level(store: Store) -> None:
    """Verteilt sich der Bestand, bleibt es bei der obersten Ebene."""
    store.replace_documents(
        "nextcloud",
        [
            _doc("a.pdf", folder="/Dokumente/02 Medizinisch"),
            _doc("b.pdf", folder="/Mac Downloads"),
        ],
    )
    namen = {o["top"].strip("/") for o in store.document_folders()}
    assert namen == {"Dokumente", "Mac Downloads"}


def test_folders_empty_index(store: Store) -> None:
    assert store.document_folders() == []


def test_search_survives_fts_syntax(store: Store) -> None:
    """Eine Anfrage aus Sonderzeichen darf die Seite nicht zerlegen."""
    store.replace_documents("nextcloud", [_doc("Vertrag.pdf")])
    assert store.search_documents('"') == []
    assert store.search_documents("*") == []


def test_replace_removes_deleted_files(store: Store) -> None:
    store.replace_documents("nextcloud", [_doc("a.pdf"), _doc("b.pdf")])
    store.replace_documents("nextcloud", [_doc("a.pdf")])
    assert len(store.search_documents("a.pdf")) == 1
    assert store.search_documents("b.pdf") == []


def test_replace_keeps_other_sources(store: Store) -> None:
    """Der Nextcloud-Lauf darf meine eigenen Dokumente nicht mitloeschen."""
    store.replace_documents("jana", [_doc("Bewerbung.docx", source="jana")])
    store.replace_documents("nextcloud", [_doc("Ausweis.pdf")])
    assert store.document_stats()["gesamt"] == 2


def test_fts_index_survives_replace(store: Store) -> None:
    """Nach dem Ersetzen darf der Suchindex keine Karteileichen enthalten."""
    store.replace_documents("nextcloud", [_doc("Geburtsurkunde.pdf")])
    store.replace_documents("nextcloud", [_doc("Ausweis.pdf")])
    assert store.search_documents("geburtsurkunde") == []
    assert len(store.search_documents("ausweis")) == 1


# --- Kennzahlen -----------------------------------------------------------


def test_stats(store: Store) -> None:
    store.replace_documents("nextcloud", [_doc("a.pdf"), _doc("b.docx")])
    store.replace_documents("jana", [_doc("c.pdf", source="jana")])
    stats = store.document_stats()
    assert stats["gesamt"] == 3
    assert {q["source"] for q in stats["quellen"]} == {"nextcloud", "jana"}
    assert stats["typen"][0]["ext"] == ".pdf"


def test_stats_on_empty_index(store: Store) -> None:
    stats = store.document_stats()
    assert stats["gesamt"] == 0
    assert stats["neuestes"] is None


# --- Aufbereitung ---------------------------------------------------------


def test_entry_splits_path(store: Store) -> None:
    e = _entry("/Dokumente/01 Persönliches/Ausweis.pdf", 2048, "", "nextcloud")
    assert e["name"] == "Ausweis.pdf"
    assert e["folder"] == "/Dokumente/01 Persönliches"
    assert e["ext"] == ".pdf"


def test_iso_normalises_webdav_dates() -> None:
    """Ohne Normalisierung sortiert "Tue, 19 May" vor "Mon, 03 Aug"."""
    mai = _iso("Tue, 19 May 2026 10:00:00 GMT")
    august = _iso("Mon, 03 Aug 2026 10:00:00 GMT")
    assert mai < august


def test_iso_survives_garbage() -> None:
    assert _iso("") == ""
    assert _iso("kein datum") == ""


def test_doc_exts_excludes_media() -> None:
    """Bilder und Videos gehoeren nicht in einen Dokumenten-Index."""
    assert ".jpg" not in DOC_EXTS
    assert ".mp4" not in DOC_EXTS
    assert ".pdf" in DOC_EXTS


# --- Crawler --------------------------------------------------------------
#
# Der WebDAV-Teil wird gegen einen nachgebauten Server geprueft, weil genau
# hier der Fehler aus 08/2026 steckte: doppelt kodierte Pfade brechen die
# Rekursion still ab, und die Suche meldet dann faelschlich "nichts gefunden".


def _propfind_xml(user: str, entries: list[tuple[str, bool]]) -> str:
    """Eine WebDAV-Antwort bauen. hrefs sind URL-kodiert, wie beim Original."""
    import urllib.parse

    parts = []
    for i, (path, isdir) in enumerate(entries, start=1000):
        href = f"/remote.php/dav/files/{user}" + urllib.parse.quote(path)
        collection = "<d:collection/>" if isdir else ""
        size = "" if isdir else "<d:getcontentlength>2048</d:getcontentlength>"
        parts.append(
            f"<d:response><d:href>{href}</d:href><d:propstat><d:prop>"
            f"<d:resourcetype>{collection}</d:resourcetype>{size}"
            f"<d:getlastmodified>Mon, 03 Aug 2026 10:00:00 GMT</d:getlastmodified>"
            f"<oc:fileid>{i}</oc:fileid>"
            f"</d:prop></d:propstat></d:response>"
        )
    return f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">{"".join(parts)}</d:multistatus>'


@pytest.fixture
def fake_nextcloud(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Ein Nextcloud mit Umlaut-Ordner. Merkt sich die angefragten URLs.

    Gepatcht wird ``documents.settings``, nicht ``config.settings``: ``test_api``
    laedt ``src.config`` per ``importlib.reload`` neu und erzeugt dabei ein
    zweites Settings-Objekt. Der Collector haelt aber noch die Referenz vom
    Import. Wer das falsche Objekt patcht, sieht seinen Test allein bestehen
    und in der vollen Suite scheitern.
    """
    import httpx

    from src.collectors import documents as docmod

    monkeypatch.setattr(docmod.settings, "nextcloud_url", "https://nas.example.dev")
    monkeypatch.setattr(docmod.settings, "nextcloud_user", "mia")
    monkeypatch.setattr(docmod.settings, "nextcloud_password", "geheim")
    monkeypatch.setattr(docmod.settings, "documents_local_path", "")
    monkeypatch.setattr(docmod.settings, "documents_min_expected", 1)

    tree: dict[str, list[tuple[str, bool]]] = {
        "/": [("/Dokumente", True)],
        "/Dokumente": [("/Dokumente/01 Persönliches", True)],
        "/Dokumente/01 Persönliches": [
            ("/Dokumente/01 Persönliches/Meldebescheinigung.pdf", False),
            ("/Dokumente/01 Persönliches/Urlaubsfoto.jpg", False),
        ],
    }
    calls: dict[str, list[str]] = {"urls": [], "bodies": []}

    def handler(request: httpx.Request) -> httpx.Response:
        import urllib.parse

        calls["urls"].append(str(request.url))
        calls["bodies"].append(request.content.decode() if request.content else "")
        path = urllib.parse.unquote(request.url.path).split("/files/mia", 1)[-1] or "/"
        if path not in tree:
            return httpx.Response(404)
        body = _propfind_xml("mia", [(path, True), *tree[path]])
        return httpx.Response(207, text=body)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient.__init__

    def patched(self: httpx.AsyncClient, *a: Any, **kw: Any) -> None:
        kw["transport"] = transport
        original(self, *a, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)
    return calls


@pytest.mark.asyncio
async def test_crawl_walks_umlaut_folders(
    store: Store, fake_nextcloud: dict[str, list[str]]
) -> None:
    """Die Rekursion darf an "01 Persoenliches" nicht abbrechen."""
    from src.collectors.documents import DocumentCollector

    collector = DocumentCollector(store)
    assert await collector.run() is True

    treffer = store.search_documents("meldebescheinigung")
    assert len(treffer) == 1, "Datei hinter dem Umlaut-Ordner wurde nicht gefunden"


@pytest.mark.asyncio
async def test_crawl_encodes_path_exactly_once(
    store: Store, fake_nextcloud: dict[str, list[str]]
) -> None:
    """Doppelte Kodierung war der eigentliche Bug: %C3%B6 darf nie %25C3 werden."""
    from src.collectors.documents import DocumentCollector

    await DocumentCollector(store).run()
    assert not any("%25" in url for url in fake_nextcloud["urls"]), "Pfad wurde doppelt kodiert"


@pytest.mark.asyncio
async def test_crawl_skips_images(store: Store, fake_nextcloud: dict[str, list[str]]) -> None:
    from src.collectors.documents import DocumentCollector

    await DocumentCollector(store).run()
    assert store.search_documents("urlaubsfoto") == []


@pytest.mark.asyncio
async def test_collector_records_no_filenames(
    store: Store, fake_nextcloud: dict[str, list[str]]
) -> None:
    """Die Kennzahlen der Kategorie duerfen keinen Dateinamen enthalten.

    Der Leitwert steht auf der Startseite. Ein Arztbericht-Titel gehoert dort
    nicht hin, auch nicht als Bildunterschrift.
    """
    from src.collectors.documents import DocumentCollector

    await DocumentCollector(store).run()
    werte = str(store.latest("dokumente"))
    assert "Meldebescheinigung" not in werte
    assert ".pdf" not in werte


@pytest.mark.asyncio
async def test_partial_crawl_keeps_old_index(
    store: Store, fake_nextcloud: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ein abgebrochener Crawl darf den Index nicht leeren.

    Genau dieser Fall ist am 18.08.2026 passiert: 7 statt 1517 Dateien gesehen
    und daraus faelschlich "nicht vorhanden" gefolgert.
    """
    from src.collectors import documents as docmod

    store.replace_documents("nextcloud", [_doc("Wichtig.pdf")])
    monkeypatch.setattr(docmod.settings, "documents_min_expected", 500)

    assert await docmod.DocumentCollector(store).run() is False, (
        "zu kleiner Crawl muss fehlschlagen"
    )
    assert len(store.search_documents("wichtig")) == 1, "alter Index ueberlebt"


def test_collector_needs_credentials(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.collectors import documents as docmod

    monkeypatch.setattr(docmod.settings, "nextcloud_url", "")
    assert docmod.DocumentCollector(store).is_configured() is False


# --- Vorschau -------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawl_captures_fileid(store: Store, fake_nextcloud: dict[str, list[str]]) -> None:
    """Ohne oc:fileid gibt es keine Vorschau. Muss aus dem PROPFIND kommen."""
    from src.collectors.documents import DocumentCollector

    await DocumentCollector(store).run()
    doc = store.search_documents("meldebescheinigung")[0]
    assert doc["file_id"], "fileid fehlt, Vorschau waere unmoeglich"
    assert doc["file_id"].isdigit()


@pytest.mark.asyncio
async def test_propfind_requests_fileid(store: Store, fake_nextcloud: dict[str, list[str]]) -> None:
    """Nextcloud liefert oc:fileid nur, wenn man sie im Rumpf anfordert."""
    from src.collectors.documents import PROPFIND_BODY, DocumentCollector

    await DocumentCollector(store).run()
    assert "oc:fileid" in PROPFIND_BODY
    assert fake_nextcloud["bodies"], "kein PROPFIND-Rumpf gesendet"
    assert all("oc:fileid" in b for b in fake_nextcloud["bodies"])


def test_migration_adds_fileid_to_old_db(tmp_path: Path) -> None:
    """Eine bestehende DB ohne file_id darf beim Start nicht scheitern.

    ``CREATE TABLE IF NOT EXISTS`` fasst vorhandene Tabellen nicht an, deshalb
    braucht es das ALTER. Sonst laeuft es lokal und stirbt auf dem LXC.
    """
    import sqlite3

    pfad = tmp_path / "alt.db"
    conn = sqlite3.connect(pfad)
    conn.executescript(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL, path TEXT NOT NULL, name TEXT NOT NULL,
            folder TEXT NOT NULL DEFAULT '', ext TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            modified_at TEXT NOT NULL DEFAULT '',
            seen_at TEXT NOT NULL, UNIQUE(source, path)
        );
        INSERT INTO documents (source, path, name, seen_at)
        VALUES ('nextcloud', '/alt.pdf', 'alt.pdf', '2026-09-05T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    store = Store(str(pfad))
    doc = store.list_documents()[0]
    assert doc["name"] == "alt.pdf", "Bestand ueberlebt die Migration"
    assert doc["file_id"] == ""
