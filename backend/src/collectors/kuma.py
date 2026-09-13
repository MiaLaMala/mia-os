"""Uptime Kuma: Status und Verfuegbarkeit der ueberwachten Dienste.

Warum ueber SSH und nicht ueber die API: Kumas ``/metrics`` verlangt einen
API-Key, und **sobald der erste Key existiert, ist die Basic-Authentifizierung
fuer diesen Endpunkt dauerhaft abgeschaltet** (steht so im Kuma-Wiki). Das ist
eine Einbahnstrasse an einem laufenden Dienst, den Mia selbst betreibt. Die
Badge-Endpunkte wiederum liefern nur ``N/A``, solange die Monitore keiner
oeffentlichen Statusseite zugeordnet sind.

Also der Weg, der nichts veraendert: die Kuma-Datenbank **nur lesend**
abfragen. Ein eigener SSH-Schluessel, ein festes Kommando, keine Schreibrechte.

Gelesen werden ausschliesslich Dienstnamen, Status und Zeiten. Keine
Zugangsdaten, keine Benachrichtigungseinstellungen.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from src.collectors.base import Collector
from src.config import settings

# Eine Abfrage, ein JSON-Ergebnis. Mehrere Aufrufe ueber zwei SSH-Ebenen sind
# zu langsam und brechen leichter.
ABFRAGE = """
SELECT json_group_array(json_object(
  'name', m.name,
  'status', COALESCE(h.status, 2),
  'msg', COALESCE(h.msg, ''),
  'ping', COALESCE(h.ping, 0),
  'seit', COALESCE(h.time, ''),
  'uptime24', COALESCE((
    SELECT ROUND(100.0*SUM(s.up)/NULLIF(SUM(s.up)+SUM(s.down),0), 2)
    FROM stat_hourly s
    WHERE s.monitor_id = m.id AND s.timestamp > strftime('%s','now','-1 day')
  ), -1),
  'uptime30', COALESCE((
    SELECT ROUND(100.0*SUM(s.up)/NULLIF(SUM(s.up)+SUM(s.down),0), 2)
    FROM stat_daily s
    WHERE s.monitor_id = m.id AND s.timestamp > strftime('%s','now','-30 day')
  ), -1)
))
FROM monitor m
LEFT JOIN heartbeat h ON h.id = (
  SELECT id FROM heartbeat WHERE monitor_id = m.id ORDER BY time DESC LIMIT 1
)
WHERE m.active = 1
ORDER BY m.name;
"""

# Kuma-Status: 0 unten, 1 oben, 2 in Arbeit, 3 Wartung.
OBEN, UNTEN, WARTUNG = 1, 0, 3


class KumaCollector(Collector):
    """Liest den Zustand aller Monitore."""

    name = "kuma"
    category = "homelab"

    def is_configured(self) -> bool:
        return bool(settings.kuma_ssh_host and settings.kuma_container)

    async def collect(self) -> None:
        dienste = await self._abfragen()
        if not dienste:
            raise RuntimeError("Kuma lieferte keine Monitore")

        self.store.replace_services(dienste)

        unten = [d for d in dienste if d["status"] == UNTEN]
        wartung = [d for d in dienste if d["status"] == WARTUNG]
        gemessen = [d for d in dienste if d["uptime24"] >= 0]

        self.store.record(self.category, "dienste_gesamt", float(len(dienste)))
        self.store.record(self.category, "dienste_unten", float(len(unten)))

        if gemessen:
            mittel = sum(d["uptime24"] for d in gemessen) / len(gemessen)
            self.store.record(self.category, "uptime_24h", round(mittel, 2), unit="%")

        antwortzeiten = [d["ping"] for d in dienste if d["ping"] > 0]
        if antwortzeiten:
            self.store.record(
                self.category,
                "antwortzeit_ms",
                round(sum(antwortzeiten) / len(antwortzeiten)),
                unit="ms",
            )

        # Klartext fuer die Kachel: was gerade nicht laeuft, ist die Aussage.
        if unten:
            namen = ", ".join(d["name"] for d in unten[:3])
            rest = f" und {len(unten) - 3} weitere" if len(unten) > 3 else ""
            lage = f"{namen}{rest} nicht erreichbar"
        elif wartung:
            lage = f"{len(wartung)} in Wartung, sonst alles oben"
        else:
            lage = "alle erreichbar"
        self.store.record(self.category, "dienste_lage", text_value=lage)

    async def _abfragen(self) -> list[dict[str, Any]]:
        """Die Kuma-Datenbank ueber SSH lesen.

        Geschickt wird **nur** das SQL. Was damit passiert, steht auf dem
        Proxmox-Host in ``authorized_keys`` fest verdrahtet:

            command="pct exec 125 -- docker exec uptime-kuma
                     sqlite3 -readonly /app/data/kuma.db \"$SSH_ORIGINAL_COMMAND\""

        Damit kann dieser Schluessel nichts anderes tun als lesen, selbst wenn
        der Container uebernommen wuerde. ``-readonly`` ist die zweite
        Sicherung: ein DELETE scheitert mit "attempt to write a readonly
        database".
        """
        sql = " ".join(ABFRAGE.split())

        prozess = await asyncio.create_subprocess_exec(
            "ssh",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            # Kein -i: Schluessel und HostName stehen in der ssh/config des
            # Images unter dem Alias "pve". Der blosse Name wuerde sonst ueber
            # die Suchdomain auf den Reverse Proxy zeigen.
            settings.kuma_ssh_host,
            sql,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            aus, fehler = await asyncio.wait_for(prozess.communicate(), timeout=45)
        except TimeoutError as exc:
            prozess.kill()
            await prozess.wait()
            raise RuntimeError("Kuma-Abfrage dauerte zu lange") from exc

        if prozess.returncode != 0:
            raise RuntimeError(f"Kuma nicht lesbar: {fehler.decode()[:200]}")

        roh = aus.decode().strip()
        if not roh:
            return []
        daten: list[dict[str, Any]] = json.loads(roh)
        return daten
