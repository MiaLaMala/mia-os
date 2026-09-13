"""Version, Änderungsverlauf und die About-Seite.

Der Anlass für diese Tests: die Version stand an drei Stellen im Code und sie
widersprachen sich bereits (``pyproject.toml`` 0.2.0, ``src/__init__.py``
0.1.0, ``main.py`` nochmal 0.2.0). Eine Zahl, die von Hand gepflegt werden
muss, ist eine Zahl, die irgendwann lügt.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src import ueber
from src.store import Store

WURZEL = Path(__file__).resolve().parents[1]


def _flacher_klon() -> bool:
    """Hat dieses Arbeitsverzeichnis nur einen Commit?

    Die CI klont flach, dort ist die Historie ein einziger Commit. Tests,
    die über den Verlauf laufen, haben dann nichts zu prüfen und sagen
    nichts aus. Sie zu überspringen ist ehrlicher, als sie an einer leeren
    Liste scheitern zu lassen.
    """
    ergebnis = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=WURZEL,
        capture_output=True,
        text=True,
    )
    return ergebnis.returncode != 0 or int(ergebnis.stdout.strip() or 0) < 5


@pytest.fixture(autouse=True)
def _kein_zwischenspeicher() -> None:
    """``_daten`` merkt sich das Ergebnis. Zwischen Tests muss das weg."""
    ueber._daten.cache_clear()


# --- version.json lesen ---------------------------------------------------


def test_fehlende_datei_ist_kein_fehler(monkeypatch: pytest.MonkeyPatch) -> None:
    """Eine About-Seite, die wegen einer fehlenden Zahl wirft, wäre die
    schlechteste aller Antworten auf eine fehlende Zahl."""
    monkeypatch.setattr(ueber, "VERSION_DATEI", Path("/gibt/es/nicht.json"))
    assert ueber.version() == "unbekannt"
    assert ueber._daten()["changelog"] == []


def test_kaputte_datei_ist_kein_fehler(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    kaputt = tmp_path / "version.json"
    kaputt.write_text("{ das ist kein json", encoding="utf-8")
    monkeypatch.setattr(ueber, "VERSION_DATEI", kaputt)
    assert ueber.version() == "unbekannt"


def test_halbe_datei_wird_ergaenzt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Eine ältere Fassung ohne alle Felder darf keinen KeyError auslösen."""
    halb = tmp_path / "version.json"
    halb.write_text(json.dumps({"version": "1.2.3"}), encoding="utf-8")
    monkeypatch.setattr(ueber, "VERSION_DATEI", halb)

    daten = ueber._daten()
    assert daten["version"] == "1.2.3"
    assert daten["changelog"] == []
    assert daten["commits"] == 0


@pytest.mark.skipif(_flacher_klon(), reason="flacher Klon, Commit-Zahl waere falsch")
def test_version_im_repo_ist_gebaut() -> None:
    """Die mitgelieferte Datei muss zur Bildungsregel passen.

    Fällt auf, wenn jemand sie von Hand bearbeitet oder das Bauskript
    kaputtgeht.
    """
    daten = ueber._daten()
    teile = daten["version"].split(".")
    assert len(teile) == 3, f"Version sieht falsch aus: {daten['version']}"
    assert all(t.isdigit() for t in teile)
    # Der dritte Teil ist die Anzahl der Commits.
    assert int(teile[2]) == daten["commits"]


def test_alle_drei_stellen_sagen_dasselbe() -> None:
    """Genau der Widerspruch, der diese Arbeit ausgelöst hat."""
    import src
    import src.main

    assert src.__version__ == ueber.version()
    assert src.main.app.version == ueber.version()


# --- Laufzeit -------------------------------------------------------------


@pytest.mark.parametrize(
    ("vor_sekunden", "erwartet"),
    [
        (10, "gerade neu gestartet"),
        (60 * 5, "seit 5 Minuten"),
        (60 * 60 * 3, "seit 3 Stunden"),
        (60 * 60 * 24, "seit einem Tag"),
        (60 * 60 * 24 * 9, "seit 9 Tagen"),
    ],
)
def test_laufzeit_in_worten(vor_sekunden: int, erwartet: str) -> None:
    """Sekundengenau wäre Angeberei: interessant ist Minuten oder Wochen."""
    start = datetime.now(UTC) - timedelta(seconds=vor_sekunden)
    assert ueber._laufzeit(start) == erwartet


def test_laufzeit_ohne_start() -> None:
    assert ueber._laufzeit(None) == ""


# --- Überblick ------------------------------------------------------------


def test_ueberblick_zaehlt_den_echten_bestand(store: Store) -> None:
    """Zahlen aus der Datenbank, nicht aus einer gepflegten Liste."""
    seite = store.create_page("Behörden", hat_sammlung=True)
    store.create_entry("Erster", page_id=seite)
    zweiter = store.create_entry("Zweiter", page_id=seite)
    store.update_entry(zweiter, archiviert=True)
    store.replace_documents("nextcloud", [_doc("/a.pdf"), _doc("/b.pdf")])

    daten = ueber.ueberblick(store, [], None)
    zahlen = {z["titel"]: z["wert"] for z in daten["zahlen"]}

    # Archivierte zählen mit: sie sind Bestand, nur nicht sichtbar.
    assert zahlen["Einträge"] == 2
    assert zahlen["Dokumente"] == 2
    assert zahlen["Seiten"] >= 1


def test_ueberblick_nennt_keine_namen(store: Store) -> None:
    """Auf einer Seite über die Anwendung haben Dokumenttitel nichts verloren.

    Dieselbe Regel wie auf der Startseite: dort standen einmal medizinische
    Unterlagen Dritter, weil eine Liste ungefiltert durchlief. Deshalb sind
    die Beispiele hier bewusst heikel gewählt, ein Titel darf nirgends
    durchrutschen.
    """
    store.create_entry("Befund Kardiologie")
    store.replace_documents("nextcloud", [_doc("/Attest Facharzt.pdf")])

    text = json.dumps(ueber.ueberblick(store, [], None), ensure_ascii=False)
    assert "Kardiologie" not in text
    assert "Facharzt" not in text
    assert "Attest" not in text


def _doc(path: str) -> dict[str, Any]:
    return {
        "path": path,
        "name": path.rsplit("/", 1)[-1],
        "folder": path.rsplit("/", 1)[0] or "/",
        "ext": "." + path.rsplit(".", 1)[-1],
        "size_bytes": 100,
        "modified_at": "2026-09-01T10:00:00+00:00",
        "file_id": "1",
    }


# --- Das Bauskript --------------------------------------------------------


@pytest.mark.skipif(_flacher_klon(), reason="flacher Klon, keine Historie zum Pruefen")
def test_bauskript_laeuft_und_erzeugt_dieselbe_version() -> None:
    """Der Erzeuger und die mitgelieferte Datei dürfen nicht auseinanderlaufen."""
    ergebnis = subprocess.run(
        [sys.executable, str(WURZEL / "scripts" / "version_bauen.py")],
        cwd=WURZEL,
        capture_output=True,
        text=True,
    )
    assert ergebnis.returncode == 0, ergebnis.stderr

    neu = json.loads((WURZEL / "src" / "version.json").read_text(encoding="utf-8"))
    assert neu["version"].count(".") == 2
    assert neu["commits"] > 0
    assert neu["changelog"], "Änderungsverlauf ist leer"


def test_changelog_filtert_uebergabenotizen() -> None:
    """HANDOFF- und chore-Commits sind für mich wichtig, nicht für Mia."""
    import importlib.util

    pfad = WURZEL / "scripts" / "version_bauen.py"
    spec = importlib.util.spec_from_file_location("version_bauen", pfad)
    assert spec and spec.loader
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)

    for still in ("HANDOFF: irgendwas", "chore: Formatierung", "test: mehr Tests"):
        assert modul.STILL.match(still), f"{still!r} sollte gefiltert werden"
    for laut in ("Scanner: aus einem Foto einen Scan", "Belege einfangen"):
        assert not modul.STILL.match(laut), f"{laut!r} sollte drinbleiben"


# --- API ------------------------------------------------------------------


def test_api_ueber(client: TestClient) -> None:
    antwort = client.get("/api/ueber")
    assert antwort.status_code == 200

    daten = antwort.json()
    assert daten["version"] == ueber.version()
    assert {z["titel"] for z in daten["zahlen"]} == {
        "Einträge",
        "Seiten",
        "Dokumente",
        "Änderungen",
    }
    assert isinstance(daten["changelog"], list)
    assert isinstance(daten["quellen"], list)


def test_api_ueber_meldet_kaputte_quellen(client: TestClient) -> None:
    """Eine Quelle, die nicht liefert, gehört sichtbar gemacht."""
    from src.main import get_store

    get_store().record_run(
        "dokumente", ok=False, error="Nextcloud nicht erreichbar", duration_ms=12
    )

    quellen = {q["name"]: q for q in client.get("/api/ueber").json()["quellen"]}
    assert quellen["dokumente"]["ok"] is False
    assert "Nextcloud" in quellen["dokumente"]["fehler"]


# --- Umlaute in Commit-Nachrichten ---------------------------------------


def _vb() -> Any:
    """Das Bauskript als Modul laden. Es liegt nicht im Paket."""
    import importlib.util

    pfad = WURZEL / "scripts" / "version_bauen.py"
    spec = importlib.util.spec_from_file_location("version_bauen", pfad)
    assert spec and spec.loader
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.mark.parametrize(
    ("roh", "erwartet"),
    [
        # Umgeschriebene Umlaute zurueckholen
        ("anhaengen", "anhängen"),
        ("Aenderungsverlauf", "Änderungsverlauf"),
        ("Schaltflaechen", "Schaltflächen"),
        ("ueberlebt", "überlebt"),
        ("Stoerung", "Störung"),
        ("Groesse", "Größe"),
        ("groesser", "größer"),
        # Und die Faelle, in denen ae/oe/ue KEIN Umlaut ist. Genau hier ist
        # mein erster Wurf gescheitert: aus "Quelle" wurde "Qülle".
        ("Quelle", "Quelle"),
        ("Queue", "Queue"),
        ("quer", "quer"),
        ("Dauer", "Dauer"),
        ("zuerst", "zuerst"),
        ("neue", "neue"),
        ("visueller", "visueller"),
        ("Steuer", "Steuer"),
        ("aktuell", "aktuell"),
        ("Israel", "Israel"),
        # "ue" nach einem Vokal ist nie ein Umlaut. Die Wortliste hatte hier
        # 14 Luecken, gefunden durch einen Lauf ueber alle 3623 Woerter aus
        # beiden Repo-Verlaeufen. "Bauen" wurde dort zu "Baün".
        ("Bauen", "Bauen"),
        ("bauen", "bauen"),
        ("Einbauen", "Einbauen"),
        ("zusammenbauen", "zusammenbauen"),
        ("dauerhaft", "dauerhaft"),
        ("neueste", "neueste"),
        ("blauer", "blauer"),
        ("grauen", "grauen"),
        ("feuert", "feuert"),
        # Und die Gegenprobe: nach einem KONSONANTEN wird weiter ersetzt.
        ("pruefen", "prüfen"),
        ("Gruenwald", "Grünwald"),
        ("Buendel", "Bündel"),
    ],
)
def test_umlaute_zurueckholen(roh: str, erwartet: str) -> None:
    assert _vb()._wort_lesbar(roh) == erwartet


@pytest.mark.skipif(_flacher_klon(), reason="flacher Klon, keine Historie zum Pruefen")
def test_ganzer_verlauf_ohne_falsche_ersetzung() -> None:
    """Der echte Verlauf ist der ehrlichste Test.

    Eine Wortliste von Hand hatte nach 107 Commits schon 25 Lücken. Jetzt
    greifen Regeln, und dieser Test läuft über alles, was je committet
    wurde: findet er ein "Qülle", "Grösse" oder "Baün", ist eine Regel kaputt.

    **Das Muster prüfte zuerst nur ``öss`` und ``Qü``**, und genau deshalb
    lief der Test grün, während im erzeugten Changelog "Baün" stand. Ein
    Umlaut direkt hinter einem Vokal kommt im Deutschen nicht vor, das ist
    das verlässlichere Merkmal für eine falsche Ersetzung.
    """
    import re

    modul = _vb()
    roh = modul._git("log", "--no-merges", "--format=%s%x1f%b%x1e")

    falsch = re.compile(r"öss|[Qq][üäö]|[aeiouAEIOU][üÜ]")
    schlecht = set()
    for block in roh.split("\x1e"):
        for text in block.strip().split("\x1f"):
            for wort in re.findall(r"\b[A-Za-z]+\b", text):
                neu = modul._wort_lesbar(wort)
                if neu != wort and falsch.search(neu):
                    schlecht.add((wort, neu))

    assert not schlecht, f"Falsch ersetzt: {schlecht}"


@pytest.mark.skipif(_flacher_klon(), reason="flacher Klon, keine Historie zum Pruefen")
def test_release_notizen_sind_lesbar() -> None:
    """Was in einem GitHub-Release steht, liest ein Mensch.

    Bewusst gegen den *ganzen* Verlauf statt gegen ``HEAD~3``: die CI holt
    per Vorgabe nur den letzten Commit, dort gibt es kein ``HEAD~3`` und der
    Test brach mit exit 128 ab. Lokal lief er durch, weil dort die ganze
    Historie liegt. Genau der Fehler, den ein Test nicht haben darf: rot nur
    da, wo man nicht hinsieht.
    """
    modul = _vb()
    text = modul.notizen()
    assert "###" in text

    # Der Text muss bereits durch ``lesbar`` gelaufen sein. Geprüft wird das
    # als Unveränderlichkeit: ein zweiter Lauf darf nichts mehr finden.
    #
    # Vorher stand hier eine nachgebaute Bedingung ("alles außer qu-Wörtern"),
    # und die musste bei jeder neuen Regel mitgepflegt werden. Sie tat es
    # nicht: als die Vokalregel dazukam, prüfte dieser Test noch die alte
    # Welt. Eine Kopie der Regel weicht irgendwann ab und prüft dann das
    # Falsche.
    assert modul.lesbar(text) == text, "Die Notizen sind nicht durch lesbar() gelaufen"

    # Und die Gegenprobe, dass ``lesbar`` überhaupt etwas tut: im Verlauf
    # stehen umgeschriebene Umlaute, sonst wäre der Test oben wertlos.
    assert modul.lesbar("Foto anhaengen") == "Foto anhängen"


def test_release_notizen_ohne_historie() -> None:
    """Ein flacher Klon darf die Notizen nicht sprengen.

    Die CI klont flach. Ein unbekannter Tag als Startpunkt ist damit der
    Normalfall, nicht die Ausnahme.
    """
    text = _vb().notizen("v999.999.999")
    assert isinstance(text, str)
    assert text.strip()
