# DESIGN.md

> Die visuelle Wahrheit von Mia OS. Was das Produkt sein soll, steht in PRODUCT.md.
> Stand: 13.09.2026. Entstanden im Gespräch mit Mia, entlang von Impeccable.

## Was hier steht und was nicht

Hier steht das **Fundament**: Farben, der Umgang mit dem Akzent, die Grenze
zwischen Systemvorgabe und eigener Stimme. Das gilt ab sofort für jede Fassung.

Hier steht **noch nicht**, wie einzelne Bildschirme aussehen. Termine, Sammlung,
Board, Kalender, Dokumente, die leeren und kaputten Zustände, Bewegung: alles
offen. Das entsteht Bildschirm für Bildschirm, jeder erst im echten Fenster
angesehen und dann hier nachgetragen.

**Warum diese Trennung:** eine HTML-Vorschau lügt. Was im Entwurf stimmig
aussieht, kann im laufenden Fenster daneben liegen. Festgeschrieben wird nur,
was wirklich entschieden ist.

## Die Lage, aus der das entstand

Am 13.09.2026 gab es Mia OS als Web-Oberfläche, Mac-App, iPhone-App, Display
und halbfertige Uhr-App. Jede Fassung war für sich entstanden, und sie waren
sich uneinig:

- DESIGN.md setzte den Akzent auf Systemblau `#0a84ff`
- das Display hatte `#d92d3c`, ein Rot
- das App-Symbol ein drittes Rot
- die Mac-App benutzte gar keinen davon, sondern die Systemfarbe

Mias Urteil über die erste Mac-Fassung: *„sieht... aus... nicht gut."* Sie hatte
recht. Es war die Web-Oberfläche in Swift, ohne eigene Haltung.

## Die Haltung

**Gerüst vom System, Stimme von Mia OS.**

Impeccable sagt es für native Apps so: *„brand expresses through the layer the
platform leaves open (tint, type, motion, content)."*

Was dem System gehört:

- Navigation: Seitenleiste auf dem Mac, Tab-Balken auf dem iPhone
- Bedienelemente: Schalter, Knöpfe, Auswahllisten, Blätter, Kontextmenüs
- Hell und Dunkel, Dynamic Type, Bedienungshilfen
- Bewegung beim Blättern und Öffnen

Was Mia OS gehört:

- der Akzent und wofür er steht
- das warme Neutral im Untergrund
- die Anordnung: was groß ist, was einrückt, was verschwindet
- die Sprache in Beschriftungen und Meldungen

Eigene Knöpfe zu bauen ist der häufigste Fehler bei portierten Apps. Der Akzent
ist genau die Stelle, die Apple offen lässt.

## Die eine Regel für den Akzent

**Rot markiert, was jetzt dran ist. Sonst nichts.**

Aus `impeccable colorize`: *„Let the strongest color own a deliberate region or
role instead of scattering tiny accents."*

Der nächste Termin bekommt eine Fläche (`akzent_hauch`), eine Kante
(`akzent_matt`) und die kräftige Ziffer (`akzent`). Alles danach steht ruhig in
`gedaempft` und rückt auf die Linie der Kante ein. Die Hierarchie ist damit
räumlich **und** farbig, nicht nur farbig: wer Rot nicht unterscheiden kann,
sieht die Einrückung.

Nicht erlaubt:

- Rot an jeder Uhrzeit
- Rot als Farbe für aktive Menüpunkte (dafür reicht der Hauch als Fläche)
- Rot an Knöpfen, die nur Standard sind
- Rot als Zier

Fällige Sachen bekommen `achtung` (orange), nicht Rot. Fehler bekommen `fehler`,
das ist ein zum Orange verschobenes Rot. Läge es auf dem Akzent, sähe eine
Auswahl wie ein Fehler aus.

## Farben

**Die einzige Quelle ist `farben.json`.** Daraus erzeugt
`scripts/farben_bauen.py`:

| Datei | Fassung |
|---|---|
| `frontend/src/farben.css` | Web, als CSS-Variablen |
| `apple/MiaOS/Bausteine/Farben.swift` | Mac, iPhone, Uhr |
| `build/farben.h` | Display, als RGB565 |

Keine dieser Dateien wird von Hand angefasst. Sie tragen einen Hinweis im Kopf
und werden bei jedem Lauf überschrieben.

Das Skript rechnet bei jedem Lauf 14 Kontraste nach und **bricht ab**, wenn
einer unter seinen Wert fällt. Eine Farbe zu ändern, ohne die Lesbarkeit zu
prüfen, ist damit nicht mehr möglich. `scripts/gates.sh` ruft es mit
`--pruefen` auf.

### Woher die Werte kommen

Alles liegt auf **OKLCH-Farbton 20**, einem warmen Rot. Dort wohnte das
Display-Rot schon.

OKLCH statt HSL, weil sich dort die Helligkeit ändern lässt, ohne dass die
Farbe kippt: ein in HSL aufgehelltes Rot wird rosa, in OKLCH bleibt es Rot.
Die Chroma fällt an den hellen und dunklen Enden, sonst leuchten die Ränder
unnatürlich.

### Neutral ist nicht grau

Die Grautöne tragen eine winzige Spur desselben Rots (Chroma 0.004 bis 0.020).
Bewusst sieht man das nicht. Der Grund wirkt dadurch warm statt nach kaltem
Dashboard-Schiefer. **Das ist der eigentliche Charakter der Oberfläche**, nicht
der Akzent: er ist selten, das Neutral ist überall.

### Hell ist nicht Dunkel umgedreht

Beide Themen sind einzeln gesetzt. Der Akzent ist im Hellen dunkler
(`#c70030` statt `#f33e52`), weil ein leuchtendes Rot auf Weiß grell wird und
den Kontrast verliert. Aus `impeccable colorize`: *„In dark mode, design
surface elevation and contrast explicitly; do not invert the light theme
mechanically."*

## Schrift

**Auf Apple: San Francisco über Dynamic Type.** Keine festen Punktgrößen.
Impeccable ist dort eindeutig: *„Use the system text styles so text follows the
user's reading size."* Eine App, die Mias eingestellte Schriftgröße ignoriert,
ist kaputt, egal wie hübsch sie aussieht.

**Inter für Datum und Zahlen.** Die Stellen, an denen Charakter sitzt: der
Tageskopf, Uhrzeiten, Zählwerte. Dort ist eine eigene Schrift erlaubt und
sinnvoll, weil sie nichts bedient, sondern etwas aussagt.

**Im Web und auf dem Display: Inter überall.** Beide haben keine Systemschrift,
der Browser fiele sonst auf Arial zurück.

**Tabellenziffern durchgehend** (`font-variant-numeric: tabular-nums`, in Swift
`.monospacedDigit()`). Zahlen, die beim Aktualisieren springen, sind das
Gegenteil von ruhig.

## Wie sich Fassungen unterscheiden dürfen

| | darf abweichen | muss gleich bleiben |
|---|---|---|
| **Mac** | Seitenleiste, Menüleiste, Tastaturbefehle, Hell/Dunkel | Akzentregel, Neutral, Tageskopf |
| **iPhone** | Tab-Balken, Blätter, Wischgesten, Hell/Dunkel | dieselben |
| **Uhr** | reines Schwarz als Grund (spart Strom), nur das Nächste | Akzent, Zeit vor Titel |
| **Display** | immer dunkel, Kante statt Kachel (3 px kosten nichts) | Akzent, Neutral, Zeit vor Titel |
| **Web** | Seitenbaum, vier Ansichten, Tastaturbefehle | alles |

Grundsatz: **je kleiner der Schirm, desto weniger steht drauf.** Nicht dasselbe
kleiner.

## Was bleibt

Aus der alten Fassung dieses Dokuments gilt weiter:

- **Dunkel als Standard** dort, wo kein System es vorgibt. Mia sieht morgens im
  Halbdunkel drauf.
- **Ruhe zuerst, Tiefe auf Abruf.** Eine Zahl pro Sache, alles Weitere hinter
  einem Ausklappen.
- **Erhebung durch Fläche und Linie**, nicht durch Schatten. Radien 14 px an
  Kacheln, 10 px an Bedienelementen.
- **Bewegung 150 bis 220 ms**, `cubic-bezier(0.32, 0.72, 0, 1)`, und nur bei
  Zustandsänderung. `prefers-reduced-motion` schaltet alles ab.
- **Keine Emojis in der Oberfläche.** SF Symbols auf Apple, gezeichnete SVGs im
  Web, an deren Formensprache angeglichen. Die Begründung, auch die
  lizenzrechtliche, steht in `docs/apple-zuschnitt.md`.

## Ton

Mia OS **kennt Mia**. Das steht nicht als Absicht hier, sondern als Befund:
die Weboberfläche macht es längst. Der Seitenkopf heißt `{gruss()},
{vorname}`, also „Guten Abend, Mia", und die Texte sind ganze Sätze statt
Etiketten: *„Noch nichts drin. Oben etwas eintragen."*, *„Änderungen gelten
sofort. Zugangsdaten stehen bewusst nicht hier."*

Die Apple-Apps übernehmen das unverändert. Es ist keine neue Entscheidung,
nur die vorhandene, konsequent weitergezogen.

**Wo ganze Sätze stehen statt Zahlen:**

- Leerer Tag: „Nichts mehr heute." Nicht `0`.
- Kein Netz: ein Satz, der sagt, was trotzdem stimmt. Nicht „Fehler 502".
- Nichts gefunden: was man stattdessen tun kann.

**Wo nichts steht:**

- Abhaken passiert still. Die Zeile verblasst, der Zähler zählt runter.
  Kein Lob für etwas Selbstverständliches.
- Im Widget keine Ansprache. Dort ist kein Platz, und wer aufs Telefon
  schaut, will die Uhrzeit sehen.

**Die Grenze:** die App redet nur, wenn sie etwas zu sagen hat. Kein „Super
gemacht!", kein „Schön, dich zu sehen", keine Sprüche auf leeren
Bildschirmen. Ein Gruß am Anfang und ganze Sätze dort, wo sonst eine Null
stünde. Mehr nicht.

Beim Vergleich der ersten Apple-Entwürfe mit dem Web fiel auf, dass sie
**kühler** waren: „13. September" statt „Guten Abend, Mia", Zahlen statt
Sätze. Das war ein Rückschritt, den niemand bestellt hatte.

## Was nicht geht

- Systemblau. Es gehört Apple, nicht Mia OS.
- Eine Farbe von Hand in eine erzeugte Datei schreiben.
- Rot für mehr als eine Sache auf einem Bildschirm.
- Feste Schriftgrößen in einer Apple-App.
- Gleich große Kacheln aus Symbol, Überschrift und Text als Seitengerüst.
- Kacheln in Kacheln, Glaseffekt als Zierde, farbige Ränder über 1 px.
- Dicktengleiche Schrift als Kostüm für „technisch".
- Eine nackte `0`, wo ein Satz die Lage beschreibt.
- Lob für Erledigtes. Abhaken ist selbstverständlich, kein Erfolg.
- Miniaturkurven und Fortschrittsringe als Platzhalter für Inhalt.

## Was die Apps zeigen

Steht in `docs/apple-zuschnitt.md`. Kurz: fünf Reiter (Heute, Termine,
Sammlung, Dokumente, Homelab), Scannen als Knopf statt als Reiter.
Berichtsheft, Gesundheit und der Seitenbaum bleiben im Browser.

Dokumente tragen dort eine Festlegung, die keine Gestaltungsfrage ist:
leeres Suchfeld zeigt keine Dateinamen, und Dokumente erscheinen weder im
Widget noch in einer Siri-Antwort.

## Offen

- **Hell ist nirgends erprobt.** Die Palette ist gerechnet und besteht die
  Kontraste, aber sie lief noch nie in einem echten Fenster.
- **Das Display braucht die neue Palette.** Sie liegt als `build/farben.h`
  bereit und muss ins Repo `jana-desktop` übertragen werden.
- **Bewegung ist ungeplant.** Was beim Abhaken passiert, beim Blättern, beim
  Aktualisieren.
