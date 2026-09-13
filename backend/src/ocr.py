"""OCR: aus einem gescannten Bild den Text lesen, damit man ihn suchen kann.

Der Anlass ist eine Lücke, die man erst beim Suchen merkt. Der Index kennt
Dateinamen, sonst nichts. Ein abfotografierter Bescheid heißt ``2026-09-03
Meldebescheinigung.jpg`` und ist damit unter genau diesem Wort auffindbar,
aber das Aktenzeichen, der Absender und der Betrag stehen nur im Bild. Wer
"43-044" sucht, findet nichts.

**Der Text wird ausschließlich für selbst gescannte Belege gespeichert, nie
für den Bestand.** Das ist keine technische Vorsichtsmaßnahme, sondern die
Zusage an die Nutzerin: in ihren Ordnern liegen Ausweise, Geburtsurkunden
und medizinische Unterlagen Dritter. Der Index enthält bis heute Name, Pfad, Größe und Datum, und
das bleibt so. Wer ein Blatt selbst durch den Scanner schickt, hat es dagegen
in der Hand und weiß, was drauf steht. Durchgesetzt wird die Grenze nicht
hier, sondern beim Schreiben in ``Store.set_document_text``: eine Regel, an
der sich ein künftiger Aufrufer vorbeimogeln kann, ist keine.

**Tesseract läuft als eigener Prozess, nicht als Bibliothek.** Es gibt
Python-Bindungen, aber sie bringen die Bibliothek als Wheel mit, und dann
hängt die Sprachdatei an einer anderen Stelle als die des Systems. Der
Aufruf über ``stdin``/``stdout`` braucht keine Zwischendatei: ein Bescheid
soll nicht als Datei in ``/tmp`` liegen bleiben, wenn der Prozess abstürzt.

**Gemessen statt geschätzt** (09.09.2026, gestelltes Behördenschreiben,
1654x2339, als Handyfoto verzerrt mit Schattenkante):

| Eingabe                | psm 3  | psm 6  |
|------------------------|--------|--------|
| Foto direkt            | 62,9 % | 84,3 % |
| durch den Scanner      | 96,6 % | 97,8 % |

Deshalb läuft OCR **hinter** dem Scanner und nicht auf dem Rohfoto: das
Entzerren und Aufhellen ist der größte einzelne Gewinn, größer als jede
Tesseract-Einstellung. Und deshalb ``--psm 6``: bei einem entzerrten Blatt
mit einer Textspalte gewinnt "ein zusammenhängender Block" gegen die
automatische Layout-Analyse, die aus Absätzen gern Spalten macht.

**Gelesen wird das TSV-Format, nicht der fertige Text**, weil dort je Wort
eine Konfidenz danebensteht. Am gerenderten Beleg gemessen: die Zeile, die
Tesseract aus der Schattenkante des Handys gemacht hat, kam auf 22 von 100,
während jede echte Textzeile über 82 lag. Kein anderes Merkmal trennt das
sauber: nach Wortlänge sieht "Meldebescheinigung nach § 18 Abs. 1 BMG"
genauso aus wie "| a kia. a See SS en, Bie orn".
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from collections import defaultdict

from src.config import settings

log = logging.getLogger(__name__)


# Wie viel Text höchstens gespeichert wird. Ein dichtes A4-Blatt hat rund
# 3000 Zeichen, ein mehrseitiges PDF käme darüber. Der Deckel schützt die
# Datenbank davor, dass ein Fehlgriff ein ganzes Buch hineinschreibt.
MAX_ZEICHEN = 20000

# Ab welcher mittleren Konfidenz eine Zeile als gelesen gilt.
#
# Gemessen am Beleg vom 09.09.2026: Schattenkante 22, jede echte Zeile über
# 82. Die Grenze liegt bewusst bei 60 und damit näher am Müll: eine echte
# Zeile wegzuwerfen ist der teurere Fehler. Wer nach einem Aktenzeichen sucht,
# das der Filter entfernt hat, findet nichts und weiß nicht warum.
MIN_KONFIDENZ = 60.0


def _umgebung() -> dict[str, str]:
    """Wo Tesseract seine Sprachdateien und Bibliotheken findet.

    Im Container liegt beides an den Standardstellen, dort ist die Zuordnung
    leer und wird nicht gesetzt. Auf dem Entwicklungsrechner liegt Tesseract
    entpackt ohne root im Benutzerverzeichnis und findet ohne diese beiden
    Variablen weder ``deu.traineddata`` noch ``libtesseract.so``.
    """
    umgebung = {}
    if settings.ocr_tessdata:
        umgebung["TESSDATA_PREFIX"] = settings.ocr_tessdata
    if settings.ocr_lib_path:
        umgebung["LD_LIBRARY_PATH"] = settings.ocr_lib_path
    # Tesseract greift sich sonst alle Kerne für eine einzelne Seite. Auf
    # Mias Xeon von 2012 macht das die Seite nicht schneller, blockiert aber
    # den Webserver: der Container hat vier Kerne und muss nebenbei antworten.
    umgebung["OMP_THREAD_LIMIT"] = "1"
    return umgebung


def verfuegbar() -> bool:
    """Ob Tesseract überhaupt da ist.

    Wird beim Upload gefragt: fehlt es, wird der Beleg trotzdem abgelegt und
    nur der Text nicht geschrieben. Ein fehlendes OCR darf einen Bescheid
    nicht daran hindern, in Nextcloud zu landen.
    """
    pfad = settings.ocr_binary
    return bool(pfad) and (shutil.which(pfad) is not None)


# Tesseract hängt gern einen Rattenschwanz Leerzeilen und Seitenumbrüche an,
# und einzelne Buchstabenreste an den Blatträndern werden zu Zeilen mit einem
# Zeichen. Beides bläht den Index auf, ohne dass es jemand sucht.
_MEHRFACH_LEER = re.compile(r"\n{3,}")
_RAND_RESTE = re.compile(r"^[^\wÄÖÜäöüß]{1,2}$", re.MULTILINE)


def _aus_tsv(tsv: str) -> str:
    """Aus der TSV-Ausgabe die Zeilen bauen, die Tesseract selbst zutraut.

    Je Wort stehen dort Blockzeichen, die Konfidenz und der Text. Gruppiert
    wird über ``(block, absatz, zeile)``: das ist Tesseracts eigene
    Zeilenaufteilung, und die Konfidenz einer ganzen Zeile sagt mehr als die
    eines einzelnen Wortes. Ein einzelnes schlecht gelesenes Wort mitten im
    Text ist normal, eine Zeile aus lauter solchen Wörtern ist die
    Schattenkante.

    Ist die Ausgabe nicht wie erwartet aufgebaut, gibt es einen leeren String
    und der Aufrufer nimmt den Klartext. Lieber ungefilterter Text als gar
    keiner: der Filter ist Komfort, das Lesen ist der Zweck.
    """
    zeilen: dict[tuple[str, str, str], list[tuple[float, str]]] = defaultdict(list)
    reihenfolge: list[tuple[str, str, str]] = []

    for roh in tsv.splitlines()[1:]:  # erste Zeile sind die Spaltennamen
        felder = roh.split("\t")
        if len(felder) < 12:
            continue
        wort = felder[11].strip()
        if not wort:
            continue
        try:
            konfidenz = float(felder[10])
        except ValueError:
            continue
        schluessel = (felder[2], felder[3], felder[4])
        if schluessel not in zeilen:
            reihenfolge.append(schluessel)
        zeilen[schluessel].append((konfidenz, wort))

    ausgabe = []
    for schluessel in reihenfolge:
        woerter = zeilen[schluessel]
        mittel = sum(k for k, _ in woerter) / len(woerter)
        if mittel < MIN_KONFIDENZ:
            log.debug("OCR: Zeile mit Konfidenz %.1f verworfen", mittel)
            continue
        ausgabe.append(" ".join(w for _, w in woerter))
    return "\n".join(ausgabe)


def aufraeumen(text: str) -> str:
    """Den Rohtext auf das reduzieren, wonach jemand suchen würde."""
    text = text.replace("\x0c", "\n")
    # Zeilenweise die Ränder abschneiden: Tesseract setzt gern ein Leerzeichen
    # vor jede Zeile, und ein Suchtreffer auf " Aktenzeichen" wäre derselbe.
    text = "\n".join(zeile.strip() for zeile in text.splitlines())
    text = _RAND_RESTE.sub("", text)
    text = _MEHRFACH_LEER.sub("\n\n", text)
    return text.strip()[:MAX_ZEICHEN]


async def _tesseract(bild: bytes, ausgabe: str, sprache: str = "") -> bytes | None:
    """Tesseract laufen lassen und seine Ausgabe zurückgeben. ``None`` bei Fehler.

    Gemeinsamer Unterbau für beide Verwendungen: ``tsv`` für den Text, der in
    die Datenbank geht, und ``pdf`` für die Datei, die in Nextcloud landet.
    Beide brauchen dieselbe Behandlung von Zeitgrenze, Absturz und fehlendem
    Programm, und die stand vorher nur einmal da.

    **Wirft nicht.** Der Aufrufer legt gerade einen Beleg ab, und ein
    hängender Tesseract darf diesen Vorgang nicht mitreißen. Alles Unerwartete
    landet im Log und führt zu ``None``.

    Die Zeitgrenze ist kein Luxus. Tesseract braucht auf einem A4-Scan gut
    eine Sekunde, aber auf einem Bild mit sehr viel feiner Struktur (ein
    fotografierter Zeitungsstapel) kann die Layout-Analyse minutenlang
    laufen, und der Upload würde so lange offen stehen.
    """
    if not verfuegbar():
        return None

    befehl = [
        settings.ocr_binary,
        "stdin",
        "stdout",
        "-l",
        sprache or settings.ocr_sprache,
        "--psm",
        "6",
        ausgabe,
    ]
    try:
        prozess = await asyncio.create_subprocess_exec(
            *befehl,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_umgebung(),
        )
    except (OSError, ValueError):
        log.warning("OCR: %s liess sich nicht starten", settings.ocr_binary)
        return None

    try:
        aus, fehler = await asyncio.wait_for(
            prozess.communicate(input=bild), timeout=settings.ocr_timeout
        )
    except TimeoutError:
        # Erst freundlich, dann bestimmt. Ein Tesseract, der die Zeitgrenze
        # reisst, haengt in der Layout-Analyse und reagiert dort auf TERM;
        # bleibt er trotzdem stehen, wuerde ``wait()`` ewig warten und der
        # Upload mit ihm.
        prozess.terminate()
        try:
            await asyncio.wait_for(prozess.wait(), timeout=5)
        except TimeoutError:
            prozess.kill()
            await prozess.wait()
        log.warning("OCR: Zeitgrenze von %ss ueberschritten", settings.ocr_timeout)
        return None

    if prozess.returncode != 0:
        log.warning("OCR fehlgeschlagen (%s): %s", prozess.returncode, fehler.decode()[:200])
        return None

    return aus


async def text_lesen(bild: bytes, sprache: str = "") -> str:
    """Den Text aus einem Bild lesen. Leerer String, wenn nichts geht.

    Gelesen wird ``tsv``: nur dort steht je Wort eine Konfidenz, und die ist
    das einzige verlässliche Merkmal gegen Kauderwelsch-Zeilen.
    """
    aus = await _tesseract(bild, "tsv", sprache)
    if aus is None:
        return ""

    roh = aus.decode("utf-8", "replace")
    gefiltert = _aus_tsv(roh)
    # Kein einziger Fund heisst entweder leeres Blatt oder unerwartetes Format.
    # Im zweiten Fall waere ein leeres Ergebnis der schlechtere Ausgang: der
    # Filter ist Komfort, das Lesen der Zweck.
    return aufraeumen(gefiltert or roh)


async def als_pdf(bild: bytes, sprache: str = "") -> bytes | None:
    """Aus dem gescannten Bild ein durchsuchbares PDF machen. ``None`` bei Fehler.

    Tesseract legt das Bild als Seite an und schreibt den erkannten Text als
    **unsichtbare Ebene** darunter (``GlyphLessFont``). Das Ergebnis sieht aus
    wie der Scan, lässt sich aber im PDF-Betrachter mit Strg+F durchsuchen und
    kopieren.

    Gemessen am Beleg vom 09.09.2026: 142 KB gegenüber 137 KB als JPEG, also
    gut 3 % mehr für ein Format, das sich überall öffnen, drucken und
    weiterleiten lässt. Und es kostet keinen zweiten Durchgang, weil Tesseract
    ohnehin schon liest.

    **Der Konfidenzfilter greift hier nicht.** Tesseract schreibt die
    Textebene selbst, inklusive der Zeilen, die es aus einer Schattenkante
    gemacht hat. Das stört nicht: die Ebene ist unsichtbar, und in die
    Datenbank geht weiterhin nur der gefilterte Text aus ``text_lesen``.
    """
    aus = await _tesseract(bild, "pdf", sprache)
    if aus is None:
        return None
    # Ein PDF, das nicht mit %PDF anfaengt, ist keins. Lieber das Bild ablegen
    # als eine kaputte Datei, die sich nirgends oeffnen laesst.
    if not aus.startswith(b"%PDF"):
        log.warning("OCR: Ausgabe ist kein PDF (%d Bytes)", len(aus))
        return None
    return aus
