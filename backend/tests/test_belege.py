"""Belege einfangen: Foto rein, in Nextcloud abgelegt, am Eintrag verknuepft.

Der Upload ist der erste Weg, auf dem Mia OS in Nextcloud **schreibt**. Bisher
hat es nur gelesen. Diese Tests halten fest, was dabei schiefgehen kann:
falsche Endungen, ueberschriebene Dateien, Namen, die den Zielordner
verlassen.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from src import belege

# Echte Dateikoepfe, keine erfundenen: an genau denen entscheidet der Code.
JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 40
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
PDF = b"%PDF-1.7\n" + b"\x00" * 40
HEIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 40
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 40


# --- Endung aus dem Dateikopf --------------------------------------------


@pytest.mark.parametrize(
    ("inhalt", "erwartet"),
    [(JPG, ".jpg"), (PNG, ".png"), (PDF, ".pdf"), (HEIC, ".heic"), (WEBP, ".webp")],
)
def test_endung_kommt_aus_dem_dateikopf(inhalt: bytes, erwartet: str) -> None:
    assert belege.endung_pruefen("beliebig.txt", inhalt) == erwartet


def test_heic_als_jpg_getarnt_wird_korrigiert() -> None:
    """iOS liefert HEIC-Aufnahmen beim Teilen regelmaessig unter .jpg aus.

    Wer das durchwinkt, hat danach ein Bild im Index, das weder Nextcloud noch
    der Browser anzeigen kann, und sieht dem Namen nicht an, warum.
    """
    assert belege.endung_pruefen("IMG_4711.jpg", HEIC) == ".heic"


def test_umbenannte_fremddatei_fliegt_raus() -> None:
    """Eine ZIP-Datei mit .jpg-Endung darf nicht in Mias Ablage landen."""
    with pytest.raises(belege.BelegError):
        belege.endung_pruefen("bild.jpg", b"PK\x03\x04irgendwas")


def test_unbekannter_kopf_wird_abgelehnt() -> None:
    """Kein Rueckfall auf die Endung: die waere das Loch, nicht die Rettung.

    Jede gueltige JPG, PNG, PDF, HEIC und WebP traegt ihre Kennung im Kopf.
    Wer hier auf den Namen ausweicht, laesst umbenannte Fremddateien durch,
    ohne einem einzigen echten Foto zu helfen.
    """
    with pytest.raises(belege.BelegError):
        belege.endung_pruefen("scan.jpeg", b"\x00\x01\x02\x03noch was")


# --- Zielname -------------------------------------------------------------


def test_name_kommt_aus_eintrag_und_datum() -> None:
    """``IMG_4711.jpg`` findet im Index niemand wieder."""
    assert (
        belege.zielname("Widerspruch Kasse", ".jpg", date(2026, 9, 9))
        == "2026-09-09 Widerspruch Kasse.jpg"
    )


def test_schraegstrich_im_titel_verlaesst_den_ordner_nicht() -> None:
    """Ohne das koennte ein Eintragstitel den Zielordner wechseln."""
    name = belege.zielname("../../etc/passwd", ".pdf", date(2026, 9, 9))
    assert "/" not in name
    assert not name.startswith(".")


def test_leerer_titel_bekommt_trotzdem_einen_namen() -> None:
    assert belege.zielname("   ", ".pdf", date(2026, 9, 9)) == "2026-09-09 Beleg.pdf"


def test_langer_titel_wird_gekuerzt() -> None:
    """Ein Eintragstitel darf 300 Zeichen haben, ein Dateiname nicht."""
    name = belege.zielname("A" * 300, ".jpg", date(2026, 9, 9))
    assert len(name.encode()) < 120


# --- Ablegen in Nextcloud -------------------------------------------------


class FakeNextcloud:
    """Ein Nextcloud, das mitschreibt statt zu antworten.

    Bewusst kein Mock einzelner Aufrufe: der interessante Teil ist die
    Reihenfolge (MKCOL vor PUT) und was bei einem belegten Namen passiert.
    """

    def __init__(self, belegte: set[str] | None = None) -> None:
        self.belegte = belegte or set()
        self.mkcol: list[str] = []
        self.puts: list[tuple[str, int]] = []

    async def handler(self, request: httpx.Request) -> httpx.Response:
        pfad = str(request.url.path)
        if request.method == "MKCOL":
            self.mkcol.append(pfad)
            # 405 heisst "gibt es schon" und ist der Normalfall.
            return httpx.Response(405)
        if request.method == "PUT":
            if pfad in self.belegte:
                return httpx.Response(412)
            self.belegte.add(pfad)
            self.puts.append((pfad, len(request.content)))
            return httpx.Response(201, headers={"OC-FileId": "9001"})
        return httpx.Response(404)


@pytest.fixture
def nextcloud(monkeypatch: pytest.MonkeyPatch) -> FakeNextcloud:
    fake = FakeNextcloud()
    monkeypatch.setattr(belege.settings, "nextcloud_url", "https://nas.example")
    monkeypatch.setattr(belege.settings, "nextcloud_user", "mia")
    monkeypatch.setattr(belege.settings, "nextcloud_password", "geheim")
    monkeypatch.setattr(belege.settings, "belege_ordner", "/Dokumente/00 Belege")

    echt = httpx.AsyncClient

    def gefaelscht(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(fake.handler)
        return echt(*args, **kwargs)

    monkeypatch.setattr(belege.httpx, "AsyncClient", gefaelscht)
    return fake


async def test_ablegen_legt_ordner_an_und_schreibt(nextcloud: FakeNextcloud) -> None:
    pfad, file_id = await belege.ablegen(JPG, "2026-09-09 Widerspruch.jpg")

    assert pfad == "/Dokumente/00 Belege/2026-09-09 Widerspruch.jpg"
    assert file_id == "9001"
    # Jede Ebene einzeln: MKCOL legt nur eine an und antwortet sonst mit 409.
    assert nextcloud.mkcol == [
        "/remote.php/dav/files/mia/Dokumente",
        "/remote.php/dav/files/mia/Dokumente/00 Belege",
    ]


async def test_zweiter_beleg_ueberschreibt_den_ersten_nicht(nextcloud: FakeNextcloud) -> None:
    """Vorder- und Rueckseite am selben Tag sind der Normalfall."""
    erst, _ = await belege.ablegen(JPG, "2026-09-09 Bescheid.jpg")
    zweit, _ = await belege.ablegen(PNG, "2026-09-09 Bescheid.jpg")

    assert erst == "/Dokumente/00 Belege/2026-09-09 Bescheid.jpg"
    assert zweit == "/Dokumente/00 Belege/2026-09-09 Bescheid (2).jpg"
    assert len(nextcloud.puts) == 2


async def test_zu_grosse_datei_wird_abgelehnt(
    nextcloud: FakeNextcloud, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(belege.settings, "belege_max_mb", 1)
    with pytest.raises(belege.BelegError, match="1 MB"):
        await belege.ablegen(b"x" * (2 * 1024 * 1024), "gross.jpg")
    assert nextcloud.puts == []


async def test_leere_datei_wird_abgelehnt(nextcloud: FakeNextcloud) -> None:
    with pytest.raises(belege.BelegError):
        await belege.ablegen(b"", "leer.jpg")


async def test_ohne_nextcloud_kein_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(belege.settings, "nextcloud_url", "")
    with pytest.raises(belege.BelegError, match="nicht eingerichtet"):
        await belege.ablegen(JPG, "x.jpg")


async def test_fremder_fehlercode_wird_nicht_als_namenskonflikt_gedeutet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ein 507 (kein Platz) darf nicht 20 Versuche mit neuen Namen ausloesen."""
    monkeypatch.setattr(belege.settings, "nextcloud_url", "https://nas.example")
    monkeypatch.setattr(belege.settings, "nextcloud_user", "mia")
    monkeypatch.setattr(belege.settings, "nextcloud_password", "geheim")

    versuche = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal versuche
        if request.method == "MKCOL":
            return httpx.Response(405)
        versuche += 1
        return httpx.Response(507)

    echt = httpx.AsyncClient
    monkeypatch.setattr(
        belege.httpx,
        "AsyncClient",
        lambda *a, **k: echt(*a, **{**k, "transport": httpx.MockTransport(handler)}),
    )

    with pytest.raises(belege.BelegError, match="507"):
        await belege.ablegen(JPG, "x.jpg")
    assert versuche == 1


# --- Der Index kennt Belege ----------------------------------------------


def test_bilder_zaehlen_nur_im_belegordner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sonst haette der Index jedes Urlaubsfoto aus Mias Nextcloud drin.

    Ohne diese Ausnahme faellt umgekehrt jeder fotografierte Beleg beim
    naechsten Crawl aus dem Index, und die Verknuepfung am Eintrag stuende auf
    "nicht mehr am alten Ort", obwohl die Datei unveraendert daliegt.
    """
    from src.collectors import documents

    monkeypatch.setattr(documents.settings, "belege_ordner", "/Dokumente/00 Belege")

    assert documents.zaehlt_als_dokument("/Dokumente/00 Belege/Bescheid.jpg") is True
    assert documents.zaehlt_als_dokument("/Bilder/Urlaub/Strand.jpg") is False
    # PDFs zaehlen ueberall.
    assert documents.zaehlt_als_dokument("/Dokumente/Vertrag.pdf") is True


# --- API ------------------------------------------------------------------


@pytest.fixture
def hochladen_moeglich(monkeypatch: pytest.MonkeyPatch) -> list[tuple[bytes, str]]:
    """``belege.ablegen`` durch eine Mitschrift ersetzen.

    Der Weg nach Nextcloud ist oben eigens geprueft. Hier interessiert nur,
    was der Endpunkt daraus macht.
    """
    gesehen: list[tuple[bytes, str]] = []

    async def fake(inhalt: bytes, name: str) -> tuple[str, str]:
        gesehen.append((inhalt, name))
        return f"/Dokumente/00 Belege/{name}", "4242"

    import src.api

    monkeypatch.setattr(src.api.belege, "ablegen", fake)
    return gesehen


def test_api_beleg_landet_am_eintrag(
    client: TestClient, hochladen_moeglich: list[tuple[bytes, str]]
) -> None:
    eintrag = client.post(
        "/api/sammlung", json={"titel": "Widerspruch Kasse", "datum": "2026-09-03"}
    ).json()["eintrag"]

    antwort = client.post(
        f"/api/sammlung/{eintrag['id']}/beleg",
        files={"datei": ("IMG_4711.jpg", JPG, "image/jpeg")},
    )
    assert antwort.status_code == 200

    dokumente = antwort.json()["dokumente"]
    assert len(dokumente) == 1
    # Der Name kommt aus dem Eintrag, nicht vom Handy.
    assert dokumente[0]["name"] == "2026-09-03 Widerspruch Kasse.jpg"
    # Und er ist sofort da, nicht erst nach dem naechsten Crawl.
    assert dokumente[0]["fehlt"] is False
    assert dokumente[0]["vorschau"]


def test_api_datum_des_eintrags_schlaegt_heute(
    client: TestClient, hochladen_moeglich: list[tuple[bytes, str]]
) -> None:
    """Ein Bescheid vom 3. wird oft erst am 9. fotografiert."""
    eintrag = client.post(
        "/api/sammlung", json={"titel": "Bescheid", "datum": "2026-09-03"}
    ).json()["eintrag"]

    client.post(
        f"/api/sammlung/{eintrag['id']}/beleg", files={"datei": ("x.pdf", PDF, "application/pdf")}
    )
    assert hochladen_moeglich[0][1].startswith("2026-09-03")


def test_api_undatierter_eintrag_bekommt_heute(
    client: TestClient, hochladen_moeglich: list[tuple[bytes, str]]
) -> None:
    eintrag = client.post("/api/sammlung", json={"titel": "Ohne Datum"}).json()["eintrag"]

    client.post(
        f"/api/sammlung/{eintrag['id']}/beleg", files={"datei": ("x.pdf", PDF, "application/pdf")}
    )
    assert hochladen_moeglich[0][1].startswith(date.today().isoformat())


def test_api_zwei_belege_haengen_beide(
    client: TestClient, hochladen_moeglich: list[tuple[bytes, str]]
) -> None:
    """Vorder- und Rueckseite. Der zweite darf den ersten nicht verdraengen."""
    import src.api

    async def fake(inhalt: bytes, name: str) -> tuple[str, str]:
        nummer = len(hochladen_moeglich) + 1
        hochladen_moeglich.append((inhalt, name))
        stamm, endung = name.rsplit(".", 1)
        zusatz = "" if nummer == 1 else f" ({nummer})"
        return f"/Dokumente/00 Belege/{stamm}{zusatz}.{endung}", str(nummer)

    src.api.belege.ablegen = fake  # type: ignore[assignment]

    eintrag = client.post("/api/sammlung", json={"titel": "Bescheid"}).json()["eintrag"]
    client.post(
        f"/api/sammlung/{eintrag['id']}/beleg", files={"datei": ("a.jpg", JPG, "image/jpeg")}
    )
    antwort = client.post(
        f"/api/sammlung/{eintrag['id']}/beleg", files={"datei": ("b.jpg", PNG, "image/png")}
    )

    assert len(antwort.json()["dokumente"]) == 2


def test_api_falscher_dateityp_wird_erklaert(client: TestClient) -> None:
    """Der Grund gehoert Mia gezeigt, nicht nur ein Statuscode."""
    eintrag = client.post("/api/sammlung", json={"titel": "X"}).json()["eintrag"]

    antwort = client.post(
        f"/api/sammlung/{eintrag['id']}/beleg",
        files={"datei": ("virus.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert antwort.status_code == 400
    assert "Bild" in antwort.json()["detail"]


def test_api_unbekannter_eintrag(client: TestClient) -> None:
    antwort = client.post("/api/sammlung/9999/beleg", files={"datei": ("a.jpg", JPG, "image/jpeg")})
    assert antwort.status_code == 404


def test_api_nextcloud_weg_gibt_502(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ein Netzfehler ist kein Fehler von Mia: 502 statt 400."""
    import src.api

    async def kaputt(inhalt: bytes, name: str) -> tuple[str, str]:
        raise httpx.ConnectError("keine Verbindung")

    monkeypatch.setattr(src.api.belege, "ablegen", kaputt)

    eintrag = client.post("/api/sammlung", json={"titel": "X"}).json()["eintrag"]
    antwort = client.post(
        f"/api/sammlung/{eintrag['id']}/beleg", files={"datei": ("a.jpg", JPG, "image/jpeg")}
    )
    assert antwort.status_code == 502


# --- Verschieben (Ordnervorschlag angenommen) -----------------------------


class FakeMove:
    """Ein Nextcloud, das MOVE mitschreibt."""

    def __init__(self, belegte: set[str] | None = None) -> None:
        self.belegte = belegte or set()
        self.moves: list[tuple[str, str]] = []

    async def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method != "MOVE":
            return httpx.Response(405)
        ziel = str(httpx.URL(request.headers["Destination"]).path)
        if ziel in self.belegte:
            return httpx.Response(412)
        self.belegte.add(ziel)
        self.moves.append((str(request.url.path), ziel))
        return httpx.Response(201)


@pytest.fixture
def nextcloud_move(monkeypatch: pytest.MonkeyPatch) -> FakeMove:
    fake = FakeMove()
    monkeypatch.setattr(belege.settings, "nextcloud_url", "https://nas.example")
    monkeypatch.setattr(belege.settings, "nextcloud_user", "mia")
    monkeypatch.setattr(belege.settings, "nextcloud_password", "geheim")

    echt = httpx.AsyncClient

    def gefaelscht(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(fake.handler)
        return echt(*args, **kwargs)

    monkeypatch.setattr(belege.httpx, "AsyncClient", gefaelscht)
    return fake


async def test_verschieben_liefert_den_neuen_pfad(nextcloud_move: FakeMove) -> None:
    neu = await belege.verschieben(
        "/Dokumente/00 Belege/2026-09-03 Bescheid.pdf", "/Dokumente/01 Persönliches"
    )
    assert neu == "/Dokumente/01 Persönliches/2026-09-03 Bescheid.pdf"
    assert len(nextcloud_move.moves) == 1


async def test_verschieben_ueberschreibt_nichts(monkeypatch: pytest.MonkeyPatch) -> None:
    """WebDAV ueberschreibt beim MOVE per Vorgabe, und zwar in die falsche Richtung.

    Bei gleichem Namen verschwaende das aeltere Original in Mias Ablage und
    der frische Scan bliebe. Deshalb ``Overwrite: F`` und durchnummerieren.
    """
    fake = FakeMove(belegte={"/remote.php/dav/files/mia/Dokumente/01 Ziel/Bescheid.pdf"})
    monkeypatch.setattr(belege.settings, "nextcloud_url", "https://nas.example")
    monkeypatch.setattr(belege.settings, "nextcloud_user", "mia")
    monkeypatch.setattr(belege.settings, "nextcloud_password", "geheim")
    echt = httpx.AsyncClient
    monkeypatch.setattr(
        belege.httpx,
        "AsyncClient",
        lambda *a, **k: echt(*a, **{**k, "transport": httpx.MockTransport(fake.handler)}),
    )

    neu = await belege.verschieben("/Dokumente/00 Belege/Bescheid.pdf", "/Dokumente/01 Ziel")
    assert neu == "/Dokumente/01 Ziel/Bescheid (2).pdf"


async def test_verschieben_legt_keinen_ordner_an(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vorgeschlagen wird nur, was es gibt. Ein Tippfehler baut keinen Ordner."""
    monkeypatch.setattr(belege.settings, "nextcloud_url", "https://nas.example")
    monkeypatch.setattr(belege.settings, "nextcloud_user", "mia")
    monkeypatch.setattr(belege.settings, "nextcloud_password", "geheim")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409)

    echt = httpx.AsyncClient
    monkeypatch.setattr(
        belege.httpx,
        "AsyncClient",
        lambda *a, **k: echt(*a, **{**k, "transport": httpx.MockTransport(handler)}),
    )

    with pytest.raises(belege.BelegError, match="gibt es nicht"):
        await belege.verschieben("/Dokumente/00 Belege/x.pdf", "/Dokumente/Tippfehler")


async def test_verschieben_lehnt_relative_pfade_ab(nextcloud_move: FakeMove) -> None:
    with pytest.raises(belege.BelegError):
        await belege.verschieben("/Dokumente/00 Belege/x.pdf", "Dokumente/01 Ziel")
    with pytest.raises(belege.BelegError, match="Ungültig"):
        await belege.verschieben("/Dokumente/00 Belege/x.pdf", "/Dokumente/../../etc")
    assert nextcloud_move.moves == []


def test_api_verschieben_nur_aus_dem_belegordner(client: TestClient) -> None:
    """Ein Endpunkt, der jede Datei schieben kann, ist ein Schreibrecht auf alles."""
    antwort = client.post(
        "/api/dokumente/verschieben",
        json={
            "pfad": "/Dokumente/01 Persönliches/Geburtsurkunde.pdf",
            "ordner": "/Dokumente/07 Projekte",
        },
    )
    assert antwort.status_code == 400
    assert "Belege" in antwort.json()["detail"]


def test_api_verschieben_zieht_den_index_nach(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sonst stuende der Beleg bis zum naechsten Crawl auf "nicht mehr am alten Ort"."""
    import src.api
    from src.main import get_store

    async def fake(alt: str, ziel: str) -> str:
        return f"{ziel}/{alt.rsplit('/', 1)[-1]}"

    monkeypatch.setattr(src.api.belege, "verschieben", fake)

    store = get_store()
    eintrag = client.post("/api/sammlung", json={"titel": "Bescheid"}).json()["eintrag"]
    alt = "/Dokumente/00 Belege/2026-09-03 Bescheid.pdf"
    store.upsert_document(
        {
            "source": "nextcloud",
            "path": alt,
            "name": "2026-09-03 Bescheid.pdf",
            "folder": "/Dokumente/00 Belege",
            "ext": ".pdf",
        }
    )
    store.link_document(eintrag["id"], "nextcloud", alt, "2026-09-03 Bescheid.pdf")

    antwort = client.post(
        "/api/dokumente/verschieben", json={"pfad": alt, "ordner": "/Dokumente/01 Persönliches"}
    )
    assert antwort.status_code == 200
    neu = antwort.json()["pfad"]
    assert neu == "/Dokumente/01 Persönliches/2026-09-03 Bescheid.pdf"

    # Der Anhang zeigt weiter auf die Datei, nicht auf eine Luecke.
    anhaenge = client.get(f"/api/sammlung/{eintrag['id']}/dokumente").json()["dokumente"]
    assert [a["path"] for a in anhaenge] == [neu]
    assert not anhaenge[0].get("fehlt")


# --- Umbenennen (Namensvorschlag angenommen) ------------------------------


async def test_umbenennen_bleibt_im_selben_ordner(nextcloud_move: FakeMove) -> None:
    neu = await belege.umbenennen(
        "/Dokumente/00 Belege/2026-09-03 Bescheid.pdf",
        "2026-08-03 Hansestadt Buxtehude Meldebescheinigung",
    )
    assert neu == "/Dokumente/00 Belege/2026-08-03 Hansestadt Buxtehude Meldebescheinigung.pdf"


async def test_umbenennen_behaelt_die_endung(nextcloud_move: FakeMove) -> None:
    """Die Endung kam beim Upload aus dem Dateikopf, der Vorschlag hat da nichts zu melden.

    Eine PDF, die ploetzlich ``.jpg`` heisst, oeffnet niemand mehr.
    """
    neu = await belege.umbenennen("/Dokumente/00 Belege/x.pdf", "Bescheid.jpg")
    assert neu.endswith(".pdf")
    assert neu == "/Dokumente/00 Belege/Bescheid.pdf"


async def test_umbenennen_laesst_den_belegordner_nicht_verlassen(
    nextcloud_move: FakeMove,
) -> None:
    """Ein Schraegstrich im Vorschlag waere ein Schreibrecht auf die ganze Ablage.

    Der Text kommt aus einem Foto: auf einem Blatt Papier kann alles stehen.
    """
    neu = await belege.umbenennen("/Dokumente/00 Belege/x.pdf", "../../01 Persönliches/Ausweis")
    assert neu.startswith("/Dokumente/00 Belege/")
    assert ".." not in neu.split("/")


async def test_umbenennen_ueberschreibt_nichts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zwei Blaetter mit demselben Betreff sind der Normalfall, nicht die Ausnahme."""
    fake = FakeMove(belegte={"/remote.php/dav/files/mia/Dokumente/00 Belege/Bescheid.pdf"})
    monkeypatch.setattr(belege.settings, "nextcloud_url", "https://nas.example")
    monkeypatch.setattr(belege.settings, "nextcloud_user", "mia")
    monkeypatch.setattr(belege.settings, "nextcloud_password", "geheim")
    echt = httpx.AsyncClient
    monkeypatch.setattr(
        belege.httpx,
        "AsyncClient",
        lambda *a, **k: echt(*a, **{**k, "transport": httpx.MockTransport(fake.handler)}),
    )

    neu = await belege.umbenennen("/Dokumente/00 Belege/Scan.pdf", "Bescheid")
    assert neu == "/Dokumente/00 Belege/Bescheid (2).pdf"


async def test_umbenennen_lehnt_leere_namen_ab(nextcloud_move: FakeMove) -> None:
    with pytest.raises(belege.BelegError):
        await belege.umbenennen("/Dokumente/00 Belege/x.pdf", "   ")
    assert nextcloud_move.moves == []


def test_api_umbenennen_nur_aus_dem_belegordner(client: TestClient) -> None:
    """In Mias gewachsener Ablage benennt Mia OS nichts um."""
    antwort = client.post(
        "/api/dokumente/umbenennen",
        json={"pfad": "/Dokumente/01 Persönliches/Geburtsurkunde.pdf", "name": "Irgendwas"},
    )
    assert antwort.status_code == 400
    assert "Belege" in antwort.json()["detail"]


def test_api_umbenennen_zieht_namen_und_anhang_nach(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Der Anhang merkt sich einen Namen, und der stuende sonst veraltet am Eintrag."""
    import src.api
    from src.main import get_store

    async def fake(alt: str, name: str) -> str:
        return f"{alt.rsplit('/', 1)[0]}/{name}.pdf"

    monkeypatch.setattr(src.api.belege, "umbenennen", fake)

    store = get_store()
    eintrag = client.post("/api/sammlung", json={"titel": "Bescheid"}).json()["eintrag"]
    alt = "/Dokumente/00 Belege/2026-09-03 Bescheid.pdf"
    store.upsert_document(
        {
            "source": "nextcloud",
            "path": alt,
            "name": "2026-09-03 Bescheid.pdf",
            "folder": "/Dokumente/00 Belege",
            "ext": ".pdf",
        }
    )
    store.link_document(eintrag["id"], "nextcloud", alt, "2026-09-03 Bescheid.pdf")

    antwort = client.post(
        "/api/dokumente/umbenennen",
        json={"pfad": alt, "name": "2026-08-03 Hansestadt Buxtehude Meldebescheinigung"},
    )
    assert antwort.status_code == 200
    neu = antwort.json()["pfad"]

    anhaenge = client.get(f"/api/sammlung/{eintrag['id']}/dokumente").json()["dokumente"]
    assert [a["path"] for a in anhaenge] == [neu]
    assert anhaenge[0]["name"] == "2026-08-03 Hansestadt Buxtehude Meldebescheinigung.pdf"
    assert not anhaenge[0].get("fehlt")


def test_api_umbenennen_laesst_den_gelesenen_text_stehen(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Der Text haengt am Dokument, nicht am Namen. Sonst waere die Suche im Beleg still kaputt."""
    import src.api
    from src.main import get_store

    async def fake(alt: str, name: str) -> str:
        return f"{alt.rsplit('/', 1)[0]}/{name}.pdf"

    monkeypatch.setattr(src.api.belege, "umbenennen", fake)

    store = get_store()
    alt = "/Dokumente/00 Belege/Scan.pdf"
    store.upsert_document(
        {"source": "nextcloud", "path": alt, "name": "Scan.pdf", "folder": "/Dokumente/00 Belege"}
    )
    store.set_document_text("nextcloud", alt, "Aktenzeichen 43-044-26211-000896")

    neu = client.post(
        "/api/dokumente/umbenennen", json={"pfad": alt, "name": "Meldebescheinigung"}
    ).json()["pfad"]

    assert "43-044" in store.document_text("nextcloud", neu)
    assert [t["path"] for t in store.search_documents("43-044")] == [neu]
