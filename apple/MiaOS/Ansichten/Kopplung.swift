// UNGEPRUEFT: geaendert am 14.09.2026 nachts, ohne Compiler.
// Betrifft nur die Schriftgroessen: feste Punktzahl auf Dynamic Type.
// Vor dem Verwenden: scripts/beide_pruefen.sh auf Mias Mac.
// Der erste Bildschirm: dieses Gerät mit Mia OS verbinden.
//
// Sechs Ziffern, ein Knopf. Der Code steht in Mia OS unter Einstellungen und
// gilt zehn Minuten.

import SwiftUI

struct Kopplung: View {
    @Environment(Zentrale.self) private var zentrale
    @State private var code = ""
    @State private var laeuft = false
    @State private var fehler = ""
    @FocusState private var imFeld: Bool

    private var codeGueltig: Bool {
        code.count == 6 && code.allSatisfy(\.isNumber)
    }

    var body: some View {
        VStack(spacing: Mass.abstandGross) {
            Spacer()

            Image(systemName: "square.stack.3d.up")
                // Waechst mit Dynamic Type mit. Eine feste Punktzahl bliebe
                // stehen, waehrend der Text darunter groesser wird.
                .font(.system(.largeTitle, weight: .light))
                .foregroundStyle(.tint)

            VStack(spacing: 6) {
                Text("Mia OS")
                    .font(.largeTitle.weight(.semibold))
                Text("Code aus Mia OS, Einstellungen")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }

            TextField("000000", text: $code)
                // Der Code ist das Wichtigste auf diesem Bildschirm und muss
                // beim Abtippen gut lesbar sein: `.title` waechst mit Dynamic
                // Type, `size: 34` nicht. Monospaced, damit die sechs Ziffern
                // beim Tippen nicht springen.
                .font(.system(.title, design: .monospaced).weight(.medium))
                .multilineTextAlignment(.center)
                .textFieldStyle(.plain)
                .focused($imFeld)
                #if os(iOS)
                // Ziffernblock statt voller Tastatur: der Code hat keine
                // Buchstaben, und eine Tastatur mit Buchstaben lädt dazu ein,
                // welche zu tippen.
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
                #endif
                .onChange(of: code) { _, neu in
                    // Nur Ziffern, höchstens sechs. Filtern statt meckern:
                    // eine Fehlermeldung für ein Zeichen, das ohnehin nicht
                    // hingehört, ist eine Meldung zu viel.
                    let sauber = String(neu.filter(\.isNumber).prefix(6))
                    if sauber != neu { code = sauber }
                    fehler = ""
                }
                .padding(.vertical, Mass.abstand)
                .frame(maxWidth: 260)
                .background(
                    RoundedRectangle(cornerRadius: Mass.ecke)
                        .fill(.quaternary.opacity(0.5))
                )

            if !fehler.isEmpty {
                Text(fehler)
                    .font(.callout)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, Mass.abstandGross)
            }

            Button {
                Task { await koppeln() }
            } label: {
                if laeuft {
                    ProgressView().controlSize(.small)
                } else {
                    Text("Verbinden")
                }
            }
            .frame(maxWidth: 260)
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(!codeGueltig || laeuft)

            Spacer()

            Text(Einstellungen.adresse.host() ?? "")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .padding(Mass.abstandGross)
        .onAppear { imFeld = true }
    }

    private func koppeln() async {
        laeuft = true
        fehler = ""
        defer { laeuft = false }
        do {
            try await zentrale.koppeln(code: code)
        } catch {
            fehler = error.localizedDescription
            // Das Feld leeren: ein Code gilt genau einmal, der im Feld ist
            // nach einem Fehlversuch in jedem Fall verbraucht.
            code = ""
            imFeld = true
        }
    }
}
