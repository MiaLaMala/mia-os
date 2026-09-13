# Mia OS

Eine persönliche Zentrale: Termine, Aufgaben, Dokumente und der Zustand des
eigenen Homelabs an einer Stelle. Läuft im Browser, als Mac- und iPhone-App
und auf einem kleinen Display auf dem Schreibtisch.

Kein Fremdprodukt, weil keins passte. Grafana ist für Server-Metriken gebaut,
Homepage ist eine Linksammlung, Notion kann alles und nichts richtig. Hier
geht es um einen Tag: was jetzt ansteht, was noch offen ist, wo ein Beleg
liegt.

Gebaut für genau eine Person. Wer es nachbauen will, kann das gern tun, aber
es ist kein Produkt und will keins werden.

## Was drin ist

| Bereich | Quelle | Was man sieht |
|---|---|---|
| Heute | alles zusammen | der nächste Termin, was fällig ist |
| Termine | CalDAV | Tag, Woche, Monat |
| Sammlung | eigene Datenbank | Einträge mit Status, Feldern, Belegen |
| Dokumente | Nextcloud über WebDAV | Suche über einen Index, Vorschau, Editor |
| Berichtsheft | eigene Datenbank | Wochenblätter für die Ausbildung |
| Gesundheit | wger | Gewicht und Verlauf |
| Homelab | Proxmox, Uptime Kuma | Gäste, Auslastung, Störungen |

## Aufbau

```
Sammler (async)  ->  SQLite  ->  FastAPI  ->  Svelte
                                      \->  SwiftUI (Mac, iPhone)
                                      \->  ESP32-Display
```

Vier Entscheidungen, die den Rest erklären:

1. **Ein Sammler wirft nie nach oben.** Fällt eine Quelle aus, wird der
   Fehler protokolliert und die Kachel zeigt einen roten Punkt. Die Seite
   bleibt erreichbar.
2. **SQLite statt Zeitreihen-Datenbank.** Eine Datei, kein Server, Backup
   durch Kopieren. Bei stündlichen Werten völlig ausreichend.
3. **Dokumente werden nur indiziert, nie gespeichert.** Name, Pfad, Größe,
   Datum. Der Inhalt bleibt in der Nextcloud.
4. **Ohne Suchbegriff zeigt die Dokumentensuche keine Dateinamen**, nur
   Ordner und Anzahl. In solchen Ordnern liegen Ausweise und medizinische
   Unterlagen, auch von anderen Menschen. Eine Startseite, die sie auflistet,
   ist eine Datenpanne mit Komfortfunktion.

## Gestaltung

Steht in [DESIGN.md](DESIGN.md). Kurz: Gerüst vom System, Stimme von Mia OS.
Die Farben kommen aus einer einzigen Quelle (`farben.json`) und werden für
Web, Swift und das Display **erzeugt**, nie von Hand gepflegt. Ein Skript
rechnet dabei vierzehn Kontraste nach und bricht ab, wenn einer reißt.

## Entwickeln

```bash
python -m venv .venv
.venv/bin/pip install -e "backend[dev]"
cp .env.example .env          # eigene Zugänge eintragen

bash scripts/gates.sh         # alle Prüfungen auf einmal
.venv/bin/uvicorn src.main:app --reload --port 8080
```

Die Apple-Apps liegen unter `apple/`, das Baurezept steht in
[apple/README.md](apple/README.md). Es gibt keine `.xcodeproj` im Repo, das
Projekt wird mit XcodeGen aus `apple/project.yml` erzeugt.

## Betreiben

```bash
docker compose up -d
curl http://localhost:8080/health
```

Der Server steht in einem privaten Netz und ist von außen nicht erreichbar.
Deshalb **holt** er sich neue Versionen selbst: ein systemd-Timer führt
`deploy/pull-deploy.sh` aus, baut das Abbild, prüft `/health` und rollt bei
fehlendem Gesundheitscheck auf den vorherigen Commit zurück.

Werte, die nicht ins Repo gehören, liest der Deploy aus
`/etc/mia-os/deploy.env` auf dem Server.

## Sicherheit

Zugangsdaten kommen aus Umgebungsvariablen, nie aus dem Quelltext. Der
Container läuft als unprivilegierter Nutzer.

Apps melden sich mit einem Schlüssel an, den sie beim Koppeln bekommen.
Gespeichert wird nur dessen SHA-256-Abdruck: wer die Datenbank in die Hand
bekommt, kann sich damit nicht anmelden. Aus dem eigenen Netz geht es ohne
Anmeldung, dieselbe Grenze, die vorher schon galt.

## Lizenz

MIT
