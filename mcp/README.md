# mia-os-mcp

MCP-Server fuer Mia OS. Damit kann ein Assistent (Jana) direkt Eintraege,
Aufgaben und Seiten anlegen, statt Mia Sachen zu erzaehlen, die sie danach
selbst abtippt.

## Werkzeuge

| Werkzeug | Zweck |
| --- | --- |
| `briefing` | Was heute ansteht |
| `notiz` | Ein Satz rein, Mia OS deutet ihn (Datum, Gewicht, Mahlzeit) |
| `eintrag_anlegen` | Eintrag mit Feldern |
| `eintrag_aendern` | Felder oder eine einzelne Eigenschaft setzen |
| `eintraege_suchen` | Suche und Zeitraum |
| `aufgabe_anlegen` / `aufgabe_abhaken` / `aufgaben` | Aufgaben |
| `termine` | Kalender lesen |
| `suche` | Ueber alles suchen |
| `seiten` / `seite_anlegen` | Seitenbaum |
| `dokumente_suchen` | Nur Titel und Pfad, nie Inhalte |

## Grenzen, mit Absicht

- **Kein Loeschen.** Nichts kann vernichtet werden, hoechstens archiviert.
  Ein Assistent, der eine Anweisung falsch versteht, legt dann Muell an,
  statt etwas zu zerstoeren.
- **Keine Dokumentinhalte.** Im Index stehen Arztberichte und Ausweise.
- **Nur im eigenen Netz.** Der Server spricht mit der Mia-OS-Instanz.

## Einrichten

```bash
uv --directory mcp run mia-os-mcp
```

In der Hermes-Konfiguration:

```yaml
mia-os:
  command: uv
  args: ["--directory", "/home/openclaw/projects/mia-os/mcp", "run", "mia-os-mcp"]
```

`MIA_OS_URL` setzt die Adresse (Vorgabe `http://localhost:8080`).

## Warum das nicht veraltet

`tests/test_mcp_deckung.py` vergleicht die Routen aus `src/api.py` mit den
Pfaden im Serverquelltext. Kommt ein Endpunkt dazu, wird der Test rot,
bis er entweder ein Werkzeug bekommt oder mit Begruendung in
`BEWUSST_AUSSEN` steht. Wird einer umbenannt, faellt das ebenfalls auf,
statt erst im Gespraech. Ein dritter Test haelt fest, dass kein DELETE
in den Server rutscht.
