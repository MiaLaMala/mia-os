"""Gezeichnete SVG-Icons.

Ein einziger Satz, 24px-Raster, 1.5px Strich, runde Enden. Inline gerendert,
damit sie ``currentColor`` erben und keinen zusaetzlichen Netzabruf kosten.

Keine Emojis: die brechen die Strichstaerke, sehen auf jedem System anders aus
und tragen Fremdfarbe in die Palette.
"""

from __future__ import annotations

from markupsafe import Markup

_PATHS: dict[str, str] = {
    # Herz, fuer Gesundheit
    "heart": (
        '<path d="M12 20.25s-7.5-4.4-7.5-9.6a4.35 4.35 0 0 1 7.5-3 4.35 4.35 0 0 1 7.5 3'
        'c0 5.2-7.5 9.6-7.5 9.6Z"/>'
    ),
    # Kalenderblatt, fuer Termine
    "calendar": (
        '<rect x="3.25" y="5.25" width="17.5" height="15.5" rx="2.5"/>'
        '<path d="M3.25 10.25h17.5M8 3.25v4M16 3.25v4"/>'
    ),
    # Gestapelte Einschuebe, fuer Homelab
    "server": (
        '<rect x="3.25" y="4.25" width="17.5" height="6" rx="2"/>'
        '<rect x="3.25" y="13.75" width="17.5" height="6" rx="2"/>'
        '<path d="M7 7.25h.01M7 16.75h.01"/>'
    ),
    # Aufgeschlagenes Buch, fuer Ausbildung
    "book": (
        '<path d="M12 6.5c-1.8-1.5-4.2-2.25-7.25-2.25v13.5C7.8 17.75 10.2 18.5 12 20'
        'c1.8-1.5 4.2-2.25 7.25-2.25V4.25C15.8 4.25 13.8 5 12 6.5Z"/>'
        '<path d="M12 6.5V20"/>'
    ),
    # Aktenordner, fuer Behoerden
    "folder": (
        '<path d="M3.25 7.25a2 2 0 0 1 2-2h3.4a2 2 0 0 1 1.5.7l1.1 1.3h7.5a2 2 0 0 1 2 2'
        'v7.5a2 2 0 0 1-2 2H5.25a2 2 0 0 1-2-2Z"/>'
    ),
    # Chevron, fuer das Ausklappen
    "chevron": '<path d="M8.5 10.5 12 14l3.5-3.5"/>',
    # Pfeil hoch/runter, fuer Trends
    "arrow-up": '<path d="M12 19V5M12 5l-5.5 5.5M12 5l5.5 5.5"/>',
    "arrow-down": '<path d="M12 5v14M12 19l-5.5-5.5M12 19l5.5-5.5"/>',
    # Kreisender Pfeil, fuer Aktualisieren
    "refresh": ('<path d="M20 12a8 8 0 1 1-2.35-5.65"/><path d="M20 4.5V10h-5.5"/>'),
    # Raster, fuer die Uebersicht
    "grid": (
        '<rect x="3.5" y="3.5" width="7" height="7" rx="2"/>'
        '<rect x="13.5" y="3.5" width="7" height="7" rx="2"/>'
        '<rect x="3.5" y="13.5" width="7" height="7" rx="2"/>'
        '<rect x="13.5" y="13.5" width="7" height="7" rx="2"/>'
    ),
    # Pfeil zurueck
    "back": '<path d="M15 5.5 8.5 12l6.5 6.5"/>',
    # Chevron nach rechts, fuer Listeneintraege
    "chevron-right": '<path d="M10 7.5 14.5 12 10 16.5"/>',
    # Spiegelbild, fuer das Zurueckblaettern im Kalender
    "chevron-left": '<path d="M14 7.5 9.5 12 14 16.5"/>',
    # Blatt mit Eselsohr, fuer Dokumente
    "document": (
        '<path d="M6.25 3.75h7l4.5 4.5v12a1.5 1.5 0 0 1-1.5 1.5h-10a1.5 1.5 0 0 1-1.5-1.5'
        'V5.25a1.5 1.5 0 0 1 1.5-1.5Z"/>'
        '<path d="M13.25 3.75v4.5h4.5"/>'
        '<path d="M8.75 13h6.5M8.75 16.5h4.5"/>'
    ),
    # Lupe, fuer die Suche
    "search": '<circle cx="11" cy="11" r="6.25"/><path d="M15.5 15.5 20 20"/>',
    # Externer Verweis, fuer den Sprung in den Editor
    "external": (
        '<path d="M13.75 4.25h6v6"/><path d="M19.75 4.25 11 13"/>'
        '<path d="M18 14v5.25a1.5 1.5 0 0 1-1.5 1.5h-11a1.5 1.5 0 0 1-1.5-1.5v-11'
        'a1.5 1.5 0 0 1 1.5-1.5H10"/>'
    ),
    # Schieberegler, fuer Einstellungen. Bewusst kein Zahnrad: das steht in
    # vielen Oberflaechen fuer Technik, hier geht es um Vorlieben.
    "settings": (
        '<path d="M4.5 7.5h9M17 7.5h2.5"/><circle cx="15" cy="7.5" r="2"/>'
        '<path d="M4.5 16.5h2.5M11 16.5h8.5"/><circle cx="9" cy="16.5" r="2"/>'
    ),
}


def icon(name: str, size: int = 24, cls: str = "") -> Markup:
    """SVG-Icon als sicheres Markup."""
    path = _PATHS.get(name)
    if path is None:
        return Markup("")
    classes = f"icon {cls}".strip()
    return Markup(
        f'<svg class="{classes}" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true" focusable="false">{path}</svg>'
    )


def available() -> list[str]:
    """Alle bekannten Icon-Namen."""
    return sorted(_PATHS)
