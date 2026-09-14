"""Mia OS im lokalen Netz auffindbar machen (Bonjour, mDNS).

Das Problem, das hier geloest wird
----------------------------------

Die Apps mussten ihre Serveradresse kennen, bevor sie das erste Mal reden
konnten. Auf dem iPhone hiess das: sechs Ziffern Kopplungscode eintippen und
vorher die Adresse von Hand. Mia hat am 14.09.2026 genau daran gehangen, die
App zeigte ``localhost`` und der Code lief ins Leere.

Mit einer mDNS-Ankuendigung findet die App den Server selbst: sie fragt im
Netz nach ``_miaos._tcp`` und bekommt Name, Adresse und Port zurueck.

Warum von Hand und nicht mit einer Bibliothek
---------------------------------------------

``zeroconf`` waere die naheliegende Wahl, zieht aber eine Abhaengigkeit samt
eigenem Netzwerk-Thread mit. Das Protokoll ist fuer den Fall "ein Dienst,
eine Ankuendigung" ueberschaubar: ein UDP-Socket auf der Multicast-Gruppe
224.0.0.251:5353, und auf jede passende Anfrage wird geantwortet.

**Nur antworten, nie von selbst senden.** Ein Dienst, der alle paar Sekunden
ins Netz ruft, ist in einem Heimnetz mit Handys und Fernsehern zusaetzlicher
Verkehr ohne Gewinn. Wer suchen will, fragt; wir antworten.

Was NICHT angekuendigt wird
---------------------------

Nichts Persoenliches. Der Name im Netz ist ``Mia OS``, dazu Adresse, Port und
die Version. Keine Dokumentnamen, keine Termine, keine Benutzerkennung. Eine
mDNS-Ankuendigung hoert jeder im selben Netz mit, auch ein Gast im WLAN.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import struct
from dataclasses import dataclass
from typing import Any, cast

log = logging.getLogger(__name__)

# Die Standard-Gruppe und der Port fuer mDNS. Beide sind festgelegt und
# koennen nicht frei gewaehlt werden: wer sucht, hoert genau hier zu.
GRUPPE = "224.0.0.251"
MDNS_PORT = 5353

# Der Diensttyp. "_tcp", weil dahinter HTTP liegt. Der Name ist frei
# waehlbar, muss aber auf beiden Seiten derselbe sein: er steht so auch im
# Info.plist der Apple-Apps unter NSBonjourServices.
DIENST = "_miaos._tcp.local."

# Wie lange ein Sucher die Antwort behalten darf, in Sekunden. Zwei Minuten:
# lang genug, dass eine App nicht dauernd nachfragt, kurz genug, dass ein
# umgezogener Server nicht ewig falsch im Netz steht.
TTL = 120

# DNS-Satzarten, die hier vorkommen.
TYP_A = 1
TYP_PTR = 12
TYP_TXT = 16
TYP_SRV = 33
TYP_ALLE = 255

KLASSE_IN = 1
# Das oberste Bit der Klasse heisst in mDNS "cache flush": der Empfaenger
# soll aeltere Eintraege fuer diesen Namen wegwerfen. Ohne das bleibt nach
# einem IP-Wechsel die alte Adresse im Cache stehen.
CACHE_FLUSH = 0x8000


@dataclass(frozen=True)
class Ankuendigung:
    """Was ueber Mia OS im Netz steht."""

    instanz: str
    port: int
    version: str
    adresse: str

    @property
    def voller_name(self) -> str:
        """Der Name im DNS-Format, etwa ``Mia OS._miaos._tcp.local.``"""
        return f"{self.instanz}.{DIENST}"

    @property
    def rechnername(self) -> str:
        """Der A-Eintrag, auf den der SRV-Satz zeigt."""
        sauber = self.instanz.replace(" ", "-").lower()
        return f"{sauber}.local."


def _name_kodieren(name: str) -> bytes:
    """Einen DNS-Namen in Laengen-Praefix-Form bringen.

    ``mia-os.local.`` wird zu ``\\x06mia-os\\x05local\\x00``. Ohne
    Namenskompression: die spart ein paar Byte und kostet viel Sorgfalt,
    und ein Paket dieser Groesse passt ohnehin in jedes Netz.
    """
    teile = [t for t in name.split(".") if t]
    roh = b"".join(bytes([len(t)]) + t.encode("utf-8") for t in teile)
    return roh + b"\x00"


def _name_lesen(daten: bytes, pos: int) -> tuple[str, int]:
    """Einen Namen ab ``pos`` lesen, mit Kompressionszeigern.

    Anfragen von Apple-Geraeten benutzen Kompression, also muss zumindest
    das Lesen sie beherrschen. Der Zaehler begrenzt Zeigerschleifen: ein
    fehlerhaftes Paket darf den Dienst nicht aufhaengen.
    """
    teile: list[str] = []
    sprung: int | None = None
    schritte = 0
    while pos < len(daten) and schritte < 128:
        schritte += 1
        laenge = daten[pos]
        if laenge == 0:
            pos += 1
            break
        if laenge & 0xC0 == 0xC0:
            if pos + 1 >= len(daten):
                break
            ziel = ((laenge & 0x3F) << 8) | daten[pos + 1]
            if sprung is None:
                sprung = pos + 2
            pos = ziel
            continue
        pos += 1
        teile.append(daten[pos : pos + laenge].decode("utf-8", "replace"))
        pos += laenge
    return ".".join(teile) + ".", (sprung if sprung is not None else pos)


def _satz(name: bytes, typ: int, inhalt: bytes, cache_flush: bool = True) -> bytes:
    """Einen einzelnen Antwortsatz zusammenbauen."""
    klasse = KLASSE_IN | (CACHE_FLUSH if cache_flush else 0)
    return name + struct.pack("!HHIH", typ, klasse, TTL, len(inhalt)) + inhalt


def antwort_bauen(an: Ankuendigung, frage_id: int = 0) -> bytes:
    """Die vollstaendige Antwort auf eine Suche nach ``_miaos._tcp``.

    Vier Saetze, die zusammen alles sagen, was eine App braucht:

    * **PTR** vom Diensttyp auf unsere Instanz: "es gibt hier ein Mia OS"
    * **SRV** mit Port und Rechnername
    * **TXT** mit Version und Pfad
    * **A** mit der IP-Adresse

    Alle vier in einem Paket: eine App, die nur den PTR bekommt, muesste
    dreimal nachfragen, und jede Nachfrage ist eine Runde mehr, in der etwas
    schiefgehen kann.
    """
    voll = _name_kodieren(an.voller_name)
    rechner = _name_kodieren(an.rechnername)

    ptr = _satz(_name_kodieren(DIENST), TYP_PTR, voll, cache_flush=False)
    srv = _satz(voll, TYP_SRV, struct.pack("!HHH", 0, 0, an.port) + rechner)

    # TXT: Schluessel-Wert-Paare, jedes mit Laengen-Praefix. Bewusst knapp.
    eintraege = [f"version={an.version}", "pfad=/", f"port={an.port}"]
    txt_roh = b"".join(bytes([len(e)]) + e.encode("utf-8") for e in eintraege)
    txt = _satz(voll, TYP_TXT, txt_roh)

    a_satz = _satz(rechner, TYP_A, socket.inet_aton(an.adresse))

    # Kopf: Antwort (0x8400 = Antwort + autoritativ), keine Fragen, vier
    # Antwortsaetze.
    kopf = struct.pack("!HHHHHH", frage_id, 0x8400, 0, 4, 0, 0)
    return kopf + ptr + srv + txt + a_satz


def _fragen_lesen(daten: bytes) -> list[tuple[str, int]]:
    """Die Fragen aus einem mDNS-Paket ziehen.

    Gibt eine Liste aus Name und Typ zurueck. Faellt bei einem kaputten
    Paket auf eine leere Liste zurueck: ein Fremdpaket im Netz darf nichts
    umwerfen.
    """
    if len(daten) < 12:
        return []
    _, flags, anzahl, *_ = struct.unpack("!HHHHHH", daten[:12])
    # Nur Anfragen beantworten, keine Antworten anderer Geraete.
    if flags & 0x8000:
        return []
    pos = 12
    fragen: list[tuple[str, int]] = []
    for _ in range(min(anzahl, 16)):
        try:
            name, pos = _name_lesen(daten, pos)
            typ, _klasse = struct.unpack("!HH", daten[pos : pos + 4])
            pos += 4
        except (struct.error, IndexError, UnicodeDecodeError):
            break
        fragen.append((name.lower(), typ))
    return fragen


def eigene_adresse() -> str:
    """Die IP, unter der dieser Rechner im Heimnetz erreichbar ist.

    Ueber einen UDP-Socket zu einer externen Adresse: es wird nichts
    gesendet, aber das Betriebssystem waehlt dabei die Schnittstelle aus,
    ueber die es hinausginge, und genau deren Adresse ist die richtige.
    ``gethostbyname(gethostname())`` liefert in einem Container dagegen oft
    ``127.0.0.1``, und das ist im Netz wertlos.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))  # TEST-NET-1, nie erreichbar
        adresse: str = s.getsockname()[0]
        return adresse
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class _Empfang(asyncio.DatagramProtocol):
    """Nimmt die Pakete entgegen und laesst den Melder antworten.

    **Warum ein Protokoll und keine Schleife mit ``sock_recvfrom``:** unter
    ``uvicorn[standard]`` laeuft uvloop, und uvloop kennt ``sock_recvfrom``
    schlicht nicht. Der Aufruf wirft ``NotImplementedError``, der Task stirbt
    im ersten Durchlauf, und zwar lautlos: der Socket bleibt offen, der
    Empfangspuffer fuellt sich, ``ss`` zeigt einen lauschenden Dienst. Von
    aussen sieht alles richtig aus, nur antwortet nie jemand.

    Genau so ist es am 14.09.2026 auf dem LXC passiert, nachdem es lokal
    ohne uvicorn funktioniert hatte. ``create_datagram_endpoint`` ist der
    Weg, den beide Schleifen koennen.
    """

    def __init__(self, melder: Melder) -> None:
        self.melder = melder
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        # KEIN isinstance-Test auf asyncio.DatagramTransport: uvloop liefert
        # seinen eigenen Typ, der davon nicht erbt. Ein assert hier bricht
        # die Verbindung sofort wieder ab, und zwar genau im Betrieb unter
        # uvicorn, waehrend es lokal mit der Standard-Schleife durchlaeuft.
        # Gebraucht wird ohnehin nur ``sendto``.
        self.transport = cast("asyncio.DatagramTransport", transport)

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        if self.transport is None:
            return
        self.melder.beantworten(data, addr, self.transport)

    def error_received(self, exc: Exception) -> None:
        # Ein ICMP-Fehler auf einen frueheren Versand. Nichts zu tun: das
        # naechste Paket kommt trotzdem an.
        log.debug("mDNS: %s", exc)


class Melder:
    """Beantwortet mDNS-Anfragen nach Mia OS, solange er laeuft."""

    def __init__(self, an: Ankuendigung) -> None:
        self.an = an
        self._sock: socket.socket | None = None
        self._transport: asyncio.DatagramTransport | None = None

    def _oeffnen(self) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        with contextlib.suppress(AttributeError, OSError):
            # Nicht ueberall vorhanden. Ohne diese Einstellung scheitert das
            # Binden, wenn auf demselben Rechner schon ein mDNS-Dienst
            # lauscht (Avahi im LXC, Bonjour auf dem Mac).
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        s.bind(("", MDNS_PORT))
        mreq = struct.pack("4s4s", socket.inet_aton(GRUPPE), socket.inet_aton("0.0.0.0"))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        s.setblocking(False)
        return s

    def beantworten(
        self,
        daten: bytes,
        absender: tuple[str | Any, int],
        transport: asyncio.DatagramTransport,
    ) -> None:
        """Auf eine einzelne Anfrage antworten, falls sie uns gilt."""
        # Zwei Arten von Anfrage zaehlen: die Suche nach dem Diensttyp
        # (so sucht ein iPhone) und die gezielte Nachfrage nach unserer
        # Instanz (so fragt eines nach, das uns schon kennt).
        gesucht = any(
            (name == DIENST and typ in (TYP_PTR, TYP_ALLE))
            or (name == self.an.voller_name.lower() and typ in (TYP_SRV, TYP_TXT, TYP_ALLE))
            for name, typ in _fragen_lesen(daten)
        )
        if not gesucht:
            return

        # Die Adresse bei jeder Antwort neu bestimmen: im Heimnetz
        # vergibt der DHCP neu, und eine beim Start gemerkte IP waere
        # nach einem Wechsel eine falsche Auskunft.
        aktuell = Ankuendigung(
            instanz=self.an.instanz,
            port=self.an.port,
            version=self.an.version,
            adresse=eigene_adresse(),
        )
        with contextlib.suppress(OSError):
            # An den Fragenden direkt, nicht an die Gruppe: die Antwort
            # interessiert nur ihn, und ein Multicast weniger ist in
            # einem WLAN mit Handys spuerbar.
            transport.sendto(antwort_bauen(aktuell), absender)

    async def starten(self) -> bool:
        """Anfangen zu antworten. ``False``, wenn das Netz es nicht zulaesst.

        Faellt still aus, statt zu werfen: ohne mDNS laeuft Mia OS
        vollstaendig weiter, nur muss die Adresse dann von Hand eingetragen
        werden. Ein Dienst, der wegen einer Bequemlichkeit nicht startet,
        waere die schlechtere Wahl.
        """
        try:
            self._sock = self._oeffnen()
        except OSError as fehler:
            log.info("Bonjour nicht moeglich (%s). Adresse muss von Hand gesetzt werden.", fehler)
            return False

        schleife = asyncio.get_running_loop()
        try:
            transport, _ = await schleife.create_datagram_endpoint(
                lambda: _Empfang(self), sock=self._sock
            )
        except (OSError, NotImplementedError) as fehler:
            log.info("Bonjour nicht moeglich (%s).", fehler)
            with contextlib.suppress(OSError):
                self._sock.close()
            self._sock = None
            return False

        self._transport = transport
        # Auf WARNING, damit die Zeile auch im Container sichtbar ist: die
        # Vorgabe von uvicorn zeigt INFO aus fremden Modulen nicht an, und
        # eine Startmeldung, die niemand sieht, beweist nichts.
        log.warning("Bonjour: %s auf Port %d", self.an.voller_name, self.an.port)
        return True

    async def stoppen(self) -> None:
        if self._transport is not None:
            with contextlib.suppress(Exception):
                self._transport.close()
            self._transport = None
        # Den Socket NICHT selbst schliessen: das Transport hat ihn
        # uebernommen und tut es beim Schliessen. Ein zweiter close() auf
        # denselben Dateideskriptor trifft sonst einen, den inzwischen ein
        # anderer Teil des Programms bekommen hat.
        self._sock = None
