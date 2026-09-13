"""Belege einfangen: eine Datei landet in Nextcloud und haengt am Eintrag.

Bisher konnte Mia OS nur verknuepfen, was ohnehin schon in Nextcloud lag.
Der haeufigste Fall ist aber der andere: Mia hat einen Bescheid in der Hand,
fotografiert ihn, und danach liegt das Bild in der Kamerarolle statt bei dem
Vorgang, zu dem es gehoert.

Drei Entscheidungen, die den Rest erklaeren:

**Eigener Zielordner.** Alles Hochgeladene geht nach ``BELEGE_ORDNER`` und
nirgendwo sonst. Mia OS schreibt damit nie in Mias gewachsene Ablage, und was
es angelegt hat, laesst sich an einer Stelle wieder herausnehmen. Ein
Zielordner, den der Aufrufer bestimmen darf, waere ein Schreibrecht auf die
ganze Nextcloud.

**Der Name kommt vom Eintrag, nicht vom Handy.** ``IMG_4711.jpg`` ist im Index
wertlos: gesucht wird ueber den Dateinamen, Inhalte stehen dort bewusst nicht
drin. Aus dem Eintrag wird deshalb ``2026-09-09 Widerspruch Kasse.jpg``.

**Die Endung folgt dem Inhalt.** iOS benennt HEIC-Aufnahmen beim Teilen gern
als ``.jpg``. Eine Datei mit falscher Endung liegt fuer immer als kaputtes
Vorschaubild da, deshalb entscheidet der Dateikopf und nicht der Name.
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import date

import httpx

from src.config import settings


class BelegError(Exception):
    """Etwas am Beleg stimmt nicht. Der Text geht so an Mia."""


# Was hochgeladen werden darf, mit dem Dateikopf, an dem es erkannt wird.
# Bewusst eng: Belege sind Fotos und PDFs. Office-Dateien legt Mia ueber den
# Editor an, ausfuehrbares Zeug hat hier ueberhaupt nichts verloren.
KOPFPRUEFUNG: list[tuple[str, str, bytes]] = [
    (".pdf", "application/pdf", b"%PDF"),
    (".jpg", "image/jpeg", b"\xff\xd8\xff"),
    (".png", "image/png", b"\x89PNG\r\n\x1a\n"),
]

ERLAUBTE_ENDUNGEN = {".pdf", ".jpg", ".png", ".heic", ".webp"}

# Zeichen, die in einem Dateinamen nichts verloren haben. Der Schraegstrich
# steht bewusst vorne: ohne ihn koennte ein Eintragstitel den Zielordner
# verlassen.
VERBOTEN = re.compile(r"[/\\:*?\"<>|\x00-\x1f]")


def _kopf_erkennen(inhalt: bytes) -> tuple[str, str] | None:
    """Endung und Medientyp aus dem Dateikopf. ``None``, wenn unbekannt."""
    for endung, typ, magie in KOPFPRUEFUNG:
        if inhalt.startswith(magie):
            return endung, typ

    # HEIC und WebP tragen ihre Kennung nicht am Anfang, sondern in einer
    # Box beziehungsweise hinter der RIFF-Groesse.
    if len(inhalt) >= 12:
        if inhalt[4:8] == b"ftyp" and inhalt[8:12] in (b"heic", b"heix", b"mif1", b"heim"):
            return ".heic", "image/heic"
        if inhalt[:4] == b"RIFF" and inhalt[8:12] == b"WEBP":
            return ".webp", "image/webp"
    return None


def endung_pruefen(dateiname: str, inhalt: bytes) -> str:
    """Welche Endung die Datei wirklich verdient.

    **Allein der Dateikopf entscheidet, der Name gar nicht.** Zwei Gruende:

    iOS liefert HEIC-Aufnahmen beim Teilen regelmaessig unter ``.jpg`` aus.
    Wer das durchwinkt, hat danach ein Bild im Index, das weder Nextcloud noch
    der Browser anzeigen kann, und sieht dem Namen nicht an, warum.

    Und ein Rueckfall auf die Endung waere ein Loch: eine ZIP-Datei, die
    jemand ``foto.jpg`` nennt, laege danach in Mias Ablage. Jede gueltige
    Datei der erlaubten Typen traegt ihre Kennung im Kopf, der Rueckfall
    braeuchte also niemand ausser dem Angreifer.
    """
    erkannt = _kopf_erkennen(inhalt)
    if erkannt:
        return erkannt[0]
    raise BelegError("Das ist kein Bild und kein PDF. Erlaubt sind JPG, PNG, HEIC, WebP und PDF.")


def zielname(titel: str, endung: str, tag: date | None = None) -> str:
    """Aus Eintrag und Datum einen Namen bauen, der im Index etwas taugt.

    ``IMG_4711.jpg`` findet niemand wieder: die Suche laeuft ueber Dateinamen,
    Inhalte stehen im Index bewusst nicht. Der Titel des Eintrags ist genau
    das Wort, unter dem Mia spaeter sucht.
    """
    sauber = VERBOTEN.sub(" ", titel).strip()
    # Fuehrende Punkte machen die Datei in Nextcloud unsichtbar.
    sauber = sauber.lstrip(". ").strip()
    sauber = re.sub(r"\s+", " ", sauber)
    # Deckel beim Namen, nicht beim ganzen Pfad: manche Dateisysteme geben bei
    # 255 Bytes auf, und ein Eintragstitel kann 300 Zeichen lang sein.
    sauber = sauber[:80].strip() or "Beleg"
    return f"{(tag or date.today()).isoformat()} {sauber}{endung}"


def _url(pfad: str) -> str:
    basis = settings.nextcloud_url.rstrip("/")
    return f"{basis}/remote.php/dav/files/{settings.nextcloud_user}{urllib.parse.quote(pfad)}"


async def _ordner_anlegen(client: httpx.AsyncClient, ordner: str) -> None:
    """Den Zielordner sicherstellen, Ebene fuer Ebene.

    ``MKCOL`` legt nur eine Ebene an und antwortet mit 409, wenn der
    Elternordner fehlt. Beim ersten Beleg existiert ``/Dokumente/00 Belege``
    aber noch gar nicht. 405 heisst \"gibt es schon\" und ist der Normalfall.
    """
    teile = [t for t in ordner.strip("/").split("/") if t]
    weg = ""
    for teil in teile:
        weg = f"{weg}/{teil}"
        antwort = await client.request("MKCOL", _url(weg))
        if antwort.status_code not in (201, 405):
            raise BelegError(f"Ordner {weg} liess sich nicht anlegen ({antwort.status_code}).")


async def ablegen(inhalt: bytes, name: str) -> tuple[str, str]:
    """Die Datei in den Belegordner legen. Gibt Pfad und Nextcloud-ID zurueck.

    Zwei Belege am selben Tag zum selben Eintrag sind der Normalfall, nicht
    die Ausnahme: Vorder- und Rueckseite. Deshalb wird nicht ueberschrieben,
    sondern durchnummeriert.

    ``If-None-Match: *`` laesst Nextcloud entscheiden, ob der Name frei ist.
    Ein vorheriges Nachsehen waere ein Wettlauf: zwischen Pruefung und
    Schreiben kann derselbe Name belegt werden, und dann ueberschreibt der
    zweite Beleg still den ersten.

    Die ``OC-FileId`` steht in der Antwort auf das PUT. Mit ihr hat der Beleg
    sofort ein Vorschaubild, ohne auf den naechsten Crawl zu warten.
    """
    if not (settings.nextcloud_url and settings.nextcloud_user and settings.nextcloud_password):
        raise BelegError("Nextcloud ist nicht eingerichtet.")

    grenze = settings.belege_max_mb * 1024 * 1024
    if len(inhalt) > grenze:
        raise BelegError(f"Die Datei ist groesser als {settings.belege_max_mb} MB.")
    if not inhalt:
        raise BelegError("Die Datei ist leer.")

    ordner = settings.belege_ordner.rstrip("/") or "/Dokumente/00 Belege"
    auth = (settings.nextcloud_user, settings.nextcloud_password)

    async with httpx.AsyncClient(timeout=120, auth=auth, follow_redirects=True) as client:
        await _ordner_anlegen(client, ordner)

        stamm, endung = name.rsplit(".", 1)
        for versuch in range(1, 21):
            kandidat = stamm if versuch == 1 else f"{stamm} ({versuch})"
            pfad = f"{ordner}/{kandidat}.{endung}"
            antwort = await client.put(_url(pfad), content=inhalt, headers={"If-None-Match": "*"})
            if antwort.status_code in (201, 204):
                return pfad, antwort.headers.get("OC-FileId", "")
            # 412 heisst: der Name ist belegt. Alles andere ist ein echter
            # Fehler und darf nicht als "nimm den naechsten Namen" enden.
            if antwort.status_code != 412:
                raise BelegError(f"Nextcloud hat den Beleg abgelehnt ({antwort.status_code}).")

    raise BelegError("Zu viele Belege mit demselben Namen.")


async def _move(alt: str, ziel: str, stamm: str, endung: str) -> str:
    """Der gemeinsame MOVE mit Durchnummerieren. Liefert den neuen Pfad.

    Unterbau für ``verschieben`` und ``umbenennen``: beide sind derselbe
    WebDAV-Aufruf und brauchen dieselbe Behandlung von belegten Namen.
    """
    auth = (settings.nextcloud_user, settings.nextcloud_password)
    async with httpx.AsyncClient(timeout=120, auth=auth, follow_redirects=True) as client:
        for versuch in range(1, 21):
            kandidat = stamm if versuch == 1 else f"{stamm} ({versuch})"
            neu = f"{ziel}/{kandidat}" + (f".{endung}" if endung else "")
            if neu == alt:
                return alt
            antwort = await client.request(
                "MOVE",
                _url(alt),
                headers={"Destination": _url(neu), "Overwrite": "F"},
            )
            if antwort.status_code in (201, 204):
                return neu
            # 412 heisst: am Ziel liegt schon etwas mit dem Namen.
            if antwort.status_code != 412:
                if antwort.status_code == 409:
                    raise BelegError("Den Zielordner gibt es nicht.")
                raise BelegError(f"Verschieben abgelehnt ({antwort.status_code}).")

    raise BelegError("Zu viele Dateien mit demselben Namen im Zielordner.")


async def umbenennen(alt: str, neuer_name: str) -> str:
    """Eine abgelegte Datei umbenennen, im selben Ordner. Liefert den neuen Pfad.

    Für den Namensvorschlag aus dem gelesenen Text. Der Beleg heißt nach dem
    Hochladen nach seinem Eintrag; nimmt Mia den Vorschlag an, heißt er danach
    nach dem, was auf dem Blatt steht.

    **Die Endung bleibt, egal was im Vorschlag steht.** Sie wurde beim Upload
    aus dem Dateikopf bestimmt, und ein aus OCR-Text gebauter Name hat dabei
    nichts mitzureden: eine ``.pdf``, die plötzlich ``.jpg`` heißt, öffnet
    niemand mehr.
    """
    if not (settings.nextcloud_url and settings.nextcloud_user and settings.nextcloud_password):
        raise BelegError("Nextcloud ist nicht eingerichtet.")

    ordner, _, name = alt.rpartition("/")
    _, _, endung = name.rpartition(".")

    # Eine Endung im Vorschlag wird weggeworfen, die echte haengt unten dran.
    # Abgeschnitten wird nur, was wie eine Endung aussieht: ein Vorschlag
    # ``../../01 Persoenliches/Ausweis`` haette sonst am ersten Punkt geendet
    # und waere zu einem leeren Namen geworden.
    stamm = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", neuer_name)
    # Der Schraegstrich zuerst: ohne ihn koennte ein Vorschlag den Belegordner
    # verlassen, und der Text stammt von einem Blatt Papier, auf dem alles
    # stehen kann.
    stamm = VERBOTEN.sub(" ", stamm)
    stamm = re.sub(r"\s+", " ", stamm).strip().lstrip(". ").strip()[:110].strip()
    if not stamm:
        raise BelegError("Der Name ist leer.")

    return await _move(alt, ordner, stamm, endung)


async def verschieben(alt: str, zielordner: str) -> str:
    """Eine abgelegte Datei in einen anderen Ordner schieben. Liefert den neuen Pfad.

    Fuer den Ordnervorschlag: der Beleg landet beim Hochladen immer im
    Belegordner, und wenn Mia den Vorschlag annimmt, geht er von dort weiter.

    **``Overwrite: F``.** WebDAV ueberschreibt bei einem MOVE standardmaessig,
    was am Ziel liegt. Bei gleichen Dateinamen waere das ein stiller
    Datenverlust in Mias gewachsener Ablage, und zwar in genau der Richtung,
    in der es wehtut: das aeltere Original verschwindet, der frische Scan
    bleibt. Deshalb wird durchnummeriert wie beim Hochladen.

    **Der Zielordner wird nicht angelegt.** Vorgeschlagen wird nur, was es
    schon gibt; ein Tippfehler soll keinen Ordner in die Ablage schreiben.
    """
    if not (settings.nextcloud_url and settings.nextcloud_user and settings.nextcloud_password):
        raise BelegError("Nextcloud ist nicht eingerichtet.")

    ziel = zielordner.rstrip("/")
    if not ziel.startswith("/"):
        raise BelegError("Der Zielordner muss ein absoluter Pfad sein.")
    if ".." in ziel.split("/"):
        raise BelegError("Ungültiger Zielordner.")

    name = alt.rsplit("/", 1)[-1]
    stamm, _, endung = name.rpartition(".")
    if not stamm:
        stamm, endung = name, ""

    return await _move(alt, ziel, stamm, endung)
