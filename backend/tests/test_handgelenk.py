"""Der Endpunkt für die Uhr.

Zwei Dinge unterscheiden ihn vom Briefing, und beide sind hier geprueft:
er ist klein, und er zeigt was NOCH KOMMT statt des ganzen Tages.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from datetime import time as dtime

from fastapi.testclient import TestClient


def _termin(store, titel: str, start: datetime, ganztags: bool = False) -> None:
    """Einen Termin anlegen, so wie der Collector ihn ablegt."""
    store.replace_events(
        [
            {
                "uid": f"uid-{titel}",
                "title": titel,
                "start_at": start.isoformat(),
                "end_at": (start + timedelta(hours=1)).isoformat(),
                "ganztags": ganztags,
                "location": "",
                "calendar": "Privat",
            }
        ],
        von=date.today().isoformat(),
        bis=date.today().isoformat(),
    )


def test_vergangene_termine_fallen_raus(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Der Kern des Ganzen.

    Ein Termin um neun ist um halb elf keine nuetzliche Anzeige mehr. Das
    Briefing zeigt den ganzen Tag, die Uhr zeigt, was noch kommt.

    **Gefaelschte Uhrzeit statt Rechnerei um den echten Jetzt-Zeitpunkt:**
    dieser Test hat sich zweimal selbst zerlegt. Erst mit ``jetzt + 2
    Stunden`` (fiel um 22:15 um, weil der Termin auf den naechsten Tag
    rutschte), dann mit ``jetzt.hour - 1`` als Vergangenheit (fiel um 00:15
    um, weil ``max(1, -1)`` die 01:00 ergibt und die um Mitternacht noch in
    der Zukunft liegt). Jede Heuristik um die echte Uhr herum hat ein
    Zeitfenster, in dem sie falsch liegt. Also wird die Uhr gefaelscht, wie
    in ``test_jede_tageszeit`` auch: Mittag, davor zehn, danach zwei.
    """
    import src.api as api_modul
    import src.main as m

    store = m.get_store()
    heute = date.today()
    mittag = datetime.combine(heute, dtime(12, 0))

    class GefaelschteZeit(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def,override]
            return mittag

    monkeypatch.setattr(api_modul, "datetime", GefaelschteZeit)

    def am_tag(stunde: int, minute: int) -> str:
        return datetime.combine(heute, dtime(stunde, minute)).isoformat()

    store.replace_events(
        [
            {
                "uid": "vorbei",
                "title": "Schon gewesen",
                "start_at": am_tag(10, 0),
                "end_at": am_tag(10, 30),
                "ganztags": False,
                "location": "",
                "calendar": "Privat",
            },
            {
                "uid": "kommt",
                "title": "Kommt noch",
                "start_at": am_tag(14, 0),
                "end_at": None,
                "ganztags": False,
                "location": "Buxtehude",
                "calendar": "Privat",
            },
        ],
        von=heute.isoformat(),
        bis=heute.isoformat(),
    )

    daten = client.get("/api/handgelenk").json()
    assert daten["naechster"] is not None, "Um 12:00 wurde der 14-Uhr-Termin nicht gefunden."
    assert daten["naechster"]["titel"] == "Kommt noch"
    assert daten["naechster"]["ort"] == "Buxtehude"
    # Nur der eine kommt noch, also nichts weiter danach.
    assert daten["spaeter_heute"] == 0


def test_ganztaegiges_bleibt_stehen(client: TestClient) -> None:
    """Ein Geburtstag hat keine Uhrzeit, die vergehen koennte."""
    import src.main as m

    _termin(m.get_store(), "Geburtstag", datetime.combine(date.today(), datetime.min.time()), True)

    daten = client.get("/api/handgelenk").json()
    assert daten["naechster"]["titel"] == "Geburtstag"
    # Ohne Uhrzeit: die Uhr zeigt sonst "00:00" und das waere gelogen.
    assert daten["naechster"]["zeit"] == ""


def test_leerer_tag_sagt_nichts_statt_null(client: TestClient) -> None:
    daten = client.get("/api/handgelenk").json()
    assert daten["naechster"] is None
    assert daten["faellig"] == 0


def test_antwort_bleibt_klein(client: TestClient) -> None:
    """Der Grund fuer den eigenen Endpunkt.

    Eine Komplikation wacht den ganzen Tag alle paar Minuten auf. Jedes
    uebertragene Byte ist Akkulaufzeit. Wird die Antwort hier spuerbar
    groesser, hat jemand etwas hineingelegt, das nicht auf eine Uhr gehoert.
    """
    import src.main as m

    store = m.get_store()
    jetzt = datetime.now()
    store.replace_events(
        [
            {
                "uid": f"t{i}",
                "title": f"Termin {i} mit einem langen Titel zum Testen",
                "start_at": (jetzt + timedelta(hours=i)).isoformat(),
                "end_at": (jetzt + timedelta(hours=i, minutes=30)).isoformat(),
                "ganztags": False,
                "location": "Irgendwo in Hamburg",
                "calendar": "Privat",
            }
            for i in range(1, 6)
        ],
        von=date.today().isoformat(),
        bis=date.today().isoformat(),
    )

    antwort = client.get("/api/handgelenk")
    assert len(antwort.content) < 500, f"Antwort ist {len(antwort.content)} Bytes"

    # Und der Gegenbeweis: das Briefing ist um ein Vielfaches groesser.
    briefing = client.get("/api/briefing")
    assert len(briefing.content) > len(antwort.content) * 2


def test_faellige_werden_gezaehlt(client: TestClient) -> None:
    import src.main as m

    store = m.get_store()
    gestern = (date.today() - timedelta(days=1)).isoformat()
    store.create_entry(titel="Ueberfaellig", datum=gestern)
    store.create_entry(titel="Ohne Datum")

    daten = client.get("/api/handgelenk").json()
    assert daten["faellig"] == 1
    assert daten["offen"] == 2


def test_uhr_braucht_zugang(fremder: TestClient) -> None:
    """Dieselbe Sperre wie alles andere. Die Uhr koppelt sich ueber das iPhone."""
    assert fremder.get("/api/handgelenk").status_code == 401


def test_jede_tageszeit(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Der Endpunkt muss rund um die Uhr stimmen, nicht nur tagsüber.

    Anlass: der Test darueber lief am 13.09.2026 vier Stunden gruen und fiel
    um 22:15 um, weil "jetzt plus zwei Stunden" nach 22 Uhr am naechsten Tag
    liegt. Ein Test, der nur zwischen 9 und 21 Uhr gruen ist, ist keiner.

    Statt der Systemzeit wird ``datetime`` im Modul ersetzt: der Endpunkt
    holt seine Zeit ueber genau diesen Weg, und so braucht es kein
    libfaketime und keine Rechte.
    """
    import src.api as api_modul
    import src.main as m

    store = m.get_store()
    heute = date.today()

    def zeit_faelschen(auf: datetime) -> type[datetime]:
        """Eine datetime-Klasse, die immer ``auf`` als Jetzt meldet.

        Eigene Funktion und keine Klasse in der Schleife: sonst liest ``now``
        die Schleifenvariable erst beim Aufruf und meldet fuer alle 24
        Durchgaenge dieselbe Stunde. Ruff faengt das als B023.
        """

        class GefaelschteZeit(datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[no-untyped-def,override]
                return auf

        return GefaelschteZeit

    for stunde in range(24):
        jetzt = datetime.combine(heute, dtime(stunde, 30))
        monkeypatch.setattr(api_modul, "datetime", zeit_faelschen(jetzt))

        # Eine Viertelstunde spaeter, im selben Tag gehalten.
        spaeter = min(23, stunde + 1)
        store.replace_events(
            [
                {
                    "uid": "t",
                    "title": "Kommt noch",
                    "start_at": datetime.combine(heute, dtime(spaeter, 45)).isoformat(),
                    "end_at": None,
                    "ganztags": False,
                    "location": "Buxtehude",
                    "calendar": "Privat",
                }
            ],
            von=heute.isoformat(),
            bis=heute.isoformat(),
        )

        daten = client.get("/api/handgelenk").json()
        assert daten["naechster"] is not None, f"Um {stunde:02d}:30 kein Termin gefunden"
        assert daten["naechster"]["titel"] == "Kommt noch"


def test_stand_ist_lesbar(client: TestClient) -> None:
    """Die Uhr zeigt notfalls alte Zahlen und muss sagen koennen, wie alt."""
    daten = client.get("/api/handgelenk").json()
    # Wirft, wenn es kein ISO-Zeitpunkt ist.
    datetime.fromisoformat(daten["stand"])
    assert json.dumps(daten)  # laesst sich vollstaendig serialisieren
