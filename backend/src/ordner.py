"""Ordnervorschlag: wohin ein frischer Beleg in Mias Ablage gehoert.

Ein Beleg landet beim Hochladen immer in ``/Dokumente/00 Belege``. Das ist
Absicht, siehe ``belege.py``: Mia OS schreibt nie in Mias gewachsene Ablage.
Nur bleibt er dann auch dort liegen. Nach zwei Monaten ist der Belegordner
eine Halde, und die Ordnerstruktur, die Mia sich gebaut hat, weiss von nichts.

Dieses Modul schlaegt vor, wo das Blatt hingehoert, und laesst Mia
entscheiden. Verschoben wird nur auf Klick.

**Gemessen statt geraten** (10.09.2026, gegen Mias echten Bestand, 161
Dokumente unter ``/Dokumente``, jedes gegen die anderen geprueft):

| Verfahren                              | richtig |
|----------------------------------------|---------|
| gegen den Ordnernamen                  | 22 %    |
| gegen den Schwerpunkt seiner Dateien   | 70 %    |
| beides gemischt                        | 65 %    |

Der Ordnername allein taugt nichts, und er verschlechtert das Ergebnis auch
noch, wenn man ihn dazumischt. Das ist kein Zufall: ``01 Persoenliches`` sagt
ueber den Inhalt weniger als die zehn Dateinamen, die darin liegen. Verglichen
wird deshalb **nur** gegen den Schwerpunkt der Dateien eines Ordners.

**Der Abstand zum zweiten Platz ist das eigentliche Signal.** Aus denselben
161 Faellen:

| Schwelle | bekommt einen Vorschlag | davon richtig |
|----------|-------------------------|---------------|
| 0,00     | 100 %                   | 70 %          |
| 0,03     |  65 %                   | 75 %          |
| **0,05** | **42 %**                | **88 %**      |
| 0,10     |  16 %                   | 85 %          |

Bei 0,05 springt die Trefferquote von 76 auf 88 %, darueber bringt strenger
sein nichts mehr. Also 0,05. In gut der Haelfte der Faelle sagt Mia OS damit
gar nichts, und das ist richtig so: ein falscher Vorschlag kostet Mia mehr als
kein Vorschlag. Sie muss ihn lesen, pruefen und ablehnen, und beim dritten
falschen klickt niemand mehr hin.

**Nur Dateinamen, kein Inhalt.** Der Index enthaelt bewusst keine Inhalte aus
dem Bestand, und daran aendert sich hier nichts. Fuer den Beleg selbst darf
der OCR-Text mitgelesen werden: Mia hat ihn selbst gescannt, und er steht
ohnehin schon in der Datenbank.

**Der Embedding-Server ist optional.** Faellt LXC 140 aus, gibt es keinen
Vorschlag und sonst passiert nichts. Ein Beleg, der abgelegt ist, ist der
Zweck; der Vorschlag ist die Zugabe.
"""

from __future__ import annotations

import array
import logging
import math
from typing import Any

import httpx

from src.config import settings

log = logging.getLogger(__name__)

# Die Aufgaben-Praefixe von EmbeddingGemma. Ohne sie fiel die Trefferquote in
# der Messung vom 09.09. von 9/9 auf 6/9: das Modell ist darauf trainiert und
# legt Frage und Fundstelle sonst in verschiedene Ecken des Raums.
PRAEFIX_DOKUMENT = "title: none | text: "
PRAEFIX_ORDNER = "task: search result | query: "

# Ab welchem Abstand zum zweitbesten Ordner der Vorschlag gezeigt wird.
# Begruendung und Messwerte stehen oben im Modulkopf.
MIN_ABSTAND = 0.05

# Wie viele Dokumente ein Ordner mindestens haben muss, um ein Ziel zu sein.
# Ein Ordner mit einer einzigen Datei hat keinen Schwerpunkt, sondern nur
# diese eine Datei, und zieht dann alles an, was ihr entfernt aehnelt.
MIN_DOKUMENTE = 3

# Wie tief ein Zielordner liegt. Mias Ablage haengt komplett unter
# ``/Dokumente``, die erste Ebene waere also eine einzige Gruppe. Zwei Ebenen
# ergeben die Sachordner ("02 Medizinisch"), drei waeren schon Vorgaenge
# (Name der dritten Person im Titel) und damit zu fein zum Raten.
EBENEN = 2

# Wie viel Text vom Dokument in das Embedding geht. Der Dateiname traegt das
# meiste, ein paar Zeilen OCR helfen. Ein ganzes Blatt verwaessert den Vektor:
# Anschrift, Fusszeile und Rechtsbehelfsbelehrung stehen auf jedem Bescheid
# und sagen nichts darueber aus, in welchen Ordner er gehoert.
MAX_TEXT = 400

# Wohin nie vorgeschlagen wird: der Belegordner selbst. Er ist der
# Ausgangspunkt, ihn vorzuschlagen hiesse "lass es, wo es ist" und waere ein
# leerer Klick. Abgeleitet statt fest hingeschrieben, sonst laeuft die Regel
# leer, sobald Mia den Ordner umbenennt.


def _nie() -> set[str]:
    ordner_ = (settings.belege_ordner or "").rstrip("/")
    return {ordner_} if ordner_ else set()


def verfuegbar() -> bool:
    """Ob ein Embedding-Server eingerichtet ist."""
    return bool(settings.embed_url)


def _norm(v: list[float]) -> list[float]:
    laenge = math.sqrt(sum(x * x for x in v))
    if not laenge:
        return v
    return [x / laenge for x in v]


def _skalar(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


def packen(v: list[float]) -> bytes:
    """Vektor als float32-Bytes. 768 Werte werden so zu 3 KB statt 15 KB JSON."""
    return array.array("f", v).tobytes()


def auspacken(b: bytes) -> list[float]:
    a = array.array("f")
    a.frombytes(b)
    return list(a)


async def einbetten(texte: list[str]) -> list[list[float]]:
    """Texte in Vektoren uebersetzen. Leere Liste, wenn der Server nicht mag.

    **Wirft nie.** Der Aufrufer steht mitten in einem Upload, der bereits
    geglueckt ist. Ein Embedding-Server, der nicht antwortet, darf den Beleg
    nicht mit sich reissen.
    """
    if not (texte and settings.embed_url):
        return []
    ziel = settings.embed_url.rstrip("/") + "/v1/embeddings"
    try:
        async with httpx.AsyncClient(timeout=settings.embed_timeout) as client:
            antwort = await client.post(ziel, json={"input": texte, "model": settings.embed_model})
            antwort.raise_for_status()
            daten = antwort.json().get("data", [])
    except (httpx.HTTPError, ValueError) as fehler:
        log.warning("Embedding fehlgeschlagen: %s", fehler)
        return []

    vektoren = [_norm(list(e.get("embedding", []))) for e in daten]
    # Weniger Vektoren als Texte waere still gefaehrlich: die Zuordnung
    # Text -> Vektor liefe danach um eins verschoben.
    if len(vektoren) != len(texte) or any(not v for v in vektoren):
        log.warning("Embedding-Antwort passt nicht zur Anfrage")
        return []
    return vektoren


def dokumenttext(name: str, ocr_text: str = "") -> str:
    """Woraus der Vektor eines Dokuments gebildet wird."""
    text = name
    if ocr_text:
        text = f"{name}\n{ocr_text}"
    return PRAEFIX_DOKUMENT + text[:MAX_TEXT]


def sachordner(pfad: str) -> str:
    """Der Ordner auf Sachebene, zu dem ein Pfad gehoert."""
    teile = [t for t in pfad.split("/") if t]
    if len(teile) < EBENEN:
        return ""
    return "/" + "/".join(teile[:EBENEN])


def wurzel() -> str:
    """Der Ordner, unter dem vorgeschlagen wird.

    Das ist der Elternordner des Belegordners, bei Mia also ``/Dokumente``.
    Der Belegordner liegt mitten in ihrer nummerierten Ablage, und genau
    deren Faecher sind die Ziele.

    Warum ueberhaupt eine Grenze: im Index steht auch ``/Mac Downloads``, ein
    Stapel von Kopien dessen, was anderswo schon abgelegt ist. Ohne die Grenze
    wird daraus ein Vorschlagsziel, und Mia OS bietet an, einen frischen
    Bescheid in den Download-Ordner zu schieben. Handverlesene Ausnahmen
    waeren die schlechtere Loesung: die veralten, sobald Mia einen Ordner
    umbenennt.
    """
    ordner_ = (settings.belege_ordner or "").rstrip("/")
    eltern = ordner_.rsplit("/", 1)[0]
    return eltern or ""


def zentren(dokumente: list[dict[str, Any]]) -> dict[str, list[float]]:
    """Je Sachordner den Schwerpunkt seiner Dokumente.

    Erwartet Eintraege mit ``folder`` und ``vektor``. Ordner mit zu wenigen
    Dokumenten fallen raus, siehe ``MIN_DOKUMENTE``.
    """
    unter = wurzel()
    nie = _nie()
    gruppen: dict[str, list[list[float]]] = {}
    for d in dokumente:
        pfad = str(d.get("folder", ""))
        if unter and not pfad.startswith(unter + "/"):
            continue
        ordner_ = sachordner(pfad)
        if not ordner_ or ordner_ in nie:
            continue
        vektor = d.get("vektor")
        if vektor:
            gruppen.setdefault(ordner_, []).append(list(vektor))

    out: dict[str, list[float]] = {}
    for ordner, vektoren in gruppen.items():
        if len(vektoren) < MIN_DOKUMENTE:
            continue
        mitte = [sum(werte) / len(vektoren) for werte in zip(*vektoren, strict=True)]
        out[ordner] = _norm(mitte)
    return out


def vorschlagen(vektor: list[float], zentren_: dict[str, list[float]]) -> dict[str, Any] | None:
    """Der beste Ordner samt Abstand zum zweiten, oder ``None``.

    ``None`` heisst nicht "kein Ordner passt", sondern "ich weiss es nicht
    sicher genug, um zu fragen". Der Unterschied zaehlt: bei einem Blatt, das
    wirklich in keinen vorhandenen Ordner passt, sieht das Ergebnis genauso
    aus wie bei einem, das zwischen zweien steht.
    """
    if not (vektor and len(zentren_) >= 2):
        return None

    treffer = sorted(
        ((_skalar(vektor, mitte), ordner) for ordner, mitte in zentren_.items()),
        reverse=True,
    )
    abstand = treffer[0][0] - treffer[1][0]
    if abstand < MIN_ABSTAND:
        return None
    return {
        "ordner": treffer[0][1],
        "naehe": round(treffer[0][0], 4),
        "abstand": round(abstand, 4),
    }
