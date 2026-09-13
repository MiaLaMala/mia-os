"""Die Torwache vor der Schnittstelle.

Sitzt als Middleware vor allem, was unter ``/api`` liegt, und beantwortet
genau eine Frage: darf diese Anfrage herein.

**Drei Antworten sind moeglich.**

*Offen.* ``/health`` fuer Uptime Kuma, die Kopplung selbst, und alles, was
kein ``/api`` ist (die Oberflaeche, die statischen Dateien). Die Oberflaeche
auszuliefern verraet nichts: sie ist leer, bis sie Daten bekommt, und die
kommen durch dieses Tor.

*Aus dem Heimnetz.* Wer aus 172.16.0.0/16 oder dem Jana-Netz kommt, darf
alles. Das ist die Grenze, die vorher schon galt, hier nur ausgesprochen.

*Mit Schluessel.* ``Authorization: Bearer <schluessel>``. So reden die Apps,
auch von unterwegs.

**Warum das Display eine Ausnahme ist.** Der ESP32 holt seine Firmware und
sein Briefing ueber den Pi, und damit aus 10.42.7.0/24: er faellt unter das
Heimnetz und braucht keinen eigenen Schluessel. Ein Schluessel im Flash eines
Geraets, das offen auf dem Schreibtisch liegt, waere ohnehin keiner.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from src.zugang import abdruck, aus_vertrautem_netz

log = logging.getLogger(__name__)

# Pfade, die ohne jeden Nachweis antworten.
#
# ``/health`` muss offen bleiben: Uptime Kuma fragt von aussen, und ein
# Monitor, der einen Schluessel braucht, ist ein Schluessel mehr im Umlauf.
# Die Antwort enthaelt nur "ok" und die Uhrzeit.
#
# Die Kopplung selbst ist der Weg herein und kann ihn nicht voraussetzen.
# Sie ist trotzdem nicht offen: ``/api/kopplung/einloesen`` verlangt einen
# Code, den nur sieht, wer schon drin ist.
OFFEN = frozenset(
    {
        "/health",
        "/api/kopplung/einloesen",
    }
)

# Betriebsauskunft: dieselbe Sperre wie die Schnittstelle.
#
# ``/health`` sagt nur "ok". ``/health/bereit`` und ``/metrics`` sagen, welche
# Quellen klemmen, wie gross die Datenbank ist und wie lange der Dienst
# laeuft. Das ist nichts Persoenliches, aber es ist eine Landkarte fuer
# jemanden, der einen Weg herein sucht, und es steht unter einem Namen, den
# das ganze Netz aufloesen kann. Uptime Kuma und Prometheus stehen im
# Heimnetz und kommen ueber die Netzpruefung herein, ohne Schluessel.
BETRIEB = frozenset(
    {
        "/health/bereit",
        "/metrics",
    }
)


def _adresse(request: Request) -> str:
    """Die echte Adresse des Anfragenden.

    Hinter dem Reverse Proxy steht in ``request.client.host`` immer NPM.
    ``X-Forwarded-For`` traegt die echte, und zwar als Kette: der erste
    Eintrag ist der urspruengliche Absender.

    *Warum das hier sicher ist und anderswo nicht:* der Header laesst sich
    faelschen, aber nur von jemandem, der den Server direkt erreicht. Genau
    das kann von aussen niemand, davor steht NPM und setzt den Header selbst
    neu. Wer den Server direkt erreicht, steht bereits im Heimnetz.
    """
    kette = request.headers.get("x-forwarded-for", "")
    if kette:
        return kette.split(",")[0].strip()
    return request.client.host if request.client else ""


def _schluessel(request: Request) -> str:
    """Den Schluessel aus dem Authorization-Header, oder leer."""
    kopf = request.headers.get("authorization", "")
    if kopf[:7].lower() == "bearer ":
        return kopf[7:].strip()
    return ""


async def torwache(request: Request, weiter: Callable[[Request], Awaitable[Response]]) -> Response:
    """Jede Anfrage einmal ansehen, bevor sie an die Route geht."""
    pfad = request.url.path

    # Alles, was keine Schnittstelle ist, geht durch: die Oberflaeche, die
    # gebauten Buendel, die Symbole.
    if not pfad.startswith("/api") and pfad != "/health" and pfad not in BETRIEB:
        return await weiter(request)

    if pfad in OFFEN:
        return await weiter(request)

    # CORS-Vorabfragen beantwortet der Browser-Standard, nicht die Anwendung.
    # Sie tragen nie einen Authorization-Header, und sie aufzuhalten hiesse,
    # jede App-Anfrage schon vor der ersten Runde zu blockieren.
    if request.method == "OPTIONS":
        return await weiter(request)

    adresse = _adresse(request)
    if aus_vertrautem_netz(adresse):
        request.state.zugang = "netz"
        return await weiter(request)

    roh = _schluessel(request)
    if roh:
        from src.main import get_store

        eintrag = get_store().geraetezugang_pruefen(abdruck(roh), adresse)
        if eintrag is not None:
            request.state.zugang = "geraet"
            request.state.geraet = eintrag["name"]
            return await weiter(request)
        log.warning("Unbekannter Schluessel von %s auf %s", adresse or "?", pfad)

    return JSONResponse(
        status_code=401,
        content={"detail": "Nicht gekoppelt"},
        # Sagt der App, womit sie es versuchen soll. Ohne diesen Kopf muesste
        # sie die 401 raten.
        headers={"WWW-Authenticate": "Bearer"},
    )
