"""Homelab: Uptime aus Kuma, Auslastung aus Proxmox."""

from __future__ import annotations

import httpx

from src.collectors.base import Collector
from src.config import settings


class HomelabCollector(Collector):
    name = "homelab"
    category = "homelab"

    def is_configured(self) -> bool:
        return bool(settings.proxmox_url and settings.proxmox_token_id)

    async def collect(self) -> None:
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            # Selbstsigniertes Zertifikat im LAN: bewusst akzeptiert, rein interner Aufruf.
            await self._proxmox(client)

    async def _proxmox(self, client: httpx.AsyncClient) -> None:
        headers = {
            "Authorization": f"PVEAPIToken={settings.proxmox_token_id}={settings.proxmox_token_secret}"
        }
        base = settings.proxmox_url.rstrip("/")
        resp = await client.get(f"{base}/api2/json/cluster/resources", headers=headers)
        resp.raise_for_status()
        items = resp.json().get("data", [])

        guests = [i for i in items if i.get("type") in {"lxc", "qemu"}]
        running = [g for g in guests if g.get("status") == "running"]
        nodes = [i for i in items if i.get("type") == "node"]

        self.store.record(self.category, "gaeste_gesamt", float(len(guests)))
        self.store.record(self.category, "gaeste_laufend", float(len(running)))

        for node in nodes:
            name = node.get("node", "node")
            if (mem := node.get("mem")) and (maxmem := node.get("maxmem")):
                self.store.record(
                    self.category, f"{name}_ram_prozent", round(mem / maxmem * 100, 1), unit="%"
                )
            if (cpu := node.get("cpu")) is not None:
                self.store.record(
                    self.category, f"{name}_cpu_prozent", round(float(cpu) * 100, 1), unit="%"
                )

        storages = [i for i in items if i.get("type") == "storage" and i.get("maxdisk")]
        if storages:
            worst = max(storages, key=lambda s: s["disk"] / s["maxdisk"])
            self.store.record(
                self.category,
                "storage_vollster_prozent",
                round(worst["disk"] / worst["maxdisk"] * 100, 1),
                unit="%",
            )
            self.store.record(
                self.category, "storage_vollster_name", text_value=worst.get("storage", "?")
            )
