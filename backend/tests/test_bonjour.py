"""Die Bonjour-Ankuendigung.

Geprueft wird das Paket, nicht das Netz: ein Test, der einen echten
Multicast verschickt, ist auf einem CI-Runner ohne Netz rot und sagt auch
sonst wenig. Was zaehlt, ist die Frage: steht im Paket das Richtige, und
antwortet der Dienst nur auf die passende Anfrage?
"""

from __future__ import annotations

import socket
import struct

import pytest

from src import bonjour


def _an() -> bonjour.Ankuendigung:
    return bonjour.Ankuendigung(
        instanz="Mia OS",
        port=8080,
        version="0.3.10",
        adresse="172.16.30.230",
    )


def test_name_kodieren_und_lesen_sind_umkehrbar() -> None:
    """Der Kern des Protokolls. Geht das schief, ist alles Weitere Unsinn."""
    for name in ("mia-os.local.", "_miaos._tcp.local.", "Mia OS._miaos._tcp.local."):
        roh = bonjour._name_kodieren(name)
        gelesen, _ = bonjour._name_lesen(roh, 0)
        assert gelesen == name


def test_antwort_enthaelt_alle_vier_saetze() -> None:
    """PTR, SRV, TXT und A in einem Paket.

    Fehlt einer, muss die App nachfragen, und jede Nachfrage ist eine Runde
    mehr, in der etwas schiefgehen kann.
    """
    paket = bonjour.antwort_bauen(_an())
    _, flags, fragen, antworten, _, _ = struct.unpack("!HHHHHH", paket[:12])
    assert flags & 0x8000, "Kein Antwort-Bit gesetzt"
    assert fragen == 0
    assert antworten == 4


def test_antwort_traegt_adresse_port_und_version() -> None:
    an = _an()
    paket = bonjour.antwort_bauen(an)

    # Die IP steht als vier rohe Bytes drin.
    assert socket.inet_aton(an.adresse) in paket
    # Der Port als 16-Bit-Zahl im SRV-Satz.
    assert struct.pack("!H", an.port) in paket
    # Version und Instanzname als Text.
    assert b"version=0.3.10" in paket
    assert b"Mia OS" in paket


def test_ankuendigung_traegt_nichts_persoenliches() -> None:
    """Eine mDNS-Antwort hoert jeder im Netz mit, auch ein Gast im WLAN.

    Deshalb steht dort der Dienstname und die Version, sonst nichts. Dieser
    Test faellt um, sobald jemand auf die Idee kommt, etwa den Benutzernamen
    oder die Zahl der Dokumente mit anzukuendigen.
    """
    paket = bonjour.antwort_bauen(_an())
    text = paket.decode("utf-8", "replace")
    for verboten in ("Grünwald", "Gruenwald", "dokument", "termin", "@"):
        assert verboten.lower() not in text.lower(), f"{verboten} steht in der Ankuendigung"


def _frage(name: str, typ: int) -> bytes:
    """Ein mDNS-Anfragepaket bauen, wie ein iPhone es schickt."""
    kopf = struct.pack("!HHHHHH", 0, 0, 1, 0, 0, 0)
    return kopf + bonjour._name_kodieren(name) + struct.pack("!HH", typ, 1)


def test_fragen_lesen_findet_den_diensttyp() -> None:
    fragen = bonjour._fragen_lesen(_frage(bonjour.DIENST, bonjour.TYP_PTR))
    assert fragen == [(bonjour.DIENST.lower(), bonjour.TYP_PTR)]


def test_antworten_anderer_werden_ignoriert() -> None:
    """Sonst antwortet der Dienst auf sich selbst und auf fremde Geraete.

    Das Antwort-Bit im Kopf unterscheidet beides. Ohne diese Pruefung
    entstuende im Netz ein Echo zwischen zwei Mia-OS-Instanzen.
    """
    antwort = bonjour.antwort_bauen(_an())
    assert bonjour._fragen_lesen(antwort) == []


@pytest.mark.parametrize(
    "kaputt",
    [
        b"",
        b"\x00",
        b"\x00" * 11,
        # Anzahl Fragen behauptet 5, danach kommt nichts.
        struct.pack("!HHHHHH", 0, 0, 5, 0, 0, 0),
        # Ein Laengenbyte, das ueber das Paketende zeigt.
        struct.pack("!HHHHHH", 0, 0, 1, 0, 0, 0) + b"\xff",
    ],
)
def test_kaputte_pakete_werfen_nicht(kaputt: bytes) -> None:
    """Im Netz liegt allerlei. Ein Fremdpaket darf den Dienst nicht umwerfen."""
    assert bonjour._fragen_lesen(kaputt) == []


def test_namenszeiger_laufen_nicht_endlos() -> None:
    """Ein Zeiger auf sich selbst ist der klassische Weg, einen Parser aufzuhaengen."""
    # Kopf, dann ein Kompressionszeiger auf Position 12, also auf sich selbst.
    boese = struct.pack("!HHHHHH", 0, 0, 1, 0, 0, 0) + b"\xc0\x0c"
    name, _ = bonjour._name_lesen(boese, 12)
    assert isinstance(name, str)


def test_eigene_adresse_ist_keine_loopback_wenn_netz_da_ist() -> None:
    """``gethostbyname`` liefert im Container oft 127.0.0.1, und das ist wertlos.

    Auf einem Rechner ohne Netz faellt der Wert zurueck, das ist erlaubt:
    dann gibt es auch nichts anzukuendigen.
    """
    adresse = bonjour.eigene_adresse()
    # Wirft, wenn es keine gueltige IPv4-Adresse ist.
    socket.inet_aton(adresse)


def test_rechnername_ist_ein_gueltiger_dns_name() -> None:
    """Leerzeichen im Instanznamen duerfen nicht in den A-Satz durchschlagen."""
    an = _an()
    assert " " not in an.rechnername
    assert an.rechnername.endswith(".local.")
    assert an.voller_name.endswith(bonjour.DIENST)
