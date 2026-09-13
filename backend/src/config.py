"""Konfiguration: alle Secrets kommen aus Umgebungsvariablen, nie aus dem Code."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Laufzeit-Konfiguration.

    Jede Quelle ist optional: fehlt ein Token, meldet der zugehoerige Collector
    sauber "nicht konfiguriert" statt das ganze Dashboard zu killen.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8080
    db_path: str = "/var/lib/mia-os/mia-os.db"
    collect_interval_minutes: int = 60

    # --- wger (Gesundheit) ---
    wger_url: str = ""
    wger_token: str = ""

    # --- Uptime Kuma (Homelab) ---
    kuma_url: str = ""

    # --- Proxmox (Homelab) ---
    proxmox_url: str = ""
    proxmox_token_id: str = ""
    proxmox_token_secret: str = ""

    # --- CalDAV (Termine) ---
    caldav_url: str = ""
    caldav_user: str = ""
    caldav_password: str = ""

    # --- Moodle (Ausbildung) ---
    moodle_url: str = ""
    moodle_token: str = ""

    # --- Nextcloud (Dokumente) ---
    # Nur lesend, nur Metadaten. Es ist ein App-Passwort, kein Login-Passwort.
    nextcloud_url: str = ""
    nextcloud_user: str = ""
    nextcloud_password: str = ""
    # Ordner mit den von Jana erstellten Dokumenten, optional eingehaengt.
    documents_local_path: str = ""
    # Wohin hochgeladene Belege gelegt werden. Ein eigener Ordner, damit sie
    # sich nie mit Mias gewachsener Ablage vermischen: was Mia OS anlegt,
    # laesst sich so jederzeit von Hand wieder herausnehmen.
    belege_ordner: str = "/Dokumente/00 Belege"
    # Deckel je Datei. Ein Handyfoto liegt bei 2 bis 5 MB, ein gescanntes
    # Mehrseiten-PDF bei 10. Alles darueber ist ein Versehen.
    belege_max_mb: int = 25
    # Notbremse gegen einen halb abgebrochenen Crawl. Realbestand 09/2026: 1527
    # Dateien insgesamt, davon gut 100 Dokumente im engeren Sinn.
    documents_min_expected: int = 50

    # --- OCR (Text aus gescannten Belegen) ---
    # Gilt NUR fuer Belege, die Mia selbst durch den Scanner schickt. Fuer den
    # Bestand wird kein Text gelesen und keiner gespeichert: dort liegen
    # Ausweise, Geburtsurkunden und Unterlagen Dritter. Die Grenze steht in
    # store.set_document_text, nicht nur hier.
    #
    # Im Container liegt tesseract im PATH, auf dem Entwicklungsrechner
    # entpackt im Benutzerverzeichnis. Die beiden Pfade darunter sind deshalb
    # im Container leer und werden dann nicht gesetzt.
    ocr_binary: str = "tesseract"
    ocr_tessdata: str = ""
    ocr_lib_path: str = ""
    ocr_sprache: str = "deu+eng"
    # Ein A4-Scan braucht gut eine Sekunde. Die Grenze faengt den Fall ab, in
    # dem die Layout-Analyse sich an einem sehr feinstrukturierten Bild
    # festbeisst und der Upload so lange offen steht.
    ocr_timeout: int = 60

    # --- Ordnervorschlag (Embedding-Server auf LXC 140) ---
    # Schlaegt vor, in welchen Sachordner ein frisch abgelegter Beleg gehoert.
    # Verglichen werden ausschliesslich Dateinamen aus dem Index, dazu der
    # OCR-Text des Belegs selbst, den Mia ohnehin gescannt hat. Aus dem Haus
    # geht dabei nichts: der Server laeuft im Heimnetz.
    #
    # Leer heisst aus. Ohne Server gibt es keinen Vorschlag und sonst nichts.
    embed_url: str = ""
    embed_model: str = "embeddinggemma"
    # Ein Vektor entsteht in gut 0,25 s. Die Grenze faengt den Fall ab, in dem
    # der Server steht, waehrend ein Upload auf ihn wartet.
    embed_timeout: int = 30

    # --- Uptime Kuma ---
    # Gelesen wird die Kuma-Datenbank ueber SSH, nur lesend. Grund steht in
    # collectors/kuma.py: ein API-Key wuerde die Basic-Auth an Mias laufender
    # Kuma-Instanz dauerhaft abschalten.
    #
    # ``pve`` ist ein SSH-Alias, kein DNS-Name: der blosse Name loest im
    # Heimnetz auf den Reverse Proxy auf. Die Zuordnung steht in der
    # ssh/config im Image.
    kuma_ssh_host: str = "pve"
    kuma_ssh_key: str = "/etc/mia-os/kuma_key"
    kuma_container: str = "125"
    kuma_docker_name: str = "uptime-kuma"
    kuma_db_pfad: str = "/app/data/kuma.db"

    # --- OnlyOffice (Dokumente bearbeiten) ---
    # Der Document Server rendert den Editor. Mia OS liefert die Datei selbst
    # aus und nimmt Aenderungen zurueck, Nextcloud bleibt der Speicherort.
    onlyoffice_url: str = ""
    # Interne Adresse: der Document Server holt die Datei damit ab, nicht der
    # Browser. Muss aus Sicht des Containers erreichbar sein.
    onlyoffice_internal_url: str = ""
    onlyoffice_jwt_secret: str = ""
    # Woher der Document Server Mia OS erreicht (fuer Datei- und Rueckruf-URL).
    # Ohne das kaeme dort eine Browser-Adresse an, die er nicht aufloesen kann.
    public_base_url: str = ""


settings = Settings()
