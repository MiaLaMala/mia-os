#!/usr/bin/env bash
# Pull-Deployment: laeuft AUF dem LXC, holt sich neue Commits selbst.
# Der Homelab-Container ist von aussen nicht erreichbar, deshalb zieht der
# Server statt dass GitHub pusht.
#
# Health-Gate: wird die neue Version nicht gesund, wird auf den vorherigen
# Commit zurueckgerollt und neu gebaut.

set -euo pipefail

REPO_DIR=/opt/mia-os/src-repo
COMPOSE_DIR=/opt/mia-os
HEALTH_URL=http://localhost:8080/health

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
git reset -q --hard origin/main

build_and_start() {
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
    cd "$COMPOSE_DIR"
    docker compose up -d --force-recreate > /dev/null 2>&1
}

healthy() {
    for _ in $(seq 1 30); do
        if curl -fsS --max-time 3 "$HEALTH_URL" > /dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

build_and_start

if healthy; then
    echo "$(date -Is) deployment gesund auf $NEW"
    docker image prune -f > /dev/null
    exit 0
fi

echo "$(date -Is) FEHLER: nicht gesund, rolle zurueck auf $PREV" >&2
cd "$REPO_DIR"
git reset -q --hard "$PREV"
build_and_start

if healthy; then
    echo "$(date -Is) rollback erfolgreich" >&2
else
    echo "$(date -Is) rollback ebenfalls fehlgeschlagen, manueller Eingriff noetig" >&2
fi
exit 1
