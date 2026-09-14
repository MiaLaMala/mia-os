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
///
/// **Fünf, und `geraet` ist keiner davon.** Entschieden am 13.09.2026, siehe
/// `docs/apple-zuschnitt.md`. Apple lässt im Tab-Balken zwei bis fünf zu,
/// der sechste zwänge zu einem „Mehr“-Reiter, und das ist die Ecke, in der
/// Dinge sterben. Scannen ist deshalb ein Knopf in „Heute“ und kein Ort:
/// es ist eine Handlung. „Dieses Gerät“ liegt aus demselben Grund hinter
/// dem Zahnrad und nicht im Balken.
enum Bereich: String, Hashable, CaseIterable, Identifiable {
    case heute, termine, sammlung, dokumente, homelab

    /// Was diese Plattform zeigt.
    ///
    /// Auf beiden dieselben fünf. Der Unterschied sitzt nur in der Form der
    /// Navigation, nicht im Inhalt.
    static var sichtbare: [Bereich] { allCases }

    var id: String { rawValue }

    var titel: String {
        switch self {
        case .heute: return "Heute"
        case .termine: return "Termine"
        case .sammlung: return "Sammlung"
        case .dokumente: return "Dokumente"
        case .homelab: return "Homelab"
        }
    }

    var symbol: String {
        switch self {
        case .heute: return "sun.max"
        case .termine: return "calendar"
        case .sammlung: return "checklist"
        // Die Lupe und nicht `folder`: die Ansicht ist eine Suche und keine
        // Dateiablage. Ein Ordnersymbol verspricht Blättern, und genau das
        // gibt es hier bewusst nicht.
        case .dokumente: return "magnifyingglass"
        case .homelab: return "server.rack"
        }
    }

    @ViewBuilder
    var ansicht: some View {
        switch self {
        case .heute: Heute()
        case .termine: Termine()
        case .sammlung: Sammlungsliste()
        case .dokumente: Dokumentensuche()
        case .homelab: Homelab()
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
    /// Ob „Dieses Gerät“ als Blatt offen ist. Nur auf dem iPhone: auf dem Mac
    /// steht es unten in der Seitenleiste.
    @State private var geraetOffen = false

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
                        // Das Zahnrad hängt an jedem Reiter und nicht nur an
                        // „Heute“: ein `NavigationStack` je Reiter heißt eine
                        // eigene Werkzeugleiste je Reiter, und ein Knopf, der
                        // nur auf einem Bildschirm existiert, ist einer, den
                        // man sucht.
                        .toolbar {
                            ToolbarItem(placement: .topBarLeading) {
                                Button {
                                    geraetOffen = true
                                } label: {
                                    Label("Dieses Gerät", systemImage: "gearshape")
                                }
                            }
                        }
                }
                .tabItem { Label(bereich.titel, systemImage: bereich.symbol) }
                .tag(Optional(bereich))
            }
        }
        .sheet(isPresented: $geraetOffen) {
            NavigationStack {
                Geraet()
                    .toolbar {
                        ToolbarItem(placement: .confirmationAction) {
                            Button("Fertig") { geraetOffen = false }
                        }
                    }
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
                    ForEach(Bereich.sichtbare) { b in
                        Label(b.titel, systemImage: b.symbol).tag(Optional(b))
                    }
                }
                // „Dieses Gerät“ ist kein Bereich mehr, sondern steht unten
                // für sich. Ein eigener Zustand statt eines `Bereich`-Falls:
                // sonst stünde es auf dem iPhone wieder im Tab-Balken, und
                // genau den hat Mia nicht bestellt.
                Section {
                    Button {
                        geraetOffen = true
                    } label: {
                        Label("Dieses Gerät", systemImage: "laptopcomputer")
                    }
                    .buttonStyle(.plain)
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
        .sheet(isPresented: $geraetOffen) {
            Geraet()
                .frame(minWidth: 420, minHeight: 380)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Fertig") { geraetOffen = false }
                    }
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
