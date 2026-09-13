"""Aus dem gelesenen Text einen Dateinamen bauen. Nur Muster, kein Modell.

Ein Beleg heißt nach dem Hochladen ``2026-09-09 Widerspruch Kasse.jpg``: das
Datum kommt vom Eintrag, der Rest ist dessen Titel. Für einen Beleg, der zu
keinem Eintrag gehört, oder wenn der Eintrag anders heißt als das Blatt, ist
das zu wenig. Datum, Absender und Betreff stehen wörtlich auf dem Papier und
seit der OCR-Runde auch in der Datenbank.

**Warum ohne Sprachmodell.** Gemessen am 10.09.2026 auf Mias Hardware: das
Embedding-Modell kann nicht generieren, Qwen3 0.6B braucht 14 s und rät
falsch, Qwen3 1.7B trifft, braucht aber 62 s und gibt als Dateinamen den
ganzen Dokumenttext zurück. Der Xeon E5-2630 ist von 2012, ohne AVX2 und ohne
GPU. Feste Muster brauchen Millisekunden und antworten jedes Mal gleich.

**Vorgeschlagen, nie gesetzt.** Der Name ist ein Vorschlag im Blatt, den Mia
annimmt oder wegtippt, genau wie beim Ordner. Ein automatisch umbenannter
Beleg wäre unter dem Namen weg, unter dem Mia ihn abgelegt hat.
"""

from __future__ import annotations

import contextlib
import re
from datetime import date

MONATE = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}  # fmt: skip

_ZAHLDATUM = re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})\b")
_WORTDATUM = re.compile(r"\b(\d{1,2})\.\s*(" + "|".join(MONATE) + r")\s*(\d{4})\b", re.I)
_DATUMSLABEL = re.compile(r"\bDatum\b|^Stand:", re.I)

_ANREDE = re.compile(r"^(sehr geehrte|sehr geehrter|liebe|lieber|hallo|guten tag)", re.I)

# Tesseract macht aus ``ü`` regelmäßig ``u``: ``fur Arbeit`` statt ``für``.
# Deshalb steht neben jedem Umlaut die entschärfte Fassung.
_ABSENDER = re.compile(
    r"\b(GmbH|mbH|gGmbH|AG|KG|Sparkasse|Volksbank|Krankenkasse|"
    r"Bundesagentur f[uü]r Arbeit|Agentur f[uü]r Arbeit|Standesamt|Landesamt|Finanzamt|"
    r"Amtsgericht|Jobcenter|Hansestadt|Gemeinde|Landkreis|Berufsbildungswerk|"
    r"Gemeinschaftspraxis|Praxis|Klinik|Hochschule|Versicherung|IKK|AOK|DAK|Barmer|"
    r"B[uü]rgermeister|B[uü]rgermeisterin)\b"
)

# Die Wortkerne, an denen eine Betreffzeile hängt. Ein Kompositum-**Präfix**
# ist erlaubt (``Meldebescheinigung``, ``Teilnahmebestätigung``), ein Suffix
# nicht: sonst zählt ``Vertragsbeginn`` als Betreff, und aus einem
# Kontoauszug wurde der Dateiname "… Sparkasse Vertragsbeginn ist".
_BETREFF_WORT = re.compile(
    r"\b[\wÄÖÜäöüß]*(?:Antrag|Bescheid|Bescheinigung|Best[aä]tigung|K[uü]ndigung|"
    r"Erkl[aä]rung|Fragebogen|Mahnung|Rechnung|Widerspruch|Mitteilung|Einladung|Zusage|"
    r"Absage|Vertrag|Aufforderung|Nachweis|Anschreiben|Aufkl[aä]rung|Bericht|Anmeldung|"
    r"Abmeldung|Zeugnis|Quittung|Beitrag|[ÄA]nderung|Schweigepflichtentbindung|"
    r"Schweigepflichtsentbindung|Einwilligung)\b",
    re.I,
)

# Zeilen, die im Briefkopf stehen und in keinem Dateinamen etwas verloren haben.
_MUELL = re.compile(
    r"^(seite \d|blatt \d|www\.|tel\b|telefon|fax|e-?mail|postfach|öffnungszeiten|zimmer|"
    r"datum\b|anlage|version|stand:|ihre nachricht|ihr zeichen|ust-?id|blz\b|iban\b|bic\b|"
    r"powered by|© |konto|drittes buch|§|\$\s?\d)",
    re.I,
)

# Eine Anschrift. Steht im Adressfeld direkt über der Anrede und sieht von dort
# aus wie eine Betreffzeile.
_ANSCHRIFT = re.compile(
    r"^\d{5}\s+\w|"
    r"\b(?:stra[sß]e|str\.|weg|platz|allee|gasse|ring|damm)\s+\d|"
    r"^(?:herrn|frau|firma|an)\b",
    re.I,
)

# Die Adresse, die hinter einem Absendernamen klebt: OCR wirft Briefkopf und
# Anschriftfeld gern in eine Zeile.
_ADRESSE_AB = re.compile(
    r"\s+(?:Postfach|Stra[sß]e|Str\.|Weg|Platz|Allee|Sand|Domhof)\b|\s+\d{5}\b|"
    r"\s+[A-ZÄÖÜ][a-zäöüß]+(?:stra[sß]e|str\.|weg|platz|allee)\b"
)

# Was aus einer danebenliegenden Spalte in die Zeile gerutscht ist. Eine
# Mailadresse oder Telefonnummer mitten in einer Betreffzeile ist immer der
# Briefkopf rechts daneben, nie Teil des Betreffs.
_SPALTENREST = re.compile(r"\s+(?:\S+@\S+|Telefon|Telefax|Tel\.|Fax|T \d|F \d).*$", re.I)

# Aktenzeichen und Datum stehen in Behördenpost oft in derselben Zeile wie der
# Betreff, rechts daneben. Im Dateinamen stünde das Datum dann zweimal.
_NEBENANGABE = re.compile(
    r"\b(?:Aktenzeichen|Az\.|Gesch[aä]ftszeichen|Kundennummer|Vorgang(?:s?nummer)?)\b[:\s].*?"
    r"(?=\s[A-ZÄÖÜ][a-zäöüß]{3,}|$)",
    re.I,
)

# Ein Betreff, der auf einem Bindewort endet, ist mittendrin abgeschnitten.
_HAENGEND = re.compile(
    r"\s+(?:und|oder|der|die|das|des|dem|den|f[uü]r|mit|von|vom|im|in|zur|zum|bei|auf|"
    r"eine[rs]?|ein)$",
    re.I,
)

# Ein Datum am Rand der Zeile ist die Ortszeile, die neben den Betreff
# gerutscht ist. Mitten in der Zeile gehört es dazu und bleibt stehen: sonst
# wird aus "Ab dem 01.11.2015 muss der Wohnungsgeber" ein "Ab dem muss der".
_RANDDATUM = re.compile(
    r"^\s*(?:vom\s+)?" + _ZAHLDATUM.pattern + r"|" + _ZAHLDATUM.pattern + r"\s*$"
)

# Woran ein Fließtextsatz zu erkennen ist, der versehentlich als Betreff
# durchgeht. Ein Betreff ist ein Nominalausdruck, kein Satz mit Prädikat.
_SATZ = re.compile(
    r"\b(?:muss|müssen|wird|werden|ist|sind|war|waren|habe|haben|hat|kann|können|"
    r"soll|sollen|darf|dürfen|gilt|gelten|erhalten Sie|bitte)\b",
    re.I,
)

VERBOTEN = re.compile(r'[/\\:*?"<>|\x00-\x1f]')

# Wie viele Wörter eine Zeile ohne Betreffwort mindestens haben muss, um als
# Betreff durchzugehen. Ein Betreff ist ein Satzfragment ("Anpassung Ihrer
# Zugangsdaten für pushTAN"), eine Namens- oder Ortszeile hat zwei bis drei
# Wörter. Ohne diese Grenze wurde aus dem Adressfeld eines Briefs ohne
# Betreffzeile der Dateiname "2025-02-10 MAXEDV Beratung GmbH Boytinstraße".
MIN_WOERTER = 4


# Gedankenstriche in beiden Laengen. Sie stehen so auf dem Papier, deshalb ist
# die Aehnlichkeit zum Bindestrich hier gewollt und kein Tippfehler.
STRICHE = "-\u2013\u2014"


def _saeubern(text: str) -> str:
    text = VERBOTEN.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" .,;:|=~" + STRICHE)
    return text.strip()


def _ohne_logorest(text: str) -> str:
    """Ein einzelner verirrter Buchstabe am Ende ist ein Logo-Rest.

    Nur für den Absender. In einem Betreff wäre das falsch: aus
    ``Meldebescheinigung gemäß § 18 Absatz 1`` würde ``… Absatz``.
    """
    return re.sub(r"\s+[\w&#*]{1,2}$", "", text).strip()


# Wie viele Zeichen ``_entlogo`` höchstens wegwirft. Ein Logo wird zu drei bis
# fünf Zeichen Unsinn. Ohne die Grenze schnitt die Regel mitten in einen
# umgebrochenen Satz: aus "können. Bei der Anmeldung des neuen Wohnsitzes"
# wurde "Anmeldung des neuen Wohnsitzes" und daraus ein Dateiname.
MAX_LOGO = 12


def _entlogo(zeile: str) -> str:
    """Den OCR-Schrott vor dem ersten echten Wort abschneiden.

    Aus einem Logo wird ``ees``, ``— 8 e``, ``C d ® B)``. Geschnitten wird bis
    zum ersten echten Wort: entweder ein Wort ab vier Zeichen, das groß
    anfängt, oder eine reine Versalienabkürzung ab zwei (``IKK``, ``DAK``).
    """
    m = re.search(r"[A-ZÄÖÜ][\wÄÖÜäöüß-]{3,}|\b[A-ZÄÖÜ]{2,}\b", zeile)
    if not m or m.start() > MAX_LOGO:
        return zeile
    return zeile[m.start() :]


def datum_finden(text: str, heute: date | None = None) -> date | None:
    """Das Briefdatum, in drei Stufen.

    Die Reihenfolge ist der ganze Trick. In einer Kündigung stehen
    Vertragsbeginn, Kündigungstermin und Briefdatum nebeneinander, und nur
    eines davon gehört in den Dateinamen: ein ausdrücklich als ``Datum``
    ausgezeichnetes schlägt ein alleinstehendes, und das wiederum schlägt
    alles, was im Fließtext steht.

    Ein Briefdatum liegt nie in der Zukunft und selten mehr als zehn Jahre
    zurück. Alles andere fällt raus, ohne dass geraten wird.
    """
    heute = heute or date.today()
    grenze = date(heute.year - 10, 1, 1)

    def aus_zeile(zeile: str) -> list[date]:
        out: list[date] = []
        for m in _ZAHLDATUM.finditer(zeile):
            tag, monat, jahr = (int(g) for g in m.groups())
            with contextlib.suppress(ValueError):
                out.append(date(jahr, monat, tag))
        for m in _WORTDATUM.finditer(zeile):
            with contextlib.suppress(ValueError, KeyError):
                out.append(date(int(m.group(3)), MONATE[m.group(2).lower()], int(m.group(1))))
        return out

    beschriftet: list[date] = []
    allein: list[date] = []
    alle: list[date] = []
    for zeile in text.splitlines():
        gefunden = aus_zeile(zeile)
        if not gefunden:
            continue
        alle += gefunden
        if _DATUMSLABEL.search(zeile):
            beschriftet += gefunden
        rest = _ZAHLDATUM.sub("", _WORTDATUM.sub("", zeile)).strip(" ,.-")
        if len(rest) <= 25:
            allein += gefunden

    for stufe in (beschriftet, allein, alle):
        gueltig = [d for d in stufe if grenze <= d <= heute]
        if gueltig:
            return max(gueltig)
    return None


def absender_finden(text: str) -> str:
    """Wer den Brief geschrieben hat, aus dem Briefkopf.

    Gesucht wird nur in den ersten Zeilen. Weiter unten steht der Empfänger,
    und der ist bei Mias Post sie selbst: ``2026-08-03 Mia Grünwald
    Meldebescheinigung`` hilft in einer Ablage, die komplett ihr gehört,
    niemandem weiter.
    """
    for roh in [z.strip() for z in text.splitlines()][:25]:
        if not roh or _MUELL.match(roh):
            continue
        zeile = _entlogo(roh)
        if not _ABSENDER.search(zeile):
            continue
        zeile = _saeubern(_ADRESSE_AB.split(zeile)[0])
        zeile = _ohne_logorest(zeile)
        # Ein Absender ist ein Name, kein Satz.
        if 3 <= len(zeile) <= 45:
            return zeile
    return ""


def betreff_finden(text: str) -> str:
    """Worum es geht. Bevorzugt die Zeile über der Anrede.

    Deutsche Geschäftsbriefe setzen den Betreff nach DIN 5008 direkt über die
    Anrede, und Behördenpost hält sich fast ausnahmslos daran. Diese Stelle
    ist verlässlicher als jedes Schlüsselwort: ``Anpassung Ihrer Zugangsdaten
    für pushTAN`` enthält keines und ist trotzdem genau der Betreff.

    **Gesammelt wird über mehrere Zeilen.** Ein langer Betreff bricht um, und
    die untere Hälfte allein ergibt ``Bundesmeldegesetz (BMG)``.

    **Ohne Betreffzeile bleibt es leer.** Ein privat geschriebener Brief hat
    oft keine, und über der Anrede steht dann das Adressfeld des Empfängers.
    """
    zeilen = [z.strip() for z in text.splitlines()]

    def kuerzen(zeile: str) -> str:
        zeile = _SPALTENREST.sub("", zeile)
        zeile = _NEBENANGABE.sub("", zeile)
        zeile = _RANDDATUM.sub("", zeile)
        # Formularüberschriften hängen ihre Erläuterung mit Strich an:
        # "Erklärung zum Geschlechtseintrag - Erklärung einer volljährigen …".
        # Der erste Teil ist der Betreff, der Rest ist Kleingedrucktes.
        for trenner in (f" {s} " for s in STRICHE):
            if trenner in zeile and len(zeile.split(trenner)[0]) >= 12:
                return zeile.split(trenner)[0]
        return zeile

    def aufbereiten(zeile: str) -> str:
        return _saeubern(_HAENGEND.sub("", _saeubern(kuerzen(_entlogo(zeile)))))

    def taugt(zeile: str) -> bool:
        return (
            bool(zeile)
            and not _MUELL.match(zeile)
            and not _SATZ.search(zeile)
            and 10 <= len(zeile) <= 80
        )

    def reicht(zeile: str) -> bool:
        """Genug, um es Mia als Dateinamen anzubieten."""
        return bool(_BETREFF_WORT.search(zeile)) or len(zeile.split()) >= MIN_WOERTER

    for i, zeile in enumerate(zeilen):
        if not _ANREDE.match(zeile):
            continue
        gesammelt: list[str] = []
        for j in range(i - 1, max(i - 4, -1), -1):
            roh = zeilen[j]
            if not roh:
                if gesammelt:
                    break
                continue
            if _ANSCHRIFT.search(roh):
                break
            # Über dem Betreff steht der Briefkopf. Ohne diesen Halt wanderte
            # "Hansestadt Buxtehude Postfach 1555" in den Dateinamen, und der
            # Absender stand darin zweimal.
            if _ABSENDER.search(roh) or _ADRESSE_AB.search(roh):
                break
            fertig = aufbereiten(roh)
            if not taugt(fertig):
                break
            gesammelt.insert(0, fertig)
        zusammen = _saeubern(" ".join(gesammelt))
        if zusammen and reicht(zusammen) and len(zusammen) <= 90:
            return zusammen
        break

    # Kein Betreff über der Anrede: dann die erste Zeile mit einem Betreffwort,
    # aber nur oberhalb der Anrede. Weiter unten steht Fließtext, und der
    # enthält Wörter wie "Kündigung", ohne der Betreff zu sein.
    ende = next((i for i, z in enumerate(zeilen) if _ANREDE.match(z)), 30)
    for roh in zeilen[:ende]:
        # Eine Zeile, die klein anfängt, ist die Fortsetzung der vorherigen.
        # Mitten aus einem Absatz wird kein Betreff.
        if roh[:1].islower():
            continue
        fertig = aufbereiten(roh)
        if not _BETREFF_WORT.search(fertig):
            continue
        if taugt(fertig):
            return fertig
        # Zu lang: eine Formularüberschrift, die ohne Umbruch in ihren
        # Erklärtext übergeht ("Wohnungsgeberbestätigung Ab dem 01.11.2015
        # muss der Wohnungsgeber …"). Alles ab dem Betreffwort ist
        # Kleingedrucktes. Gekürzt wird nur hier, nicht bei Zeilen, die für
        # sich schon taugen: "Meldebescheinigung gemäß § 18 Absatz 1" ist
        # vollständig der Betreff und wäre sonst zu "Meldebescheinigung"
        # gestutzt worden.
        # Eine Formularüberschrift **beginnt** mit ihrem Titel. Steht das
        # Betreffwort weiter hinten, ist die Zeile ein Satz, und der wird nicht
        # zurechtgeschnitten: aus "Diese Bestätigung gilt für folgende
        # Personen" würde sonst der Dateiname "Diese Bestätigung".
        treffer = _BETREFF_WORT.match(fertig)
        if treffer:
            gestutzt = _saeubern(fertig[: treffer.end()])
            if gestutzt and not _MUELL.match(gestutzt):
                return gestutzt
    return ""


def vorschlagen(text: str, heute: date | None = None) -> dict[str, str]:
    """Datum, Absender und Betreff, jeweils leer wenn nicht sicher.

    Aus den drei Teilen setzt der Aufrufer den Namen zusammen. Getrennt statt
    fertig, weil das Blatt selbst weiß, welche Teile es gibt: bei einer
    Teilnahmebestätigung ohne Absender im Kopf soll der Name nicht mit einem
    Leerzeichen anfangen.
    """
    gefunden = datum_finden(text, heute)
    return {
        "datum": gefunden.isoformat() if gefunden else "",
        "absender": absender_finden(text),
        "betreff": betreff_finden(text),
    }


def name_bauen(text: str, endung: str, heute: date | None = None) -> str:
    """Der fertige Dateinamensvorschlag, oder leer.

    Leer heißt: zu wenig erkannt, um Mia etwas anzubieten. Ein Vorschlag, der
    nur aus einem Datum besteht, ist keiner, den würde sie nur wegtippen.
    """
    teile = vorschlagen(text, heute)
    if not teile["betreff"]:
        return ""
    stamm = " ".join(t for t in (teile["datum"], teile["absender"], teile["betreff"]) if t)
    return f"{stamm[:110].strip()}{endung}"
