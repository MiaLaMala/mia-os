# Mia OS im Betrieb

Was zu tun ist, wenn etwas klemmt. Jeder Abschnitt hat dieselbe Form:
woran man es erkennt, was sofort hilft, wo die Ursache liegt.

Alle Befehle laufen über Proxmox, weil der LXC keinen direkten SSH-Zugang
hat:

```
ssh root@<proxmox> 'pct exec 141 -- bash -lc "<befehl>"'
```

## Die drei Auskünfte

| Adresse | Frage | Rot heißt |
|---|---|---|
| `/health` | Läuft der Prozess? | neu starten |
| `/health/bereit` | Darf Verkehr hierhin? | kein Verkehr, aber nicht neu starten |
| `/metrics` | Zahlen für Prometheus | nichts, das ist nur Messung |

`/health` fasst absichtlich nichts an, was ausfallen kann. Eine Liveness,
die von der Datenbank abhängt, startet den Container bei einer langsamen
Abfrage neu und macht aus einem kleinen Problem einen Ausfall.

`/health/bereit` antwortet 503, wenn die Datenbank nicht schreibbar ist oder
die Sammelschleife gestorben ist. Alte Sammeldaten färben **nicht** rot: Mia
kann mit stundenalten Zahlen weiterhin Termine ansehen, suchen und
schreiben. Das steht als Warnung in der Antwort, nicht als Ausfall.

`/health` ist offen, weil Uptime Kuma es von außen braucht und es nur „ok"
sagt. Die anderen beiden verlangen dieselbe Kopplung wie die Schnittstelle:
sie verraten, welche Quellen klemmen und wie groß die Datenbank ist, und das
ist eine Landkarte für jemanden, der einen Weg herein sucht.

## Die App startet nicht

**Erkennen:** `docker ps` zeigt den Container als `Restarting` oder gar
nicht. `/health` antwortet nicht.

**Sofort:**
```
pct exec 141 -- docker logs mia-os --tail 50
pct exec 141 -- docker ps -a --filter name=mia-os
```

**Ursache suchen.** Die häufigsten drei:

Fehlende oder kaputte `.env`. Der Dienst startet trotzdem, einzelne
Collector melden dann „nicht konfiguriert". Wenn er gar nicht hochkommt,
steht es in den ersten zehn Zeilen des Logs.

Die Schlüsseldateien in `/opt/mia-os/` gehören nicht UID 1000. Der Container
läuft als `mia` und kann sie dann nicht lesen. Zu erkennen an
`Permission denied` mit einem Pfad unter `/etc/mia-os/`.

Das Abbild wurde neu gebaut und der Bau ist mittendrin gescheitert. Dann
steht in `journalctl -u mia-os-deploy.service` das Health-Gate mit einer
Absage. Der alte Container läuft in diesem Fall weiter, das ist der Sinn des
Gates.

**Zurück auf einen laufenden Stand:**
```
pct exec 141 -- bash -lc "cd /opt/mia-os && docker compose up -d"
pct exec 141 -- docker ps --filter name=mia-os --format '{{.Status}}'
```

## Ein Collector hängt

**Erkennen:** `/health/bereit` listet die Quelle mit `"ok": false` und
`"eingerichtet": true`. In `/metrics` steht `mia_os_quelle_ok{quelle="…"} 0`.

**Sofort:** nichts. Ein einzelner Collector hält den Dienst nicht auf, der
Rest sammelt weiter. Das ist der Vertrag aus `collectors/base.py`: ein
Collector wirft nie nach oben.

**Ursache:** der letzte Fehler steht in der Datenbank.
```
pct exec 141 -- python3 -c "
import sqlite3
db=sqlite3.connect('/var/lib/docker/volumes/mia-os_mia-os-data/_data/mia-os.db')
for r in db.execute('SELECT collector,ok,error,ran_at FROM collector_runs ORDER BY ran_at DESC LIMIT 15'):
    print(r)"
```

`kuma` mit `TimeoutError` heißt meist, dass der SSH-Weg zum Proxmox-Host
klemmt. `termine` mit einem HTTP-Fehler heißt, dass das CalDAV-Passwort
abgelaufen ist.

Quellen mit `"eingerichtet": false` sind kein Fehler. Moodle ist bewusst
nicht eingerichtet, und ein Monitor, der dauerhaft rot leuchtet, wird nach
drei Tagen ignoriert. Dann ist er schlechter als keiner.

## Die Datenbank ist voll oder langsam

**Erkennen:** `mia_os_db_abfrage_ms` steigt über 1000, oder `/health/bereit`
meldet `"schreibbar": false`. `df -h /` zeigt die Wurzel über 90 Prozent.

**Sofort:** alte Messwerte wegwerfen. Die Zeitreihen sind der Teil, der
wächst; Dokumente und Termine sind es nicht.
```
pct exec 141 -- docker exec mia-os python -c "
from src.main import get_store
print('geloescht:', get_store().prune(keep_days=180))"
```

Danach die Datei wirklich schrumpfen lassen. `DELETE` gibt den Platz in
SQLite nicht an die Platte zurück, `VACUUM` tut es:
```
pct exec 141 -- docker exec mia-os python -c "
import sqlite3; sqlite3.connect('/var/lib/mia-os/mia-os.db').execute('VACUUM')"
```

**Ursache:** die Sicherungen unter `/var/backups/mia-os` sind die zweite
übliche Quelle für eine volle Platte. Vierzehn Stände liegen dort, jeder
etwa anderthalb Megabyte. Wenn es mehr sind, ist das Aufräumen im
Sicherungsskript nicht gelaufen.

## Ein Deploy ist gescheitert

**Erkennen:** `journalctl -u mia-os-deploy.service -n 30 --output cat` endet
ohne die Zeile „deployment gesund auf <sha>".

**Sofort:** nichts. Das Health-Gate hat den alten Container stehen lassen,
Mia OS läuft weiter. Genau so ist es am 13.09.2026 passiert, als das
Dockerfile umgezogen war.

**Ursache suchen:** der Bau selbst schlägt fehl (dann steht der
Compiler- oder npm-Fehler im Log), oder der neue Container kommt hoch und
bleibt rot (dann steht dort der Health-Check).

**Auf den vorigen Stand zurück:**
```
pct exec 141 -- docker images ghcr.io/mialamala/mia-os --format '{{.Tag}} {{.CreatedSince}}'
pct exec 141 -- bash -lc "cd /opt/mia-os && docker compose up -d"
```

## Sicherung und Rückspiel

Der Timer `mia-os-sicherung.timer` läuft täglich um 03:15 und macht beides
in einem Lauf: sichern und die Sicherung in eine Wegwerf-Datenbank
zurückspielen. Erst wenn das Rückspiel die Tabellen wiederfindet, gilt der
Lauf als bestanden. Eine Sicherung, die nie zurückgespielt wurde, ist keine
Sicherung, sondern eine Datei.

```
pct exec 141 -- systemctl status mia-os-sicherung.timer
pct exec 141 -- journalctl -u mia-os-sicherung.service -n 30 --output cat
pct exec 141 -- ls -la /var/backups/mia-os/
```

Von Hand prüfen, ohne eine neue anzulegen:
```
pct exec 141 -- python3 /opt/mia-os/sicherung.py --nur-pruefen /var/backups/mia-os/<datei>
```

Eine Sicherung wirklich zurückspielen (der Container muss dafür aus sein,
sonst schreibt er weiter in die Datei, die gerade ersetzt wird):
```
pct exec 141 -- docker stop mia-os
pct exec 141 -- bash -lc "gunzip -c /var/backups/mia-os/<datei> > /var/lib/docker/volumes/mia-os_mia-os-data/_data/mia-os.db"
pct exec 141 -- bash -lc "chown 1000:1000 /var/lib/docker/volumes/mia-os_mia-os-data/_data/mia-os.db"
pct exec 141 -- docker start mia-os
```

## Wie viel das Ding hält

Gemessen am 14.09.2026 mit `bombardier` gegen eine lokale Instanz, leere
Datenbank, uvicorn ohne Reverse Proxy. **Auf einem Rechner mit vier Kernen,
nicht auf dem LXC:** der hat zwei, dort ist grob mit der Hälfte zu rechnen.

| Pfad | Anfragen/s | Mittel | 95% | 99% |
|---|---|---|---|---|
| `/health` | 1157 | 8,6 ms | 13,4 ms | 15,5 ms |
| `/` (App-Hülle) | 1011 | 9,9 ms | | |
| `/health/bereit` | 398 | 25,1 ms | | |
| `/api/handgelenk` | 349 | 28,6 ms | | |
| `/api/briefing` | 188 | 53,1 ms | 82,6 ms | 87,9 ms |

Jeweils zehn gleichzeitige Verbindungen, keine einzige Antwort mit
Fehlercode.

Der interessante Teil ist, wo es bricht. `/api/briefing` unter steigender
Last:

| Gleichzeitig | Anfragen/s | Mittel | 99% |
|---|---|---|---|
| 10 | 188 | 53 ms | 88 ms |
| 25 | 205 | 121 ms | 218 ms |
| 50 | 196 | 252 ms | 468 ms |
| 100 | 197 | 497 ms | 1,47 s |

Der Durchsatz steht ab etwa 200 Anfragen pro Sekunde und bewegt sich nicht
mehr, egal wie viele gleichzeitig anklopfen. Was steigt, ist nur die
Wartezeit. Das ist das erwartete Bild für einen Prozess, der an der CPU
hängt: mehr Nebenläufigkeit verteilt dieselbe Rechenzeit auf mehr Wartende.

Eingeordnet: Mia OS bedient eine Person, ein iPhone, einen Mac und ein
Display. Das sind Einzelanfragen, keine 200 pro Sekunde. Die Zahl ist
trotzdem nützlich, weil sie den Vergleichswert für später liefert. Fällt
`/api/briefing` irgendwann auf 20 pro Sekunde, ist etwas passiert, und ohne
diese Messung wüsste niemand, dass es früher zehnmal mehr war.

Selbst nachmessen:
```
bombardier -c 10 -d 20s -l http://127.0.0.1:8080/api/briefing
```

## Was bewusst nicht gebaut ist

**Kein Kubernetes.** Der LXC hat 1 GB RAM, k3s braucht allein für die
Steuerungsebene rund 512 MB. Der wichtigere Grund: ein Cluster für eine
Anwendung, die eine Person bedient, löst kein Problem, das hier existiert.

**Kein zweiter Container zum Ausgleichen der Last.** Die Zahlen oben zeigen,
dass ein Prozess für diesen Zweck weit überdimensioniert ist.

**Keine Alarme bei jedem einzelnen Fehlschlag.** Uptime Kuma hängt an ntfy;
was dort eingestellt gehört, ist eine Wiederholungsschwelle und eine
Ruhezeit nachts. Ein Alarm um drei Uhr, bei dem niemand etwas tun kann, ist
ein Alarm, den man abschaltet.
