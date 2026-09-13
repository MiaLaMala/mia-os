# Mia OS auf Apple: was die Apps zeigen

> Entstanden im Gespräch mit Mia am 13.09.2026. Ergänzt DESIGN.md um die
> Frage, die vor der Gestaltung kommt: was gehört überhaupt hinein.

## Warum das geschrieben steht

Die erste Mac-Fassung war die Web-Oberfläche in Swift. Mias Urteil:
*„sieht... aus... nicht gut."* Beim Nachfassen kam heraus, dass nicht nur
die Gestaltung fehlte, sondern die Entscheidung davor: welche der zehn
Web-Seiten überhaupt auf Apple gehören. Ohne diese Antwort entwirft man
Bildschirme, die es vielleicht nie gibt.

## Der Zuschnitt

**iPhone: fünf Reiter.**

| Reiter | Was es zeigt |
|---|---|
| Heute | der Tag, das Fällige |
| Termine | Kalender, lesend und anlegend |
| Sammlung | Einträge, Status, Abhaken |
| Dokumente | Suche im Index |
| Homelab | Dienste und ihr Zustand |

**Scannen ist kein Reiter, sondern ein Knopf oben rechts in „Heute".** Es
ist eine Handlung, kein Ort. Apple lässt im Tab-Balken zwei bis fünf Reiter
zu, sechs wären einer zu viel, und die Wahl fiel bewusst gegen einen
„Mehr"-Reiter: das ist die Ecke, in der Dinge sterben.

**Mac: dieselben fünf in der Seitenleiste**, dazu Einstellungen über das
Systemmenü und die Menüleiste als sechster Weg hinein.

**Nicht auf Apple:** Berichtsheft, Gesundheit, der freie Seitenbaum mit
Board- und Tabellenansicht. Das sind Formulare mit Zustand (Termine 723
Zeilen, Gesundheit 395, Berichtsheft 367 im Web), die man im Sitzen
ausfüllt. Sie bleiben im Browser, einen Tipp entfernt.

## Was nur die App kann

Diese vier sind der eigentliche Grund für native Apps. Sie stehen in jedem
Zuschnitt fest:

- **Widget** auf Sperr- und Home-Bildschirm: der nächste Termin, ohne etwas
  zu öffnen.
- **Siri und Kurzbefehle**: fragen, eintragen, abhaken, ohne die App zu
  öffnen.
- **Scannen** mit der Systemkamera: entzerrt, während man zielt.
- **Schnelleingabe**: ein Satz, der Server deutet ihn.

## Dokumente: die Regel aus dem Web gilt verschärft

Im Web zeigt die Dokumentensuche **ohne Suchbegriff keine Dateinamen**, nur
Ordner und Anzahl. Der Grund steht im Code: sonst stehen medizinische
Unterlagen Dritter auf der Startseite.

Auf dem iPhone wiegt das schwerer. Das Telefon liegt auf Tischen, jemand
schaut mit, der Sperrbildschirm zeigt Vorschauen. Deshalb:

- Leeres Suchfeld zeigt Ordner und Anzahl, nie Namen.
- **Dokumente tauchen nie im Widget auf**, in keiner Größe.
- **Dokumente tauchen nie in einer Siri-Antwort auf.** Siri spricht laut.

Das ist keine Gestaltungsfrage, sondern eine Festlegung. Sie wird getestet,
nicht kommentiert.

## Icons: SF Symbols auf Apple, das Web zeichnet nach

Entschieden am 13.09.2026.

**Auf Apple die echten SF Symbols.** Sie sind kein Icon-Satz, sondern Teil
der Schrift: sie hängen an San Francisco, folgen der Schriftgröße mit,
kennen neun Gewichte und sitzen auf der Grundlinie. Ein fremder Satz kann
das nicht nachmachen, und Impeccable nennt ihn ausdrücklich als Fehler
(*„Don't mix in a web icon set"*).

**Im Web die eigenen SVGs, an deren Formensprache angeglichen.** Gleiche
Strichstärke, gleiche Rundungen, gleiche Metaphern. Dann sieht es überall
gleich aus, ohne dass etwas kopiert wird.

**Warum nicht SF Symbols überall:** Apples Lizenz erlaubt es nicht. Sie
gelten als systemgelieferte Bilder und sind lizenziert *„solely for the
purpose of developing Applications for Apple-branded products that run on
the system for which the image was provided"* (Xcode-Lizenz 2.13, dazu die
Human Interface Guidelines). Eine Web-Oberfläche im Chrome auf einem
Linux-Rechner fällt nicht darunter, das ESP32-Display erst recht nicht. Man
kann die SVGs exportieren, aber sie mitzuliefern wäre ein Lizenzbruch.

Nebeneinander sieht man beide Sätze ohnehin nie. Der Unterschied fällt nur
beim Wechsel vom Browser in die App auf, und genau den soll das Angleichen
glätten.

## Was noch offen ist

Nach der Reihenfolge, in der es blockiert:

1. **Leere und kaputte Zustände.** Sechs im Web, alle anders formuliert.
   Nichts los heute, kein Netz, lädt, erster Start, Suche ohne Treffer.
2. **Typografie als System.** Größen, Zeilenhöhen, Abstände. Dazu: drei
   feste Schriftgrößen im Apple-Code, die Impeccable verbietet
   (`.system(size: 46)` in Kopplung.swift und Scannen.swift).
3. **Bewegung.** Abhaken, Blättern, Aktualisieren.

**Diese drei werden nicht am Entwurf beantwortet, sondern beim Bauen.** Eine
HTML-Vorschau lügt: sie fallen von selbst an, sobald „Heute" mit den neuen
Farben im echten Fenster läuft.

Der Ton war die vierte offene Frage und ist beantwortet: er steht in
DESIGN.md unter „Ton". Kurz: die App kennt Mia, grüßt sie, schreibt ganze
Sätze statt Nullen, und hakt still ab. Die Antwort stand schon im Web, ich
hatte nur nicht nachgesehen, bevor ich drei Möglichkeiten zur Wahl stellte.

## Der nächste Schritt

„Heute" auf dem Mac mit den Farben aus `farben.json` bauen, im laufenden
Fenster ansehen, und was dabei auffällt zurück in DESIGN.md schreiben.
Danach Bildschirm für Bildschirm.

Gebraucht wird dafür Mias Mac. Er war am Abend des 13.09. offline.
