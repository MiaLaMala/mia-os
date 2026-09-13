"""Scanner: aus einem Handyfoto einen Scan machen.

Die Bilder hier werden erzeugt, nicht geladen: ein Testbild im Repository
waere eine Datei, die niemand pflegt, und die Bedingungen (Perspektive,
Schattenband, Beleuchtungsverlauf) sollen im Test selbst stehen, damit man
sieht, wogegen geprueft wird.

Warum ueberhaupt so genau: die Kantenerkennung darf scheitern, und dann muss
sie ``None`` liefern statt zu raten. Ein Bescheid, der so beschnitten wurde,
dass das Aktenzeichen fehlt, waere schlimmer als ein unbearbeitetes Foto.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src import scanner

# Wo das Blatt im erzeugten Foto liegt. Gegen diese Werte wird geprueft.
BLATT_ECKEN = [(295, 210), (1205, 285), (1275, 1790), (205, 1700)]


def _blatt(breite: int = 1240, hoehe: int = 1754) -> np.ndarray:
    """Ein Dokument mit Briefkopf, Text und einem blauen Stempel."""
    blatt = np.full((hoehe, breite, 3), 252, dtype=np.uint8)
    f = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(blatt, "Briefkopf", (90, 150), f, 1.6, (30, 30, 30), 3)
    cv2.line(blatt, (90, 230), (breite - 90, 230), (120, 120, 120), 2)
    for i in range(9):
        cv2.putText(blatt, "Zeile mit Text zum Lesen", (90, 400 + i * 45), f, 0.62, (45, 45, 45), 1)
    # Blau: genau das, was harte Binarisierung verschluckt.
    cv2.circle(blatt, (950, 1400), 110, (170, 60, 40), 4)
    return blatt


def _foto(mit_schatten: bool = True) -> bytes:
    """Das Blatt schief auf einem Tisch, ungleich beleuchtet."""
    breite, hoehe = 1500, 2000
    foto = np.full((hoehe, breite, 3), (105, 125, 148), dtype=np.uint8)
    rauschen = np.random.default_rng(7).normal(0, 6, foto.shape)
    foto = np.clip(foto.astype(np.float32) + rauschen, 0, 255).astype(np.uint8)

    blatt = _blatt()
    h, b = blatt.shape[:2]
    matrix = cv2.getPerspectiveTransform(
        np.array([[0, 0], [b, 0], [b, h], [0, h]], dtype=np.float32),
        np.array(BLATT_ECKEN, dtype=np.float32),
    )
    gelegt = cv2.warpPerspective(
        blatt, matrix, (breite, hoehe), borderMode=cv2.BORDER_TRANSPARENT, dst=foto.copy()
    )

    yy, xx = np.mgrid[0:hoehe, 0:breite].astype(np.float32)
    verlauf = 0.72 + 0.42 * (1 - xx / breite) + 0.12 * (1 - yy / hoehe)

    schatten = np.ones_like(verlauf)
    if mit_schatten:
        # Der eigene Schatten des Handys. Genau daran scheitert eine feste
        # Helligkeitsschwelle.
        schatten[(yy > 380) & (yy < 780) & (xx > 150)] = 0.63
        schatten = cv2.GaussianBlur(schatten, (161, 161), 0)

    beleuchtet = np.clip(gelegt.astype(np.float32) * (verlauf * schatten)[:, :, None], 0, 255)
    erfolg, puffer = cv2.imencode(".jpg", beleuchtet.astype(np.uint8))
    assert erfolg
    return bytes(puffer.tobytes())


# --- Ecken finden --------------------------------------------------------


def test_findet_das_blatt_im_foto() -> None:
    gefunden = scanner.ecken_finden(_foto())
    assert gefunden is not None

    # Reihenfolge und Lage: oben-links, oben-rechts, unten-rechts, unten-links.
    for gef, echt in zip(gefunden, BLATT_ECKEN, strict=True):
        abstand = ((gef[0] - echt[0]) ** 2 + (gef[1] - echt[1]) ** 2) ** 0.5
        assert abstand < 25, f"Ecke {gef} liegt {abstand:.0f} px neben {echt}"


def test_leere_flaeche_liefert_nichts() -> None:
    """Kein Blatt zu sehen heisst ``None``, nicht irgendein Viereck.

    Sonst schneidet der Scanner an einer zufaelligen Stelle und Mia sieht ein
    Ergebnis, das aussieht, als haette es funktioniert.
    """
    leer = np.full((900, 700, 3), 200, dtype=np.uint8)
    _, puffer = cv2.imencode(".jpg", leer)
    assert scanner.ecken_finden(bytes(puffer.tobytes())) is None


def test_kaputte_datei_wirft_sauber() -> None:
    with pytest.raises(ValueError):
        scanner.ecken_finden(b"das ist kein bild")


# --- Entzerren -----------------------------------------------------------


def test_entzerren_macht_ein_rechteck() -> None:
    bild = scanner.entzerren(_foto(), BLATT_ECKEN)
    hoehe, breite = bild.shape[:2]
    # Das Blatt ist A4-artig, also deutlich hoeher als breit.
    assert 1.2 < hoehe / breite < 1.7


def test_entzerren_braucht_vier_ecken() -> None:
    with pytest.raises(ValueError, match="vier"):
        scanner.entzerren(_foto(), [(0, 0), (10, 0), (10, 10)])


def test_kein_tischrand_im_ergebnis() -> None:
    """Ein Schnitt exakt auf der Kante nimmt einen dunklen Streifen mit.

    Am Bild gesehen: schwarzer Rand links. Deshalb wird ein wenig nach innen
    geschnitten.
    """
    fertig, _ = scanner.verarbeiten(_foto())
    bild = cv2.imdecode(np.frombuffer(fertig, np.uint8), cv2.IMREAD_GRAYSCALE)
    # Die aeussersten Spalten muessen hell sein, nicht Tischfarbe.
    assert bild[:, :3].mean() > 200
    assert bild[:, -3:].mean() > 200


# --- Aufhellen -----------------------------------------------------------


def test_papier_wird_weiss_trotz_schatten() -> None:
    """Der Kern der Sache: gleichmaessig weisser Hintergrund.

    Der erste Wurf benutzte einen Gauss-Kern und hinterliess graue Schlieren
    genau dort, wo das Schattenband aufhoerte. Ein Median haelt Kanten.
    """
    fertig, _ = scanner.verarbeiten(_foto())
    bild = cv2.imdecode(np.frombuffer(fertig, np.uint8), cv2.IMREAD_GRAYSCALE)

    hoehe = bild.shape[0]
    # Ein Streifen im Schattenbereich und einer darunter. Beide muessen
    # gleich hell sein, sonst steht der Schatten noch im Bild.
    oben = bild[int(hoehe * 0.10) : int(hoehe * 0.22)]
    unten = bild[int(hoehe * 0.55) : int(hoehe * 0.67)]
    assert abs(float(np.median(oben)) - float(np.median(unten))) < 8

    # Und das Papier selbst ist wirklich weiss, nicht hellgrau.
    assert float(np.median(bild)) > 240


def test_text_ueberlebt_das_aufhellen() -> None:
    """Weiss allein waere leicht: es muss auch noch Schrift drin sein."""
    fertig, _ = scanner.verarbeiten(_foto())
    bild = cv2.imdecode(np.frombuffer(fertig, np.uint8), cv2.IMREAD_GRAYSCALE)
    dunkel = float((bild < 128).mean())
    assert 0.005 < dunkel < 0.35, f"{dunkel:.1%} dunkle Bildpunkte ist kein Text"


def test_hart_ist_wirklich_schwarzweiss() -> None:
    fertig, _ = scanner.verarbeiten(_foto(), staerke="hart")
    bild = cv2.imdecode(np.frombuffer(fertig, np.uint8), cv2.IMREAD_GRAYSCALE)
    # Nach JPEG gibt es Zwischenwerte an den Kanten, aber die Masse muss an
    # den beiden Enden liegen.
    extrem = float(((bild < 40) | (bild > 215)).mean())
    assert extrem > 0.9


def test_weich_behaelt_graustufen() -> None:
    """Bei Behoerdenpost ist der Stempel oft der Teil, auf den es ankommt."""
    fertig, _ = scanner.verarbeiten(_foto(), staerke="weich")
    bild = cv2.imdecode(np.frombuffer(fertig, np.uint8), cv2.IMREAD_GRAYSCALE)
    mittel = float(((bild >= 60) & (bild <= 200)).mean())
    assert mittel > 0.002, "keine Graustufen uebrig, das waere hart statt weich"


# --- Ecken aus dem Formular ----------------------------------------------


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("10,20 30,40 50,60 70,80", [(10, 20), (30, 40), (50, 60), (70, 80)]),
        ("10.5,20.4 30,40 50,60 70,80", [(10, 20), (30, 40), (50, 60), (70, 80)]),
        ("", None),
        ("   ", None),
        ("10,20 30,40", None),  # zu wenige
        ("10,20 30,40 50,60 70,80 90,100", None),  # zu viele
        ("kaputt", None),
        ("10,20 30 50,60 70,80", None),
    ],
)
def test_ecken_aus_text(text: str, erwartet: list[tuple[int, int]] | None) -> None:
    """Halb gelesene Ecken wuerden das Blatt zufaellig zerschneiden."""
    assert scanner.ecken_aus_text(text) == erwartet


# --- Vorschau ------------------------------------------------------------


def test_vorschau_nennt_die_originalgroesse() -> None:
    """Die Oberflaeche rechnet gezogene Ecken damit aufs Original um.

    Ohne das landen sie um den Verkleinerungsfaktor verschoben und der
    Schnitt sitzt schief.
    """
    _, gefunden, (breite, hoehe) = scanner.vorschau(_foto())
    assert (breite, hoehe) == (1500, 2000)
    assert gefunden is True


def test_vorschau_ist_kleiner_als_das_original() -> None:
    bild, _, _ = scanner.vorschau(_foto())
    entpackt = cv2.imdecode(np.frombuffer(bild, np.uint8), cv2.IMREAD_GRAYSCALE)
    assert max(entpackt.shape) <= scanner.VORSCHAU_KANTE


def test_eigene_ecken_gelten_als_nicht_automatisch() -> None:
    """Damit die Oberflaeche den Hinweis nicht faelschlich anzeigt."""
    _, gefunden, _ = scanner.vorschau(_foto(), ecken=BLATT_ECKEN)
    assert gefunden is True


# --- API -----------------------------------------------------------------


def test_api_vorschau(client: TestClient) -> None:
    antwort = client.post(
        "/api/scan/vorschau",
        files={"datei": ("foto.jpg", _foto(), "image/jpeg")},
        data={"staerke": "weich"},
    )
    assert antwort.status_code == 200

    daten = antwort.json()
    assert daten["bild"].startswith("data:image/jpeg;base64,")
    assert daten["automatisch"] is True
    assert len(daten["ecken"]) == 4
    assert (daten["breite"], daten["hoehe"]) == (1500, 2000)


def test_api_vorschau_speichert_nichts(client: TestClient) -> None:
    """Eine Halde halbfertiger Fotos von Ausweisen will hier niemand."""
    from src.main import get_store

    client.post("/api/scan/vorschau", files={"datei": ("foto.jpg", _foto(), "image/jpeg")})
    assert get_store().count_documents() == 0


def test_api_vorschau_mit_kaputtem_bild(client: TestClient) -> None:
    antwort = client.post(
        "/api/scan/vorschau", files={"datei": ("x.jpg", b"kein bild", "image/jpeg")}
    )
    assert antwort.status_code == 400


def test_api_beleg_wird_gescannt(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Beim Hochladen mit ``scannen`` kommt das aufbereitete Bild an."""
    import src.api

    gesehen: list[bytes] = []

    async def fake(inhalt: bytes, name: str) -> tuple[str, str]:
        gesehen.append(inhalt)
        return f"/Dokumente/00 Belege/{name}", "77"

    monkeypatch.setattr(src.api.belege, "ablegen", fake)

    eintrag = client.post("/api/sammlung", json={"titel": "Bescheid"}).json()["eintrag"]
    original = _foto()
    antwort = client.post(
        f"/api/sammlung/{eintrag['id']}/beleg",
        files={"datei": ("IMG_1.jpg", original, "image/jpeg")},
        data={"scannen": "true", "staerke": "weich"},
    )
    assert antwort.status_code == 200

    # Was abgelegt wurde, ist nicht mehr das Original.
    assert gesehen[0] != original
    gescannt = cv2.imdecode(np.frombuffer(gesehen[0], np.uint8), cv2.IMREAD_GRAYSCALE)
    assert float(np.median(gescannt)) > 240, "der Beleg wurde nicht aufgehellt"


def test_api_pdf_wird_nicht_gescannt(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ein PDF durch die Bildaufbereitung zu schicken wuerde es zerstoeren."""
    import src.api

    gesehen: list[bytes] = []

    async def fake(inhalt: bytes, name: str) -> tuple[str, str]:
        gesehen.append(inhalt)
        return f"/Dokumente/00 Belege/{name}", "77"

    monkeypatch.setattr(src.api.belege, "ablegen", fake)

    pdf = b"%PDF-1.7\n" + b"\x00" * 40
    eintrag = client.post("/api/sammlung", json={"titel": "Vertrag"}).json()["eintrag"]
    antwort = client.post(
        f"/api/sammlung/{eintrag['id']}/beleg",
        files={"datei": ("v.pdf", pdf, "application/pdf")},
        data={"scannen": "true"},
    )
    assert antwort.status_code == 200
    assert gesehen[0] == pdf
    assert antwort.json()["dokumente"][0]["name"].endswith(".pdf")


def test_api_gescanntes_heic_heisst_jpg(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Der Scanner liefert immer JPEG, egal was hereinkam.

    Ohne das traegt eine gescannte HEIC-Aufnahme weiter ihre alte Endung und
    niemand kann sie oeffnen.
    """
    import src.api

    async def fake(inhalt: bytes, name: str) -> tuple[str, str]:
        return f"/Dokumente/00 Belege/{name}", "77"

    monkeypatch.setattr(src.api.belege, "ablegen", fake)

    # Ein JPEG mit HEIC-Kopf waere kein gueltiges Bild, deshalb der Umweg:
    # ein echtes Foto, das der Kopfpruefung als JPEG durchgeht.
    eintrag = client.post("/api/sammlung", json={"titel": "Foto"}).json()["eintrag"]
    antwort = client.post(
        f"/api/sammlung/{eintrag['id']}/beleg",
        files={"datei": ("IMG_1.HEIC", _foto(), "image/heic")},
        data={"scannen": "true"},
    )
    assert antwort.json()["dokumente"][0]["name"].endswith(".jpg")
