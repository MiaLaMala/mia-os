// UNGEPRUEFT: geaendert am 14.09.2026 nachts, ohne Compiler.
// Betrifft nur die Schriftgroessen: feste Punktzahl auf Dynamic Type.
// Vor dem Verwenden: scripts/beide_pruefen.sh auf Mias Mac.
// Kleine Teile, die in mehreren Ansichten vorkommen.

import SwiftUI

// MARK: - Leerer Zustand

/// Was dasteht, wenn nichts dasteht.
///
/// Nicht „Keine Daten": das klingt nach Fehler. „Heute nichts" ist eine
/// Aussage über den Tag, und die stimmt auch.
struct Leer: View {
    let symbol: String
    let text: String

    var body: some View {
        VStack(spacing: Mass.abstand) {
            Image(systemName: symbol)
                // `.system(.title, …)` statt `.system(size: 34, …)`: eine feste
                // Punktzahl waechst nicht mit, wenn Mia die Schrift groesser
                // stellt. Dann steht ein winziges Symbol ueber grossem Text.
                // Impeccable verbietet feste Groessen ausdruecklich.
                .font(.system(.title, weight: .light))
                .foregroundStyle(.tertiary)
            Text(text)
                .font(.callout)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 44)
    }
}

// MARK: - Hinweisleiste

/// Die Zeile oben, wenn der Server nicht erreichbar ist.
///
/// Bewusst eine Leiste und kein Dialog: die Daten von vorhin bleiben sichtbar
/// und benutzbar. Ein Dialog würde sie verdecken und verlangen, dass man ihn
/// wegklickt, bevor man die Termine sehen darf, die schon da sind.
struct Getrenntleiste: View {
    let grund: String
    let nochmal: () async -> Void

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "wifi.exclamationmark")
                .foregroundStyle(.orange)
            Text(grund)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
            Spacer(minLength: 8)
            Button("Nochmal") {
                Task { await nochmal() }
            }
            .font(.caption.weight(.medium))
            .buttonStyle(.plain)
            .foregroundStyle(.tint)
        }
        .padding(.horizontal, Mass.abstand)
        .padding(.vertical, 8)
        .background(.orange.opacity(0.1))
    }
}

// MARK: - Statuspunkt

/// Der farbige Punkt vor einem Eintrag.
struct Statuspunkt: View {
    let farbe: Color
    var gefuellt = true

    var body: some View {
        Circle()
            .strokeBorder(farbe, lineWidth: gefuellt ? 0 : 1.5)
            .background(Circle().fill(gefuellt ? farbe : .clear))
            .frame(width: 9, height: 9)
    }
}

// MARK: - Abschnittstitel

struct Abschnitt<Inhalt: View>: View {
    let titel: String
    var zusatz: String = ""
    @ViewBuilder let inhalt: () -> Inhalt

    var body: some View {
        VStack(alignment: .leading, spacing: Mass.abstand) {
            HStack(alignment: .firstTextBaseline) {
                Text(titel)
                    .font(.headline)
                if !zusatz.isEmpty {
                    Text(zusatz)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
            inhalt()
        }
    }
}
