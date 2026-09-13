"""Werte fuer die Anzeige aufbereiten.

Trennt Formatierung von Datenhaltung: der Store kennt Zahlen, das Template
kennt Text. Diese Schicht uebersetzt.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from src.categories import Category, Field

# Emojis stehen in Mias Kalendertiteln ("📚 Berufsschule"). Inter hat keine
# Emoji-Glyphen, der Browser zeichnet ein leeres Ersatzkaestchen, und
# DESIGN.md verbietet sie ohnehin. Hier statt in jedem Template: durch diese
# Schicht laeuft JEDER Textwert, egal auf welcher Seite.
_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff\ufe0f\u2b00-\u2bff]+"
)


def ohne_emoji(text: str) -> str:
    """Emojis entfernen, aber nie den ganzen Text leeren."""
    return _EMOJI.sub("", text).strip() or text.strip()


def format_value(field: Field, row: dict[str, Any] | None) -> dict[str, Any]:
    """Einen Rohwert in Anzeigeform bringen."""
    if row is None:
        return {"key": field.key, "label": field.label, "display": None, "empty": True}

    value = row.get("value")
    text = row.get("text_value")
    unit = row.get("unit")

    if value is None:
        display = _relative_or_text(text)
        # Mehrere Eintraege trennt der Collector mit "|". Als Liste ausgeben,
        # damit lange Termintitel nicht in einer rechtsbuendigen Textwurst kleben.
        items = [p.strip() for p in display.split("|") if p.strip()] if "|" in display else []
        return {
            "key": field.key,
            "label": field.label,
            "display": display,
            "items": items,
            "empty": not display,
            "trend": None,
        }

    if field.trend:
        return {
            "key": field.key,
            "label": field.label,
            "display": f"{abs(value):.1f} {unit}".strip() if unit else f"{abs(value):.1f}",
            "trend": "down" if value < 0 else ("up" if value > 0 else None),
            "empty": False,
        }

    display = f"{value:g}"
    if unit:
        display = f"{display} {unit}"
    return {
        "key": field.key,
        "label": field.label,
        "display": display,
        "value": value,
        "unit": unit,
        "trend": None,
        "empty": False,
    }


def _relative_or_text(text: str | None) -> str:
    """ISO-Zeitstempel als 'vor 3 Tagen', sonst der Text selbst."""
    if not text:
        return ""
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # Kein Zeitstempel, also echter Text: hier laufen Termintitel und
        # Dienstmeldungen durch, und genau dort standen die Ersatzkaestchen.
        return ohne_emoji(text)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - dt
    days = delta.days

    if days == 0:
        return "heute"
    if days == 1:
        return "gestern"
    if days < 7:
        return f"vor {days} Tagen"
    if days < 14:
        return "letzte Woche"
    if days < 60:
        return f"vor {days // 7} Wochen"
    return dt.strftime("%d.%m.%Y")


def build_card(cat: Category, latest: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Eine Kategorie in Kartenform: Leitwert, Bildunterschrift, Details."""
    lead = format_value(cat.lead, latest.get(cat.lead.key)) if cat.lead else None
    caption = format_value(cat.caption, latest.get(cat.caption.key)) if cat.caption else None
    details = [format_value(f, latest.get(f.key)) for f in cat.details]

    # Eine nackte 0 liest sich wie ein Fehler. Sag stattdessen, was sie bedeutet.
    if lead and not lead["empty"] and lead.get("value") == 0 and cat.key == "termine":
        lead["display"] = "frei"
        lead["muted"] = True

    # Ein Leitwert ist als Zahl gedacht ("88,7 kg") und wird in 26 Pixeln
    # gesetzt, ohne Umbruch. Steht dort ein ganzer Satz wie "Homepage nicht
    # erreichbar", schiebt er die Kachel auf: gemessen 111 Pixel ueber den
    # Rand, die ganze Seite wurde seitlich scrollbar. Laengere Texte bekommen
    # deshalb die kleinere Stufe.
    if lead and not lead["empty"] and lead.get("value") is None:
        lead["lang"] = len(str(lead.get("display") or "")) > 12

    return {
        "key": cat.key,
        "title": cat.title,
        "icon": cat.icon,
        # Wohin die Kachel fuehrt. Das Frontend soll das Ziel nicht aus dem
        # Schluessel zusammenbauen muessen.
        "route": cat.route or f"/{cat.key}",
        "live": cat.live,
        "lead": lead,
        "caption": caption,
        "details": [d for d in details if not d["empty"]],
        "has_data": bool(lead and not lead["empty"]),
    }
