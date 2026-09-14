# PRODUCT.md

> Produktwahrheit für Mia OS. Keine visuellen Entscheidungen (die stehen in DESIGN.md).
> Mit `[abgeleitet]` markierte Punkte stammen aus Projekt- und Gesprächskontext und
> warten auf Bestätigung.

## Platform

adaptive

Die Weboberfläche mobil zuerst, dazu native Apps für iPhone, Mac und Uhr aus
einer SwiftUI-Codebasis (`apple/`) und ein ESP32-Display.

Bis zum 13.09.2026 stand hier `web`. Das stimmt seit den nativen Apps nicht
mehr, und der falsche Wert hat Folgen: Impeccable prüft eine als `web`
deklarierte SwiftUI-App mit Web-Regeln und übergeht `reference/ios.md`.

Welche Bereiche auf Apple landen, steht in `docs/apple-zuschnitt.md`, wie sie
dort aussehen in `docs/apple-bildschirme.md`.

## Stack

Backend Python 3.13, FastAPI, SQLite als Zeitreihe. Frontend Svelte und
Tailwind, gebaut mit Vite. Läuft als Docker-Container auf einem LXC im eigenen
Netz. Apple-Apps in SwiftUI, Projekt über XcodeGen aus `apple/project.yml`.

Der Container bleibt schlank und ohne fremde Dienste: keine externe Datenbank,
kein Suchindex daneben, kein Cluster für eine Anwendung, die eine Person
bedient.

## Primärer Nutzer

Eine einzige Person: Mia. Kein Mehrbenutzerbetrieb, keine Rollen, keine
Registrierung. Das Produkt ist bewusst für genau einen Menschen gebaut.

**Situation** `[abgeleitet]`: Blick aufs Handy, im Vorbeigehen, oft müde oder
zwischen zwei Dingen. Nicht am Schreibtisch, nicht mit Zeit zum Studieren.

**Aufgabe** `[abgeleitet]`: In wenigen Sekunden erfassen, wie die eigenen
Kennzahlen gerade stehen, ohne sich in sieben verschiedene Oberflächen
einzuloggen.

## Was das Produkt möglich macht

Die Zahlen eines Lebens liegen verstreut über viele Dienste: Gewicht und Essen
in wger, Termine im iCloud-Kalender, Server-Auslastung in Proxmox, Fristen in
Moodle. Jede Quelle zeigt nur ihren Ausschnitt und nur den aktuellen Stand.

Mia OS führt sie zusammen **und hält Verlauf**. Das ist der eigentliche
Unterschied zu einem Dashboard aus Kacheln mit Links: nicht „89,5 kg", sondern
„89,5 kg, ein Kilo weniger als zuletzt".

## Kategorien

Feststehend, weil sie Lebensbereiche abbilden, nicht Datenquellen:

| Kategorie | Status | Inhalt |
|---|---|---|
| Gesundheit | live | Gewicht, Veränderung, Ernährungstagebuch |
| Termine | live | heute, morgen, diese Woche |
| Homelab | live | Gäste, RAM, CPU, Speicherbelegung |
| Ausbildung | geplant | Moodle-Fristen und Abgaben |
| Behörden | geplant | offene Vorgänge und Fristen |

## Durable Constraints

- **Ein ausgefallener Collector darf das Dashboard nie mitreißen.** Die Kachel
  wird als veraltet markiert, alles andere bleibt bedienbar. Das ist als
  Vertrag in `collectors/base.py` festgeschrieben.
- **Kein Login.** Der Dienst ist nur im eigenen Netz erreichbar und steht hinter
  einem Reverse Proxy. Eine Anmeldemaske wäre Reibung ohne Sicherheitsgewinn.
- **Keine Zugangsdaten im Code**, ausschließlich Umgebungsvariablen.
- **Kein Build-Schritt im Frontend.** Was der Browser bekommt, liegt als Datei
  im Repo.
- **Deutsche Oberfläche.** Keine Mehrsprachigkeit nötig.

## Erfolg

Mia schaut morgens auf das Dashboard, statt drei Apps zu öffnen. Und sie sieht
dort etwas, das ihr keine der Einzelquellen zeigt: die Richtung, in die sich
eine Zahl bewegt.

## Verbindliche Vorgabe von Mia

> „Ein professionelles Dashboard mit Icons, gebaut nach der Design-Philosophie
> von Apple."

Wörtlich übernommen, nicht ausgelegt. Die Umsetzung gehört in DESIGN.md.

## Voice

Deutsch, knapp, ohne Werbesprache. Beschriftungen benennen die Sache
(„Gewicht", nicht „Dein aktuelles Körpergewicht"). Keine Ausrufezeichen, keine
Motivationssprüche. Zahlen sprechen für sich.
