"""Die Auslieferung der gebauten Apps.

Ohne echtes Git: geprueft wird, was Mia OS mit dem tut, was im Zweig liegt,
nicht ob GitHub antwortet. Der Klon selbst ist eine Zeile ``git clone``, die
Logik daneben ist das, was schiefgehen kann.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.apps as apps_modul


@pytest.fixture
def zweig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Ein Verzeichnis, das aussieht wie der frisch geklonte Zweig."""
    ablage = tmp_path / "apps"
    monkeypatch.setattr(apps_modul, "ABLAGE", ablage)
    # Den Modulzustand zuruecksetzen: er lebt sonst ueber Tests hinweg.
    monkeypatch.setattr(apps_modul, "_apps", None)
    return ablage


def _zweig_fuellen(ziel: Path, *, mac: bytes = b"MAC-APP", ios: bytes = b"IOS-APP") -> dict:
    """Einen Zweig anlegen, wie die CI ihn schreibt."""
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / "MiaOS-Mac.zip").write_bytes(mac)
    (ziel / "MiaOS-iOS.ipa").write_bytes(ios)
    beschreibung = {
        "version": "0.1.42",
        "commit": "abc1234",
        "gebaut_am": "2026-09-13T15:00:00Z",
        "mac": {
            "datei": "MiaOS-Mac.zip",
            "groesse": len(mac),
            "sha256": hashlib.sha256(mac).hexdigest(),
        },
        "ios": {
            "datei": "MiaOS-iOS.ipa",
            "groesse": len(ios),
            "sha256": hashlib.sha256(ios).hexdigest(),
        },
    }
    (ziel / "apps.json").write_text(json.dumps(beschreibung), encoding="utf-8")
    return beschreibung


def test_stand_meldet_was_bereitsteht(zweig: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = apps_modul.Apps()
    # Den Klon ersetzen: er soll den Zweig anlegen, statt zu GitHub zu gehen.
    monkeypatch.setattr(a, "_holen", lambda: _fake_holen(a, zweig))

    stand = a.stand()
    assert stand["version"] == "0.1.42"
    assert stand["mac"]["groesse"] == len(b"MAC-APP")
    assert a.datei("mac") is not None
    assert a.datei("ios") is not None


def _fake_holen(a: apps_modul.Apps, ablage: Path) -> None:
    """Was ``_holen`` tut, ohne git: Dateien hinlegen und den Stand setzen."""
    from datetime import UTC, datetime

    beschreibung = _zweig_fuellen(ablage)
    a._stand = beschreibung
    a._geholt = datetime.now(UTC)


def test_falsche_pruefsumme_wird_verworfen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Der wichtigste Test hier.

    Eine halb uebertragene App laesst sich herunterladen und nicht oeffnen.
    Dann steht Mia mit einer kaputten Datei da und weiss nicht, warum. Also
    wird erst geprueft und dann uebernommen, nie umgekehrt.
    """
    ziel = tmp_path / "apps.neu"
    beschreibung = _zweig_fuellen(ziel)
    # Die Datei nachtraeglich aendern: die Pruefsumme in apps.json stimmt nun
    # nicht mehr.
    (ziel / "MiaOS-Mac.zip").write_bytes(b"KAPUTT")

    ablage = tmp_path / "apps"
    monkeypatch.setattr(apps_modul, "ABLAGE", ablage)

    # Den Klon nachstellen: er hat den Zweig bereits nach .neu gelegt.
    def kein_git(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(apps_modul.subprocess, "run", kein_git)

    a = apps_modul.Apps()
    with pytest.raises(ValueError, match=r"Pruefsumme|Prüfsumme"):
        a._holen()
    # Nichts uebernommen: die alte Fassung bleibt, wo sie war.
    assert not ablage.exists()
    assert beschreibung["mac"]["sha256"] != hashlib.sha256(b"KAPUTT").hexdigest()


def test_unbekannte_art_gibt_nichts(zweig: Path) -> None:
    a = apps_modul.Apps()
    assert a.datei("windows") is None
    assert a.datei("") is None


def test_api_ohne_zweig_antwortet_leer(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kein Zweig, kein Schluessel, kein Netz: dann eben keine Version.

    Bewusst 200 mit leeren Feldern und kein Fehler: eine App, die beim Start
    nach Updates fragt, soll nicht abstuerzen, weil gerade nichts da ist.
    """
    monkeypatch.setattr(apps_modul, "_apps", None)
    monkeypatch.setattr(apps_modul, "ABLAGE", Path("/nicht/vorhanden"))

    antwort = client.get("/api/app/neueste")
    assert antwort.status_code == 200
    assert antwort.json()["version"] == ""


def test_api_datei_ohne_app_ist_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps_modul, "_apps", None)
    monkeypatch.setattr(apps_modul, "ABLAGE", Path("/nicht/vorhanden"))
    assert client.get("/api/app/datei/mac").status_code == 404


def test_api_app_braucht_zugang(fremder: TestClient) -> None:
    """Die Apps liegen hinter derselben Sperre wie alles andere.

    Sie sind zwar kein Geheimnis, aber sie tragen die Adresse des Servers im
    Code. Ein offener Download waere ein Hinweis nach draussen, wo Mia OS
    steht.
    """
    assert fremder.get("/api/app/neueste").status_code == 401
    assert fremder.get("/api/app/datei/mac").status_code == 401
