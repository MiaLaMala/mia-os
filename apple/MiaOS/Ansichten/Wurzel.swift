// Was die App zeigt, je nachdem wo sie läuft.
//
// **Der Punkt, an dem „nativ" sich entscheidet.** Dieselben Ansichten, aber
// auf dem iPhone in einem Tab-Balken unten und auf dem Mac in einer
// Seitenleiste. Ein Tab-Balken auf dem Mac sieht aus wie eine portierte
// iPad-App, eine Seitenleiste auf dem iPhone verschenkt den halben
// Bildschirm.

import SwiftUI

/// Die Bereiche der App. Einmal aufgezählt, beide Plattformen lesen daraus.
///
/// Ohne diesen Typ stünden Titel und Symbol zweimal da, einmal je Plattform,
/// und liefen auseinander, sobald einer davon sich ändert.
enum Bereich: String, Hashable, CaseIterable, Identifiable {
    case heute, termine, sammlung, scannen, geraet

    /// Was diese Plattform zeigt.
    ///
    /// Scannen gibt es nur auf dem iPhone: `VNDocumentCameraViewController`
    /// ist iOS-only, und ein MacBook hält man nicht über ein Blatt Papier.
    static var sichtbare: [Bereich] {
        #if os(iOS)
        return allCases
        #else
        return allCases.filter { $0 != .scannen }
        #endif
    }

    var id: String { rawValue }

    var titel: String {
        switch self {
        case .heute: return "Heute"
        case .termine: return "Termine"
        case .sammlung: return "Sammlung"
        case .scannen: return "Scannen"
        case .geraet: return "Dieses Gerät"
        }
    }

    var symbol: String {
        switch self {
        case .heute: return "sun.max"
        case .termine: return "calendar"
        case .sammlung: return "checklist"
        case .scannen: return "doc.viewfinder"
        case .geraet:
            #if os(iOS)
            return "gearshape"
            #else
            return "laptopcomputer"
            #endif
        }
    }

    @ViewBuilder
    var ansicht: some View {
        switch self {
        case .heute: Heute()
        case .termine: Termine()
        case .sammlung: Sammlungsliste()
        case .scannen:
            #if os(iOS)
            Scannen()
            #else
            EmptyView()
            #endif
        case .geraet: Geraet()
        }
    }
}

struct Wurzel: View {
    @Environment(Zentrale.self) private var zentrale

    var body: some View {
        Group {
            switch zentrale.lage {
            case .unbekannt:
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .nichtGekoppelt:
                Kopplung()
            case .bereit, .getrennt:
                Inhalt()
            }
        }
        .task { await zentrale.lagePruefen() }
        // Koppeln per Link: miaos://koppeln?code=123456
        //
        // Der Weg für den Mac, wo der Code sowieso auf demselben Bildschirm
        // steht und niemand ihn abtippen will. Auf dem iPhone bleibt das
        // Tippfeld der Normalfall, denn dort steht der Code auf einem
        // anderen Gerät.
        .onOpenURL { adresse in
            guard adresse.scheme == "miaos", adresse.host() == "koppeln",
                  let teile = URLComponents(url: adresse, resolvingAgainstBaseURL: false),
                  let code = teile.queryItems?.first(where: { $0.name == "code" })?.value
            else { return }
            Task { try? await zentrale.koppeln(code: code) }
        }
    }
}

private struct Inhalt: View {
    @Environment(Zentrale.self) private var zentrale

    var body: some View {
        VStack(spacing: 0) {
            if case .getrennt(let grund) = zentrale.lage {
                Getrenntleiste(grund: grund) {
                    await zentrale.alleslLaden()
                }
            }
            Navigation()
        }
    }
}

// MARK: - Navigation je Plattform

private struct Navigation: View {
    /// Was gerade offen ist. Auf dem Mac steuert das die rechte Spalte, auf
    /// dem iPhone den Tab-Balken.
    @State private var offen: Bereich? = .heute

    var body: some View {
        #if os(iOS)
        // Die klassische `TabView` mit `tabItem` und nicht die neue
        // `Tab`-Syntax: die gibt es erst ab iOS 18, und die App soll auch auf
        // einem iPhone laufen, das noch auf 17 steht. Beide sehen identisch
        // aus, die neue ist nur kürzer zu schreiben.
        TabView(selection: $offen) {
            ForEach(Bereich.sichtbare) { bereich in
                NavigationStack {
                    bereich.ansicht
                }
                .tabItem { Label(bereich.titel, systemImage: bereich.symbol) }
                .tag(Optional(bereich))
            }
        }
        #else
        NavigationSplitView {
            // Die Auswahl der Liste IST die Navigation. Ein
            // `navigationDestination` in der Seitenleiste würde die Ansicht
            // in die Seitenleiste schieben statt in die rechte Spalte: genau
            // das hatte ich erst falsch.
            List(selection: $offen) {
                Section {
                    ForEach(Bereich.sichtbare.filter { $0 != .geraet }) { b in
                        Label(b.titel, systemImage: b.symbol).tag(Optional(b))
                    }
                }
                Section {
                    Label(Bereich.geraet.titel, systemImage: Bereich.geraet.symbol)
                        .tag(Optional(Bereich.geraet))
                }
            }
            .navigationTitle("Mia OS")
            .navigationSplitViewColumnWidth(min: 180, ideal: 200, max: 260)
        } detail: {
            if let offen {
                offen.ansicht
            } else {
                Leer(symbol: "sidebar.left", text: "Links auswählen")
            }
        }
        #endif
    }
}

// MARK: - Dieses Gerät

/// Adresse, Verbindungszustand, abmelden.
struct Geraet: View {
    @Environment(Zentrale.self) private var zentrale
    @State private var fragtNach = false

    /// Wohin der Ladeknopf zeigt.
    ///
    /// Der Download landet im Browser und nicht in der App: eine laufende
    /// Anwendung, die sich selbst ersetzt, ist der Punkt, an dem ein Fehler
    /// sie unbrauchbar macht — und dann fehlt Mia genau das Werkzeug, mit
    /// dem sie das melden würde. Derselbe Gedanke wie beim Umbenennen von
    /// Belegen: der Klick ist die Zustimmung.
    private var ladeAdresse: URL {
        #if os(macOS)
        let art = "mac"
        #else
        let art = "ios"
        #endif
        return URL(string: "/api/app/datei/\(art)", relativeTo: Einstellungen.adresse)!
    }

    var body: some View {
        Form {
            if let update = zentrale.update {
                Section("Aktualisierung") {
                    LabeledContent("Bereit", value: update.version)
                    if let datei = update.fuerDiesesGeraet {
                        LabeledContent("Größe", value: datei.lesbareGroesse)
                    }
                    Link(destination: ladeAdresse) {
                        Label("Herunterladen", systemImage: "arrow.down.circle")
                    }
                }
            }

            Section("Verbindung") {
                LabeledContent("Server", value: Einstellungen.adresse.host() ?? "")
                LabeledContent("Dieses Gerät", value: Einstellungen.geraetename)
                LabeledContent("Zustand") {
                    switch zentrale.lage {
                    case .bereit:
                        Label("verbunden", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                    case .getrennt:
                        Label("getrennt", systemImage: "exclamationmark.triangle.fill")
                            .foregroundStyle(.orange)
                    default:
                        Text("–")
                    }
                }
            }

            Section {
                Button("Gerät abmelden", role: .destructive) {
                    fragtNach = true
                }
            } footer: {
                Text("Der Schlüssel wird gelöscht. Zum Wiederverbinden braucht es einen neuen Code aus Mia OS.")
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Dieses Gerät")
        .confirmationDialog("Abmelden?", isPresented: $fragtNach) {
            Button("Abmelden", role: .destructive) {
                Task { await zentrale.abmelden() }
            }
        }
    }
}
