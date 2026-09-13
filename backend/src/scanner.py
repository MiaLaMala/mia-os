"""Aus einem Foto einen Scan machen: entzerren und Beleuchtung rausrechnen.

Der Weg, den ein abfotografiertes Blatt hier nimmt:

1. **Ecken finden.** Das Blatt liegt schief und perspektivisch verzerrt im
   Bild. Gesucht wird das groesste Viereck, das wie ein Blatt aussieht.
2. **Entzerren.** Die vier Ecken werden auf ein Rechteck gezogen, aus dem
   Trapez wird ein gerades DIN A4.
3. **Aufhellen.** Papier ist auf einem Foto nie weiss, sondern grau bis
   gelblich, mit Schattenverlauf und oft dem eigenen Schatten des Handys.

**Die Ecken-Erkennung darf scheitern und tut das auch.** Weisses Blatt auf
hellem Tisch, geknicktes Papier, schlechtes Licht: dann findet sie nichts
oder das Falsche. Deshalb gibt ``ecken_finden`` bei Zweifel ``None`` zurueck,
statt zu raten, und die Oberflaeche laesst Mia die Ecken selbst ziehen. Ein
falsch beschnittener Bescheid, bei dem das Aktenzeichen fehlt, waere
schlimmer als ein unbearbeitetes Foto.

**Aufgehellt wird in zwei Staerken.** ``weich`` teilt das Bild durch seinen
eigenen weichgezeichneten Hintergrund: Schatten verschwinden, Stempel,
Unterschriften und farbige Markierungen bleiben. ``hart`` macht daraus reines
Schwarzweiss, was bei reinem Text schaerfer aussieht, aber eine blaue
Unterschrift verschluckt. Vorgabe ist ``weich``: bei Behoerdenpost ist der
Stempel oft der Teil, auf den es ankommt.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

# Bewusst ``Any`` als Elementtyp: OpenCV gibt je nach Aufruf uint8, int32 oder
# float64 zurueck, und das steht in keiner Typdatei verlaesslich drin. Ein
# engerer Alias erzwingt nur eine Reihe von cast-Aufrufen, die nichts pruefen.
Bild = NDArray[Any]
Ecken = list[tuple[int, int]]

# Auf diese Kantenlaenge wird zum Suchen verkleinert. Die Ecken-Erkennung
# braucht keine Megapixel, und auf dem kleinen Bild ist sie zwanzigmal
# schneller. Gefunden wird auf klein, geschnitten auf gross.
SUCH_KANTE = 800

# Wie viel Blattflaeche mindestens im Bild sein muss, damit der Fund als
# Dokument durchgeht. Darunter ist es eher eine Fliese oder ein Buchruecken.
MIN_FLAECHENANTEIL = 0.18

# Und wie viel hoechstens: fuellt das gefundene Viereck fast das ganze Bild,
# hat der Kantenfinder in Wahrheit den Bildrand gefunden. Das passiert genau
# dann, wenn das Blatt selbst gar nicht erkennbar war.
MAX_FLAECHENANTEIL = 0.985


def _laden(rohdaten: bytes) -> Bild:
    daten = np.frombuffer(rohdaten, dtype=np.uint8)
    bild = cv2.imdecode(daten, cv2.IMREAD_COLOR)
    if bild is None:
        raise ValueError("Das ist kein lesbares Bild.")
    return bild


def _sortiere_ecken(punkte: NDArray[np.float32]) -> NDArray[np.float32]:
    """Vier Punkte in die Reihenfolge oben-links, oben-rechts, unten-rechts, unten-links.

    Ohne feste Reihenfolge dreht oder spiegelt die Entzerrung das Blatt,
    je nachdem, wo die Kantensuche zu laufen begonnen hat.

    Der Trick: die Summe x+y ist oben links am kleinsten und unten rechts am
    groessten, die Differenz y-x trennt die beiden anderen. Das gilt auch
    noch, wenn das Blatt deutlich gedreht liegt.
    """
    sortiert = np.zeros((4, 2), dtype=np.float32)
    summe = punkte.sum(axis=1)
    sortiert[0] = punkte[np.argmin(summe)]
    sortiert[2] = punkte[np.argmax(summe)]
    differenz = np.diff(punkte, axis=1)
    sortiert[1] = punkte[np.argmin(differenz)]
    sortiert[3] = punkte[np.argmax(differenz)]
    return sortiert


def ecken_finden(rohdaten: bytes) -> Ecken | None:
    """Die vier Ecken des Blattes im Foto. ``None``, wenn unsicher.

    Bewusst kein Rateergebnis im Zweifelsfall: lieber laesst die Oberflaeche
    Mia die Ecken ziehen, als einen Bescheid so zu beschneiden, dass das
    Aktenzeichen fehlt.
    """
    bild = _laden(rohdaten)
    hoehe, breite = bild.shape[:2]
    faktor = SUCH_KANTE / max(hoehe, breite)
    klein = cv2.resize(bild, None, fx=faktor, fy=faktor) if faktor < 1 else bild

    grau = cv2.cvtColor(klein, cv2.COLOR_BGR2GRAY)
    # Kantenerhaltend glaetten: normales Weichzeichnen frisst die Blattkante
    # gleich mit, wenn der Untergrund aehnlich hell ist.
    grau = cv2.bilateralFilter(grau, 9, 75, 75)
    kanten = cv2.Canny(grau, 40, 120)
    # Die Blattkante ist oft unterbrochen (Schatten, heller Tisch). Einmal
    # dicker machen schliesst die Luecken, sonst zerfaellt der Umriss in
    # Bruchstuecke und findConcours findet kein geschlossenes Viereck.
    kanten = cv2.dilate(kanten, np.ones((3, 3), np.uint8), iterations=1)

    umrisse, _ = cv2.findContours(kanten, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not umrisse:
        return None

    klein_flaeche = float(klein.shape[0] * klein.shape[1])
    for umriss in sorted(umrisse, key=cv2.contourArea, reverse=True)[:8]:
        umfang = cv2.arcLength(umriss, True)
        # Den Umriss auf seine Eckpunkte eindampfen. 2% des Umfangs als
        # Toleranz: weniger und jede Papierwelle wird ein eigener Eckpunkt,
        # mehr und ein Blatt wird zum Dreieck.
        genaehert = cv2.approxPolyDP(umriss, 0.02 * umfang, True)
        if len(genaehert) != 4 or not cv2.isContourConvex(genaehert):
            continue

        anteil = cv2.contourArea(genaehert) / klein_flaeche
        if not MIN_FLAECHENANTEIL < anteil < MAX_FLAECHENANTEIL:
            continue

        ecken = _sortiere_ecken(genaehert.reshape(4, 2).astype(np.float32))
        # Zurueck auf die Masse des Originals: gesucht wurde auf dem kleinen.
        ecken /= faktor if faktor < 1 else 1
        return [(int(x), int(y)) for x, y in ecken]

    return None


def _zielgroesse(ecken: NDArray[np.float32]) -> tuple[int, int]:
    """Wie gross das entzerrte Blatt wird.

    Genommen wird jeweils die laengere der beiden gegenueberliegenden Kanten.
    Die kuerzere ist die weiter entfernte, und die auf sie zu stauchen wuerde
    genau den Teil des Blattes unscharf machen, der ohnehin am schlechtesten
    zu lesen ist.
    """
    ol, orr, ur, ul = ecken
    breite = max(np.linalg.norm(orr - ol), np.linalg.norm(ur - ul))
    hoehe = max(np.linalg.norm(ul - ol), np.linalg.norm(ur - orr))
    return max(int(breite), 50), max(int(hoehe), 50)


def _einwaerts(ecken: NDArray[np.float32], anteil: float = 0.004) -> NDArray[np.float32]:
    """Die Ecken ein wenig zur Mitte ziehen.

    Ein Schnitt exakt auf der erkannten Kante nimmt einen dunklen Streifen
    Tischplatte mit: am Bild sichtbar als schwarzer Rand links. Die Kante
    sitzt nie pixelgenau, und ein Millimeter Papier weniger stoert niemanden,
    ein Rahmen aus Tischfarbe schon.
    """
    mitte = ecken.mean(axis=0)
    return mitte + (ecken - mitte) * (1 - anteil)


def entzerren(rohdaten: bytes, ecken: Ecken) -> Bild:
    """Das schiefe Viereck auf ein gerades Rechteck ziehen."""
    if len(ecken) != 4:
        raise ValueError("Es braucht genau vier Ecken.")
    bild = _laden(rohdaten)
    quelle = _einwaerts(_sortiere_ecken(np.array(ecken, dtype=np.float32)))
    breite, hoehe = _zielgroesse(quelle)
    ziel = np.array(
        [[0, 0], [breite - 1, 0], [breite - 1, hoehe - 1], [0, hoehe - 1]], dtype=np.float32
    )
    matrix = cv2.getPerspectiveTransform(quelle, ziel)
    return cv2.warpPerspective(bild, matrix, (breite, hoehe))


def aufhellen(bild: Bild, staerke: str = "weich") -> Bild:
    """Beleuchtung rausrechnen, damit Papier weiss wird statt grau.

    Der Kern ist eine Division durch den eigenen Hintergrund: ein Bild, in
    dem nur noch der Helligkeitsverlauf steckt und keine Schrift mehr. Teilt
    man das Original dadurch, bleibt die Schrift und der Verlauf verschwindet.
    Das faengt auch den eigenen Schatten des Handys ab, an dem eine feste
    Helligkeitsschwelle scheitert.

    **Der Hintergrund wird per Median geschaetzt, nicht per Weichzeichner.**
    Am ersten Wurf sichtbar: ein Gauss-Kern zieht die harte Schattenkante zu
    einem Verlauf auseinander, und uebrig bleiben graue Schlieren genau dort,
    wo der Schatten aufhoerte. Ein Medianfilter haelt Kanten, und die
    Schattenkante ist genau eine. Der Median ignoriert ausserdem die Schrift,
    solange sein Fenster groesser ist als die Buchstaben: dunkle Pixel sind
    in der Minderheit, der Mittelwert waere von ihnen mitgezogen worden.
    """
    grau = cv2.cvtColor(bild, cv2.COLOR_BGR2GRAY)

    # Zum Schaetzen verkleinern. Ein Median mit grossem Fenster ist auf dem
    # vollen Bild quaelend langsam (Sekunden je Megapixel), auf einem
    # Achtel-Bild dagegen sofort da. Der Hintergrund ist per Definition
    # grobkoernig, ihm fehlt beim Verkleinern nichts.
    hoehe, breite = grau.shape
    faktor = max(1, min(hoehe, breite) // 400)
    klein = grau[::faktor, ::faktor] if faktor > 1 else grau

    # Fenster deutlich groesser als die Schrift, sonst wird die Schrift
    # selbst Teil des Hintergrunds und loest sich mit auf.
    fenster = max(11, (min(klein.shape) // 8) | 1)
    hintergrund_klein = cv2.medianBlur(klein, fenster)
    hintergrund = cv2.resize(hintergrund_klein, (breite, hoehe), interpolation=cv2.INTER_LINEAR)

    geteilt = cv2.divide(grau, hintergrund, scale=255)

    if staerke == "hart":
        # Reines Schwarzweiss. Schaerfer bei reinem Text, verschluckt aber
        # blaue Unterschriften und Stempel.
        return cv2.adaptiveThreshold(
            geteilt, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 10
        )

    # Weich: Kontrast spreizen, Graustufen behalten. Die Grenzen 2% und 98%
    # statt Minimum und Maximum, damit ein einzelnes dunkles Staubkorn nicht
    # die ganze Spreizung bestimmt.
    unten, oben = np.percentile(geteilt, (2, 98))
    if oben - unten < 10:
        return geteilt
    gespreizt = np.clip((geteilt.astype(np.float32) - unten) * 255 / (oben - unten), 0, 255)

    # Papier endgueltig weiss machen. Nach der Division liegt der Hintergrund
    # bei etwa 245 mit leichtem Rauschen, und dieses Rauschen ist genau das,
    # was als Schlieren zu sehen war. Alles ab 232 wird glatt weiss, der Rest
    # bleibt unangetastet: Graustufen an den Buchstabenraendern sind das, was
    # den Text weich statt ausgefranst aussehen laesst.
    gespreizt[gespreizt > 232] = 255
    fertig: Bild = gespreizt.astype(np.uint8)
    return fertig


def als_jpeg(bild: Bild, qualitaet: int = 88) -> bytes:
    """Fertig fuer die Ablage. JPEG, weil PNG bei Scans ein Vielfaches wiegt."""
    erfolg, gepuffert = cv2.imencode(".jpg", bild, [cv2.IMWRITE_JPEG_QUALITY, qualitaet])
    if not erfolg:
        raise ValueError("Bild liess sich nicht speichern.")
    return bytes(gepuffert.tobytes())


def ecken_aus_text(text: str) -> Ecken | None:
    """Ecken aus dem Formularfeld lesen: ``"x,y x,y x,y x,y"``.

    Kommt aus der Adresszeile beziehungsweise dem Formular, wird also nie
    ungeprueft geglaubt. Bei allem, was nicht genau vier Zahlenpaare sind,
    gibt es ``None`` und die Automatik uebernimmt: eine halb gelesene
    Eckenliste wuerde das Blatt an einer zufaelligen Stelle zerschneiden.
    """
    if not text.strip():
        return None
    try:
        paare = [p for p in text.replace(";", " ").split() if p]
        ecken = [(int(float(p.split(",")[0])), int(float(p.split(",")[1]))) for p in paare]
    except (ValueError, IndexError):
        return None
    return ecken if len(ecken) == 4 else None


# Wie gross die Vorschau hoechstens wird. Sie geht als base64 durch JSON und
# waechst dabei um ein Drittel: ein 12-Megapixel-Foto waere ein Vielfaches
# dessen, was ein Handybildschirm zeigen kann.
VORSCHAU_KANTE = 1400


def vorschau(
    rohdaten: bytes, ecken: Ecken | None = None, staerke: str = "weich"
) -> tuple[bytes, bool, tuple[int, int]]:
    """Aufbereiten und verkleinert zurueckgeben, ohne etwas zu speichern.

    Gibt zusaetzlich die Groesse des **Originals** zurueck. Die braucht die
    Oberflaeche, um die gezogenen Eckpunkte vom angezeigten Bild auf das
    Original umzurechnen: sonst landen die Ecken um den Verkleinerungsfaktor
    verschoben, und der Schnitt sitzt schief.
    """
    original = _laden(rohdaten)
    hoehe, breite = original.shape[:2]

    gefunden = ecken is not None
    if ecken is None:
        ecken = ecken_finden(rohdaten)
        gefunden = ecken is not None

    bild = entzerren(rohdaten, ecken) if ecken else original
    bild = aufhellen(bild, staerke)

    # Verkleinern erst nach dem Aufhellen: die Hintergrundschaetzung arbeitet
    # sonst auf weniger Bildpunkten und wird ungenauer.
    laengste = max(bild.shape[:2])
    if laengste > VORSCHAU_KANTE:
        faktor = VORSCHAU_KANTE / laengste
        bild = cv2.resize(bild, None, fx=faktor, fy=faktor, interpolation=cv2.INTER_AREA)

    return als_jpeg(bild, qualitaet=78), gefunden, (breite, hoehe)


def verarbeiten(
    rohdaten: bytes, ecken: Ecken | None = None, staerke: str = "weich"
) -> tuple[bytes, bool]:
    """Der ganze Weg: Ecken, entzerren, aufhellen, als JPEG.

    Gibt zusaetzlich zurueck, ob die Ecken automatisch gefunden wurden. Die
    Oberflaeche zeigt bei ``False`` das ungeschnittene Bild mit dem Hinweis,
    die Ecken selbst zu setzen.
    """
    gefunden = ecken is not None
    if ecken is None:
        ecken = ecken_finden(rohdaten)
        gefunden = ecken is not None

    bild = entzerren(rohdaten, ecken) if ecken else _laden(rohdaten)
    return als_jpeg(aufhellen(bild, staerke)), gefunden
