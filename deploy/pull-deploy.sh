#!/usr/bin/env bash
# Pull-Deployment: laeuft AUF dem LXC, holt sich neue Commits selbst.
# Der Homelab-Container ist von aussen nicht erreichbar, deshalb zieht der
# Server statt dass GitHub pusht.
#
# Rollback ueber das alte Abbild, nicht ueber einen Neubau
# --------------------------------------------------------
# Die vorige Fassung rollte zurueck, indem sie den alten Commit auscheckte
# und **neu baute**. Das dauert auf den zwei Kernen des LXC rund acht
# Minuten, und die laufen genau dann, wenn Mia OS gerade kaputt ist. Acht
# Minuten Ausfall, um einen Stand wiederherzustellen, der als fertiges
# Abbild bereits auf der Platte liegt.
#
# Jetzt wird das alte Abbild vor dem Bau umbenannt und im Fehlerfall direkt
# wieder gestartet. Das dauert Sekunden. Der Neubau bleibt als letzte
# Rueckfalloption, falls das alte Abbild verschwunden ist.
#
# Geprueft wird ausserdem die Bereitschaft, nicht nur die Liveness:
# ``/health`` antwortet auch dann mit "ok", wenn die Datenbank klemmt oder
# die Sammelschleife gar nicht erst angelaufen ist. Genau diese Faelle soll
# ein Deploy-Gate fangen.

set -euo pipefail

REPO_DIR=/opt/mia-os/src-repo
COMPOSE_DIR=/opt/mia-os
BASIS_URL=http://localhost:8080
HEALTH_URL="$BASIS_URL/health"
BEREIT_URL="$BASIS_URL/health/bereit"

# Werte, die nicht ins oeffentliche Repo gehoeren (etwa PVE_HOST fuer den
# Kuma-Zugriff). Die Datei liegt nur auf dem Server. Fehlt sie, laeuft der
# Deploy trotzdem, nur ohne diese Zusaetze.
if [ -f /etc/mia-os/deploy.env ]; then
    # shellcheck disable=SC1091
    set -a; . /etc/mia-os/deploy.env; set +a
fi

cd "$REPO_DIR"

PREV=$(git rev-parse HEAD)
git fetch -q origin main
NEW=$(git rev-parse origin/main)

if [ "$PREV" = "$NEW" ]; then
    echo "$(date -Is) keine Aenderung ($PREV)"
    exit 0
fi

echo "$(date -Is) neue Version: $PREV -> $NEW"

# Das laufende Abbild beiseitelegen, BEVOR der Bau es ueberschreibt.
# ``docker build -t mia-os:local`` nimmt dem alten Abbild nur den Namen, der
# Inhalt bleibt als namenloses Abbild liegen und faellt beim naechsten
# ``image prune`` weg. Mit einem eigenen Namen ueberlebt es.
ALT_VORHANDEN=0
if docker image inspect mia-os:local > /dev/null 2>&1; then
    docker tag mia-os:local mia-os:vorher
    ALT_VORHANDEN=1
    echo "$(date -Is) altes Abbild gesichert als mia-os:vorher"
fi

git reset -q --hard origin/main

bauen() {
    # Der Bau-Kontext bleibt die Repo-Wurzel, das Dockerfile liegt seit der
    # Trennung unter backend/. Der Kontext MUSS die Wurzel bleiben: die erste
    # Stufe baut das Frontend und braucht dafuer frontend/.
    #
    # PVE_HOST kommt aus /etc/mia-os/deploy.env und steht bewusst nicht im
    # Repo: das ist oeffentlich, und die Adresse gehoert in ein privates Netz.
    # Fehlt sie, baut das Abbild trotzdem, nur der Kuma-Zugriff bleibt still
    # aus.
    docker build -q -f "$REPO_DIR/backend/Dockerfile" \
        --build-arg "PVE_HOST=${PVE_HOST:-}" \
        -t mia-os:local "$REPO_DIR" > /dev/null
}

starten() {
    cd "$COMPOSE_DIR"
    docker compose up -d --force-recreate > /dev/null 2>&1
}

lebt() {
    # Liveness: antwortet der Prozess ueberhaupt? Grosszuegig, weil der
    # Container erst hochfahren muss.
    for _ in $(seq 1 30); do
        if curl -fsS --max-time 3 "$HEALTH_URL" > /dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

bereit() {
    # Readiness: Datenbank erreichbar und beschreibbar, Sammelschleife laeuft.
    # Kuerzeres Fenster, weil der Prozess zu diesem Zeitpunkt schon antwortet.
    #
    # Faellt der Endpunkt weg (aeltere Fassung ohne Betriebsauskunft), zaehlt
    # die Liveness allein. Sonst wuerde ein Rueckrollen auf einen alten Stand
    # daran scheitern, dass dieser den neuen Endpunkt nicht kennt.
    local code
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BEREIT_URL" || echo 000)
    if [ "$code" = "404" ]; then
        echo "$(date -Is) Hinweis: /health/bereit fehlt in dieser Fassung, pruefe nur Liveness"
        return 0
    fi
    for _ in $(seq 1 15); do
        if curl -fsS --max-time 5 "$BEREIT_URL" > /dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

gesund() {
    lebt && bereit
}

bauen
starten

if gesund; then
    echo "$(date -Is) deployment gesund auf $NEW"
    docker image rm mia-os:vorher > /dev/null 2>&1 || true
    docker image prune -f > /dev/null
    exit 0
fi

echo "$(date -Is) FEHLER: nicht gesund auf $NEW" >&2

# Erst der schnelle Weg: das alte Abbild wieder unter den erwarteten Namen
# und neu starten. Sekunden statt Minuten.
if [ "$ALT_VORHANDEN" = "1" ]; then
    echo "$(date -Is) rolle zurueck auf das vorige Abbild" >&2
    docker tag mia-os:vorher mia-os:local
    git reset -q --hard "$PREV"
    starten
    if gesund; then
        echo "$(date -Is) rollback erfolgreich, wieder auf $PREV" >&2
        exit 1
    fi
    echo "$(date -Is) altes Abbild kommt ebenfalls nicht hoch" >&2
fi

# Letzte Rueckfalloption: den alten Stand neu bauen. Dauert Minuten, ist aber
# besser als ein stehendes Mia OS.
echo "$(date -Is) baue den alten Stand $PREV neu" >&2
git reset -q --hard "$PREV"
bauen
starten

if gesund; then
    echo "$(date -Is) rollback ueber Neubau erfolgreich" >&2
else
    echo "$(date -Is) rollback ebenfalls fehlgeschlagen, manueller Eingriff noetig" >&2
fi
exit 1
