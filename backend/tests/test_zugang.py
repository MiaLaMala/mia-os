"""Die Torwache und die Kopplung.

Diese Tests sind der Grund, warum ich der Sperre traue. Eine Middleware, die
nur im Gutfall geprueft wird, sieht genauso aus wie eine, die jeden
durchlaesst.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.zugang import Kopplung, abdruck, aus_vertrautem_netz, neuer_schluessel

# --- Das Netz -------------------------------------------------------------


def test_heimnetz_darf_herein() -> None:
    assert aus_vertrautem_netz("172.16.30.230")
    assert aus_vertrautem_netz("127.0.0.1")
    # Das WLAN am Pi-Gateway, aus dem das Display kommt.
    assert aus_vertrautem_netz("10.42.7.15")


def test_fremdes_netz_darf_nicht() -> None:
    assert not aus_vertrautem_netz("203.0.113.7")
    # Ein Hotel-WLAN vergibt auch private Adressen. Privat heisst nicht
    # vertraut: nur die Netze, die wirklich Mias sind.
    assert not aus_vertrautem_netz("192.168.1.20")
    assert not aus_vertrautem_netz("10.0.0.5")


def test_unlesbare_adresse_gilt_als_fremd() -> None:
    """Im Zweifel zu, nicht auf.

    Der TestClient setzt ohne Zutun den Hostnamen "testclient" statt einer
    IP. Faellt das auf "vertraut" zurueck, waere die ganze Sperre im Testlauf
    unsichtbar und im Betrieb trotzdem da.
    """
    assert not aus_vertrautem_netz("testclient")
    assert not aus_vertrautem_netz("")


# --- Die Sperre selbst ----------------------------------------------------


def test_fremder_kommt_nicht_an_die_daten(fremder: TestClient) -> None:
    antwort = fremder.get("/api/uebersicht")
    assert antwort.status_code == 401
    assert antwort.headers.get("www-authenticate") == "Bearer"


def test_fremder_darf_die_gesundheit_fragen(fremder: TestClient) -> None:
    """Uptime Kuma fragt von aussen und soll keinen Schluessel brauchen."""
    assert fremder.get("/health").status_code == 200


def test_fremder_bekommt_keinen_kopplungscode(fremder: TestClient) -> None:
    """Sonst koennte sich jeder selbst einen Code ausstellen."""
    assert fremder.post("/api/kopplung/code").status_code == 401


def test_heimnetz_kommt_durch(client: TestClient) -> None:
    assert client.get("/api/uebersicht").status_code == 200


# --- Kopplung -------------------------------------------------------------


def test_kopplung_von_anfang_bis_ende(client: TestClient, fremder: TestClient) -> None:
    """Der ganze Weg: Code holen, einloesen, von aussen hereinkommen.

    Beide Clients teilen sich den Prozess und damit die Kopplungsliste im
    Arbeitsspeicher, aber NICHT die Datenbank. Deshalb wird hier nur der
    Tausch Code gegen Schluessel geprueft, und die Sperre gegen einen
    erfundenen Schluessel getrennt darunter.
    """
    code = client.post("/api/kopplung/code").json()
    assert len(code["code"]) == 6 and code["code"].isdigit()

    antwort = client.post(
        "/api/kopplung/einloesen",
        json={"code": code["code"], "name": "Mias iPhone", "plattform": "ios"},
    )
    assert antwort.status_code == 200
    schluessel = antwort.json()["schluessel"]
    assert len(schluessel) > 30

    # Das Geraet steht jetzt in der Liste.
    geraete = client.get("/api/kopplung/geraete").json()["geraete"]
    assert [g["name"] for g in geraete] == ["Mias iPhone"]
    # Und zwar ohne seinen Abdruck: die Liste geht an die Oberflaeche.
    assert "abdruck" not in geraete[0]

    # Mit dem Schluessel kommt die App von aussen herein.
    mit = client.get("/api/uebersicht", headers={"Authorization": f"Bearer {schluessel}"})
    assert mit.status_code == 200

    # Abmelden, und der Schluessel gilt nicht mehr.
    assert client.delete(f"/api/kopplung/geraete/{geraete[0]['id']}").status_code == 200
    assert client.get("/api/kopplung/geraete").json()["geraete"] == []


def test_erfundener_schluessel_kommt_nicht_herein(fremder: TestClient) -> None:
    antwort = fremder.get(
        "/api/uebersicht", headers={"Authorization": f"Bearer {neuer_schluessel()}"}
    )
    assert antwort.status_code == 401


def test_falscher_code_gibt_keinen_schluessel(client: TestClient) -> None:
    client.post("/api/kopplung/code")
    antwort = client.post("/api/kopplung/einloesen", json={"code": "000000", "name": "X"})
    # 403 und nicht 401: die Anfrage darf hier sein, der Code taugt nur nicht.
    assert antwort.status_code == 403
    assert "schluessel" not in antwort.text


def test_code_gilt_nur_einmal(client: TestClient) -> None:
    code = client.post("/api/kopplung/code").json()["code"]
    assert client.post("/api/kopplung/einloesen", json={"code": code}).status_code == 200
    assert client.post("/api/kopplung/einloesen", json={"code": code}).status_code == 403


def test_schluessel_liegt_nicht_im_klartext(client: TestClient) -> None:
    """Der wichtigste Test hier.

    Wer die Datenbank in die Hand bekommt (Backup, gestohlener Datentraeger),
    soll sich damit nicht anmelden koennen. Gespeichert ist nur der Abdruck.
    """
    import src.main as m

    code = client.post("/api/kopplung/code").json()["code"]
    schluessel = client.post("/api/kopplung/einloesen", json={"code": code}).json()["schluessel"]

    with m.get_store()._conn() as conn:
        reihen = [dict(r) for r in conn.execute("SELECT * FROM geraetezugang")]
    assert len(reihen) == 1
    assert schluessel not in str(reihen[0])
    assert reihen[0]["abdruck"] == abdruck(schluessel)


# --- Der Codeautomat ------------------------------------------------------


def test_raten_verbraucht_den_code() -> None:
    """Fuenf Fehlversuche, dann ist der Code weg.

    Ohne diese Grenze waeren sechs Ziffern in einer Nacht durchprobiert.
    """
    k = Kopplung()
    code, _ = k.anlegen()
    falsch = "111111" if code != "111111" else "222222"
    for _ in range(5):
        assert not k.einloesen(falsch)
    assert k.offen() == 0
    assert not k.einloesen(code)


def test_abgelaufener_code_gilt_nicht(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime, timedelta

    import src.zugang as z

    k = z.Kopplung()
    code, _ = k.anlegen()
    monkeypatch.setattr(z, "_jetzt", lambda: datetime.now(UTC) + timedelta(minutes=11))
    assert not k.einloesen(code)
