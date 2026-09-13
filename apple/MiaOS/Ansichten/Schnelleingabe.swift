// Ein Feld, Enter, weg.
//
// **Der Punkt, an dem eine Mac-App gewinnt.** Ein Gedanke kommt, während man
// etwas anderes tut. Den Browser zu suchen, den Tab zu finden und zu klicken
// dauert lange genug, dass man es sein lässt. Ein Fenster, das über allem
// schwebt und nach dem Absenden verschwindet, dauert vier Sekunden.
//
// Der Text geht an `/api/schnell`, dieselbe Deutung wie im Browser: „AU
// abgeben Freitag" wird ein Eintrag mit Datum, „88,4 kg" ein Gewicht. Die
// Deutung bleibt auf dem Server, sie steht dort schon.

#if os(macOS)

import SwiftUI

struct Schnelleingabe: View {
    @Environment(Zentrale.self) private var zentrale
    @Environment(\.dismiss) private var schliessen
    @State private var text = ""
    @State private var laeuft = false
    @State private var meldung = ""
    @FocusState private var imFeld: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Image(systemName: "plus.circle")
                    .font(.title2)
                    .foregroundStyle(.tint)

                TextField("Was ist los?", text: $text)
                    .textFieldStyle(.plain)
                    .font(.title3)
                    .focused($imFeld)
                    .onSubmit { Task { await senden() } }
                    .disabled(laeuft)

                if laeuft {
                    ProgressView().controlSize(.small)
                }
            }

            if meldung.isEmpty {
                // Beispiele statt einer Erklärung: sie zeigen in einer Zeile,
                // dass das Feld mehr kann als Text speichern.
                //
                // Einfache Anführungszeichen im Swift-Text, keine deutschen:
                // ein typografisches Zeichen mitten im String beendet ihn für
                // den Compiler, und der meldet nur „invalid character".
                Text("Zahnarzt Freitag 9 Uhr · 88,4 kg · AU abgeben")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            } else {
                Text(meldung)
                    .font(.caption)
                    .foregroundStyle(meldung.hasPrefix("Ging nicht") ? .red : .green)
            }
        }
        .padding(16)
        .frame(width: 460)
        .onAppear { imFeld = true }
        // Escape schließt. Ohne das bliebe ein Fenster stehen, das über allem
        // schwebt, und man müsste es mit der Maus suchen.
        .onExitCommand { schliessen() }
    }

    private func senden() async {
        let sauber = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !sauber.isEmpty, !laeuft else { return }
        laeuft = true
        defer { laeuft = false }
        do {
            let antwort = try await zentrale.schnellEintragen(sauber)
            meldung = antwort
            text = ""
            // Kurz stehen lassen, damit die Bestätigung lesbar ist, dann weg.
            // Sofort zu schließen sieht aus, als wäre nichts passiert.
            try? await Task.sleep(for: .milliseconds(900))
            schliessen()
        } catch {
            meldung = "Ging nicht: \(error.localizedDescription)"
        }
    }
}

#endif
