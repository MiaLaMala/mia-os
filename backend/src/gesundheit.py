"""Schreiben nach wger: Gewicht und Essen.

Die Gesundheitsseite zeigt bisher nur, was wger hat. Eintragen musste Mia
in wger selbst. Hier steht der Rueckweg: ein Gewicht, eine Mahlzeit, mit
dem Token aus der Konfiguration. Kein eigener Speicher, wger bleibt die
Quelle, der Collector liest es beim naechsten Lauf wieder ein.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx

from src.config import settings


class WgerError(Exception):
    """wger hat nicht mitgespielt. Der Text ist fuer Mia gedacht."""


def konfiguriert() -> bool:
    return bool(settings.wger_url and settings.wger_token)


def _client() -> httpx.AsyncClient:
    if not konfiguriert():
        raise WgerError("wger ist nicht eingerichtet")
    return httpx.AsyncClient(
        base_url=settings.wger_url.rstrip("/") + "/api/v2",
        headers={"Authorization": f"Token {settings.wger_token}"},
        timeout=15,
    )


async def gewicht_eintragen(kg: float, tag: date | None = None) -> dict[str, Any]:
    """Ein Gewicht fuer einen Tag. Gibt es schon eins, wird es ersetzt.

    wger erlaubt nur einen Eintrag je Tag. Ohne die Pruefung kaeme ein 400
    zurueck, und Mia saehe "konnte nicht speichern" fuer einen Tippfehler.
    """
    if not 20 <= kg <= 400:
        raise WgerError("Das ist kein Gewicht, das ich glaube")
    tag = tag or date.today()
    async with _client() as c:
        vorhanden = await c.get(
            "/weightentry/", params={"format": "json", "date": tag.isoformat(), "limit": 1}
        )
        vorhanden.raise_for_status()
        treffer = vorhanden.json().get("results") or []
        daten = {"date": tag.isoformat(), "weight": f"{kg:.2f}"}
        if treffer:
            r = await c.patch(f"/weightentry/{treffer[0]['id']}/", json=daten)
        else:
            r = await c.post("/weightentry/", json=daten)
        if r.status_code >= 400:
            raise WgerError(f"wger: {r.text[:120]}")
        return dict(r.json())


async def zutaten_suchen(begriff: str, limit: int = 12) -> list[dict[str, Any]]:
    """Zutaten aus Mias eigener wger-Instanz.

    Nur die lokal angelegten, nicht die Open-Food-Facts-Datenbank: die
    Instanz hat den Sync nicht, und die lokalen Namen sind die, die Mia
    kennt ("Skyr natur (Schaetzung)").
    """
    begriff = begriff.strip().lower()
    async with _client() as c:
        r = await c.get("/ingredient/", params={"language__in": "1,2", "limit": 500})
        r.raise_for_status()
        alle = r.json().get("results") or []
    passend = [
        {
            "id": z["id"],
            "name": z["name"],
            "kcal": int(z.get("energy") or 0),
            "protein": float(z.get("protein") or 0),
            "kh": float(z.get("carbohydrates") or 0),
            "fett": float(z.get("fat") or 0),
        }
        for z in alle
        if not begriff or begriff in str(z["name"]).lower()
    ]
    passend.sort(key=lambda z: str(z["name"]).lower())
    return passend[:limit]


async def essen_eintragen(
    zutat_id: int, gramm: float, wann: datetime | None = None
) -> dict[str, Any]:
    """Eine Mahlzeit ins Ernaehrungstagebuch.

    Haengt am ersten Ernaehrungsplan, so wie es die wger-Oberflaeche auch
    tut. Ohne Plan gibt es kein Tagebuch, dann sagen wir das.
    """
    if not 1 <= gramm <= 5000:
        raise WgerError("Menge in Gramm zwischen 1 und 5000")
    wann = wann or datetime.now()
    async with _client() as c:
        plaene = await c.get("/nutritionplan/", params={"format": "json", "limit": 1})
        plaene.raise_for_status()
        liste = plaene.json().get("results") or []
        if not liste:
            raise WgerError("In wger gibt es keinen Ernährungsplan")
        r = await c.post(
            "/nutritiondiary/",
            json={
                "plan": liste[0]["id"],
                "ingredient": zutat_id,
                "amount": f"{gramm:.2f}",
                "datetime": wann.astimezone().isoformat(timespec="seconds"),
            },
        )
        if r.status_code >= 400:
            raise WgerError(f"wger: {r.text[:120]}")
        return dict(r.json())


async def heute_gegessen() -> list[dict[str, Any]]:
    """Was heute schon im Tagebuch steht, mit Namen und Kalorien."""
    heute = date.today().isoformat()
    async with _client() as c:
        r = await c.get(
            "/nutritiondiary/",
            params={
                "format": "json",
                "datetime__date": heute,
                "limit": 100,
                "ordering": "datetime",
            },
        )
        r.raise_for_status()
        eintraege = r.json().get("results") or []
        if not eintraege:
            return []
        z = await c.get("/ingredient/", params={"language__in": "1,2", "limit": 500})
        z.raise_for_status()
        zutaten = {i["id"]: i for i in (z.json().get("results") or [])}

    ergebnis = []
    for e in eintraege:
        zutat = zutaten.get(e["ingredient"], {})
        menge = float(e.get("amount") or 0)
        ergebnis.append(
            {
                "id": e["id"],
                "name": zutat.get("name", f"Zutat {e['ingredient']}"),
                "gramm": menge,
                "kcal": round(int(zutat.get("energy") or 0) * menge / 100),
                "zeit": str(e.get("datetime", ""))[11:16],
            }
        )
    return ergebnis
