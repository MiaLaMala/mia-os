# Die fünf Bildschirme auf dem iPhone

> Entstanden im Gespräch mit Mia am 14.09.2026, entlang von Impeccable
> (`context`, `ios.md`, `operate.md`). Ergänzt `docs/apple-zuschnitt.md` um
> die Frage danach: **wie** die fünf Reiter aussehen und was man auf ihnen tun
> kann. Die Farbregeln stehen weiter in `DESIGN.md`.

## Der Befund, der das ausgelöst hat

Die erste iPhone-Fassung war fünfmal dieselbe Liste. Mias Urteil:

> „Merkst du was ich meine? Alles ist eine Langweilige liste.. Nichts ist da"

Am Screenshot nachgesehen, und sie hat recht: **kein einziger Knopf.** Nichts
abhaken, nichts anlegen, nichts verschieben. Fünf Bildschirme zum Angucken.
Dazu drei Fehler, die keine Geschmacksfrage sind: der Tab-Balken überdeckte
Text, „Heute“ stand als Titel und als Abschnitt untereinander, und Homelab
zeigte vierzig Zeilen „100,0 %“, obwohl die Antwort in Zeile eins steht.

Impeccable ordnet Mia OS als **Operate** ein: *„the tool should disappear into
the task.“* Eine App, in der man nichts tun kann, ist in diesem Modus
durchgefallen, egal wie sie aussieht. Bunter zu machen hätte einen Betrachter
mit Farbe ergeben.

## Die Lage, aus der entworfen wird

Mia schaut **gelegentlich** drauf, nicht mit einer Frage im Kopf. Sie kommt, um
zu sehen, ob sich etwas geändert hat. Daraus folgt alles Weitere:

- Der erste Blick beantwortet in zwei Sekunden: was läuft jetzt, was kommt
  gleich, drängt etwas, ist etwas kaputt.
- Fällt ihr dabei etwas ein, geht es **in einem Griff**. Nicht: Reiter
  wechseln, Eintrag suchen, öffnen, Feld finden, tippen.

Das ist der Unterschied zur Web-Oberfläche. Die ist zum Hinsetzen, das iPhone
für zwischendurch. „Dieselben Listen, kleiner“ war deshalb von Anfang an der
falsche Ansatz.

## Vier Regeln für alle fünf

1. **Die Antwort steht vor den Daten.** „Alles läuft“ vor vierzig
   Prozentzahlen. „Nichts mehr heute“ vor einer leeren Liste.
2. **Was vorbei ist, verblasst statt zu verschwinden.** Der Tag soll laufend
   aussehen, nicht leer.
3. **Jede Zeile kann etwas.** Wischen, langer Druck, Antippen. Kann eine Zeile
   nichts, gehört sie nicht in eine Liste, sondern in einen Satz.
4. **Rot genau einmal pro Bildschirm**, für das was jetzt dran ist. Fälliges
   wird orange (`achtung`). Steht so in `DESIGN.md`.

## Heute

Die Jetzt-Karte oben: Fläche in `akzent_hauch`, Kante in `akzent`, darüber
„JETZT · NOCH 45 MIN“. Darunter in dieser Reihenfolge: was als Nächstes kommt,
Überfälliges, der Rest des Tages, Vergangenes gedämpft.

- **Plus und Scannen oben rechts** in der Navigationsleiste. Kein
  schwebender Knopf unten rechts: das ist Android, und Impeccables
  iOS-Kapitel nennt genau das als „ported from a website“.
- Wischen nach links hakt ab, still, mit kurzem Vibrieren. Wischen nach rechts
  schiebt auf morgen.
- Langer Druck auf einen Termin: Ort kopieren, in Karten öffnen, Eintrag dazu
  anlegen.

**Nicht** zwei kleine Kacheln unter der Jetzt-Karte. Kacheln in Kacheln stehen
in `DESIGN.md` unter „Was nicht geht“; der erste Entwurf hatte sie, Impeccable
hat sie gekippt.

## Termine

Ein Kalender wie die Apple-App, nicht wie ein Dashboard.

- **Monat als Einstieg:** Zahlen im Raster, farbige Punkte darunter, heute als
  gefüllter Kreis in `akzent`. Keine Kacheln, keine Titel im Raster.
- Darunter die Termine des gewählten Tages als Liste, mit Kalenderfarbe links.
- **Tag als zweite Ansicht:** Zeitachse, Termine sitzen an ihrer Uhrzeit und
  sind so hoch wie ihre Dauer, Jetzt-Linie quer durch. Für Tage, an denen viel
  los ist.
- **Keine Wochenansicht.** Sieben Spalten sind auf dem Telefon zu eng,
  dieselbe Entscheidung wie im Web am 06.09.

Mias Urteil zum ersten Wurf mit großen Tageskacheln: *„Bei Kalender gefallen
mir diese großen Kacheln nicht.“*

## Seiten

Hieß bisher „Sammlung“ und zeigte nur eine flache Statusliste. Das Notion-
Modell aus dem Web (Seiten mit Unterseiten, mehrere Ansichten auf dieselben
Zeilen) kam auf dem iPhone gar nicht an. Mias Einwand: *„Bei Sammlung fehlen
mir die anderen Seiten, die wir notion style hatten.“*

- **Einstieg ist eine Galerie** der Seiten, je eine Kachel mit Cover und
  Symbol. Gewählt von Mia gegen eine kompakte Zeilenliste und gegen einen
  Einstieg direkt in die Einträge.
- **Cover und Symbol** wie in Notion. Symbol per langem Druck (Emoji oder SF
  Symbol), Cover in drei Stufen: erst Verläufe aus der Palette, dann ein
  eigenes Bild, später aus der Fotosammlung. Beide gehören der Seite, nicht
  der App: Web und Apps lesen dasselbe Feld.
- **In der Seite:** Liste, Board, Kalender auf denselben Zeilen. **Tabelle
  fällt weg**, vier Spalten auf 390 Punkten kann niemand lesen; dafür ist der
  Browser da.
- **Der Ansichtswechsel hängt am Titel**, nicht an einem Segmentbalken. Ein
  Pfeil neben dem Seitennamen öffnet ein Menü mit Liste, Board, Kalender und
  „Fertige zeigen“. So machen es Mail, Notizen und Dateien. Der Balken war ein
  Webmuster, fraß eine Zeile dauerhaft und wurde zweimal am Tag benutzt.
- **Einträge tragen Chips** für Frist, Priorität und Anhänge, aber nur wo ein
  Wert gesetzt ist. Ein Eintrag ohne alles bleibt eine Zeile.
- Überfälliges steht als eigene Gruppe ganz oben, in `achtung`.

## Dokumente

Die Regel aus `apple-zuschnitt.md` bleibt unangetastet: **ohne Suchbegriff
keine Dateinamen.** Was dazukommt, ist das Sehen und das Tun.

- **Ordner als Collage** aus den vier zuletzt abgelegten Blättern, ohne
  Beschriftung im Bild. Ordner mit weniger als vier Blättern bekommen weniger
  Felder statt grauer Lückenfüller.
- **Die Collage kommt in 128 Pixel**, nicht in den 256, die `/vorschau/{id}`
  vorgibt. Auf 70 Punkten Kantenlänge sieht das identisch aus, aber ein
  Aktenzeichen ist dann wirklich unlesbar und nicht nur klein. Der Unterschied
  zählt: das Bild geht in voller Auflösung über die Leitung und bleibt danach
  im Zwischenspeicher des Geräts.
- **Deckel beim Wegwischen**, damit der App-Umschalter keine Blätter zeigt.
- **Keine Stock-Fotos, keine Emoji-Kacheln** als Ordnerbild. Beides war ein
  Vorschlag von mir, beides hat Mia abgelehnt: ein Aktenschrank-Foto sieht nach
  Vorlage aus, und ein Symbol ist ein Platzhalter für nichts.
- Nach einer Suche: Raster mit echten Vorschauen. **Treffer im Text bekommen
  die Fundstelle statt eines Bildes** — das Wort, wegen dem gesucht wird,
  schlägt jede Vorschau.
- Am Treffer langer Druck: teilen, umbenennen, verschieben. Den Vorschlag für
  Ordner und Namen kennt der Server längst, auf dem iPhone kam er bisher nicht
  an.
- Abschaltbar über die vorhandene Einstellung `dokumente_vorschau`.

## Homelab

Die Frage lautet „ist etwas kaputt“, und vierzig Zeilen „100,0 %“ beantworten
sie schlechter als ein Satz.

- Oben eine Karte mit der Antwort: „Alles läuft. 40 Dienste, seit 12 Tagen ohne
  Ausfall.“ Darunter drei Zahlen (RAM, CPU, Platte).
- Die Liste aller Dienste hängt hinter einem Tippen.
- **Ist etwas rot, steht das statt der grünen Karte oben**, und dann ist die
  Liste das Erste was man sieht. Nur dann.

## Was überall dazukommt

- Wischgesten, Kontextmenüs und Blätter statt eigener Bedienelemente. Impeccable
  nennt das Nachbauen von Standardelementen die häufigste native Schlamperei.
- **Eigene Zustände für leer, lädt und kaputt.** Bisher hat jeder Bildschirm
  nur „geht gut“. Leere Zustände erklären die Oberfläche, statt „nichts da“ zu
  sagen: „Nichts mehr heute. Morgen geht es um 7:30 los.“
- Kurzes Vibrieren beim Abhaken, sonst nichts. Kein Lob für Selbstverständliches,
  so steht es in `DESIGN.md`.

## Was noch offen ist

- **Bewegung.** Was beim Abhaken passiert, beim Blättern, beim Aktualisieren.
  Stand `DESIGN.md` seit dem 13.09. unverändert offen.
- **Hell** ist nirgends erprobt, die Palette ist gerechnet und nie in einem
  echten Fenster gelaufen.
- **Die Prüfung braucht Mias Mac.** Impeccable verlangt Screenshots aus dem
  Simulator, hell und dunkel und bei großer Schrift. Auf dem Arbeitsrechner
  läuft keiner (Laufzeit 26.4 gegen SDK 26.5), dort lässt sich nur übersetzen.
