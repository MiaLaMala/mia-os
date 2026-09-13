"""Termine: Store, JSON-API, Weiterleitung der alten Adresse."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from src.store import Store


def _ev(titel: str, start: datetime, **kw: Any) -> dict[str, Any]:
    return {
        "uid": kw.get("uid", f"uid-{titel}-{start.isoformat()}"),
        "start_at": start.isoformat(),
        "end_at": kw.get("ende", start + timedelta(hours=1)).isoformat()
        if kw.get("ende") is not False
        else "",
        "title": titel,
        "location": kw.get("ort", ""),
        "calendar": kw.get("kalender", "Privat"),
        "ganztags": kw.get("ganztags", False),
    }


def _fenster() -> tuple[str, str]:
    heute = date.today()
    return (
        datetime.combine(heute, datetime.min.time()).isoformat(),
        datetime.combine(heute + timedelta(days=21), datetime.max.time()).isoformat(),
    )


# --- Store ----------------------------------------------------------------


def test_termine_chronologisch(store: Store) -> None:
    heute = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    von, bis = _fenster()
    store.replace_events(
        [
            _ev("Spät", heute + timedelta(hours=6)),
            _ev("Früh", heute + timedelta(hours=1)),
        ],
        von,
        bis,
    )
    assert [e["title"] for e in store.events(von, bis)] == ["Früh", "Spät"]


def test_zweiter_lauf_verdoppelt_nicht(store: Store) -> None:
    """Derselbe Termin darf nach dem Neulesen nicht zweimal dastehen."""
    heute = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    von, bis = _fenster()
    for _ in range(3):
        store.replace_events([_ev("Berufsschule", heute, uid="fest")], von, bis)
    assert len(store.events(von, bis)) == 1


def test_abgesagter_termin_verschwindet(store: Store) -> None:
    heute = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    von, bis = _fenster()
    store.replace_events([_ev("A", heute), _ev("B", heute + timedelta(hours=2))], von, bis)
    store.replace_events([_ev("A", heute)], von, bis)
    assert [e["title"] for e in store.events(von, bis)] == ["A"]


def test_termine_ausserhalb_des_fensters_bleiben(store: Store) -> None:
    """Ein Lauf über zwei Wochen darf nicht löschen, was in vier Wochen ist."""
    heute = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    weit = heute + timedelta(days=40)
    store.replace_events(
        [_ev("Weit weg", weit)],
        weit.isoformat(),
        (weit + timedelta(days=1)).isoformat(),
    )
    von, bis = _fenster()
    store.replace_events([_ev("Bald", heute)], von, bis)

    alles = store.events(von, (weit + timedelta(days=1)).isoformat())
    assert {e["title"] for e in alles} == {"Bald", "Weit weg"}


def test_kalenderliste(store: Store) -> None:
    heute = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    von, bis = _fenster()
    store.replace_events(
        [
            _ev("A", heute, kalender="Privat"),
            _ev("B", heute + timedelta(hours=1), kalender="Berufsschule"),
            _ev("C", heute + timedelta(hours=2), kalender="Privat"),
        ],
        von,
        bis,
    )
    assert store.event_calendars() == ["Berufsschule", "Privat"]


# --- JSON-API (das Svelte-Frontend liest nur noch hier) --------------------


def _fuellen(client: TestClient) -> str:
    """Termine anlegen, gibt den Tag als ISO zurueck.

    Bewusst uebermorgen: ein Termin am heutigen Tag laeuft je nach Uhrzeit
    gerade, und der Test waere nur zu bestimmten Tageszeiten gruen.
    """
    import src.main as m

    tag = (datetime.now() + timedelta(days=2)).replace(hour=13, minute=0, second=0, microsecond=0)
    von, bis = _fenster()
    m.get_store().replace_events(
        [
            _ev("Zahnarzt", tag, ort="Buxtehude"),
            _ev("Berufsschule", tag.replace(hour=7, minute=30), kalender="Berufsschule"),
            _ev("Später mal", tag + timedelta(days=3), kalender="Privat"),
        ],
        von,
        bis,
    )
    return tag.date().isoformat()


def test_alte_adresse_fuehrt_in_die_app(client: TestClient) -> None:
    """``/termine`` war die Jinja-Seite. Alte Lesezeichen landen in der App."""
    antwort = client.get("/termine", follow_redirects=False)
    assert antwort.status_code == 307
    assert antwort.headers["location"] == "/#/termine"


def test_api_liefert_den_tag(client: TestClient) -> None:
    tag = _fuellen(client)
    daten = client.get("/api/termine", params={"von": tag, "bis": tag}).json()
    titel = [t["title"] for t in daten["termine"]]
    assert titel == ["Berufsschule", "Zahnarzt"], "chronologisch, nur dieser Tag"
    assert "Später mal" not in titel


def test_api_termin_hat_zeit_und_farbe(client: TestClient) -> None:
    tag = _fuellen(client)
    daten = client.get("/api/termine", params={"von": tag, "bis": tag}).json()
    zahnarzt = next(t for t in daten["termine"] if t["title"] == "Zahnarzt")
    assert zahnarzt["start"].startswith(f"{tag}T13:00")
    assert zahnarzt["allDay"] is False
    assert zahnarzt["farbe"].startswith("#")
    assert zahnarzt["kalender"] == "Privat"


def test_api_kalenderfilter(client: TestClient) -> None:
    tag = _fuellen(client)
    daten = client.get(
        "/api/termine", params={"von": tag, "bis": tag, "kalender": "Berufsschule"}
    ).json()
    assert [t["title"] for t in daten["termine"]] == ["Berufsschule"]
    assert set(daten["kalender"]) == {"Berufsschule", "Privat"}


def test_api_kaputtes_datum_ist_400(client: TestClient) -> None:
    for wert in ("quatsch", "2026-13-99", ""):
        antwort = client.get("/api/termine", params={"von": wert, "bis": wert})
        assert antwort.status_code == 400, wert


def test_farbe_bleibt_gleich(client: TestClient) -> None:
    """Über den Namen, nicht über die Reihenfolge.

    Sonst tauschen die Farben, sobald ein Kalender dazukommt.
    """
    from src.main import _kalenderfarbe

    assert _kalenderfarbe("Berufsschule") == _kalenderfarbe("Berufsschule")
    assert _kalenderfarbe("Arbeit") != _kalenderfarbe("Privat")


def test_emojis_verschwinden_aus_titeln(client: TestClient) -> None:
    """Inter hat keine Emoji-Glyphen: der Browser zeichnet Ersatzkästchen."""
    import src.main as m

    tag = (datetime.now() + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
    von, bis = _fenster()
    m.get_store().replace_events([_ev("📚 Berufsschule", tag)], von, bis)

    t = tag.date().isoformat()
    daten = client.get("/api/termine", params={"von": t, "bis": t}).json()
    assert daten["termine"][0]["title"] == "Berufsschule"


def test_nur_emoji_bleibt_stehen(client: TestClient) -> None:
    """Ein Titel, der NUR aus einem Emoji besteht, darf nicht leer werden."""
    import src.main as m

    tag = (datetime.now() + timedelta(days=2)).replace(hour=11, minute=0, second=0, microsecond=0)
    von, bis = _fenster()
    m.get_store().replace_events([_ev("🎉", tag)], von, bis)
    t = tag.date().isoformat()
    daten = client.get("/api/termine", params={"von": t, "bis": t}).json()
    assert daten["termine"][0]["title"] == "🎉"


def test_ganztags_kommt_als_allday(client: TestClient) -> None:
    import src.main as m

    tag = (datetime.now() + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    von, bis = _fenster()
    m.get_store().replace_events([_ev("Feiertag", tag, ganztags=True, ende=False)], von, bis)
    t = tag.date().isoformat()
    daten = client.get("/api/termine", params={"von": t, "bis": t}).json()
    assert daten["termine"][0]["allDay"] is True


def test_termin_ansicht_markiert_vergangenes() -> None:
    """Was vorbei ist, soll die Anzeige wissen. Gestern, nicht heute frueh:
    zwischen Mitternacht und 00:35 waere ein Termin um 00:05 sonst noch nicht
    vorbei und der Test jede Nacht rot."""
    from src.main import _termin_ansicht

    gestern = datetime.now() - timedelta(days=1)
    frueh = gestern.replace(hour=9, minute=0, second=0, microsecond=0)
    e = _ev("Längst durch", frueh, ende=frueh + timedelta(minutes=30))
    ansicht = _termin_ansicht(e, date.today())
    assert ansicht["vorbei"] is True
