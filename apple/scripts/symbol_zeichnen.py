#!/usr/bin/env python3
"""Das App-Symbol zeichnen.

Warum gezeichnet und nicht gemalt: ein Symbol muss in 16 Pixeln noch lesbar
sein, und dafuer braucht es gerade Kanten an Pixelgrenzen, keine weichen
Verlaeufe. Ein aus einem Bildmodell erzeugtes Symbol sieht in 512 gut aus und
in der Menueleiste nach Matsch.

Das Zeichen: drei Balken abnehmender Breite, wie eine Liste, in die man von
oben nach unten hineinsieht. Das ist, was Mia OS ist: eine Sammlung, von der
oben das Wichtigste steht.

Farben nach Mias Geschmack: schwarz als Grund, ein roter Akzent, kein
Knallrot.

Aufruf:  python3 scripts/symbol_zeichnen.py
Ergebnis: MiaOS/Assets.xcassets/AppIcon.appiconset/ mit allen Groessen.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

HIER = Path(__file__).resolve().parent
ZIEL = HIER.parent / "MiaOS" / "Assets.xcassets" / "AppIcon.appiconset"
PALETTE = HIER.parents[1] / "farben.json"

# In dieser Kantenlaenge wird gezeichnet, danach wird verkleinert. Gross genug,
# dass das Verkleinern glaettet, statt Treppen zu erzeugen.
MASS = 1024


def _hex(thema: str, name: str) -> tuple[int, int, int]:
    """Eine Farbe aus farben.json holen, als RGB-Tripel.

    Die Werte standen bis zum 14.09.2026 hier fest im Code, und sie waren
    falsch: das Symbol war mit ``#d64454`` gezeichnet, der Akzent ist
    ``#f33e52``. Zwei fast gleiche Rots nebeneinander sehen nicht nach
    Absicht aus, sondern nach Fehler. Genau dagegen gibt es die eine Quelle.
    """
    daten = json.loads(PALETTE.read_text(encoding="utf-8"))
    h = str(daten[thema][name]["hex"]).lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _dunkler(farbe: tuple[int, int, int], anteil: float) -> tuple[int, int, int]:
    """Eine Farbe abdunkeln, fuer die zweite Stufe des Akzents.

    Der Balken oben braucht zwei Toene: der Punkt leuchtet, der Balken traegt.
    Waeren beide gleich hell, verschmelzen sie in 32 Pixeln zu einem Klecks.
    """
    return tuple(int(wert * anteil) for wert in farbe)  # type: ignore[return-value]


# Der Grund: die dunkle Flaeche der App, oben mit einem Hauch des Akzents.
# Beim ersten Versuch lagen beide Toene so nah beieinander, dass der Verlauf
# unsichtbar war und das Symbol wie eine schwarze Flaeche wirkte.
GRUND_UNTEN = _hex("dunkel", "grund")
GRUND_OBEN = _hex("dunkel", "akzent_hauch")
ROT_HELL = _hex("dunkel", "akzent")
ROT = _dunkler(ROT_HELL, 0.74)
WEISS = _hex("dunkel", "text")


def _verlauf(groesse: int) -> Image.Image:
    """Der Hintergrund: dunkel, oben eine Spur heller.

    Diagonal statt senkrecht: ein senkrechter Verlauf sieht auf einem Symbol
    aus wie ein Knopf, ein diagonaler wie Licht, das von einer Seite kommt.
    """
    bild = Image.new("RGB", (groesse, groesse))
    pixel = bild.load()
    assert pixel is not None
    for y in range(groesse):
        for x in range(groesse):
            # 0 unten links, 1 oben rechts.
            t = (x / groesse + (groesse - y) / groesse) / 2
            pixel[x, y] = tuple(  # type: ignore[assignment]
                int(GRUND_UNTEN[i] + (GRUND_OBEN[i] - GRUND_UNTEN[i]) * t) for i in range(3)
            )
    return bild


def _squircle(groesse: int) -> Image.Image:
    """Die Apple-Form als Maske.

    Nicht ``rounded_rectangle``: Apples Ecken sind keine Kreisboegen, sondern
    eine Superellipse. Der Unterschied faellt neben echten Symbolen im Dock
    sofort auf, einzeln betrachtet aber nicht. Genau deshalb macht man ihn
    einmal richtig.
    """
    maske = Image.new("L", (groesse, groesse), 0)
    zeichner = ImageDraw.Draw(maske)
    n = 5.0  # Exponent der Superellipse. 5 trifft Apples Form sehr nah.
    mitte = groesse / 2
    punkte = []
    schritte = 720
    for i in range(schritte):
        winkel = 2 * math.pi * i / schritte
        cos, sin = math.cos(winkel), math.sin(winkel)
        x = mitte + mitte * math.copysign(abs(cos) ** (2 / n), cos)
        y = mitte + mitte * math.copysign(abs(sin) ** (2 / n), sin)
        punkte.append((x, y))
    zeichner.polygon(punkte, fill=255)
    return maske


def zeichnen(einfach: bool = False) -> Image.Image:
    """Das Symbol in voller Groesse, mit Alphakanal.

    ``einfach`` zeichnet die Fassung fuer kleine Groessen: nur die drei
    Balken, dicker, ohne Punkte davor. Begruendung steht bei ``KLEIN_AB``.
    """
    bild = _verlauf(MASS).convert("RGBA")
    zeichner = ImageDraw.Draw(bild)

    # Drei Zeilen, jede mit Punkt und Balken. Die Breiten nehmen ab, die
    # Abstaende bleiben gleich: so liest es sich als Liste und nicht als
    # Diagramm.
    #
    # Die ganze Gruppe wird aus ihren echten Massen zentriert, statt die
    # Startkante zu raten. Beim ersten Versuch stand sie oben links und unten
    # klaffte Luft: das faellt einzeln kaum auf und im Dock zwischen anderen
    # Symbolen sofort.
    #
    # In der einfachen Fassung sind die Balken dicker und stehen weiter
    # auseinander: bei 16 Pixeln entscheidet das Verhaeltnis von Strich zu
    # Luft darueber, ob man drei Zeilen sieht oder einen Klecks.
    hoehe = int(MASS * (0.150 if einfach else 0.105))
    ecke = hoehe // 2
    luft = int(MASS * (0.115 if einfach else 0.090))
    breiten = (0.560, 0.420, 0.280) if einfach else (0.500, 0.375, 0.250)

    punkt_r = int(hoehe * 0.29)
    # Abstand zwischen Punktmitte und Balkenanfang.
    spalte = int(hoehe * 0.95)

    gruppe_h = 3 * hoehe + 2 * luft
    # Nach der MITTLEREN Breite zentrieren, nicht nach der breitesten. Die
    # Zeilen werden nach unten kuerzer, das Gewicht liegt also links: richtet
    # man am breitesten Balken aus, sieht die Gruppe trotz korrekter Rechnung
    # nach links gerutscht aus.
    mittlere = sum(breiten) / len(breiten)
    if einfach:
        gruppe_b = int(MASS * mittlere)
        links_balken = (MASS - gruppe_b) // 2
        links_punkt = 0
    else:
        gruppe_b = punkt_r * 2 + spalte + int(MASS * mittlere)
        links_punkt = (MASS - gruppe_b) // 2 + punkt_r
        links_balken = links_punkt + spalte
    oben = (MASS - gruppe_h) // 2

    for nr, anteil in enumerate(breiten):
        y = oben + nr * (hoehe + luft)
        mitte_y = y + hoehe // 2

        # Ein Punkt vor JEDER Zeile, nicht nur vor der ersten. Einer allein
        # sieht aus wie ein Versehen; drei sind erkennbar die Statuspunkte
        # aus der App selbst.
        #
        # Nur der oberste ist gefuellt: das ist die Zeile, die dran ist.
        # Dieselbe Sprache wie in der Sammlung, wo offen hohl und fertig
        # gefuellt ist.
        if not einfach:
            punkt = [
                links_punkt - punkt_r,
                mitte_y - punkt_r,
                links_punkt + punkt_r,
                mitte_y + punkt_r,
            ]
            if nr == 0:
                zeichner.ellipse(punkt, fill=ROT_HELL)
            else:
                zeichner.ellipse(punkt, outline=WEISS, width=max(2, int(punkt_r * 0.42)))

        rechts = links_balken + int(MASS * anteil)
        # Der oberste Balken traegt in der einfachen Fassung das hellere Rot:
        # bei 16 Pixeln geht der dunklere Ton im Grund unter, und dann ist
        # nicht mehr zu sehen, welche Zeile die aktive ist.
        farbe = (ROT_HELL if einfach else ROT) if nr == 0 else WEISS
        zeichner.rounded_rectangle([links_balken, y, rechts, y + hoehe], radius=ecke, fill=farbe)

    return bild


# Was Xcode braucht. iOS bekommt ein randvolles Quadrat (das System schneidet
# die Form selbst aus), macOS die fertige Squircle mit Luft am Rand: dort
# schneidet niemand, und ein randvolles Symbol waere im Dock groesser als
# alle anderen.
#
# iOS bekommt ALLE Groessen einzeln statt nur der einen 1024er.
#
# *Warum nicht das neue Einzelformat:* seit Xcode 14 reicht fuer iOS ein
# einziges 1024er Bild mit ``"platform": "ios"``. Genau dieser Eintrag laesst
# actool aber die installierten Simulator-Laufzeiten pruefen, und wenn deren
# Version nicht zum SDK passt, bricht der Bau ab mit
# ``No simulator runtime version ... available``. Auf Mias Rechner ist genau
# das der Fall (Laufzeit 26.4, SDK 26.5), und die fehlende Laufzeit laesst
# sich ohne Administratorrechte nicht nachinstallieren.
#
# Die klassische Liste kommt ohne ``platform`` aus, actool fragt dann keine
# Laufzeit und baut. Es sind mehr Zeilen, aber es baut auf jedem Rechner.
#
# Das Idiom heisst ``iphone`` bzw. ``ipad``, NICHT ``universal``: actool
# meldet sonst "has 15 unassigned children" und dazu, dass ein 60x60@2x
# Symbol fehle, obwohl es in der Liste steht. Es ordnet die Dateien dann
# keinem Platz zu, und das Ergebnis ist eine App ohne Symbol.
IOS_GROESSEN = [
    # (Kantenlaenge in Punkten, Faktoren, Idiom)
    (20, (2, 3), "iphone"),  # Mitteilungen
    (29, (2, 3), "iphone"),  # Einstellungen
    (40, (2, 3), "iphone"),  # Spotlight
    (60, (2, 3), "iphone"),  # Home-Bildschirm
    (20, (1, 2), "ipad"),
    (29, (1, 2), "ipad"),
    (40, (1, 2), "ipad"),
    (76, (2,), "ipad"),
    (83.5, (2,), "ipad"),
]

GROESSEN = [
    # (Datei, Kantenlaenge, ist_mac)
    ("mac-16.png", 16, True),
    ("mac-32.png", 32, True),
    ("mac-64.png", 64, True),
    ("mac-128.png", 128, True),
    ("mac-256.png", 256, True),
    ("mac-512.png", 512, True),
    ("mac-1024.png", 1024, True),
    ("ios-1024.png", 1024, False),
]


# Bis zu dieser Kantenlaenge wird die vereinfachte Fassung genommen.
#
# Am gerenderten Bild entschieden, nicht geschaetzt: in 16 Pixeln verschmolzen
# die drei Balken mitsamt ihren Punkten zu einem roten Streifen ueber zwei
# grauen. Die Punkte sind dort unter einem Pixel breit, und die Luft zwischen
# den Zeilen ebenfalls. Was kleiner als ein Pixel ist, wird beim Verkleinern
# zu Grau, nicht zu einem Detail.
#
# 64 als Grenze, weil dort die Punkte gerade noch zwei Pixel bekommen. Alles
# darunter bekommt drei dicke Balken ohne Punkte: weniger Zeichen, dafuer
# erkennbare.
KLEIN_AB = 64


def ablegen() -> None:
    ZIEL.mkdir(parents=True, exist_ok=True)
    gross = zeichnen()
    klein = zeichnen(einfach=True)

    # Fuer macOS: Form ausschneiden und auf 82 Prozent schrumpfen. Das ist
    # der Anteil, den Apple selbst fuer Dock-Symbole vorgibt; ohne die Luft
    # steht die App neben den anderen hervor wie ein Fremdkoerper.
    maske = _squircle(MASS)

    def mit_rand(bild: Image.Image) -> Image.Image:
        voll = bild.copy()
        voll.putalpha(maske)
        blatt = Image.new("RGBA", (MASS, MASS), (0, 0, 0, 0))
        inhalt = int(MASS * 0.82)
        rand = (MASS - inhalt) // 2
        blatt.paste(voll.resize((inhalt, inhalt), Image.Resampling.LANCZOS), (rand, rand))
        return blatt

    mit_luft = mit_rand(gross)
    mit_luft_klein = mit_rand(klein)

    def quelle_fuer(kante: int, ist_mac: bool) -> Image.Image:
        if kante <= KLEIN_AB:
            return mit_luft_klein if ist_mac else klein
        return mit_luft if ist_mac else gross

    for name, kante, ist_mac in GROESSEN:
        quelle_fuer(kante, ist_mac).resize(
            (kante, kante), Image.Resampling.LANCZOS
        ).save(ZIEL / name)

    bilder: list[dict[str, str]] = []

    # iOS: klassische Liste, jede Groesse als eigene Datei.
    for punkte, faktoren, idiom in IOS_GROESSEN:
        for faktor in faktoren:
            pixel = int(round(punkte * faktor))
            datei = f"ios-{pixel}.png"
            # Dieselbe Pixelgroesse kommt mehrfach vor (40 ist 20@2x auf dem
            # iPhone und 40@1x auf dem iPad): einmal schreiben reicht, die
            # Eintraege zeigen beide auf dieselbe Datei.
            if not (ZIEL / datei).exists():
                quelle_fuer(pixel, False).resize(
                    (pixel, pixel), Image.Resampling.LANCZOS
                ).save(ZIEL / datei)
            # Die Groesse steht in PUNKTEN, nicht in Pixeln: "60x60" mit "3x"
            # meint eine Datei von 180 Pixeln. Und "83.5" darf nicht als
            # "83.5x83.5" mit abgeschnittener Null geschrieben werden.
            text = f"{punkte:g}x{punkte:g}"
            bilder.append(
                {"idiom": idiom, "size": text, "scale": f"{faktor}x", "filename": datei}
            )
    # Der Eintrag fuer den App Store. Ohne "platform", sonst prueft actool
    # wieder die Simulator-Laufzeiten.
    bilder.append(
        {"idiom": "ios-marketing", "size": "1024x1024", "scale": "1x", "filename": "ios-1024.png"}
    )

    # macOS.
    for kante in (16, 32, 128, 256, 512):
        for faktor in (1, 2):
            datei = f"mac-{kante * faktor}.png"
            bilder.append(
                {
                    "idiom": "mac",
                    "size": f"{kante}x{kante}",
                    "scale": f"{faktor}x",
                    "filename": datei,
                }
            )

    (ZIEL / "Contents.json").write_text(
        json.dumps({"images": bilder, "info": {"author": "xcode", "version": 1}}, indent=2),
        encoding="utf-8",
    )
    print(f"{len(bilder)} Eintraege in {ZIEL}")


if __name__ == "__main__":
    ablegen()
