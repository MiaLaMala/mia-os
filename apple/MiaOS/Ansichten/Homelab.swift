// Was gerade läuft und was nicht.
//
// Oben ein Satz, darunter die Dienste. Die Zahl „47 von 48 erreichbar“ ist
// nicht die Information, die man morgens sucht: „Alles läuft“ ist es, und
// wenn etwas kaputt ist, steht dort der Name.
//
// **Der Satz kommt fertig vom Server.** `_lage()` in `main.py` baut ihn aus
// derselben Liste, aus der auch die Weboberfläche liest. Ein zweiter Satzbau
// in Swift hieße zwei Stellen, die auseinanderlaufen, sobald jemand die
// Zählweise ändert.

import SwiftUI

struct Homelab: View {
    @Environment(Zentrale.self) private var zentrale

    var body: some View {
        List {
            Section {
                Lagezeile(lage: zentrale.homelab.lage)
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets(top: 8, leading: 0, bottom: 8, trailing: 0))
            }

            if zentrale.homelab.dienste.isEmpty {
                Section {
                    // Kein „Keine Daten“: das klingt nach Fehler, und wenn
                    // Uptime Kuma gerade nichts liefert, ist der ehrliche Satz
                    // ein anderer.
                    Leer(symbol: "server.rack", text: "Noch nichts überwacht")
                        .listRowBackground(Color.clear)
                }
            } else {
                Section("Dienste") {
                    ForEach(zentrale.homelab.dienste) { d in
                        Dienstzeile(dienst: d)
                    }
                }
            }
        }
        .navigationTitle("Homelab")
        .refreshable {
            await zentrale.homelabLaden()
        }
        .task {
            // Wie in „Heute“: `.task` läuft bei jedem Erscheinen, und ein
            // Abruf beim Zurückwischen wäre Last ohne neuen Inhalt.
            if zentrale.homelab.stand.isEmpty {
                await zentrale.homelabLaden()
            }
        }
    }
}

// MARK: - Die Aussage oben

private struct Lagezeile: View {
    let lage: Lagemeldung

    var body: some View {
        HStack(spacing: Mass.abstand) {
            Image(systemName: symbol)
                .font(.system(.title2, weight: .regular))
                .foregroundStyle(farbe)
            Text(lage.satz.isEmpty ? "Noch keine Messung" : lage.satz)
                .font(.title3.weight(.medium))
            Spacer(minLength: 0)
        }
    }

    // Rot markiert, was jetzt dran ist, und sonst nichts. Läuft alles, steht
    // hier kein Akzent: ein grüner Haken bei „Alles läuft“ wäre Lob für
    // Selbstverständliches. Deshalb gedämpft statt bunt.
    private var farbe: Color {
        switch lage.zustand {
        case "unten": return Farbe.akzent
        case "wartung": return Farbe.achtung
        default: return Farbe.gedaempft
        }
    }

    private var symbol: String {
        switch lage.zustand {
        case "unten": return "exclamationmark.triangle.fill"
        case "wartung": return "wrench.adjustable"
        default: return "checkmark.circle"
        }
    }
}

// MARK: - Ein Dienst

private struct Dienstzeile: View {
    let dienst: Dienst

    var body: some View {
        HStack(spacing: Mass.abstand) {
            Statuspunkt(farbe: punktfarbe, gefuellt: dienst.istUnten)

            VStack(alignment: .leading, spacing: 2) {
                Text(dienst.name)
                // Die Meldung nur, wenn der Dienst unten ist. Bei einem
                // laufenden Dienst steht dort „200 - OK“, und das ist Lärm.
                if dienst.istUnten && !dienst.meldung.isEmpty {
                    Text(dienst.meldung)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }

            Spacer(minLength: 0)

            // Tabellenziffern: sonst springt die Spalte zwischen „99,8 %“ und
            // „100 %“, weil die Ziffern verschieden breit sind.
            Text(uptimetext)
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }

    private var punktfarbe: Color {
        switch dienst.zustand {
        case "unten": return Farbe.akzent
        case "wartung": return Farbe.achtung
        default: return Farbe.gut
        }
    }

    /// „99,8 %“, oder ein Strich, wenn noch nichts gemessen wurde.
    ///
    /// Der Unterschied ist wichtig: `uptime` ist `nil`, solange keine Werte
    /// vorliegen. Als „0 %“ anzuzeigen wäre gelogen und sähe nach Totalausfall
    /// aus.
    private var uptimetext: String {
        guard let u = dienst.uptime else { return "–" }
        return String(format: "%.1f %%", u).replacingOccurrences(of: ".", with: ",")
    }
}
