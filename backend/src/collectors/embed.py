"""Vektoren fuer den Ordnervorschlag nachrechnen.

Der Vorschlag beim Upload braucht die Schwerpunkte der Sachordner, und die
entstehen aus den Vektoren der Dateien darin. Sie hier im Hintergrund zu
rechnen statt beim Upload hat einen einfachen Grund: 161 Dokumente einzubetten
dauert gut eine Minute, und Mia steht dabei mit dem Handy vor dem Bescheid.

**Nur Dateinamen.** Der Index enthaelt aus dem Bestand keine Inhalte, und
daran aendert dieser Collector nichts. Was er zum Embedding-Server schickt,
ist genau das, was auch in der Suche steht.

**Gedeckelt je Lauf.** Beim ersten Mal sind es alle, danach nur noch, was neu
dazugekommen oder umbenannt worden ist, also fast immer null. Der Deckel
schuetzt den Fall, in dem jemand einen ganzen Ordner in die Nextcloud kippt:
lieber ueber zwei Laeufe verteilt als eine Stunde am Stueck.
"""

from __future__ import annotations

from src import ordner
from src.collectors.base import Collector
from src.config import settings

# Wie viele Dokumente ein Lauf hoechstens einbettet. Bei 0,25 s je Stueck sind
# das gut zwei Minuten, und der Sammellauf hat sonst nichts zu tun.
PRO_LAUF = 300

# Wie viele in einem Aufruf zusammen gehen. llama.cpp nimmt Stapel entgegen,
# und ein Aufruf je Datei waere ueberwiegend Verbindungsaufbau.
STAPEL = 16


class EmbedCollector(Collector):
    """Rechnet fehlende Dokument-Vektoren nach."""

    name = "embed"
    category = "dokumente"

    def is_configured(self) -> bool:
        return bool(settings.embed_url)

    async def collect(self) -> None:
        offen = self.store.documents_ohne_embed(limit=PRO_LAUF)
        if not offen:
            self.store.record("dokumente", "embed_offen", 0)
            return

        fertig = 0
        for i in range(0, len(offen), STAPEL):
            teil = offen[i : i + STAPEL]
            vektoren = await ordner.einbetten([ordner.dokumenttext(d["name"]) for d in teil])
            # Leere Antwort heisst: der Server mag gerade nicht. Abbrechen
            # statt weiterzuklopfen, der naechste Lauf holt es nach.
            if not vektoren:
                break
            for dokument, vektor in zip(teil, vektoren, strict=True):
                self.store.set_document_embed(
                    int(dokument["id"]), ordner.packen(vektor), str(dokument["name"])
                )
                fertig += 1

        self.store.record("dokumente", "embed_neu", fertig)
        self.store.record("dokumente", "embed_offen", len(offen) - fertig)
