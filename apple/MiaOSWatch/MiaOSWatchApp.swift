// Mia OS am Handgelenk.
//
// **Was eine Uhr-App NICHT ist: eine kleine iPhone-App.** Sie wird für zwei
// Sekunden angesehen, während der Arm schon wieder sinkt. Deshalb steht hier
// eine Zahl und eine Zeile, keine Listen und kein Blättern.
//
// Der Zustand liegt in `@AppStorage` und nicht nur im Speicher: eine
// watchOS-App wird ständig beendet und neu gestartet. Ohne das zeigt sie beim
// Heben des Arms erst einen Ladekreis, obwohl die Zahlen von vor zwei Minuten
// noch stimmen.

import SwiftUI

@main
struct MiaOSWatchApp: App {
    @State private var uhr = Uhrwerk()

    var body: some Scene {
        WindowGroup {
            Handgelenkansicht()
                .environment(uhr)
        }
    }
}

// MARK: - Zustand

@MainActor
@Observable
final class Uhrwerk {
    private(set) var daten: Handgelenk = .leer
    private(set) var laedt = false
    private(set) var fehler = ""

    private let draht = Draht(adresse: Einstellungen.adresse)

    /// Die zuletzt geholten Zahlen, über Neustarts hinweg.
    ///
    /// Als JSON in `UserDefaults`: eine watchOS-App wird beendet, sobald der
    /// Arm sinkt. Ohne das sähe Mia beim nächsten Heben einen Ladekreis statt
    /// der Zahlen, die vor zwei Minuten noch galten.
    private let schluessel = "mia-os.handgelenk"

    init() {
        if let roh = UserDefaults.standard.data(forKey: schluessel),
           let alt = try? JSONDecoder().decode(Handgelenk.self, from: roh) {
            daten = alt
        }
    }

    func laden() async {
        laedt = true
        defer { laedt = false }
        do {
            daten = try await draht.handgelenk()
            fehler = ""
            if let roh = try? JSONEncoder().encode(daten) {
                UserDefaults.standard.set(roh, forKey: schluessel)
            }
        } catch NetzFehler.nichtGekoppelt {
            // Die Uhr koppelt sich nicht selbst: sechs Ziffern auf einem
            // 40-mm-Bildschirm einzutippen ist eine Zumutung. Sie erbt den
            // Schlüssel vom iPhone über die gemeinsame Keychain-Gruppe.
            fehler = "Am iPhone koppeln"
        } catch {
            // Die alten Zahlen bleiben stehen. Eine leere Uhr mit „kein Netz"
            // ist schlechter als die Termine von vorhin mit einem Punkt daneben.
            fehler = "kein Netz"
        }
    }

    /// Ob die Zahlen alt genug sind, um es zu sagen.
    ///
    /// Zehn Minuten: darunter ist jeder Hinweis Panikmache, darüber könnte ein
    /// Termin dazugekommen sein, von dem die Uhr nichts weiß.
    var istVeraltet: Bool {
        guard let stand = daten.standDatum else { return false }
        return Date().timeIntervalSince(stand) > 600
    }
}

// MARK: - Die Ansicht

struct Handgelenkansicht: View {
    @Environment(Uhrwerk.self) private var uhr

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                if let t = uhr.daten.naechster {
                    Naechster(termin: t, weitere: uhr.daten.spaeter_heute)
                } else {
                    // Nicht „Keine Termine": das klingt nach Fehler. „Nichts
                    // mehr heute" ist eine Aussage über den Tag, und sie stimmt.
                    Text("Nichts mehr heute")
                        .font(.headline)
                        .foregroundStyle(.secondary)
                }

                if uhr.daten.faellig > 0 || uhr.daten.offen > 0 {
                    Divider()
                    Zahlen(faellig: uhr.daten.faellig, offen: uhr.daten.offen)
                }

                if !uhr.fehler.isEmpty || uhr.istVeraltet {
                    Text(uhr.fehler.isEmpty ? "Stand älter als 10 Minuten" : uhr.fehler)
                        .font(.caption2)
                        .foregroundStyle(.orange)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 4)
        }
        .navigationTitle("Mia OS")
        // Läuft bei jedem Erscheinen: auf der Uhr heißt das beim Heben des
        // Arms, und genau dann sollen die Zahlen stimmen.
        .task { await uhr.laden() }
    }
}

private struct Naechster: View {
    let termin: Kurztermin
    let weitere: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            if !termin.zeit.isEmpty {
                // Die Zeit groß und in Ziffernbreite: das ist die eine
                // Information, für die man auf die Uhr schaut.
                Text(termin.zeit)
                    .font(.system(.title2, design: .rounded).weight(.semibold).monospacedDigit())
                    .foregroundStyle(.tint)
            }
            Text(termin.titel)
                .font(.headline)
                .lineLimit(2)
            if !termin.ort.isEmpty {
                Text(termin.ort)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            if weitere > 0 {
                Text(weitere == 1 ? "danach noch 1" : "danach noch \(weitere)")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
    }
}

private struct Zahlen: View {
    let faellig: Int
    let offen: Int

    var body: some View {
        HStack(spacing: 14) {
            if faellig > 0 {
                Kachel(zahl: faellig, wort: "fällig", farbe: .orange)
            }
            Kachel(zahl: offen, wort: "offen", farbe: .secondary)
            Spacer(minLength: 0)
        }
    }
}

private struct Kachel: View {
    let zahl: Int
    let wort: String
    let farbe: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("\(zahl)")
                .font(.system(.title3, design: .rounded).weight(.semibold).monospacedDigit())
                .foregroundStyle(farbe)
            Text(wort)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }
}
