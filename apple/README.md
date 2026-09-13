# Mia OS auf Mias Geräten

> Wie die Apps gebaut, geflasht und aktualisiert werden. Stand: 13.09.2026.
> Was hier steht, ist einmal wirklich gelaufen, nicht aus der Doku abgeschrieben.

## Was es gibt

Eine SwiftUI-Codebasis, daraus zwei Apps:

- **Mac**, läuft. Gebaut und gestartet am 13.09.2026.
- **iPhone**, baut. Noch nicht auf ein Gerät gespielt, dafür fehlt Xcodes
  erster Start mit Administratorrechten (siehe unten).

Windows und Linux gibt es bewusst nicht. Mia arbeitet am MacBook und am
iPhone, ihr Linux ist Server.

## Bauen

```bash
cd ~/git/mia-os/apple
xcodegen generate          # erzeugt MiaOS.xcodeproj aus project.yml
bash scripts/beide_pruefen.sh
```

`beide_pruefen.sh` ist der wichtige Befehl. **`swift build` allein reicht
nicht:** es läuft auf dem Mac und übersetzt deshalb nur die
`#if os(macOS)`-Zweige. Der iPhone-Zweig blieb dabei ungeprüft, und darin
stand eine `Tab`-Syntax, die es erst ab iOS 18 gibt. Ein grüner Mac-Build
sagt über die iPhone-App nichts.

## Die Fallen, der Reihe nach

**Xcode ohne Administratorrechte.** `xcode-select -s` braucht sudo. Ohne
Passwort geht es trotzdem:

```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
```

Das reicht für `xcodebuild`, `swift test` und `xcrun`.

**Der Simulator läuft nicht.** Die installierte Laufzeit ist 26.4, das SDK
ist 26.5. `xcrun simctl` will die passende nachinstallieren und scheitert an
„Es ist eine Autorisierung erforderlich". Der sichtbare Fehler kommt aber an
einer ganz anderen Stelle heraus:

```
MiaOS/Assets.xcassets: error: No simulator runtime version from ["23E244"]
  available to use with iphonesimulator SDK version 23F81a
```

Das sieht nach einem kaputten Asset-Katalog aus und ist keiner: `actool`
erzeugt die Icons fertig und meldet den Fehler trotzdem. Zum Gegenprüfen
`actool` einmal von Hand laufen lassen, die erzeugten PNGs liegen danach da.

Zum Bauen ohne Simulator hilft `ASSETCATALOG_COMPILER_APPICON_NAME=""`, dann
fehlt nur das Symbol. Richtig behoben ist es erst mit:

```bash
sudo xcode-select -s /Applications/Xcode.app
sudo xcodebuild -runFirstLaunch
```

**`@main` und der Test-Runner.** `MiaOSApp.swift` steht in
`Package.swift` unter `exclude`. Ohne das gibt es zwei `_main` und der
Linker bricht mit „duplicate symbol" ab.

**Swift Testing läuft nebenläufig.** Die Draht-Suite ist `.serialized`, weil
sich alle Tests denselben eingesetzten `URLProtocol` teilen. Ohne das schlagen
drei von ihnen zufällig fehl, und beim ersten Lauf ist genau das passiert.

**`#if` um eine zweite Scene.** In einem SceneBuilder ist ein `#if`, das
`Settings` einschließen soll, kein gültiger Ausdruck: „unexpected tokens in
'#if' expression body". Deshalb steht der Aufbau in `MiaOSApp.swift` zweimal
komplett da, je Plattform einmal.

**`ditto` statt `zip`.** Eine mit `zip` gepackte `.app` startet auf dem
Zielrechner mit „ist beschädigt". `ditto -c -k --sequesterRsrc --keepParent`
erhält die Ressourcen-Gabeln und die Symlinks im Bundle.

## Auf ein Gerät bringen

**Mac:** ZIP entpacken, App nach `/Applications`, beim ersten Start
Rechtsklick → Öffnen. Sie ist nicht notarisiert (dafür bräuchte es ein Apple
Developer Program), deshalb der Rechtsklick genau einmal.

**iPhone:** braucht den Entwicklermodus und Xcode oder Sideloadly. Ohne
bezahltes Programm gilt das Profil **sieben Tage**, danach muss die App neu
drauf. Mit Programm (99 USD im Jahr, Apple verkauft es nur in Dollar) ein
Jahr.

## Aktualisierung

Derselbe Weg wie bei der Display-Firmware:

1. CI baut auf einem macOS-Runner (`.github/workflows/apple.yml`).
2. Die fertigen Dateien kommen mit `apps.json` und Prüfsummen in den Zweig
   `apps`, ohne Historie.
3. Mia OS holt den Zweig per Deploy-Key (`src/apps.py`) und reicht ihn über
   `/api/app/neueste` und `/api/app/datei/{art}` weiter.
4. Die App fragt beim Laden mit, vergleicht selbst und zeigt den Hinweis
   unter „Dieses Gerät".

**Zwei verschiedene Deploy-Keys.** Ein Deploy-Key gilt bei GitHub immer nur
für ein Repo:

| Schlüssel | Repo | Wofür |
|---|---|---|
| `firmware_key` | jana-desktop | Display-Firmware |
| `apps_key` | mia-os | die gebauten Apps |

Der `apps_key` liegt auf LXC 141 bereits als `/root/.ssh/id_ed25519`. Er
gehört nach `/opt/mia-os/apps_key`, `chmod 600`, Eigentümer UID 1000, weil
der Container als `mia` läuft. Denselben Schlüssel für beides zu nehmen endet
in „Repository not found", und die Meldung klingt, als gäbe es den Zweig
nicht.

**Offen:** Das ist der einzige Schritt, der noch von Hand passieren muss.
Solange der Schlüssel nicht liegt, antwortet `/api/app/neueste` mit einer
leeren Version, und das ist Absicht: eine App, die beim Start nach Updates
fragt, soll nicht abstürzen, weil gerade nichts da ist.

## Die Anmeldung

Vorher hatte Mia OS keine. Das ging, solange nur der Browser im Heimnetz und
das Display hinter dem Pi geredet haben, davor steht NPM. Eine App redet auch
aus dem Zug mit dem Server.

- **Aus dem Heimnetz** (172.16.0.0/16, Jana-Netz 10.42.7.0/24): wie bisher
  ohne alles. Das Display fällt darunter.
- **Von außen**: `Authorization: Bearer <schlüssel>`.
- **Kopplung**: sechsstelliger Code aus den Einstellungen, zehn Minuten
  gültig, genau einmal einlösbar, nach fünf Fehlversuchen weg.

Gespeichert wird nur der SHA-256-Abdruck. Wer die Datenbank in die Hand
bekommt, kann sich damit nicht anmelden; ein Test prüft das gegen die echte
Tabelle.

Die echte Adresse kommt aus `X-Forwarded-For`. Das ist hier sicher, weil NPM
den Header selbst neu setzt und den Server von außen niemand direkt erreicht.

## Das App-Symbol

Entsteht aus `apple/scripts/symbol_zeichnen.py`, liegt nicht als PNG im Git.
Gezeichnet und nicht von einem Bildmodell gemalt: es muss in 16 Pixeln noch
lesbar sein, und dafür braucht es gerade Kanten an Pixelgrenzen.

Zwei Dinge, die beim ersten Versuch falsch waren und am gerenderten Bild
auffielen: die Gruppe war rechnerisch zentriert und sah trotzdem nach links
gerutscht aus (die Zeilen werden nach unten kürzer, also wird nach der
**mittleren** Breite ausgerichtet), und der Verlauf war so schwach, dass das
Symbol wie eine schwarze Fläche wirkte.

Für iOS die **klassische** Icon-Liste mit `iphone`/`ipad` als Idiom, nicht
`universal` und nicht das neue Einzelbild-Format. Sonst meldet actool „has 15
unassigned children" und ordnet keine Datei einem Platz zu.
