"""Hinweise fuer die Geraete: anlegen, zeigen, beantworten."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src import hinweise as modul
from src.hinweise import Hinweise


def test_anlegen_und_zeigen(tmp_path: Path) -> None:
    h = Hinweise(tmp_path / "h.json")
    a = h.anlegen("  Paket   bei Nachbarin ")
    assert a.text == "Paket bei Nachbarin"
    assert [x["id"] for x in h.offen()] == [a.id]


def test_spaeter_versteckt_eine_stunde(tmp_path: Path) -> None:
    h = Hinweise(tmp_path / "h.json")
    a = h.anlegen("eins")
    b = h.anlegen("zwei")
    h.antworten(a.id, "spaeter")
    assert [x["id"] for x in h.offen()] == [b.id]


def test_fame_bleibt_in_der_liste(tmp_path: Path) -> None:
    h = Hinweise(tmp_path / "h.json")
    a = h.anlegen("gut")
    h.antworten(a.id, "fame")
    assert h.offen() == []
    assert h.alle()[0]["zustand"] == "fame"
    # Ueberlebt den Neustart.
    assert Hinweise(tmp_path / "h.json").alle()[0]["zustand"] == "fame"


def test_leerer_text_wird_abgelehnt(tmp_path: Path) -> None:
    h = Hinweise(tmp_path / "h.json")
    try:
        h.anlegen("   ")
    except ValueError:
        return
    raise AssertionError("leerer Hinweis wurde angenommen")


def test_api_rundlauf(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(modul, "_hinweise", Hinweise(tmp_path / "h.json"))
    r = client.post("/api/hinweise", json={"text": "Jellyfin wieder oben", "von": "Kuma"})
    assert r.status_code == 200
    hid = r.json()["hinweis"]["id"]

    briefing = client.get("/api/briefing").json()
    assert briefing["hinweise"][0]["id"] == hid
    assert briefing["hinweise"][0]["von"] == "Kuma"

    assert client.post(f"/api/hinweise/{hid}/ok").status_code == 200
    assert client.get("/api/briefing").json()["hinweise"] == []
    assert client.post(f"/api/hinweise/{hid}/quatsch").status_code == 400
    assert client.post("/api/hinweise/999/ok").status_code == 404


def test_regeln_kommen(client: TestClient) -> None:
    r = client.get("/api/regeln").json()
    assert any(z.startswith("30. DOAH") for z in r["regeln"])


def test_faellig_hat_id(client: TestClient) -> None:
    client.post("/api/sammlung", json={"titel": "Ding", "datum": "2020-01-01"})
    f = client.get("/api/briefing").json()["faellig"]
    assert f and isinstance(f[0]["id"], int)
