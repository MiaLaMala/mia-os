"""Tests fuer das Berichtsheft."""

from __future__ import annotations

from datetime import date

from src.berichtsheft import Woche, entwurf, wochenanfang, zusammenfuehren


def _termin(
    tag: str, von: str, bis: str, titel: str, kalender: str, ganztags: bool = False
) -> dict[str, object]:
    return {
        "start_at": f"{tag}T{von}:00" if von else tag,
        "end_at": f"{tag}T{bis}:00" if bis else "",
        "title": titel,
        "calendar": kalender,
        "ganztags": ganztags,
    }


def test_wochenanfang_ist_immer_montag() -> None:
    assert wochenanfang(date(2026, 9, 9)) == date(2026, 9, 7)
    assert wochenanfang(date(2026, 9, 7)) == date(2026, 9, 7)
    assert wochenanfang(date(2026, 9, 13)) == date(2026, 9, 7)


def test_stunden_ohne_pausen_und_wege() -> None:
    """Mias echter Dienstag: 7:30 bis 16:15 mit zwei Pausen sind 7,25 Stunden."""
    termine = [
        _termin("2026-09-08", "07:30", "08:30", "Arbeit", "Arbeit"),
        _termin("2026-09-08", "08:30", "09:00", "Frühstück", "Privat"),
        _termin("2026-09-08", "09:00", "11:30", "Arbeit", "Arbeit"),
        _termin("2026-09-08", "11:30", "12:30", "Mittagspause", "Privat"),
        _termin("2026-09-08", "12:30", "16:15", "Arbeit", "Arbeit"),
        _termin("2026-09-08", "16:15", "16:45", "Heimweg", "Privat"),
    ]
    w = entwurf(date(2026, 9, 7), termine)
    dienstag = w.tage[1]
    assert dienstag.betrieb_stunden == 7.25
    assert dienstag.schule_stunden == 0
    assert dienstag.art == "betrieb"
    assert w.stunden == 7.25


def test_schultag_und_betrieb_am_selben_tag() -> None:
    termine = [
        _termin("2026-09-07", "07:30", "09:00", "Berufsschule", "Berufsschule"),
        _termin("2026-09-07", "09:00", "09:30", "Frühstückspause", "Berufsschule"),
        _termin("2026-09-07", "09:30", "12:45", "Berufsschule", "Berufsschule"),
        _termin("2026-09-07", "13:30", "16:15", "Betrieb (Nachmittag)", "Arbeit"),
    ]
    w = entwurf(date(2026, 9, 7), termine)
    montag = w.tage[0]
    assert montag.schule_stunden == 4.75
    assert montag.betrieb_stunden == 2.75
    assert montag.art == "schule+betrieb"


def test_krankheit_setzt_den_tag_auf_null() -> None:
    termine = [
        _termin("2026-09-08", "07:30", "16:15", "Arbeit", "Arbeit"),
        _termin("2026-09-08", "", "", "Krank gemeldet", "Privat", ganztags=True),
    ]
    w = entwurf(date(2026, 9, 7), termine)
    dienstag = w.tage[1]
    assert dienstag.art == "krank"
    assert dienstag.stunden == 0
    assert dienstag.bloecke == []
    assert w.stunden == 0


def test_aufgabe_aus_der_sammlung_ist_kein_fehltag() -> None:
    """'AU abgeben' hat den Montag faelschlich auf null Stunden gesetzt.

    Ein zu eifriges Muster faelscht den Nachweis, deshalb dieser Test.
    """
    termine = [
        _termin("2026-09-07", "07:30", "16:15", "Arbeit", "Arbeit"),
        _termin("2026-09-07", "", "", "AU abgeben", "Sammlung", ganztags=True),
    ]
    w = entwurf(date(2026, 9, 7), termine)
    montag = w.tage[0]
    assert montag.art == "betrieb"
    assert montag.stunden == 8.75
    assert "AU abgeben" in montag.hinweise


def test_sammlungseintraege_werden_zu_hinweisen() -> None:
    w = entwurf(
        date(2026, 9, 7),
        [_termin("2026-09-08", "07:30", "16:15", "Arbeit", "Arbeit")],
        [{"datum": "2026-09-08", "titel": "Firewall-Regeln dokumentiert"}],
    )
    assert "Firewall-Regeln dokumentiert" in w.tage[1].hinweise


def test_entwurf_erfindet_keine_taetigkeiten() -> None:
    """Der Kalender sagt nicht, WAS passiert ist. Also bleibt das Feld leer."""
    w = entwurf(date(2026, 9, 7), [_termin("2026-09-08", "07:30", "16:15", "Arbeit", "Arbeit")])
    assert all(t.taetigkeiten == [] for t in w.tage)


def test_wochenende_ohne_termine_ist_frei() -> None:
    w = entwurf(date(2026, 9, 7), [_termin("2026-09-08", "07:30", "16:15", "Arbeit", "Arbeit")])
    assert w.tage[5].art == "frei"
    assert w.tage[6].art == "frei"


def test_kalenderwoche_stimmt() -> None:
    w = entwurf(date(2026, 9, 7), [])
    assert w.kw == date(2026, 9, 7).isocalendar().week
    assert w.jahr == 2026
    assert w.montag == "2026-09-07"
    assert w.sonntag == "2026-09-13"


def test_korrekturen_gewinnen_ueber_den_entwurf() -> None:
    w = entwurf(date(2026, 9, 7), [_termin("2026-09-08", "07:30", "16:15", "Arbeit", "Arbeit")])
    zusammen = zusammenfuehren(
        w,
        {
            "status": "fertig",
            "bemerkung": "Woche war okay",
            "themen_schule": "Subnetting",
            "inhalt": {
                "2026-09-08": {"taetigkeiten": ["VLANs eingerichtet"], "stunden": 6.0},
            },
        },
    )
    assert zusammen.status == "fertig"
    assert zusammen.bemerkung == "Woche war okay"
    assert zusammen.themen_schule == "Subnetting"
    assert zusammen.tage[1].taetigkeiten == ["VLANs eingerichtet"]
    assert zusammen.tage[1].stunden == 6.0
    assert zusammen.stunden == 6.0


def test_zusammenfuehren_ohne_gespeichertes_aendert_nichts() -> None:
    w = entwurf(date(2026, 9, 7), [])
    assert zusammenfuehren(w, None) is w


def test_neuer_termin_korrigiert_die_stunden_trotz_gespeichertem_text() -> None:
    """Der Kalender bleibt die Quelle fuer Zeiten, Mias Text bleibt stehen."""
    termine = [
        _termin("2026-09-08", "07:30", "16:15", "Arbeit", "Arbeit"),
        _termin("2026-09-09", "07:30", "12:45", "Berufsschule", "Berufsschule"),
    ]
    w = zusammenfuehren(
        entwurf(date(2026, 9, 7), termine),
        {"inhalt": {"2026-09-08": {"taetigkeiten": ["Tickets bearbeitet"]}}},
    )
    assert w.tage[1].taetigkeiten == ["Tickets bearbeitet"]
    assert w.tage[2].stunden == 5.25


def test_as_dict_ist_serialisierbar() -> None:
    import json

    w: Woche = entwurf(date(2026, 9, 7), [_termin("2026-09-08", "07:30", "16:15", "A", "Arbeit")])
    text = json.dumps(w.as_dict(), ensure_ascii=False)
    assert "2026-09-08" in text
