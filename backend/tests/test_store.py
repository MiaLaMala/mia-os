"""Tests fuer den SQLite-Speicher."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(str(tmp_path / "test.db"))


def test_record_and_latest(store: Store) -> None:
    store.record("gesundheit", "gewicht", 89.5, unit="kg")
    rows = store.latest("gesundheit")
    assert len(rows) == 1
    assert rows[0]["value"] == 89.5
    assert rows[0]["unit"] == "kg"


def test_latest_returns_newest_per_key(store: Store) -> None:
    store.record("gesundheit", "gewicht", 90.0)
    store.record("gesundheit", "gewicht", 89.5)
    rows = store.latest("gesundheit")
    assert len(rows) == 1, "je Key nur ein Eintrag"
    assert rows[0]["value"] == 89.5, "und zwar der neueste"


def test_latest_isolates_categories(store: Store) -> None:
    store.record("gesundheit", "gewicht", 89.5)
    store.record("homelab", "gewicht", 1.0)
    assert len(store.latest("gesundheit")) == 1
    assert store.latest("gesundheit")[0]["value"] == 89.5


def test_text_values(store: Store) -> None:
    store.record("termine", "liste_heute", text_value="Berufsschule | Arzt")
    row = store.latest("termine")[0]
    assert row["text_value"] == "Berufsschule | Arzt"
    assert row["value"] is None


def test_history_is_ordered(store: Store) -> None:
    for value in (90.0, 89.8, 89.5):
        store.record("gesundheit", "gewicht", value)
    hist = store.history("gesundheit", "gewicht", days=1)
    assert [h["value"] for h in hist] == [90.0, 89.8, 89.5]


def test_history_empty_for_unknown_key(store: Store) -> None:
    assert store.history("gesundheit", "gibtsnicht") == []


def test_record_run_and_last_runs(store: Store) -> None:
    store.record_run("gesundheit", True, None, 120)
    store.record_run("termine", False, "Timeout", 5000)
    runs = {r["collector"]: r for r in store.last_runs()}
    assert runs["gesundheit"]["ok"] == 1
    assert runs["termine"]["error"] == "Timeout"


def test_last_runs_keeps_only_newest(store: Store) -> None:
    store.record_run("gesundheit", False, "alter Fehler", 10)
    store.record_run("gesundheit", True, None, 20)
    runs = store.last_runs()
    assert len(runs) == 1
    assert runs[0]["ok"] == 1


def test_prune_removes_nothing_when_fresh(store: Store) -> None:
    store.record("gesundheit", "gewicht", 89.5)
    assert store.prune(keep_days=400) == 0
    assert len(store.latest("gesundheit")) == 1


def test_schema_is_idempotent(tmp_path: Path) -> None:
    path = str(tmp_path / "twice.db")
    Store(path).record("gesundheit", "gewicht", 1.0)
    assert len(Store(path).latest("gesundheit")) == 1, "zweite Instanz darf nichts loeschen"


# --- Vektoren fuer den Ordnervorschlag ------------------------------------


def _dok(store: Store, pfad: str, name: str) -> int:
    ordner_ = pfad.rsplit("/", 1)[0]
    return int(
        store.upsert_document(
            {"source": "nextcloud", "path": pfad, "name": name, "folder": ordner_, "ext": ".pdf"}
        )
    )


def test_ohne_embed_liefert_was_fehlt(store: Store) -> None:
    doc_id = _dok(store, "/Dokumente/01 A/Bescheid.pdf", "Bescheid.pdf")
    offen = store.documents_ohne_embed()
    assert [d["id"] for d in offen] == [doc_id]

    store.set_document_embed(doc_id, b"\x00" * 12, "Bescheid.pdf")
    assert store.documents_ohne_embed() == []


def test_umbenennung_macht_den_vektor_ungueltig(store: Store) -> None:
    """Der Vektor haengt am Namen. Ohne diesen Vergleich rechnete der
    Vorschlag dauerhaft mit dem alten Namen weiter."""
    doc_id = _dok(store, "/Dokumente/01 A/Scan_001.pdf", "Scan_001.pdf")
    store.set_document_embed(doc_id, b"\x00" * 12, "Scan_001.pdf")
    assert store.documents_ohne_embed() == []

    store.upsert_document(
        {
            "source": "nextcloud",
            "path": "/Dokumente/01 A/Scan_001.pdf",
            "name": "Widerspruch Kasse.pdf",
            "folder": "/Dokumente/01 A",
            "ext": ".pdf",
        }
    )
    assert [d["id"] for d in store.documents_ohne_embed()] == [doc_id]


def test_belegordner_bleibt_aus_den_vektoren_draussen(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Der Belegordner ist Ausgangspunkt des Vorschlags, nicht sein Ziel.

    Seine Dateien duerfen die Schwerpunkte der echten Sachordner nicht
    mitbestimmen, sonst zieht die Halde die Vorschlaege zu sich.
    """
    import src.store

    monkeypatch.setattr(src.store.settings, "belege_ordner", "/Dokumente/00 Belege")
    _dok(store, "/Dokumente/00 Belege/Frisch.pdf", "Frisch.pdf")
    behalten = _dok(store, "/Dokumente/01 A/Alt.pdf", "Alt.pdf")

    assert [d["id"] for d in store.documents_ohne_embed()] == [behalten]

    store.set_document_embed(behalten, b"\x00" * 12, "Alt.pdf")
    assert [d["id"] for d in store.documents_mit_embed()] == [behalten]


def test_verschieben_zieht_anhaenge_mit(store: Store) -> None:
    alt = "/Dokumente/00 Belege/Bescheid.pdf"
    neu = "/Dokumente/01 A/Bescheid.pdf"
    _dok(store, alt, "Bescheid.pdf")
    eintrag = store.create_entry("Widerspruch")
    store.link_document(eintrag, "nextcloud", alt, "Bescheid.pdf")

    store.move_document("nextcloud", alt, neu, "/Dokumente/01 A")

    anhaenge = store.documents_for_entry(eintrag)
    assert [a["path"] for a in anhaenge] == [neu]
    assert anhaenge[0]["folder"] == "/Dokumente/01 A"


def test_verschieben_ueberlebt_eine_leiche_am_zielpfad(store: Store) -> None:
    """Beim Durchspielen mit echten Daten gefunden, nicht am Code.

    Steht am Zielpfad noch eine Indexzeile (Datei ausserhalb geloescht, Crawl
    noch nicht gelaufen), scheitert das UPDATE an UNIQUE(source, path) - und
    zwar erst, nachdem Nextcloud schon verschoben hat. Die Datei laege am
    neuen Ort und der Index zeigte auf den alten: Mias frisch einsortierter
    Beleg saehe aus wie verschwunden.
    """
    alt = "/Dokumente/00 Belege/Bescheid.pdf"
    neu = "/Dokumente/01 A/Bescheid.pdf"
    _dok(store, alt, "Bescheid.pdf")
    _dok(store, neu, "Bescheid.pdf")  # die Leiche
    eintrag = store.create_entry("Widerspruch")
    store.link_document(eintrag, "nextcloud", alt, "Bescheid.pdf")

    store.move_document("nextcloud", alt, neu, "/Dokumente/01 A")

    anhaenge = store.documents_for_entry(eintrag)
    assert [a["path"] for a in anhaenge] == [neu]
    assert not anhaenge[0]["fehlt"]
