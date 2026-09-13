"""Wer darf die Schnittstelle benutzen.

Bis jetzt hatte Mia OS keine Anmeldung. Das ging, solange nur der Browser im
Heimnetz und das Display hinter dem Pi mit dem Server geredet haben: davor
steht der Reverse Proxy, und der ist von aussen nicht erreichbar. Eine App
auf dem iPhone redet aber auch aus dem Zug mit dem Server, sobald der Tunnel
steht. Ab da entscheidet nicht mehr das Netz, wer hereindarf, sondern der
Server selbst.

**Zwei Wege herein, und das mit Absicht.**

*Der Browser* bekommt seinen Zugang geschenkt, aber nur aus dem Heimnetz oder
dem Tunnel. Das ist genau die Grenze, die bisher schon galt: wer die Seite
aufrufen kann, konnte immer schon alles. Damit aendert sich fuer Mia am
Schreibtisch nichts, und es entsteht kein neues Loch.

*Eine App* koppelt sich einmal mit einem sechsstelligen Code, den Mia auf der
Einstellungsseite ablesen kann, und bekommt dafuer einen eigenen Schluessel.
Der gilt dauerhaft und funktioniert auch von unterwegs.

**Warum ein Code und kein Passwort:** ein Passwort muesste Mia sich merken und
auf jedem Geraet eintippen, und es waere auf allen Geraeten dasselbe. Ein
Kopplungscode gilt zehn Minuten und genau einmal. Geht ein Geraet verloren,
wird sein Schluessel einzeln geloescht, ohne dass die anderen davon wissen.

**Was hier NICHT liegt:** der Schluessel selbst. Gespeichert wird nur sein
SHA-256-Abdruck. Wer die Datenbank in die Hand bekommt, kann sich damit nicht
anmelden. Das ist dieselbe Ueberlegung wie bei der Firmware: auf einer Ablage
mit Ausweisen und Arztunterlagen wird kein Geheimnis zweimal hingelegt.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

log = logging.getLogger(__name__)

# Wie lange ein Kopplungscode gilt. Lang genug, um das iPhone aus der Tasche
# zu holen, kurz genug, dass ein abgelesener Code auf dem Bildschirm nicht
# den ganzen Tag ueber gueltig bleibt.
CODE_MINUTEN = 10

# Sechs Ziffern. Buchstaben waeren mehr Moeglichkeiten, aber der Code wird
# abgetippt: "0 oder O" und "1 oder l" kosten mehr Versuche als sie an
# Sicherheit bringen. Gegen Raten hilft hier die Lebensdauer, nicht die Laenge.
CODE_STELLEN = 6

# Wie oft ein Code falsch geraten werden darf, bevor er verfaellt. Sechs
# Ziffern sind eine Million Moeglichkeiten: mit fuenf Versuchen in zehn
# Minuten kommt niemand durch.
CODE_VERSUCHE = 5

# Netze, aus denen der Browser ohne Kopplung hereindarf. Das Heimnetz, das
# WLAN am Arbeitsplatz hinter dem Pi, und der Rechner selbst.
#
# Bewusst als Liste und nicht "alles Private": ein Gastnetz in einem Hotel
# vergibt auch 192.168.x.y, und von dort soll niemand einfach hereinkommen.
VERTRAUTE_NETZE = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("172.16.0.0/16"),  # Homelab
    ipaddress.ip_network("10.42.7.0/24"),  # Jana-Netz am Pi-Gateway
)


def _jetzt() -> datetime:
    return datetime.now(UTC)


def abdruck(schluessel: str) -> str:
    """Der SHA-256-Abdruck eines Schluessels, hexadezimal."""
    return hashlib.sha256(schluessel.encode("utf-8")).hexdigest()


def neuer_schluessel() -> str:
    """Ein neuer Geraeteschluessel.

    ``token_urlsafe(32)`` sind 256 Bit Zufall. Das ist derselbe Umfang, den
    ein SHA-256-Abdruck traegt: mehr wuerde die Kette nicht staerker machen.
    """
    return secrets.token_urlsafe(32)


def neuer_code() -> str:
    """Ein Kopplungscode aus Ziffern, mit fuehrenden Nullen.

    ``randbelow`` statt ``randint``: die Zufallsquelle ist dieselbe, die auch
    den Schluessel erzeugt. Ein Code aus ``random`` waere aus der Ausgabe
    vorhersagbar.
    """
    return f"{secrets.randbelow(10**CODE_STELLEN):0{CODE_STELLEN}d}"


def aus_vertrautem_netz(adresse: str) -> bool:
    """Ob diese Adresse ohne Kopplung hereindarf.

    Faellt im Zweifel auf ``False``: eine Adresse, die sich nicht lesen
    laesst, ist kein Grund, jemanden hereinzulassen.
    """
    if not adresse:
        return False
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return False
    return any(ip in netz for netz in VERTRAUTE_NETZE)


@dataclass(frozen=True)
class Geraetezugang:
    """Ein gekoppeltes Geraet."""

    id: int
    name: str
    plattform: str
    erstellt: str
    zuletzt: str
    adresse: str

    def als_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "plattform": self.plattform,
            "erstellt": self.erstellt,
            "zuletzt": self.zuletzt,
            "adresse": self.adresse,
        }


class Kopplung:
    """Offene Kopplungscodes.

    Im Arbeitsspeicher und nicht in der Datenbank: ein Code lebt zehn Minuten
    und ueberlebt einen Neustart bewusst nicht. Startet der Server neu,
    waehrend ein Code auf dem Bildschirm steht, ist der Code weg. Das ist die
    richtige Richtung: lieber einmal neu klicken als ein Code, der seine
    eigene Lebensdauer ueberdauert.
    """

    def __init__(self) -> None:
        self._codes: dict[str, dict[str, Any]] = {}

    def anlegen(self) -> tuple[str, datetime]:
        """Einen neuen Code erzeugen. Alte desselben Vorgangs verfallen."""
        self._aufraeumen()
        code = neuer_code()
        bis = _jetzt() + timedelta(minutes=CODE_MINUTEN)
        self._codes[code] = {"bis": bis, "versuche": 0}
        return code, bis

    def _aufraeumen(self) -> None:
        jetzt = _jetzt()
        for code in [c for c, d in self._codes.items() if d["bis"] <= jetzt]:
            del self._codes[code]

    def einloesen(self, code: str) -> bool:
        """Einen Code verbrauchen. ``True``, wenn er gueltig war.

        Der Vergleich laeuft ueber ``compare_digest`` gegen jeden offenen
        Code statt ueber einen Nachschlag im Dictionary. Ein Nachschlag
        antwortet bei einem Treffer messbar anders als bei einem Fehlschlag,
        und der Code ist kurz genug, dass sich das ausnutzen liesse.
        """
        self._aufraeumen()
        code = (code or "").strip()
        treffer: str | None = None
        for offen in self._codes:
            if hmac.compare_digest(offen, code):
                treffer = offen
        if treffer is None:
            # Fehlversuche zaehlen auf ALLE offenen Codes: wer raet, weiss
            # nicht, welchen er gerade verfehlt hat.
            for daten in self._codes.values():
                daten["versuche"] += 1
            for offen in [c for c, d in self._codes.items() if d["versuche"] >= CODE_VERSUCHE]:
                log.warning("Kopplungscode nach %d Fehlversuchen verworfen", CODE_VERSUCHE)
                del self._codes[offen]
            return False
        del self._codes[treffer]
        return True

    def offen(self) -> int:
        self._aufraeumen()
        return len(self._codes)


_kopplung: Kopplung | None = None


def hole_kopplung() -> Kopplung:
    global _kopplung
    if _kopplung is None:
        _kopplung = Kopplung()
    return _kopplung
