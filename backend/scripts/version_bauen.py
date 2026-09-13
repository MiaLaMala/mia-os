"""Version und Änderungsverlauf aus der Git-Historie erzeugen.

Läuft **beim Bauen**, nicht zur Laufzeit: im fertigen Container gibt es kein
Git und keine Historie, dort liegt nur noch das Ergebnis als JSON.

Warum überhaupt automatisch: die Version stand an drei Stellen im Code und
sie widersprachen sich bereits (``pyproject.toml`` sagte 0.2.0,
``src/__init__.py`` sagte 0.1.0, ``main.py`` nochmal 0.2.0). Eine Zahl, die
von Hand gepflegt werden muss, ist eine Zahl, die irgendwann lügt.

**Die Bildungsregel:** ``MAJOR.MINOR.<Anzahl Commits>``. Major und Minor
stehen in ``pyproject.toml`` und werden von Hand gesetzt, wenn sich etwas
Grundsätzliches ändert. Der dritte Teil zählt sich selbst hoch, jeder Commit
erhöht ihn um eins. Damit ist jede gebaute Fassung eindeutig, ohne dass
irgendwer daran denken muss.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

WURZEL = Path(__file__).resolve().parents[1]
ZIEL = WURZEL / "src" / "version.json"

# Commits, die in einem Änderungsverlauf für Mia nichts verloren haben.
# Übergabenotizen, Formatierung und Testarbeit sind für mich wichtig, nicht
# für jemanden, der wissen will, was sich an der Anwendung geändert hat.
STILL = re.compile(
    r"^(HANDOFF|IDEEN|README|docs?|chore|style|test|refactor|Merge|fixup|wip)\b[:! ]",
    re.I,
)

# Woran ein Commit als Fehlerbehebung erkannt wird. Nur fürs Sortierzeichen
# in der Liste, keine Wissenschaft.
IST_FEHLER = re.compile(r"\b(fix|behoben|beheb|repariert|korrigiert|Fehler)\b", re.I)

# Commit-Nachrichten schreibe ich ohne Umlaute: sie laufen durch Terminals,
# Git-Oberflächen und Log-Ausgaben, in denen die Kodierung nicht sicher ist.
# In der Oberfläche steht dann aber "Foto anhaengen" und "verknuepft", und
# das sieht aus wie ein Fehler, obwohl es Absicht war.
#
# **Regel statt Wortliste.** Mein erster Versuch war eine Liste von Hand, und
# sie hatte nach 107 Commits schon 25 Lücken: Blaetterpfeile, Schaltflaechen,
# Ganztaegige. Eine Liste, die jemand pflegen muss, ist eine Liste, die
# irgendwann unvollständig ist.
#
# Also umgekehrt: ersetzt wird immer, außer bei den Wörtern, bei denen es
# falsch wäre. Diese Ausnahmen sind eine kurze, geschlossene Menge, während
# die Umlautwörter unbegrenzt sind. Deutsch hat wenige gängige Wörter, in
# denen "ae", "oe" oder "ue" keine Umschreibung ist: dort trifft die
# Buchstabenfolge auf eine Silbengrenze ("Dau-er", "zu-erst", "Mus-eum").
NICHT_ERSETZEN = {
    # ue an einer Silbengrenze, die die Vokalregel unten nicht erwischt:
    # dort steht vor dem "ue" ein Konsonant.
    "zuerst",
    "museum",
    "linux",
    "queue",
    "duell",
    "aktuell",
    "aktuelle",
    "aktuellen",
    "eventuell",
    "manuell",
    "manuelle",
    "visuell",
    "visueller",
    "virtuell",
    "individuell",
    "sexuell",
    "graduell",
    "prozentuell",
    # oe/ae in Fremdwörtern und Namen
    "poet",
    "koexistenz",
    "koedukation",
    "aerobic",
    "israel",
    "michael",
    "raphael",
    "maestro",
}

# Was ersetzt wird. Die Reihenfolge zählt: "ae" vor "Ae", damit die
# Großschreibung nicht durch die Kleinschreibung überschrieben wird.
_PAARE = (("ae", "ä"), ("oe", "ö"), ("ue", "ü"), ("Ae", "Ä"), ("Oe", "Ö"), ("Ue", "Ü"))

# Nach "q" ist "ue" nie ein Umlaut: Quelle, Queue, quer, Qualitaet.
# Ohne diese Regel wird aus "Quelle" ein "Qülle". Am echten Verlauf gefunden,
# dreimal in meinen eigenen Commits.
_QU = re.compile(r"([Qq])ue")

# **Nach einem Vokal ist "ue" nie ein Umlaut.** Das ist die zweite Regel, die
# eine ganze Gruppe von Wortlisten ersetzt: bauen, dauerhaft, neueste, grauer,
# feuert, blauer. Vor einem Umlaut-"ue" steht im Deutschen immer ein
# Konsonant (fuer, Gruende, bueglen); trifft es auf einen Vokal, liegt eine
# Silbengrenze dazwischen (bau-en, dau-erhaft, neu-este).
#
# Gefunden, indem die Regel gegen alle 3623 Woerter aus beiden Repo-Verlaeufen
# laufen gelassen wurde: die Wortliste hatte 14 Luecken, darunter "Bauen" ->
# "Baün", genau der Fall aus der Uebergabe. Eine Liste, die jemand pflegen
# muss, ist eine Liste mit Luecken. Eine Regel hat keine.
_VOKAL_UE = re.compile(r"([aeiouAEIOU])ue")

# "ss" nach umgeschriebenem "oe" ist fast immer ein "ß": Groesse, groesser,
# Stoesse. "Grösse" wäre schweizerisch und in Mias Oberfläche schlicht falsch.
_OESS = re.compile(r"öss")

# Ganze Wörter. Bindestrich-Zusammensetzungen werden je Teil behandelt, das
# reicht: "Scan-Pruefung" ist zweimal ein Wort.
_WORT = re.compile(r"\b[A-Za-zÄÖÜäöüß]+\b")


def _wort_lesbar(wort: str) -> str:
    if wort.lower() in NICHT_ERSETZEN:
        return wort

    # "qu" und "ue" nach einem Vokal vor der Ersetzung schützen und danach
    # zurückholen. Ein Zeichen, das in keiner Commit-Nachricht vorkommt,
    # dient als Platzhalter.
    geschuetzt = _QU.sub(lambda m: m.group(1) + "\x00", wort)
    geschuetzt = _VOKAL_UE.sub(lambda m: m.group(1) + "\x00", geschuetzt)
    for umschrieben, umlaut in _PAARE:
        geschuetzt = geschuetzt.replace(umschrieben, umlaut)
    fertig = geschuetzt.replace("\x00", "ue")

    # Groesse -> Größe, nicht Grösse.
    return _OESS.sub("öß", fertig)


def lesbar(text: str) -> str:
    """Umschriebene Umlaute in einer Commit-Nachricht zurückholen.

    ``Foto anhaengen`` wird ``Foto anhängen``, ``Dauer`` bleibt ``Dauer``.
    """
    return _WORT.sub(lambda m: _wort_lesbar(m.group(0)), text)


def _git(*argumente: str) -> str:
    return subprocess.run(
        ["git", *argumente], cwd=WURZEL, capture_output=True, text=True, check=True
    ).stdout.strip()


def _basis_version() -> str:
    """MAJOR.MINOR aus pyproject.toml. Der Rest zählt sich selbst."""
    text = (WURZEL / "pyproject.toml").read_text(encoding="utf-8")
    treffer = re.search(r'^version\s*=\s*"(\d+)\.(\d+)', text, re.M)
    return f"{treffer.group(1)}.{treffer.group(2)}" if treffer else "0.0"


def _version() -> tuple[str, int]:
    """Die Version dieses Standes und die Commit-Zahl dahinter.

    **Ein Tag auf HEAD schlägt die Rechnung.** Die CI setzt bei jedem Push auf
    main ein ``v<version>``-Tag und ist damit die Stelle, an der die Nummer
    festgelegt wird. Ohne Tag (lokaler Build, Zweig, flacher Klon) wird
    dieselbe Regel selbst gerechnet, damit ein Bauen ohne CI nicht an einer
    fehlenden Zahl scheitert. Beide Wege kommen auf dasselbe Ergebnis.
    """
    anzahl = int(_git("rev-list", "--count", "HEAD"))
    try:
        tag = _git("describe", "--tags", "--exact-match", "HEAD")
        if re.fullmatch(r"v\d+\.\d+\.\d+", tag):
            return tag.lstrip("v"), anzahl
    except subprocess.CalledProcessError:
        pass  # Kein Tag auf HEAD, das ist der Normalfall beim Entwickeln.
    return f"{_basis_version()}.{anzahl}", anzahl


def sammeln() -> dict[str, Any]:
    """Version, Commit und Änderungsverlauf aus der Historie."""
    version, anzahl = _version()

    # Trennzeichen, die in einer Commit-Nachricht nicht vorkommen. Ein
    # einfaches Zeilenweise-Lesen scheitert an mehrzeiligen Rümpfen, und
    # genau die enthalten bei mir die Begründungen.
    roh = _git("log", "--no-merges", "--date=short", "--format=%H%x1f%ad%x1f%s%x1f%b%x1e")

    eintraege = []
    for block in roh.split("\x1e"):
        if not block.strip():
            continue
        sha, datum, betreff, rumpf = (block.strip().split("\x1f") + ["", "", "", ""])[:4]
        if STILL.match(betreff):
            continue
        eintraege.append(
            {
                "sha": sha[:7],
                "datum": datum,
                "titel": lesbar(betreff),
                # Der Rumpf erklärt das Warum. Er gehört nicht in die Liste,
                # aber er soll aufklappbar sein, statt verloren zu gehen.
                "text": lesbar(rumpf.strip()),
                "art": "fix" if IST_FEHLER.search(betreff) else "neu",
            }
        )

    return {
        "version": version,
        "commit": _git("rev-parse", "--short", "HEAD"),
        "gebaut_am": _git("log", "-1", "--date=short", "--format=%ad"),
        "commits": anzahl,
        "seit": _git("log", "--reverse", "--date=short", "--format=%ad").split("\n")[0],
        "changelog": eintraege,
    }


def notizen(seit_tag: str = "") -> str:
    """Release-Notizen für alles seit dem letzten Tag, als Markdown.

    Bewusst der eigene, gefilterte Verlauf statt GitHubs automatischer Liste:
    die zählt jeden Commit auf, auch Übergabenotizen und Formatierung, und
    sie ist auf Englisch. Hier steht, was sich für Mia geändert hat.
    """
    bereich = f"{seit_tag}..HEAD" if seit_tag else "HEAD"
    try:
        roh = _git(
            "log",
            bereich,
            "--no-merges",
            "--date=short",
            "--format=%s%x1f%b%x1e",
        )
    except subprocess.CalledProcessError:
        # Der Startpunkt ist unbekannt: flacher Klon, oder ein Tag, den es
        # hier nicht gibt. Dann lieber der ganze Verlauf als ein Abbruch,
        # der den Release-Schritt mitreisst.
        roh = _git("log", "--no-merges", "--date=short", "--format=%s%x1f%b%x1e")

    neu: list[str] = []
    fixes: list[str] = []
    for block in roh.split("\x1e"):
        if not block.strip():
            continue
        betreff, rumpf = (block.strip().split("\x1f") + ["", ""])[:2]
        if STILL.match(betreff):
            continue
        titel = lesbar(betreff)
        # Die ersten Zeilen des Rumpfs bis zur Leerzeile: das ist der erste
        # Absatz und damit ein ganzer Gedanke. Nur die erste Zeile zu nehmen
        # bricht mitten im Satz ab, der ganze Rumpf wäre in einer
        # Release-Notiz zu viel. Der steht in der App zum Aufklappen.
        absatz: list[str] = []
        for zeile in lesbar(rumpf).splitlines():
            if not zeile.strip():
                if absatz:
                    break
                continue
            absatz.append(zeile.strip())
        grund = " ".join(absatz)
        zeile_md = f"- **{titel}**" + (f"  \n  {grund}" if grund else "")
        (fixes if IST_FEHLER.search(betreff) else neu).append(zeile_md)

    teile: list[str] = []
    if neu:
        teile.append("### Neu\n\n" + "\n".join(neu))
    if fixes:
        teile.append("### Behoben\n\n" + "\n".join(fixes))
    if not teile:
        teile.append("_Keine für Mia sichtbaren Änderungen._")

    return "\n\n".join(teile)


def main() -> int:
    # Zweiter Modus: nur die Release-Notizen ausgeben, für die CI.
    if len(sys.argv) > 1 and sys.argv[1] == "notizen":
        vorheriges = sys.argv[2] if len(sys.argv) > 2 else ""
        print(notizen(vorheriges))
        return 0

    try:
        daten = sammeln()
    except (subprocess.CalledProcessError, FileNotFoundError) as fehler:
        # Kein Git zur Hand: lieber eine ehrlich leere Datei als ein
        # abgebrochener Build. Die Oberflaeche zeigt dann "unbekannt".
        print(f"Keine Git-Historie ({fehler}), schreibe leere Fassung.", file=sys.stderr)
        daten: dict[str, Any] = {
            "version": f"{_basis_version()}.0",
            "commit": "",
            "gebaut_am": "",
            "commits": 0,
            "seit": "",
            "changelog": [],
        }

    ZIEL.write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{ZIEL.name}: {daten['version']} ({len(daten['changelog'])} Einträge)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
