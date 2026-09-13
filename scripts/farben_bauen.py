#!/usr/bin/env python3
"""Erzeugt die Farbdateien fuer alle Fassungen aus farben.json.

Aufruf:
    python scripts/farben_bauen.py          schreibt und prueft
    python scripts/farben_bauen.py --pruefen  prueft nur (fuer die Gates)

Warum das Skript existiert: bis zum 13.09.2026 stand die Palette an drei
Stellen von Hand, und sie war an drei Stellen anders. DESIGN.md sagte Blau,
das Display sagte Rot, das App-Symbol ein drittes Rot. Eine einzige Quelle
und erzeugte Dateien machen das unmoeglich.

Die Kontraste werden bei jedem Lauf neu gerechnet. Faellt einer unter seinen
Wert, bricht das Skript ab. Eine Farbe zu aendern, ohne die Lesbarkeit zu
pruefen, geht damit nicht mehr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
QUELLE = WURZEL / "farben.json"

KOPF = "Erzeugt aus farben.json. Nicht von Hand aendern."


def rgb(hexwert: str) -> tuple[int, int, int]:
    h = hexwert.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def helligkeit(hexwert: str) -> float:
    """Relative Leuchtdichte nach WCAG."""

    def kanal(wert: int) -> float:
        v = wert / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = rgb(hexwert)
    return 0.2126 * kanal(r) + 0.7152 * kanal(g) + 0.0722 * kanal(b)


def kontrast(vorne: str, hinten: str) -> float:
    a, b = helligkeit(vorne), helligkeit(hinten)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def rgb565(hexwert: str) -> int:
    """Fuer das Display: 16 Bit statt 24.

    Das Display kann nur 5 Bit Rot, 6 Bit Gruen, 5 Bit Blau. Gruen bekommt
    ein Bit mehr, weil das Auge dort am feinsten unterscheidet.
    """
    r, g, b = rgb(hexwert)
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def farben(daten: dict, thema: str) -> dict[str, str]:
    """Nur die echten Farben, ohne die Kommentarzeilen."""
    return {
        name: wert["hex"]
        for name, wert in daten[thema].items()
        if isinstance(wert, dict) and "hex" in wert
    }


def pruefen(daten: dict) -> list[str]:
    """Gibt die Fehlerzeilen zurueck. Leere Liste heisst: alles gut."""
    fehler = []
    for probe in daten["pflichtkontraste"]:
        if "thema" not in probe:
            continue
        thema = probe["thema"]
        vorne = daten[thema][probe["vorne"]]["hex"]
        hinten = daten[thema][probe["hinten"]]["hex"]
        ist = kontrast(vorne, hinten)
        if ist < probe["min"]:
            fehler.append(
                f"{thema}: {probe['vorne']} auf {probe['hinten']} "
                f"ist {ist:.2f}:1, gefordert {probe['min']}:1"
            )
    return fehler


def css_schreiben(daten: dict) -> Path:
    zeilen = [f"/* {KOPF} */", "", ":root {"]
    for name, hexwert in farben(daten, "hell").items():
        zeilen.append(f"  --{name}: {hexwert};")
    zeilen += ["}", "", "@media (prefers-color-scheme: dark) {", "  :root {"]
    for name, hexwert in farben(daten, "dunkel").items():
        zeilen.append(f"    --{name}: {hexwert};")
    zeilen += ["  }", "}", ""]

    ziel = WURZEL / "frontend" / "src" / "farben.css"
    ziel.write_text("\n".join(zeilen), encoding="utf-8")
    return ziel


def swift_schreiben(daten: dict) -> Path:
    zeilen = [
        f"// {KOPF}",
        "",
        "import SwiftUI",
        "",
        "/// Die Farben von Mia OS.",
        "///",
        "/// Jede Farbe kennt ihre helle und ihre dunkle Fassung und waehlt",
        "/// selbst: `Color(light:dark:)` fragt das Farbschema erst beim",
        "/// Zeichnen ab. Ein `if colorScheme == .dark` in den Ansichten waere",
        "/// an jeder einzelnen Stelle noetig und irgendwo vergisst man es.",
        "enum Farbe {",
    ]
    hell = farben(daten, "hell")
    dunkel = farben(daten, "dunkel")
    for name in hell:
        rolle = daten["hell"][name].get("rolle", "")
        zeilen.append(f"    /// {rolle}")
        zeilen.append(
            f"    static let {name} = Color(light: \"{hell[name]}\", "
            f"dark: \"{dunkel[name]}\")"
        )
    zeilen += [
        "}",
        "",
        "extension Color {",
        "    /// Eine Farbe, die dem Systemthema folgt.",
        "    ///",
        "    /// Auf dem Mac über `NSColor(name:dynamicProvider:)`, auf iOS und",
        "    /// watchOS über `UIColor(dynamicProvider:)`. Beide fragen bei",
        "    /// jedem Zeichnen nach, also stimmt die Farbe auch, wenn das Thema",
        "    /// bei geöffneter App umgeschaltet wird.",
        "    init(light: String, dark: String) {",
        "        #if os(macOS)",
        "        self.init(nsColor: NSColor(name: nil) { erscheinung in",
        "            let dunkel = erscheinung.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua",
        "            return NSColor(mosHex: dunkel ? dark : light)",
        "        })",
        "        #else",
        "        self.init(uiColor: UIColor { merkmale in",
        "            UIColor(mosHex: merkmale.userInterfaceStyle == .dark ? dark : light)",
        "        })",
        "        #endif",
        "    }",
        "}",
        "",
        "#if os(macOS)",
        "private extension NSColor {",
        "    /// Nicht `init(hex:)`: so heisst bereits ein Initialisierer in",
        "    /// Masse.swift für Kalenderfarben. Zwei gleich benannte an",
        "    /// derselben Stelle übersetzen nicht.",
        "    convenience init(mosHex hex: String) {",
        "        let z = UInt64(hex.dropFirst(), radix: 16) ?? 0",
        "        self.init(",
        "            srgbRed: Double((z >> 16) & 0xFF) / 255,",
        "            green: Double((z >> 8) & 0xFF) / 255,",
        "            blue: Double(z & 0xFF) / 255,",
        "            alpha: 1",
        "        )",
        "    }",
        "}",
        "#else",
        "private extension UIColor {",
        "    convenience init(mosHex hex: String) {",
        "        let z = UInt64(hex.dropFirst(), radix: 16) ?? 0",
        "        self.init(",
        "            red: Double((z >> 16) & 0xFF) / 255,",
        "            green: Double((z >> 8) & 0xFF) / 255,",
        "            blue: Double(z & 0xFF) / 255,",
        "            alpha: 1",
        "        )",
        "    }",
        "}",
        "#endif",
        "",
    ]

    ziel = WURZEL / "apple" / "MiaOS" / "Bausteine" / "Farben.swift"
    ziel.write_text("\n".join(zeilen), encoding="utf-8")
    return ziel


def display_schreiben(daten: dict) -> Path:
    """Fuer jana-desktop. Liegt in einem anderen Repo, deshalb nach build/."""
    zeilen = [
        f"// {KOPF}",
        "//",
        "// Gehoert nach jana-desktop/display/src/farben.h.",
        "// Das Display kennt nur Dunkel: es steht auf dem Schreibtisch und",
        "// leuchtet, ein weisser Grund waere abends eine Zumutung.",
        "#pragma once",
        "",
    ]
    for name, hexwert in farben(daten, "dunkel").items():
        rolle = daten["dunkel"][name].get("rolle", "")
        zeilen.append(
            f"#define C_{name.upper()} 0x{rgb565(hexwert):04X}  // {hexwert}  {rolle}"
        )
    zeilen.append("")

    ziel = WURZEL / "build" / "farben.h"
    ziel.parent.mkdir(exist_ok=True)
    ziel.write_text("\n".join(zeilen), encoding="utf-8")
    return ziel


def main() -> int:
    teile = argparse.ArgumentParser(description=__doc__)
    teile.add_argument("--pruefen", action="store_true", help="nur pruefen, nichts schreiben")
    args = teile.parse_args()

    daten = json.loads(QUELLE.read_text(encoding="utf-8"))

    fehler = pruefen(daten)
    if fehler:
        print("Kontraste nicht eingehalten:", file=sys.stderr)
        for zeile in fehler:
            print(f"  {zeile}", file=sys.stderr)
        return 1

    anzahl = len([p for p in daten["pflichtkontraste"] if "thema" in p])
    print(f"Kontraste: {anzahl} geprueft, alle gut")

    if args.pruefen:
        return 0

    for ziel in (css_schreiben(daten), swift_schreiben(daten), display_schreiben(daten)):
        print(f"  geschrieben: {ziel.relative_to(WURZEL)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
