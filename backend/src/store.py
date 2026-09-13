"""SQLite-Speicher fuer Zeitreihen.

Bewusst SQLite: eine Datei, kein Server, Backup = kopieren. Fuer ein
persoenliches Dashboard mit stuendlichen Messwerten voellig ausreichend.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.config import settings

log = logging.getLogger(__name__)

# Wie viel Text vor dem ersten Treffer stehen bleibt.
#
# Am gerenderten Bild gefunden: auf der Kachel stand
# ``… 03.09.2026 | [Aktenzeic…`` und die Nummer war abgeschnitten. Der Anlauf
# vor dem Treffer hatte den ganzen Platz gefressen, und der Wert, wegen dem
# jemand sucht, steht fast immer dahinter: ein Aktenzeichen, ein Betrag, ein
# Datum. Also wird vorne gekuerzt, nicht hinten.
STELLE_VORLAUF = 22


def _stelle_kuerzen(stelle: str) -> str:
    """Den Anlauf vor dem ersten Treffer stutzen.

    Der Platz reicht auf einer Handykachel fuer etwa 40 Zeichen. Steht der
    Treffer erst bei Zeichen 30, ist von dem, was dahinter kommt, nichts mehr
    zu sehen. Genau das war der Fall bei ``[Aktenzeichen]: 43-044-26211``:
    das gesuchte Wort war da, die Nummer nicht.
    """
    anfang = stelle.find("[")
    if anfang <= STELLE_VORLAUF:
        return stelle
    # An einer Wortgrenze schneiden, sonst beginnt die Anzeige mitten im Wort.
    schnitt = stelle.find(" ", anfang - STELLE_VORLAUF)
    if schnitt == -1 or schnitt >= anfang:
        schnitt = anfang
    return "… " + stelle[schnitt:].lstrip()


SCHEMA = """
CREATE TABLE IF NOT EXISTS metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT    NOT NULL,
    key         TEXT    NOT NULL,
    value       REAL,
    text_value  TEXT,
    unit        TEXT,
    collected_at TEXT   NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_lookup ON metrics(category, key, collected_at DESC);

CREATE TABLE IF NOT EXISTS collector_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    collector    TEXT    NOT NULL,
    ok           INTEGER NOT NULL,
    error        TEXT,
    duration_ms  INTEGER,
    ran_at       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_collector ON collector_runs(collector, ran_at DESC);

-- Termine aus dem CalDAV. Nur was die Anzeige braucht: Titel, Zeit, Ort,
-- Kalender. Keine Beschreibungen, keine Teilnehmer.
CREATE TABLE IF NOT EXISTS events (
    uid         TEXT    NOT NULL,
    start_at    TEXT    NOT NULL,
    end_at      TEXT    NOT NULL DEFAULT '',
    title       TEXT    NOT NULL,
    location    TEXT    NOT NULL DEFAULT '',
    calendar    TEXT    NOT NULL DEFAULT '',
    ganztags    INTEGER NOT NULL DEFAULT 0,
    seen_at     TEXT    NOT NULL,
    PRIMARY KEY (uid, start_at)
);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_at);

-- Was Mia selbst zu einem Termin schreibt.
--
-- Der Kalender kommt aus iCloud und bleibt duenn: von 187 Terminen hat
-- KEINER eine Beschreibung, einen Ort oder Teilnehmer. Mehr anzuzeigen geht
-- nicht, also legt Mia OS eigene Informationen daneben.
--
-- Gebunden an die Termin-UID, nicht an Datum oder Titel: die UID ueberlebt
-- Verschieben und Umbenennen. Wird ein Termin geloescht, bleibt die Notiz
-- verwaist stehen, statt still zu verschwinden.
CREATE TABLE IF NOT EXISTS event_notes (
    uid         TEXT    PRIMARY KEY,
    notiz       TEXT    NOT NULL DEFAULT '',
    updated_at  TEXT    NOT NULL
);

-- Aufgaben. Entweder frei stehend oder an einen Termin gehaengt.
--
-- Bewusst NICHT im Kalender: was zu erledigen ist, hat selten eine Uhrzeit.
-- Genau das fehlt in iCloud und ist der Grund fuer diese Tabelle.
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    titel       TEXT    NOT NULL,
    erledigt    INTEGER NOT NULL DEFAULT 0,
    -- Leer, wenn die Aufgabe zu keinem Termin gehoert.
    event_uid   TEXT    NOT NULL DEFAULT '',
    -- Optionales Faelligkeitsdatum, damit sie im Kalender auftauchen kann.
    faellig_am  TEXT    NOT NULL DEFAULT '',
    sortierung  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_event ON tasks(event_uid);
CREATE INDEX IF NOT EXISTS idx_tasks_faellig ON tasks(faellig_am);
CREATE INDEX IF NOT EXISTS idx_tasks_offen ON tasks(erledigt, faellig_am);

-- Seiten. Das Grundelement, wie in Notion.
--
-- Eine Seite kann Text tragen, eine Sammlung, Unterseiten, oder alles
-- zusammen. Sie kennt ihre Eltern, dadurch entsteht der Baum in der
-- Seitenleiste. Ohne Eltern steht sie ganz oben.
--
-- Bewusst KEINE feste Navigation mehr: Mia legt ihre Struktur selbst an.
-- Genau das unterscheidet eine Zentrale von einer Anzeigetafel.
CREATE TABLE IF NOT EXISTS pages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id   INTEGER REFERENCES pages(id) ON DELETE CASCADE,
    titel       TEXT    NOT NULL DEFAULT '',
    -- Ein Symbolname aus icons.py, kein Emoji: Inter hat keine Emoji-Glyphen.
    symbol      TEXT    NOT NULL DEFAULT 'document',
    -- Freier Text der Seite.
    inhalt      TEXT    NOT NULL DEFAULT '',
    -- Zeigt die Seite eine Sammlung? Dann welche Ansicht zuerst.
    hat_sammlung INTEGER NOT NULL DEFAULT 0,
    ansicht     TEXT    NOT NULL DEFAULT 'liste',
    gruppe_nach TEXT    NOT NULL DEFAULT 'status',
    -- Sammelseite: zeigt ALLE Eintraege, egal auf welcher Seite sie liegen.
    -- "Alles" ist so eine. Sonst waere sie nur ein weiterer Ordner.
    sammelt_alles INTEGER NOT NULL DEFAULT 0,
    sortierung  REAL    NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pages_parent ON pages(parent_id, sortierung);

-- Das Notion-Modell: eine Sammlung von Eintraegen.
--
-- Ein Eintrag ist wie eine Notion-Seite: er hat einen Titel, freien Inhalt
-- und beliebige Eigenschaften. Kalender, Tabelle, Board und Liste sind nur
-- verschiedene Blicke auf DIESELBEN Zeilen, nicht getrennte Werkzeuge.
--
-- Die Eigenschaften stehen als JSON in einer Spalte statt in eigenen
-- Tabellen: so kann Mia eine neue Eigenschaft anlegen, ohne dass jemand die
-- Datenbank umbaut. Genau das macht Notion aus.
CREATE TABLE IF NOT EXISTS entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    titel       TEXT    NOT NULL DEFAULT '',
    -- Freier Text unter dem Titel, wie der Seiteninhalt in Notion.
    inhalt      TEXT    NOT NULL DEFAULT '',
    -- {"status": "offen", "tags": ["Schule"], "prio": "hoch", ...}
    eigenschaften TEXT  NOT NULL DEFAULT '{}',
    -- Wann der Eintrag im Kalender steht. Leer = taucht dort nicht auf.
    datum       TEXT    NOT NULL DEFAULT '',
    -- Optionale Uhrzeit. Ohne sie ist es ein ganztaegiger Eintrag.
    zeit        TEXT    NOT NULL DEFAULT '',
    -- Wenn der Eintrag zu einem iCloud-Termin gehoert.
    event_uid   TEXT    NOT NULL DEFAULT '',
    -- Auf welcher Seite der Eintrag liegt. 0 = in der Hauptsammlung.
    page_id     INTEGER NOT NULL DEFAULT 0,
    sortierung  REAL    NOT NULL DEFAULT 0,
    archiviert  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entries_datum ON entries(datum);
CREATE INDEX IF NOT EXISTS idx_entries_event ON entries(event_uid);
CREATE INDEX IF NOT EXISTS idx_entries_aktiv ON entries(archiviert, datum);
CREATE INDEX IF NOT EXISTS idx_entries_page ON entries(page_id);

-- Welche Eigenschaften es gibt und wie sie aussehen.
--
-- In Notion legt man Spalten selbst an: Status, Tags, Prioritaet, Datum.
-- Genau das steht hier, damit die Oberflaeche weiss, wie sie ein Feld
-- zeichnen soll und welche Werte erlaubt sind.
CREATE TABLE IF NOT EXISTS entry_props (
    key         TEXT    PRIMARY KEY,
    name        TEXT    NOT NULL,
    -- auswahl | mehrfach | text | zahl | datum | haken
    art         TEXT    NOT NULL,
    -- Fuer Auswahlfelder: [{"wert": "offen", "farbe": "blau"}, ...]
    optionen    TEXT    NOT NULL DEFAULT '[]',
    sortierung  INTEGER NOT NULL DEFAULT 0
);

-- Was Mia selbst einstellen kann. Bewusst getrennt von .env: dort stehen
-- Zugangsdaten, hier stehen Vorlieben, die sich im Betrieb aendern duerfen.
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Gekoppelte Apps. Ein Eintrag pro Geraet, auf dem Mia OS laeuft.
--
-- Gespeichert wird NUR der SHA-256-Abdruck des Schluessels, nie der
-- Schluessel selbst. Wer diese Datei in die Hand bekommt, kann sich damit
-- nicht anmelden. Dieselbe Ueberlegung wie beim Dokumenten-Index: auf einer
-- Ablage mit Ausweisen wird kein Geheimnis zweimal hingelegt.
CREATE TABLE IF NOT EXISTS geraetezugang (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    abdruck     TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL DEFAULT '',
    plattform   TEXT    NOT NULL DEFAULT '',
    erstellt_at TEXT    NOT NULL,
    zuletzt_at  TEXT    NOT NULL DEFAULT '',
    adresse     TEXT    NOT NULL DEFAULT ''
);

-- Zustand der ueberwachten Dienste (aus Uptime Kuma). Nur Name, Status und
-- Verfuegbarkeit, keine Zugangsdaten.
CREATE TABLE IF NOT EXISTS services (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    status      INTEGER NOT NULL DEFAULT 2,
    msg         TEXT    NOT NULL DEFAULT '',
    ping        INTEGER NOT NULL DEFAULT 0,
    uptime24    REAL    NOT NULL DEFAULT -1,
    uptime30    REAL    NOT NULL DEFAULT -1,
    seit        TEXT    NOT NULL DEFAULT '',
    seen_at     TEXT    NOT NULL
);

-- Dokumenten-Index. Bewusst NUR Metadaten: Name, Pfad, Groesse, Datum.
-- Dateiinhalte werden nie gespeichert, dort liegen Ausweise und Recovery-Codes.
--
-- Eine Ausnahme, und nur eine: ``ocr_text`` fuer Belege, die Mia selbst durch
-- den Scanner geschickt hat. Sie hatte das Blatt dabei in der Hand. Fuer den
-- Bestand bleibt die Spalte leer, durchgesetzt in ``set_document_text``.
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    path        TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    folder      TEXT    NOT NULL DEFAULT '',
    ext         TEXT    NOT NULL DEFAULT '',
    size_bytes  INTEGER NOT NULL DEFAULT 0,
    modified_at TEXT    NOT NULL DEFAULT '',
    file_id     TEXT    NOT NULL DEFAULT '',
    ocr_text    TEXT    NOT NULL DEFAULT '',
    -- Vektor fuer den Ordnervorschlag (float32-Bytes) und der Name, fuer den
    -- er gilt. Siehe ordner.py. NULL heisst schlicht: noch nicht gerechnet.
    embed       BLOB,
    embed_name  TEXT    NOT NULL DEFAULT '',
    seen_at     TEXT    NOT NULL,
    UNIQUE(source, path)
);
CREATE INDEX IF NOT EXISTS idx_documents_name ON documents(name);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source);

-- Berichtsheft: Mias Korrekturen am Wochenentwurf.
--
-- Der Entwurf selbst wird bei jedem Aufruf frisch aus dem Kalender gebaut,
-- er steht deshalb nicht hier. Gespeichert wird nur, was Mia dazuschreibt:
-- sonst wuerde ein nachtraeglich eingetragener Termin die Stunden nicht mehr
-- korrigieren.
CREATE TABLE IF NOT EXISTS berichtswochen (
    montag       TEXT PRIMARY KEY,
    -- entwurf | bearbeitet | fertig
    status       TEXT NOT NULL DEFAULT 'entwurf',
    -- {"2026-09-07": {"taetigkeiten": [...], "art": "krank", "stunden": 0}}
    inhalt       TEXT NOT NULL DEFAULT '{}',
    themen_schule TEXT NOT NULL DEFAULT '',
    bemerkung    TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- Welches Dokument gehoert zu welchem Eintrag.
--
-- Verknuepft wird ueber (source, path), NICHT ueber documents.id: eine Datei,
-- die aus dem Index faellt und beim naechsten Crawl wiederkommt, bekommt eine
-- neue Zeile. Der Pfad ueberlebt das. ``name`` steht als Abschrift daneben,
-- damit ein Verweis auf eine verschobene Datei noch sagen kann, worauf er mal
-- zeigte, statt eine leere Zeile zu sein.
CREATE TABLE IF NOT EXISTS entry_documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id    INTEGER NOT NULL,
    source      TEXT    NOT NULL,
    path        TEXT    NOT NULL,
    name        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL,
    UNIQUE(entry_id, source, path)
);
CREATE INDEX IF NOT EXISTS idx_entry_documents_entry ON entry_documents(entry_id);
CREATE INDEX IF NOT EXISTS idx_entry_documents_datei ON entry_documents(source, path);
"""

# Volltextsuche ueber den Index. ``ocr_text`` ist bei allem aus dem Bestand
# leer, gefuellt ist es nur bei selbst gescannten Belegen.
#
# Steht bewusst getrennt von ``SCHEMA``: die Spaltenliste einer FTS5-Tabelle
# laesst sich nicht per ALTER erweitern, ein Ausbau heisst neu bauen und neu
# fuellen. Das erledigt ``_fts_sicherstellen``, und dafuer muss dieser Teil
# einzeln ausfuehrbar sein.
#
# Die Gewichtung steht in der Abfrage, nicht hier: ein Treffer im Dateinamen
# muss ueber einem Treffer irgendwo im Fliesstext stehen, sonst schiebt sich
# ein Beleg, in dem "Buxtehude" achtmal vorkommt, vor die Datei, die genau so
# heisst.
DOKUMENTE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
USING fts5(name, folder, ocr_text, content='documents', content_rowid='id',
           tokenize='unicode61');

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, name, folder, ocr_text)
    VALUES (new.id, new.name, new.folder, new.ocr_text);
END;
CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, name, folder, ocr_text)
    VALUES ('delete', old.id, old.name, old.folder, old.ocr_text);
END;
CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, name, folder, ocr_text)
    VALUES ('delete', old.id, old.name, old.folder, old.ocr_text);
    INSERT INTO documents_fts(rowid, name, folder, ocr_text)
    VALUES (new.id, new.name, new.folder, new.ocr_text);
END;
"""


class Store:
    """Duenner Wrapper um SQLite. Kein ORM, die Abfragen sind trivial."""

    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            # ERST migrieren, DANN das Schema anlegen: SCHEMA enthaelt einen
            # Index auf entries(page_id). Fehlt die Spalte in einer alten
            # Datenbank, scheitert executescript, bevor _migrate ueberhaupt
            # laeuft. Genau daran ist der Deploy gestorben.
            self._migrate(conn)
            conn.executescript(SCHEMA)
            self._migrate(conn)
            self._fts_sicherstellen(conn)

    @staticmethod
    def _fts_sicherstellen(conn: sqlite3.Connection) -> None:
        """Die Suchtabelle anlegen, und neu bauen wenn ihr eine Spalte fehlt.

        ``CREATE VIRTUAL TABLE IF NOT EXISTS`` fasst eine vorhandene Tabelle
        nicht an, und eine FTS5-Tabelle kennt kein ``ALTER TABLE ADD COLUMN``.
        Auf dem LXC liegt eine Datenbank mit der alten zweispaltigen Fassung:
        ohne diesen Schritt liefe der Container weiter und jede Suche stuerbe
        an ``no such column: ocr_text`` in den Triggern.

        Neu gebaut wird die Suchtabelle, nicht der Index: ``rebuild`` liest
        die Inhalte aus ``documents`` zurueck, die eigentlichen Daten liegen
        dort. Bei 188 Dokumenten dauert das keine Sekunde.
        """
        spalten = {r[1] for r in conn.execute("PRAGMA table_info(documents_fts)")}
        if spalten and "ocr_text" not in spalten:
            # Erst die Trigger weg: sie zeigen auf die alte Spaltenliste und
            # wuerden beim naechsten Schreiben in ``documents`` scheitern.
            for name in ("documents_ai", "documents_ad", "documents_au"):
                conn.execute(f"DROP TRIGGER IF EXISTS {name}")
            conn.execute("DROP TABLE documents_fts")
            spalten = set()

        conn.executescript(DOKUMENTE_FTS)
        if not spalten:
            conn.execute("INSERT INTO documents_fts(documents_fts) VALUES ('rebuild')")

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Nachtraeglich ergaenzte Spalten anlegen.

        ``CREATE TABLE IF NOT EXISTS`` fasst eine vorhandene Tabelle nicht an.
        Ohne diesen Schritt laeuft eine neue Spalte lokal (frische Datei) und
        stirbt auf dem LXC, wo die alte Datei liegt.

        Laeuft ZWEIMAL: einmal vor dem Schema, weil dort ein Index auf einer
        neuen Spalte steht, und einmal danach fuer frische Datenbanken. Fehlt
        eine Tabelle noch, wird sie uebersprungen statt zu scheitern.
        """

        def spalten(tabelle: str) -> set[str]:
            return {r["name"] for r in conn.execute(f"PRAGMA table_info({tabelle})")}

        dokumente = spalten("documents")
        if dokumente and "file_id" not in dokumente:
            conn.execute("ALTER TABLE documents ADD COLUMN file_id TEXT NOT NULL DEFAULT ''")
        # Text aus selbst gescannten Belegen. Fuer den Bestand bleibt die
        # Spalte leer, siehe set_document_text.
        if dokumente and "ocr_text" not in dokumente:
            conn.execute("ALTER TABLE documents ADD COLUMN ocr_text TEXT NOT NULL DEFAULT ''")
        # Der Vektor fuer den Ordnervorschlag, als float32-Bytes.
        #
        # Er haengt am Dateinamen, nicht am Inhalt: eine umbenannte Datei
        # braucht einen neuen. ``embed_name`` haelt fest, wofuer er gilt, sonst
        # liesse sich das nicht unterscheiden und der Vorschlag rechnete
        # dauerhaft mit dem alten Namen weiter.
        if dokumente and "embed" not in dokumente:
            conn.execute("ALTER TABLE documents ADD COLUMN embed BLOB")
            conn.execute("ALTER TABLE documents ADD COLUMN embed_name TEXT NOT NULL DEFAULT ''")

        # Eintraege gehoeren seit den Seiten zu einer Seite.
        eintraege = spalten("entries")
        if eintraege and "page_id" not in eintraege:
            conn.execute("ALTER TABLE entries ADD COLUMN page_id INTEGER NOT NULL DEFAULT 0")

        seiten = spalten("pages")
        if seiten and "sammelt_alles" not in seiten:
            conn.execute("ALTER TABLE pages ADD COLUMN sammelt_alles INTEGER NOT NULL DEFAULT 0")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(
        self,
        category: str,
        key: str,
        value: float | None = None,
        text_value: str | None = None,
        unit: str | None = None,
    ) -> None:
        """Einen Messwert ablegen. Zahl und Text schliessen sich nicht aus."""
        if isinstance(text_value, (dict, list)):
            text_value = json.dumps(text_value, ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO metrics (category, key, value, text_value, unit, collected_at)"
                " VALUES (?,?,?,?,?,?)",
                (category, key, value, text_value, unit, _now()),
            )

    def record_run(self, collector: str, ok: bool, error: str | None, duration_ms: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO collector_runs (collector, ok, error, duration_ms, ran_at)"
                " VALUES (?,?,?,?,?)",
                (collector, int(ok), error, duration_ms, _now()),
            )

    def latest(self, category: str) -> list[dict[str, Any]]:
        """Je Key den neuesten Wert einer Kategorie."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT m.* FROM metrics m
                JOIN (
                    SELECT key, MAX(collected_at) AS mx
                    FROM metrics WHERE category = ? GROUP BY key
                ) t ON m.key = t.key AND m.collected_at = t.mx
                WHERE m.category = ?
                ORDER BY m.key
                """,
                (category, category),
            ).fetchall()
        return [dict(r) for r in rows]

    def history(self, category: str, key: str, days: int = 30) -> list[dict[str, Any]]:
        """Verlauf eines Werts. Genau der Teil, den ein Momentaufnahme-Dashboard nicht kann."""
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT value, text_value, collected_at FROM metrics"
                " WHERE category=? AND key=? AND collected_at >= ?"
                " ORDER BY collected_at",
                (category, key, since),
            ).fetchall()
        return [dict(r) for r in rows]

    def last_runs(self) -> list[dict[str, Any]]:
        """Letzter Lauf je Collector, fuer die Statusanzeige."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT r.* FROM collector_runs r
                JOIN (
                    SELECT collector, MAX(ran_at) AS mx FROM collector_runs GROUP BY collector
                ) t ON r.collector = t.collector AND r.ran_at = t.mx
                ORDER BY r.collector
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def prune(self, keep_days: int = 400) -> int:
        """Alte Werte wegwerfen, damit die Datei nicht unbegrenzt waechst."""
        cutoff = (datetime.now(UTC) - timedelta(days=keep_days)).isoformat()
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM metrics WHERE collected_at < ?", (cutoff,))
            return cur.rowcount

    # --- Dokumenten-Index -------------------------------------------------

    def replace_documents(self, source: str, docs: list[dict[str, Any]]) -> dict[str, int]:
        """Den Bestand einer Quelle ersetzen, ohne IDs zu verlieren.

        Frueher wurde erst alles geloescht und neu eingefuegt. Dabei bekam
        jedes Dokument bei jedem Crawl eine neue ID, und jeder Editor-Link
        zeigte nach spaetestens 15 Minuten ins Leere. Jetzt zaehlt ``path``
        als Kennung: Bekanntes wird aktualisiert, nur wirklich Verschwundenes
        faellt raus.

        Laeuft in einer Transaktion: bricht der Crawl mittendrin ab, bleibt
        der alte Index stehen statt halb geleert zu werden.
        """
        now = _now()
        with self._conn() as conn:
            vorher = {
                r["path"]
                for r in conn.execute("SELECT path FROM documents WHERE source=?", (source,))
            }
            jetzt = {d["path"] for d in docs}

            conn.executemany(
                "INSERT INTO documents"
                " (source, path, name, folder, ext, size_bytes, modified_at, file_id, seen_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(source, path) DO UPDATE SET"
                "   name=excluded.name, folder=excluded.folder, ext=excluded.ext,"
                "   size_bytes=excluded.size_bytes, modified_at=excluded.modified_at,"
                "   file_id=excluded.file_id, seen_at=excluded.seen_at",
                [
                    (
                        source,
                        d["path"],
                        d["name"],
                        d.get("folder", ""),
                        d.get("ext", ""),
                        int(d.get("size_bytes", 0)),
                        d.get("modified_at", ""),
                        d.get("file_id", ""),
                        now,
                    )
                    for d in docs
                ],
            )

            verschwunden = vorher - jetzt
            if verschwunden:
                conn.executemany(
                    "DELETE FROM documents WHERE source=? AND path=?",
                    [(source, p) for p in verschwunden],
                )
        return {"vorher": len(vorher), "nachher": len(jetzt)}

    def search_documents(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Volltextsuche ueber Namen, Ordner und den Text gescannter Belege.

        Eine leere Anfrage liefert bewusst **nichts**. Der Index enthaelt
        Arztberichte, Ausweise und Unterlagen Dritter: eine Startansicht mit
        den zuletzt geaenderten Dateien legt genau die offen, sobald jemand
        das Dashboard aufmacht. Dateinamen erscheinen nur auf gezielte Suche.

        **Der Name wiegt zehnmal so schwer wie der Fliesstext.** Ohne die
        Gewichtung gewinnt ein Beleg, in dem "Buxtehude" achtmal vorkommt,
        gegen die Datei, die genau so heisst: FTS5 belohnt Haeufigkeit, und
        ein Dateiname hat je Wort genau ein Vorkommen. Wer den Namen kennt,
        will ihn oben sehen, das ist der haeufigere Fall.

        ``snippet()`` liefert die Fundstelle im Text mit Markierungen. Sie
        wird nur mitgegeben, wo tatsaechlich Text steht, und das ist
        ausschliesslich bei selbst gescannten Belegen der Fall.
        """
        query = query.strip()
        if not query:
            return []

        with self._conn() as conn:
            # Praefix-Suche je Wort: "meld beschein" findet "Meldebescheinigung".
            terms = " ".join(f'"{w}"*' for w in query.replace('"', " ").split() if w)
            if not terms:
                return []
            try:
                rows = conn.execute(
                    "SELECT d.*,"
                    # 8 Woerter Umgebung: genug fuer eine Zeile Behoerdendeutsch,
                    # kurz genug, dass die Trefferliste eine Liste bleibt.
                    "  snippet(documents_fts, 2, '[', ']', ' … ', 8) AS stelle"
                    " FROM documents_fts f JOIN documents d ON d.id = f.rowid"
                    " WHERE documents_fts MATCH ?"
                    " ORDER BY bm25(documents_fts, 10.0, 2.0, 1.0) LIMIT ?",
                    (terms, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                # Kaputte FTS-Syntax darf die Seite nicht zerlegen.
                like = f"%{query}%"
                rows = conn.execute(
                    "SELECT *, '' AS stelle FROM documents WHERE name LIKE ? OR folder LIKE ?"
                    " ORDER BY modified_at DESC LIMIT ?",
                    (like, like, limit),
                ).fetchall()

        treffer = []
        for r in rows:
            d = dict(r)
            # Die Fundstelle nur zeigen, wenn sie aus dem Text kommt. Bei einem
            # reinen Namenstreffer gibt snippet() den Textanfang zurueck, und
            # der stuende dann ohne Bezug zur Suche unter der Kachel.
            if not d.get("ocr_text") or "[" not in (d.get("stelle") or ""):
                d["stelle"] = ""
            else:
                # Zeilenumbrueche raus: der Ausschnitt geht ueber Zeilengrenzen
                # und landet in einer einzeiligen Anzeige. Am gerenderten Bild
                # aufgefallen, im JSON sah er in Ordnung aus.
                d["stelle"] = _stelle_kuerzen(" ".join(str(d["stelle"]).split()))
            treffer.append(d)
        return treffer

    def list_documents(
        self, folder: str = "", limit: int = 60, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Alle Dokumente, optional auf einen Ordner eingeschraenkt.

        Fuer die Kachelwand. Seitenweise, damit nicht 187 Vorschaubilder auf
        einmal geladen werden.
        """
        with self._conn() as conn:
            if folder:
                rows = conn.execute(
                    "SELECT * FROM documents WHERE folder = ? OR folder LIKE ?"
                    " ORDER BY modified_at DESC, name LIMIT ? OFFSET ?",
                    (folder, f"{folder}/%", limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM documents ORDER BY modified_at DESC, name LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
        return [dict(r) for r in rows]

    def count_documents(self, folder: str = "") -> int:
        """Wie viele Dokumente insgesamt, fuer die Blaetter-Anzeige."""
        with self._conn() as conn:
            if folder:
                row = conn.execute(
                    "SELECT COUNT(*) FROM documents WHERE folder = ? OR folder LIKE ?",
                    (folder, f"{folder}/%"),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
        return int(row[0])

    def document_by_id(self, doc_id: int) -> dict[str, Any] | None:
        """Ein Dokument nach interner ID, fuer den Vorschau-Endpunkt."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return dict(row) if row else None

    def upsert_document(self, doc: dict[str, Any]) -> int:
        """Ein einzelnes Dokument in den Index legen und seine ID liefern.

        Fuer hochgeladene Belege. Ohne das waere ein Beleg bis zum naechsten
        Crawl unsichtbar: keine Vorschau, kein Editor-Link, und die frische
        Verknuepfung stuende sofort auf "nicht mehr am alten Ort". Bei
        stuendlichem Sammeltakt haette Mia das eine Stunde lang so gesehen.

        ``INSERT ... ON CONFLICT`` wie im Crawl, damit ein zweiter Upload
        desselben Pfades die Zeile aktualisiert statt zu scheitern.
        """
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO documents"
                " (source, path, name, folder, ext, size_bytes, modified_at, file_id, seen_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(source, path) DO UPDATE SET"
                "   name=excluded.name, folder=excluded.folder, ext=excluded.ext,"
                "   size_bytes=excluded.size_bytes, modified_at=excluded.modified_at,"
                "   file_id=excluded.file_id, seen_at=excluded.seen_at",
                (
                    doc.get("source", "nextcloud"),
                    doc["path"],
                    doc["name"],
                    doc.get("folder", ""),
                    doc.get("ext", ""),
                    int(doc.get("size_bytes", 0)),
                    doc.get("modified_at", ""),
                    doc.get("file_id", ""),
                    _now(),
                ),
            )
            row = conn.execute(
                "SELECT id FROM documents WHERE source=? AND path=?",
                (doc.get("source", "nextcloud"), doc["path"]),
            ).fetchone()
        return int(row["id"])

    def set_document_text(self, source: str, path: str, text: str) -> bool:
        """Den gelesenen Text an ein Dokument schreiben. Nur im Belegordner.

        **Hier steht die Datenschutzgrenze, nicht beim Aufrufer.** Mias Zusage
        ist, dass Textinhalte ausschliesslich fuer Dokumente gespeichert
        werden, die sie selbst durch den Scanner geschickt hat. In ihren
        Ordnern liegen Ausweise, Geburtsurkunden und Unterlagen Dritter; von
        denen darf nie ein Wort in der Datenbank landen, auch nicht aus
        Versehen und auch nicht, wenn spaeter jemand eine bequeme
        Sammelfunktion darueber baut.

        Eine Regel, die nur in der Dokumentation steht, ist keine. Deshalb
        prueft die Methode selbst, ob der Pfad im Belegordner liegt, und gibt
        sonst ``False`` zurueck, statt zu schreiben.
        """
        ordner = (settings.belege_ordner or "").rstrip("/")
        if not ordner or not path.startswith(ordner + "/"):
            log.warning("OCR-Text fuer %s abgelehnt: liegt nicht im Belegordner", path)
            return False

        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE documents SET ocr_text=? WHERE source=? AND path=?",
                (text, source, path),
            )
        return cur.rowcount > 0

    def document_text(self, source: str, path: str) -> str:
        """Der gelesene Text, fuer die Trefferstelle in der Suche."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT ocr_text FROM documents WHERE source=? AND path=?", (source, path)
            ).fetchone()
        return str(row["ocr_text"]) if row else ""

    # --- Vektoren fuer den Ordnervorschlag ---------------------------------

    def documents_ohne_embed(self, limit: int = 200) -> list[dict[str, Any]]:
        """Dokumente, deren Vektor fehlt oder zu einem alten Namen gehoert.

        Der Vergleich mit ``embed_name`` faengt Umbenennungen: der Vektor
        haengt am Namen, und ein Dokument, das aus ``Scan_001.pdf`` zu
        ``Widerspruch Kasse.pdf`` geworden ist, muss neu gerechnet werden.

        Gerechnet wird nur unterhalb der Ablage-Wurzel (dem Elternordner des
        Belegordners, bei Mia ``/Dokumente``) und nicht im Belegordner selbst.
        Alles andere im Index waere gerechnete Zeit fuer Vektoren, die nie ein
        Ziel werden koennen.
        """
        ordner = (settings.belege_ordner or "").rstrip("/")
        wurzel = ordner.rsplit("/", 1)[0]
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, source, path, name, folder FROM documents"
                " WHERE (embed IS NULL OR embed_name <> name)"
                "   AND folder LIKE ? AND folder NOT LIKE ?"
                " ORDER BY id LIMIT ?",
                (f"{wurzel}/%" if wurzel else "/%", f"{ordner}%" if ordner else "\x00", limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def set_document_embed(self, doc_id: int, vektor: bytes, name: str) -> bool:
        """Den Vektor eines Dokuments ablegen."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE documents SET embed=?, embed_name=? WHERE id=?",
                (vektor, name, doc_id),
            )
        return cur.rowcount > 0

    def documents_mit_embed(self) -> list[dict[str, Any]]:
        """Alle Dokumente mit Vektor, fuer die Ordner-Schwerpunkte.

        Dieselbe Grenze wie oben: nur die Ablage, nicht der Belegordner.
        """
        ordner = (settings.belege_ordner or "").rstrip("/")
        wurzel = ordner.rsplit("/", 1)[0]
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, path, folder, embed FROM documents"
                " WHERE embed IS NOT NULL AND folder LIKE ? AND folder NOT LIKE ?",
                (f"{wurzel}/%" if wurzel else "/%", f"{ordner}%" if ordner else "\x00"),
            ).fetchall()
        return [dict(r) for r in rows]

    def move_document(self, source: str, alt: str, neu: str, ordner: str) -> None:
        """Index und Verknuepfungen einer verschobenen Datei nachziehen.

        Ohne das stuende der Beleg direkt nach dem Verschieben als "nicht mehr
        am alten Ort" am Eintrag: die Verknuepfung zeigt auf den Pfad, und der
        hat sich gerade geaendert. Bis zum naechsten Crawl waere das eine
        Stunde lang so.

        **Eine Leiche am Zielpfad wird vorher weggeraeumt.** Steht dort noch
        eine Indexzeile, scheitert das UPDATE an ``UNIQUE(source, path)``, und
        zwar erst nachdem Nextcloud die Datei schon verschoben hat: die Datei
        liegt am neuen Ort, der Index zeigt auf den alten, und Mia sieht ihren
        frisch einsortierten Beleg als verschwunden. Genau so ist es beim
        Durchspielen passiert.

        Die alte Zeile darf weg: Nextcloud hat mit ``Overwrite: F``
        verschoben, am Ziel lag also nichts. Eine Indexzeile dort beschreibt
        eine Datei, die es nicht mehr gibt.
        """
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM documents WHERE source=? AND path=? AND path<>?",
                (source, neu, alt),
            )
            conn.execute(
                "UPDATE documents SET path=?, folder=? WHERE source=? AND path=?",
                (neu, ordner, source, alt),
            )
            conn.execute(
                "UPDATE OR REPLACE entry_documents SET path=? WHERE source=? AND path=?",
                (neu, source, alt),
            )

    def rename_document(self, source: str, path: str, name: str) -> bool:
        """Den Namen einer Datei im Index und an den Verknuepfungen nachziehen.

        Kommt nach ``move_document``, das nur den Pfad kennt. Ohne das stuende
        am Eintrag weiter der alte Name: die Verknuepfung merkt sich einen, um
        eine verschwundene Datei noch benennen zu koennen.

        ``embed_name`` wird bewusst **nicht** mitgeschrieben. Der Vektor haengt
        am alten Namen, und genau dieser Unterschied ist es, an dem
        ``documents_ohne_embed`` die Umbenennung erkennt und neu rechnet.
        """
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE documents SET name=? WHERE source=? AND path=?",
                (name, source, path),
            )
            conn.execute(
                "UPDATE entry_documents SET name=? WHERE source=? AND path=?",
                (name, source, path),
            )
        return cur.rowcount > 0

    # --- Dokumente an Eintraegen -------------------------------------------

    def link_document(self, entry_id: int, source: str, path: str, name: str = "") -> bool:
        """Ein Dokument an einen Eintrag haengen.

        Zweimal dasselbe Dokument ist keine Fehlbedienung, sondern ein
        Doppelklick: ``INSERT OR IGNORE`` statt eines Fehlers. Der Rueckgabewert
        sagt, ob wirklich etwas dazugekommen ist.
        """
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO entry_documents (entry_id, source, path, name, created_at)"
                " VALUES (?,?,?,?,?)",
                (entry_id, source, path, name, _now()),
            )
        return cur.rowcount > 0

    def unlink_document(self, entry_id: int, source: str, path: str) -> bool:
        """Die Verknuepfung loesen. Die Datei selbst wird nie angefasst."""
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM entry_documents WHERE entry_id=? AND source=? AND path=?",
                (entry_id, source, path),
            )
        return cur.rowcount > 0

    def documents_for_entry(self, entry_id: int) -> list[dict[str, Any]]:
        """Die angehaengten Dokumente eines Eintrags.

        LEFT JOIN mit Absicht: liegt die Datei nicht mehr im Index, bleibt die
        Zeile trotzdem stehen, nur ohne ``id``. Ein stiller Verlust waere
        schlimmer als ein Hinweis, dass etwas verschwunden ist.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT v.source, v.path, v.name AS merkname, v.created_at, d.*"
                " FROM entry_documents v"
                " LEFT JOIN documents d ON d.source = v.source AND d.path = v.path"
                " WHERE v.entry_id = ? ORDER BY v.created_at, v.id",
                (entry_id,),
            ).fetchall()

        raus: list[dict[str, Any]] = []
        for r in rows:
            eintrag = dict(r)
            # Der Join liefert bei fehlender Datei ueberall NULL. Dann zaehlt
            # das, was beim Verknuepfen gemerkt wurde.
            eintrag["fehlt"] = eintrag.get("id") is None
            if eintrag["fehlt"]:
                eintrag["name"] = eintrag["merkname"]
                eintrag["folder"] = eintrag["path"].rstrip("/").rsplit("/", 1)[0] or "/"
                eintrag["ext"] = Path(eintrag["path"]).suffix.lower()
                eintrag["size_bytes"] = 0
                eintrag["modified_at"] = ""
                eintrag["file_id"] = ""
            eintrag.pop("merkname", None)
            raus.append(eintrag)
        return raus

    def entries_for_document(self, source: str, path: str) -> list[dict[str, Any]]:
        """An welchen Eintraegen diese Datei haengt."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT e.* FROM entry_documents v JOIN entries e ON e.id = v.entry_id"
                " WHERE v.source = ? AND v.path = ? ORDER BY e.datum, e.id",
                (source, path),
            ).fetchall()
        return [_entry(r) for r in rows]

    def entries_for_documents(
        self, dateien: list[tuple[str, str]]
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        """Zu mehreren Dateien auf einmal, welche Eintraege daran haengen.

        Fuer die Dokumentenwand: eine Abfrage statt sechzig, sonst kostet die
        Bueroklammer auf jeder Kachel eine eigene Runde zur Datenbank.
        """
        if not dateien:
            return {}
        platz = ",".join("(?,?)" for _ in dateien)
        werte = [w for paar in dateien for w in paar]
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT v.source, v.path, e.id, e.titel, e.datum FROM entry_documents v"
                f" JOIN entries e ON e.id = v.entry_id WHERE (v.source, v.path) IN ({platz})"
                " ORDER BY e.datum, e.id",
                werte,
            ).fetchall()

        raus: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for r in rows:
            raus.setdefault((r["source"], r["path"]), []).append(
                {"id": int(r["id"]), "titel": r["titel"], "datum": r["datum"]}
            )
        return raus

    def document_counts(self) -> dict[int, int]:
        """Wie viele Dokumente je Eintrag. Fuer die Bueroklammer in der Liste.

        Eine Abfrage fuer alle Eintraege: sonst holt eine Tabelle mit 80 Zeilen
        achtzigmal einzeln nach.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT entry_id, COUNT(*) AS n FROM entry_documents GROUP BY entry_id"
            ).fetchall()
        return {int(r["entry_id"]): int(r["n"]) for r in rows}

    # --- Termine ----------------------------------------------------------

    def replace_events(self, events: list[dict[str, Any]], von: str, bis: str) -> None:
        """Termine im Zeitfenster ersetzen.

        Nur das Fenster wird geleert, nicht die ganze Tabelle: sonst waeren
        bei einem abgebrochenen Lauf auch Termine ausserhalb weg.
        """
        now = _now()
        with self._conn() as conn:
            conn.execute("DELETE FROM events WHERE start_at >= ? AND start_at <= ?", (von, bis))
            conn.executemany(
                "INSERT OR REPLACE INTO events"
                " (uid, start_at, end_at, title, location, calendar, ganztags, seen_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                [
                    (
                        e["uid"],
                        e["start_at"],
                        e.get("end_at", ""),
                        e["title"],
                        e.get("location", ""),
                        e.get("calendar", ""),
                        1 if e.get("ganztags") else 0,
                        now,
                    )
                    for e in events
                ],
            )

    def events(self, von: str, bis: str, limit: int = 200) -> list[dict[str, Any]]:
        """Termine im Zeitraum, chronologisch."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE start_at >= ? AND start_at <= ?"
                " ORDER BY start_at LIMIT ?",
                (von, bis, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def event_calendars(self) -> list[str]:
        """Welche Kalender kommen vor. Fuer den Filter."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT calendar FROM events WHERE calendar != ''"
                " ORDER BY calendar COLLATE NOCASE"
            ).fetchall()
        return [r["calendar"] for r in rows]

    def search_events(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Termine nach Titel oder Ort suchen, die naechsten zuerst.

        Vergangene kommen hinten dran: wer "Zahnarzt" sucht, will den
        naechsten Termin, nicht den von vor sechs Wochen. Wiederholungen
        ("Berufsschule" jeden Tag) erscheinen nur einmal, mit dem naechsten
        Vorkommen: sonst waere die Liste eine Woche Berufsschule.
        """
        query = query.strip()
        if not query:
            return []
        like = f"%{query}%"
        jetzt = datetime.now().isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE title LIKE ? OR location LIKE ?"
                " ORDER BY CASE WHEN start_at >= ? THEN 0 ELSE 1 END,"
                " CASE WHEN start_at >= ? THEN start_at END ASC,"
                " start_at DESC LIMIT ?",
                (like, like, jetzt, jetzt, limit * 20),
            ).fetchall()
        gesehen: set[tuple[str, str]] = set()
        ergebnis: list[dict[str, Any]] = []
        for r in rows:
            schluessel = (str(r["title"]), str(r["calendar"]))
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            ergebnis.append(dict(r))
            if len(ergebnis) >= limit:
                break
        return ergebnis

    def search_pages(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Seiten nach Titel oder Inhalt."""
        query = query.strip()
        if not query:
            return []
        like = f"%{query}%"
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM pages WHERE titel LIKE ? OR inhalt LIKE ?"
                " ORDER BY CASE WHEN titel LIKE ? THEN 0 ELSE 1 END, titel LIMIT ?",
                (like, like, like, limit),
            ).fetchall()
        return [_page(r) for r in rows]

    # --- Einstellungen ----------------------------------------------------

    # --- Seiten: der Baum in der Seitenleiste -----------------------------

    def create_page(
        self,
        titel: str,
        parent_id: int | None = None,
        symbol: str = "document",
        hat_sammlung: bool = False,
        sammelt_alles: bool = False,
    ) -> int:
        jetzt = _now()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO pages (parent_id, titel, symbol, hat_sammlung,"
                " sammelt_alles, sortierung, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?,"
                " (SELECT COALESCE(MAX(sortierung), 0) + 1 FROM pages p2"
                "  WHERE p2.parent_id IS ?), ?, ?)",
                (
                    parent_id,
                    titel.strip(),
                    symbol,
                    int(hat_sammlung),
                    int(sammelt_alles),
                    parent_id,
                    jetzt,
                    jetzt,
                ),
            )
        return int(cur.lastrowid or 0)

    def get_page(self, page_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
        return _page(row) if row else None

    def list_pages(self) -> list[dict[str, Any]]:
        """Alle Seiten flach. Den Baum baut die Oberflaeche daraus."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM pages ORDER BY sortierung, titel").fetchall()
        return [_page(r) for r in rows]

    def update_page(self, page_id: int, **felder: Any) -> bool:
        erlaubt = {
            "titel",
            "symbol",
            "inhalt",
            "hat_sammlung",
            "sammelt_alles",
            "ansicht",
            "gruppe_nach",
            "parent_id",
            "sortierung",
        }
        teile: list[str] = []
        werte: list[Any] = []

        for name, wert in felder.items():
            if name not in erlaubt:
                continue
            teile.append(f"{name} = ?")
            werte.append(int(wert) if name in ("hat_sammlung", "sammelt_alles") else wert)

        if not teile:
            return False

        teile.append("updated_at = ?")
        werte.extend([_now(), page_id])
        with self._conn() as conn:
            cur = conn.execute(f"UPDATE pages SET {', '.join(teile)} WHERE id = ?", werte)
        return cur.rowcount > 0

    def delete_page(self, page_id: int) -> bool:
        """Seite loeschen. Unterseiten gehen mit, ihre Eintraege auch.

        Deshalb steht ON DELETE CASCADE am Fremdschluessel, und deshalb muss
        die Oberflaeche vorher fragen.
        """
        with self._conn() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            # Eintraege der Seite und aller Unterseiten mitnehmen.
            ids = self._page_und_kinder(conn, page_id)
            platz = ",".join("?" * len(ids))
            conn.execute(
                "DELETE FROM entry_documents WHERE entry_id IN"
                f" (SELECT id FROM entries WHERE page_id IN ({platz}))",
                ids,
            )
            conn.execute(f"DELETE FROM entries WHERE page_id IN ({platz})", ids)
            cur = conn.execute("DELETE FROM pages WHERE id = ?", (page_id,))
        return cur.rowcount > 0

    @staticmethod
    def _page_und_kinder(conn: sqlite3.Connection, page_id: int) -> list[int]:
        """Eine Seite samt allen Nachfahren."""
        alle = [page_id]
        offen = [page_id]
        while offen:
            aktuell = offen.pop()
            kinder = conn.execute("SELECT id FROM pages WHERE parent_id = ?", (aktuell,)).fetchall()
            for k in kinder:
                alle.append(int(k["id"]))
                offen.append(int(k["id"]))
        return alle

    # --- Eintraege: das Notion-Modell -------------------------------------

    def create_entry(
        self,
        titel: str,
        inhalt: str = "",
        eigenschaften: dict[str, Any] | None = None,
        datum: str = "",
        zeit: str = "",
        event_uid: str = "",
        page_id: int = 0,
    ) -> int:
        """Einen Eintrag anlegen. Wie eine neue Seite in Notion."""
        jetzt = _now()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO entries (titel, inhalt, eigenschaften, datum, zeit,"
                " event_uid, page_id, sortierung, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?,"
                " (SELECT COALESCE(MAX(sortierung), 0) + 1 FROM entries), ?, ?)",
                (
                    titel.strip(),
                    inhalt,
                    json.dumps(eigenschaften or {}, ensure_ascii=False),
                    datum,
                    zeit,
                    event_uid,
                    page_id,
                    jetzt,
                    jetzt,
                ),
            )
        return int(cur.lastrowid or 0)

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return _entry(row) if row else None

    def update_entry(self, entry_id: int, **felder: Any) -> bool:
        """Einzelne Felder aendern. Nicht genannte bleiben, wie sie sind."""
        erlaubt = {
            "titel",
            "inhalt",
            "datum",
            "zeit",
            "event_uid",
            "archiviert",
            "sortierung",
            "page_id",
        }
        teile: list[str] = []
        werte: list[Any] = []

        for name, wert in felder.items():
            if name == "eigenschaften":
                teile.append("eigenschaften = ?")
                werte.append(json.dumps(wert or {}, ensure_ascii=False))
            elif name in erlaubt and wert is not None:
                teile.append(f"{name} = ?")
                werte.append(int(wert) if name == "archiviert" else wert)

        if not teile:
            return False

        teile.append("updated_at = ?")
        werte.extend([_now(), entry_id])
        with self._conn() as conn:
            cur = conn.execute(f"UPDATE entries SET {', '.join(teile)} WHERE id = ?", werte)
        return cur.rowcount > 0

    def delete_entry(self, entry_id: int) -> bool:
        """Eintrag loeschen. Angehaengte Dokumente verlieren nur ihren Verweis.

        Es gibt keinen Fremdschluessel auf ``entries``, die Verknuepfungen
        muessen deshalb von Hand mit. Ohne das bleiben Waisen liegen, und die
        naechste Nummernvergabe haengt sie an einen fremden Eintrag.
        """
        with self._conn() as conn:
            conn.execute("DELETE FROM entry_documents WHERE entry_id = ?", (entry_id,))
            cur = conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        return cur.rowcount > 0

    def list_entries(
        self,
        von: str = "",
        bis: str = "",
        mit_archiv: bool = False,
        nur_mit_datum: bool = False,
        suche: str = "",
        page_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Eintraege holen. Die eine Abfrage hinter allen vier Ansichten."""
        wo: list[str] = []
        werte: list[Any] = []

        if not mit_archiv:
            wo.append("archiviert = 0")
        if page_id is not None:
            wo.append("page_id = ?")
            werte.append(page_id)
        if nur_mit_datum:
            wo.append("datum != ''")
        if von:
            wo.append("datum >= ?")
            werte.append(von)
        if bis:
            wo.append("datum <= ?")
            werte.append(bis)
        if suche:
            wo.append("(titel LIKE ? OR inhalt LIKE ?)")
            werte.extend([f"%{suche}%", f"%{suche}%"])

        bedingung = f"WHERE {' AND '.join(wo)}" if wo else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM entries {bedingung}"
                # Datierte zuerst, undatierte hinten: was keine Frist hat,
                # draengt nicht.
                " ORDER BY CASE WHEN datum = '' THEN 1 ELSE 0 END,"
                " datum, zeit, sortierung",
                werte,
            ).fetchall()
        return [_entry(r) for r in rows]

    def entries_for_event(self, uid: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM entries WHERE event_uid = ? AND archiviert = 0 ORDER BY sortierung",
                (uid,),
            ).fetchall()
        return [_entry(r) for r in rows]

    # --- Eigenschaften: die Spalten der Sammlung --------------------------

    def list_props(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM entry_props ORDER BY sortierung, name").fetchall()
        return [
            {
                "key": r["key"],
                "name": r["name"],
                "art": r["art"],
                "optionen": json.loads(r["optionen"]),
                "sortierung": r["sortierung"],
            }
            for r in rows
        ]

    def set_prop(
        self,
        key: str,
        name: str,
        art: str,
        optionen: list[dict[str, str]] | None = None,
        sortierung: int = 0,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO entry_props (key, name, art, optionen, sortierung)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET name = excluded.name,"
                " art = excluded.art, optionen = excluded.optionen,"
                " sortierung = excluded.sortierung",
                (key, name, art, json.dumps(optionen or [], ensure_ascii=False), sortierung),
            )

    def delete_prop(self, key: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM entry_props WHERE key = ?", (key,))
        return cur.rowcount > 0

    # --- Notizen an Terminen ---------------------------------------------

    def get_note(self, uid: str) -> str:
        """Was Mia zu diesem Termin geschrieben hat. Leer, wenn nichts."""
        with self._conn() as conn:
            row = conn.execute("SELECT notiz FROM event_notes WHERE uid = ?", (uid,)).fetchone()
        return str(row["notiz"]) if row else ""

    def set_note(self, uid: str, notiz: str) -> None:
        """Notiz sichern. Leerer Text loescht sie, statt eine leere Zeile zu lassen."""
        with self._conn() as conn:
            if notiz.strip():
                conn.execute(
                    "INSERT INTO event_notes (uid, notiz, updated_at) VALUES (?, ?, ?)"
                    " ON CONFLICT(uid) DO UPDATE SET notiz = excluded.notiz,"
                    " updated_at = excluded.updated_at",
                    (uid, notiz, _now()),
                )
            else:
                conn.execute("DELETE FROM event_notes WHERE uid = ?", (uid,))

    def notes_for(self, uids: list[str]) -> dict[str, str]:
        """Notizen fuer mehrere Termine auf einmal.

        Damit das Kalenderblatt in EINER Abfrage weiss, wo etwas dranhaengt,
        statt pro Termin einmal nachzufragen.
        """
        if not uids:
            return {}
        platzhalter = ",".join("?" * len(uids))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT uid, notiz FROM event_notes WHERE uid IN ({platzhalter})",
                uids,
            ).fetchall()
        return {str(r["uid"]): str(r["notiz"]) for r in rows}

    # --- Aufgaben ---------------------------------------------------------

    def add_task(self, titel: str, event_uid: str = "", faellig_am: str = "") -> int:
        """Eine neue Aufgabe. Gibt ihre Nummer zurueck."""
        jetzt = _now()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO tasks (titel, event_uid, faellig_am, sortierung,"
                " created_at, updated_at)"
                " VALUES (?, ?, ?, (SELECT COALESCE(MAX(sortierung), 0) + 1 FROM tasks),"
                " ?, ?)",
                (titel.strip(), event_uid, faellig_am, jetzt, jetzt),
            )
        return int(cur.lastrowid or 0)

    def update_task(
        self,
        task_id: int,
        titel: str | None = None,
        erledigt: bool | None = None,
        faellig_am: str | None = None,
    ) -> bool:
        """Aufgabe aendern. False, wenn es sie nicht gibt."""
        felder: list[str] = []
        werte: list[Any] = []
        if titel is not None:
            felder.append("titel = ?")
            werte.append(titel.strip())
        if erledigt is not None:
            felder.append("erledigt = ?")
            werte.append(1 if erledigt else 0)
        if faellig_am is not None:
            felder.append("faellig_am = ?")
            werte.append(faellig_am)
        if not felder:
            return False

        felder.append("updated_at = ?")
        werte.extend([_now(), task_id])
        with self._conn() as conn:
            cur = conn.execute(f"UPDATE tasks SET {', '.join(felder)} WHERE id = ?", werte)
        return cur.rowcount > 0

    def delete_task(self, task_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return cur.rowcount > 0

    def tasks_for_event(self, uid: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE event_uid = ? ORDER BY erledigt, sortierung",
                (uid,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_tasks(
        self, nur_offen: bool = False, ohne_termin: bool = False
    ) -> list[dict[str, Any]]:
        """Alle Aufgaben. Erledigte nach unten, faellige zuerst."""
        bedingungen = []
        if nur_offen:
            bedingungen.append("erledigt = 0")
        if ohne_termin:
            bedingungen.append("event_uid = ''")
        wo = f"WHERE {' AND '.join(bedingungen)}" if bedingungen else ""

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM tasks {wo}"
                " ORDER BY erledigt,"
                # Ohne Datum ans Ende: eine Aufgabe ohne Frist draengt nicht.
                " CASE WHEN faellig_am = '' THEN 1 ELSE 0 END, faellig_am, sortierung"
            ).fetchall()
        return [dict(r) for r in rows]

    def tasks_by_day(self, von: str, bis: str) -> dict[str, int]:
        """Wie viele OFFENE Aufgaben je Tag faellig sind.

        Fuer das Kalenderblatt: ein Tag mit offener Aufgabe soll das zeigen,
        auch wenn gar kein Termin darauf liegt.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT faellig_am, COUNT(*) AS anzahl FROM tasks"
                " WHERE erledigt = 0 AND faellig_am >= ? AND faellig_am <= ?"
                " AND faellig_am != '' GROUP BY faellig_am",
                (von, bis),
            ).fetchall()
        return {str(r["faellig_am"]): int(r["anzahl"]) for r in rows}

    # --- Berichtsheft -----------------------------------------------------

    def berichtswoche(self, montag: str) -> dict[str, Any] | None:
        """Mias Korrekturen zu einer Woche, falls sie welche gemacht hat."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM berichtswochen WHERE montag = ?", (montag,)
            ).fetchone()
        return _berichtswoche(row) if row else None

    def berichtswochen(self, von: str = "", bis: str = "") -> list[dict[str, Any]]:
        """Alle gespeicherten Wochen, neueste zuerst."""
        sql = "SELECT * FROM berichtswochen"
        args: list[Any] = []
        if von:
            sql += " WHERE montag >= ?"
            args.append(von)
            if bis:
                sql += " AND montag <= ?"
                args.append(bis)
        elif bis:
            sql += " WHERE montag <= ?"
            args.append(bis)
        sql += " ORDER BY montag DESC"
        with self._conn() as conn:
            return [_berichtswoche(r) for r in conn.execute(sql, args)]

    def save_berichtswoche(
        self,
        montag: str,
        *,
        inhalt: dict[str, Any] | None = None,
        status: str | None = None,
        themen_schule: str | None = None,
        bemerkung: str | None = None,
    ) -> dict[str, Any]:
        """Korrekturen speichern. Nur uebergebene Felder werden angefasst.

        Teilweises Speichern ist wichtig: das Frontend schickt beim Tippen in
        einem Tagesfeld nicht die ganze Woche mit, sonst ueberschreibt der
        letzte Tastendruck die Bemerkung mit einem leeren Text.
        """
        now = _now()
        vorher = self.berichtswoche(montag)
        neu_inhalt = dict(vorher["inhalt"]) if vorher else {}
        if inhalt is not None:
            for tag, werte in inhalt.items():
                if werte is None:
                    neu_inhalt.pop(tag, None)
                else:
                    neu_inhalt[tag] = werte
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO berichtswochen"
                " (montag, status, inhalt, themen_schule, bemerkung, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?)"
                " ON CONFLICT(montag) DO UPDATE SET"
                " status=excluded.status, inhalt=excluded.inhalt,"
                " themen_schule=excluded.themen_schule, bemerkung=excluded.bemerkung,"
                " updated_at=excluded.updated_at",
                (
                    montag,
                    status if status is not None else (vorher["status"] if vorher else "entwurf"),
                    json.dumps(neu_inhalt, ensure_ascii=False),
                    themen_schule
                    if themen_schule is not None
                    else (vorher["themen_schule"] if vorher else ""),
                    bemerkung if bemerkung is not None else (vorher["bemerkung"] if vorher else ""),
                    vorher["created_at"] if vorher else now,
                    now,
                ),
            )
        gespeichert = self.berichtswoche(montag)
        assert gespeichert is not None
        return gespeichert

    def get_settings(self) -> dict[str, str]:
        """Alle gespeicherten Vorlieben."""
        with self._conn() as conn:
            return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}

    def set_setting(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
                " updated_at=excluded.updated_at",
                (key, value, _now()),
            )

    # --- Gekoppelte Geraete -----------------------------------------------

    def geraetezugang_anlegen(self, abdruck: str, name: str, plattform: str) -> int:
        """Ein gekoppeltes Geraet eintragen. Gibt die neue ID zurueck."""
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO geraetezugang (abdruck, name, plattform, erstellt_at, zuletzt_at)"
                " VALUES (?,?,?,?,?)",
                (abdruck, name[:64], plattform[:32], now, now),
            )
            return int(cur.lastrowid or 0)

    def geraetezugang_pruefen(self, abdruck: str, adresse: str = "") -> dict[str, Any] | None:
        """Einen Schluessel-Abdruck nachschlagen und den Besuch vermerken.

        Der Vermerk laeuft im selben Aufruf, weil sonst jede Anfrage zwei
        Runden zur Datenbank braeuchte. ``zuletzt_at`` ist das, was eine
        verlorene App verraet: ein Geraet, das seit Wochen schweigt, gehoert
        aus der Liste.
        """
        with self._conn() as conn:
            reihe = conn.execute(
                "SELECT * FROM geraetezugang WHERE abdruck = ?", (abdruck,)
            ).fetchone()
            if reihe is None:
                return None
            conn.execute(
                "UPDATE geraetezugang SET zuletzt_at = ?, adresse = ? WHERE id = ?",
                (_now(), adresse[:45], reihe["id"]),
            )
            return dict(reihe)

    def geraetezugaenge(self) -> list[dict[str, Any]]:
        """Alle gekoppelten Geraete, das zuletzt gesehene zuerst.

        Ohne den Abdruck: die Liste geht an die Oberflaeche, und dort hat ein
        Abdruck nichts zu suchen. Er ist zwar kein Schluessel, aber er ist
        auch keine Information, die jemand zum Aufraeumen braucht.
        """
        with self._conn() as conn:
            reihen = conn.execute(
                "SELECT id, name, plattform, erstellt_at, zuletzt_at, adresse"
                " FROM geraetezugang ORDER BY zuletzt_at DESC"
            ).fetchall()
        return [dict(r) for r in reihen]

    def geraetezugang_loeschen(self, zugang_id: int) -> bool:
        """Ein Geraet abmelden. ``True``, wenn es eines gab."""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM geraetezugang WHERE id = ?", (zugang_id,))
            return cur.rowcount > 0

    # --- Dienste (Uptime Kuma) --------------------------------------------

    def replace_services(self, dienste: list[dict[str, Any]]) -> None:
        """Den Dienstzustand ersetzen.

        UPSERT auf dem Namen statt Loeschen und Neuanlegen, damit die IDs
        stabil bleiben. Dieselbe Lehre wie beim Dokumenten-Index.
        """
        now = _now()
        with self._conn() as conn:
            namen = {d["name"] for d in dienste}
            conn.executemany(
                "INSERT INTO services"
                " (name, status, msg, ping, uptime24, uptime30, seit, seen_at)"
                " VALUES (?,?,?,?,?,?,?,?)"
                " ON CONFLICT(name) DO UPDATE SET"
                "   status=excluded.status, msg=excluded.msg, ping=excluded.ping,"
                "   uptime24=excluded.uptime24, uptime30=excluded.uptime30,"
                "   seit=excluded.seit, seen_at=excluded.seen_at",
                [
                    (
                        d["name"],
                        int(d.get("status", 2)),
                        str(d.get("msg", ""))[:200],
                        int(d.get("ping") or 0),
                        float(d.get("uptime24", -1)),
                        float(d.get("uptime30", -1)),
                        d.get("seit", ""),
                        now,
                    )
                    for d in dienste
                ],
            )
            alt = {r["name"] for r in conn.execute("SELECT name FROM services")} - namen
            if alt:
                conn.executemany("DELETE FROM services WHERE name=?", [(n,) for n in alt])

    def services(self) -> list[dict[str, Any]]:
        """Alle Dienste, Stoerungen zuerst.

        Was nicht laeuft, gehoert nach oben: danach sucht man, wenn man die
        Seite aufmacht.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM services"
                " ORDER BY CASE status WHEN 0 THEN 0 WHEN 2 THEN 1 WHEN 3 THEN 2 ELSE 3 END,"
                " name COLLATE NOCASE"
            ).fetchall()
        return [dict(r) for r in rows]

    def document_stats(self) -> dict[str, Any]:
        """Kennzahlen fuer die Uebersichtskachel."""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            by_source = conn.execute(
                "SELECT source, COUNT(*) AS n FROM documents GROUP BY source ORDER BY n DESC"
            ).fetchall()
            by_ext = conn.execute(
                "SELECT ext, COUNT(*) AS n FROM documents WHERE ext <> ''"
                " GROUP BY ext ORDER BY n DESC LIMIT 8"
            ).fetchall()
            newest = conn.execute(
                "SELECT name, modified_at FROM documents"
                " WHERE modified_at <> '' ORDER BY modified_at DESC LIMIT 1"
            ).fetchone()
        return {
            "gesamt": total,
            "quellen": [dict(r) for r in by_source],
            "typen": [dict(r) for r in by_ext],
            "neuestes": dict(newest) if newest else None,
        }

    def document_folders(self, limit: int = 12) -> list[dict[str, Any]]:
        """Sachordner mit Anzahl, als Einstieg ohne Suche.

        Zeigt Struktur statt Inhalt: "02 Medizinisch, 14 Dokumente" verraet
        nichts ueber einzelne Befunde, hilft aber beim Einsteigen.

        Gruppiert wird auf der Ebene, die inhaltlich etwas aussagt. Mias
        Ablage haengt komplett unter ``/Dokumente``, die oberste Ebene waere
        also eine einzige Zeile mit 159 Treffern und damit nutzlos. Deshalb
        wird ein reiner Sammelordner uebersprungen und dessen Kinder gezeigt.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT folder, COUNT(*) AS n FROM documents"
                " WHERE folder <> '' AND folder <> '/' GROUP BY folder"
            ).fetchall()

        gesamt = sum(r["n"] for r in rows)
        if not gesamt:
            return []

        def gruppiere(tiefe: int) -> dict[str, int]:
            out: dict[str, int] = {}
            for r in rows:
                teile = [t for t in r["folder"].split("/") if t]
                if not teile:
                    continue
                key = "/".join(teile[:tiefe])
                out[key] = out.get(key, 0) + r["n"]
            return out

        # Solange eine einzelne Gruppe den Grossteil schluckt, ist die Ebene als
        # Einstieg wertlos ("Dokumente 159" sagt nichts). Dann wird der
        # Sammelordner aufgeklappt und seine Kinder werden gezeigt.
        gruppen = gruppiere(1)
        for tiefe in (2, 3):
            groesste = max(gruppen.values())
            if groesste <= gesamt * 0.6:
                break
            tiefer = gruppiere(tiefe)
            if len(tiefer) <= len(gruppen):
                break
            gruppen = tiefer

        sortiert = sorted(gruppen.items(), key=lambda kv: (-kv[1], kv[0]))
        return [{"top": f"/{k}", "n": n} for k, n in sortiert[:limit]]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _entry(row: Any) -> dict[str, Any]:
    """Eine Zeile in einen Eintrag verwandeln.

    Die Eigenschaften liegen als JSON in der Spalte. Ist dort Unsinn
    gelandet, wird der Eintrag trotzdem angezeigt, nur eben ohne
    Eigenschaften: eine kaputte Zeile darf nicht die ganze Ansicht killen.
    """
    d = dict(row)
    try:
        d["eigenschaften"] = json.loads(d.get("eigenschaften") or "{}")
    except (json.JSONDecodeError, TypeError):
        d["eigenschaften"] = {}
    d["archiviert"] = bool(d.get("archiviert"))
    return d


def _page(row: Any) -> dict[str, Any]:
    """Eine Zeile in eine Seite verwandeln."""
    d = dict(row)
    d["hat_sammlung"] = bool(d.get("hat_sammlung"))
    d["sammelt_alles"] = bool(d.get("sammelt_alles"))
    return d


def _berichtswoche(row: Any) -> dict[str, Any]:
    """Eine Zeile des Berichtshefts verwandeln.

    Kaputtes JSON in ``inhalt`` gibt eine leere Woche statt eines Fehlers:
    lieber ein leeres Blatt neu ausfuellen als eine Seite, die nicht laedt.
    """
    d = dict(row)
    try:
        d["inhalt"] = json.loads(d.get("inhalt") or "{}")
    except (json.JSONDecodeError, TypeError):
        d["inhalt"] = {}
    if not isinstance(d["inhalt"], dict):
        d["inhalt"] = {}
    return d
