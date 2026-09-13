# Mehrstufig: Build-Abhaengigkeiten landen nicht im finalen Image.

# Stufe 1: das Svelte-Frontend bauen. Alles wird hier erzeugt und spaeter aus
# dem eigenen Container ausgeliefert. Kein CDN: auf einer Seite mit Ausweisen
# und Arztunterlagen wird nichts von fremden Servern nachgeladen.
FROM node:24-slim AS frontend

WORKDIR /frontend
# Erst die Paketlisten kopieren: solange sie sich nicht aendern, nutzt Docker
# die zwischengespeicherte Installation und der Build bleibt schnell.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit

COPY frontend/ ./
# Das Ergebnis landet ausserhalb von /frontend, deshalb der Umweg.
RUN mkdir -p /gebaut && npm run build && cp -r /backend/src/web/static/gebaut/. /gebaut/

FROM python:3.13-slim AS builder

WORKDIR /build
COPY backend/pyproject.toml ./
COPY backend/src ./src
COPY backend/scripts ./scripts
# Die Git-Historie mitnehmen, aber nur fuer diesen Schritt: daraus entsteht
# version.json (Nummer plus Aenderungsverlauf). Im fertigen Abbild landet sie
# nicht, dort liegt nur das erzeugte JSON.
COPY .git ./.git

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    # Ein Klon ohne Historie oder ein Build aus einem Tarball soll das Abbild
    # nicht scheitern lassen: das Skript faengt das selbst ab und schreibt
    # eine ehrlich leere Fassung.
    && git config --global --add safe.directory /build \
    && python scripts/version_bauen.py \
    && apt-get purge -y git && apt-get autoremove -y

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir .

FROM python:3.13-slim

# openssh-client fuer den lesenden Zugriff auf die Uptime-Kuma-Datenbank.
# Der dazugehoerige Schluessel darf auf dem Proxmox-Host genau eine Abfrage
# ausfuehren (siehe collectors/kuma.py), deshalb ist das kein offenes Tor.
#
# tesseract-ocr liest den Text aus selbst gescannten Belegen. Die deutsche
# Sprachdatei ist ein eigenes Paket und ohne sie faellt Tesseract still auf
# Englisch zurueck: aus "Gebühr" wird dann "Gebuhr" und aus "ß" ein "B".
# osd bleibt draussen, das Blatt ist nach dem Scanner bereits gerade.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openssh-client \
        tesseract-ocr \
        tesseract-ocr-deu \
        git \
    && rm -rf /var/lib/apt/lists/*

# Nicht als root laufen.
RUN useradd --create-home --shell /bin/bash --uid 1000 mia \
    && mkdir -p /var/lib/mia-os \
    && chown -R mia:mia /var/lib/mia-os

COPY --from=builder /opt/venv /opt/venv
COPY --chown=mia:mia backend/src /app/src
# version.json entsteht erst im Builder und liegt deshalb nicht im Kontext.
# Ohne diese Zeile zeigt die About-Seite im Container "unbekannt", waehrend
# sie lokal die richtige Nummer anzeigt: der unangenehmste Fehler, weil er
# nur dort auftritt, wo man nicht hinsieht.
COPY --from=builder --chown=mia:mia /build/src/version.json /app/src/version.json
# Das gebaute Frontend aus Stufe 1 dazu.
COPY --from=frontend --chown=mia:mia /gebaut /app/src/web/static/gebaut

# Die Adresse des Virtualisierungs-Hosts, von dem die Kuma-Daten kommen.
# Als Bau-Argument, damit im Abbild keine Adresse aus einem privaten Netz
# steht. Wird beim Bauen gesetzt:
#
#     docker build --build-arg PVE_HOST=<adresse> .
#
# Ohne Angabe bleibt der SSH-Eintrag weg und der Kuma-Zugriff still aus.
ARG PVE_HOST=""

# SSH-Zuordnung fuer den Kuma-Zugriff, die Display-Firmware und die Apps.
#
# Achtung, Stolperstein: der blosse Name "pve" loest in manchen Netzen ueber
# die Suchdomain auf den Reverse Proxy auf, NICHT auf den Host selbst.
# Deshalb steht die Zuordnung hier ausdruecklich drin.
#
# Zwei GitHub-Eintraege mit ZWEI verschiedenen Schluesseln, und das ist kein
# Versehen: ein Deploy-Key gilt bei GitHub immer nur fuer ein Repo. Der
# firmware_key gehoert zu jana-desktop (Display-Firmware), der apps_key zu
# mia-os selbst (der Zweig mit den gebauten Mac- und iPhone-Apps). Den einen
# fuer beides zu nehmen endet in "Repository not found", und die Meldung
# klingt so, als gaebe es den Zweig nicht.
RUN mkdir -p /home/mia/.ssh \
    && printf '%s\n' \
        'Host pve' \
        "    HostName ${PVE_HOST}" \
        '    User root' \
        '    IdentityFile /etc/mia-os/kuma_key' \
        '    IdentitiesOnly yes' \
        '    StrictHostKeyChecking accept-new' \
        '    UserKnownHostsFile /home/mia/.ssh/known_hosts' \
        '' \
        'Host github-jana-desktop' \
        '    HostName github.com' \
        '    User git' \
        '    IdentityFile /etc/mia-os/firmware_key' \
        '    IdentitiesOnly yes' \
        '    StrictHostKeyChecking accept-new' \
        '    UserKnownHostsFile /home/mia/.ssh/known_hosts' \
        '' \
        'Host github-mia-os' \
        '    HostName github.com' \
        '    User git' \
        '    IdentityFile /etc/mia-os/apps_key' \
        '    IdentitiesOnly yes' \
        '    StrictHostKeyChecking accept-new' \
        '    UserKnownHostsFile /home/mia/.ssh/known_hosts' \
        > /home/mia/.ssh/config \
    && ([ -n "${PVE_HOST}" ] && ssh-keyscan -T 5 -H "${PVE_HOST}" >> /home/mia/.ssh/known_hosts 2>/dev/null || true) \
    && (ssh-keyscan -T 5 github.com >> /home/mia/.ssh/known_hosts 2>/dev/null || true) \
    && chown -R mia:mia /home/mia/.ssh \
    && chmod 700 /home/mia/.ssh \
    && chmod 600 /home/mia/.ssh/config

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DB_PATH=/var/lib/mia-os/mia-os.db

WORKDIR /app
USER mia
EXPOSE 8080
VOLUME ["/var/lib/mia-os"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health', timeout=3).status==200 else 1)"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
