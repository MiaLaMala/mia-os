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
                .font(.system(size: 46, weight: .light))
                .foregroundStyle(.tint)

            VStack(spacing: 6) {
                Text("Mia OS")
                    .font(.largeTitle.weight(.semibold))
                Text("Code aus Mia OS, Einstellungen")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }

            TextField("000000", text: $code)
                .font(.system(size: 34, weight: .medium, design: .monospaced))
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
