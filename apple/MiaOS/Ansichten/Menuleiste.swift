// Mia OS in der Menüleiste.
//
// **Das, was eine Mac-App von einem Browser-Tab unterscheidet.** Der nächste
// Termin steht oben rechts neben Uhrzeit und Batterie, ohne dass irgendein
// Fenster offen ist. Ein Klick öffnet eine kleine Übersicht, ein zweiter
// schließt sie wieder.
//
// Der Text neben dem Symbol ist bewusst knapp: die Menüleiste teilen sich
// alle Programme, und wer dort drei Wörter hinschreibt, verdrängt die der
// anderen. „19:30 Berufsschule" ist die Grenze, danach wird gekürzt.

#if os(macOS)

import SwiftUI

struct Menuleiste: Scene {
    /// Durchgereicht statt über `@Environment` geholt.
    ///
    /// Eine `Scene` liest `@Environment`, bevor `.environment(...)` auf ihr
    /// gewirkt hat: `MenuBarExtra` baut seinen Inhalt schon während
    /// `applicationDidFinishLaunching`, und dort ist der Wert noch nicht
    /// gesetzt. Das endet nicht in einer leeren Ansicht, sondern in einem
    /// `assertionFailure` tief in SwiftUI, und die App startet gar nicht
    /// erst. Genau so ist sie am 13.09. beim ersten Start abgestürzt.
    let zentrale: Zentrale

    var body: some Scene {
        MenuBarExtra {
            Menuinhalt().environment(zentrale)
        } label: {
            Beschriftung().environment(zentrale)
        }
        // `.window` statt `.menu`: der Inhalt ist eine SwiftUI-Ansicht mit
        // Knöpfen und Abständen, kein klassisches Menü aus Textzeilen. Mit
        // `.menu` würde SwiftUI versuchen, daraus Menüeinträge zu machen, und
        // das sieht auf halbem Weg kaputt aus.
        .menuBarExtraStyle(.window)
    }
}

/// Was in der Menüleiste steht.
private struct Beschriftung: View {
    @Environment(Zentrale.self) private var zentrale

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: symbol)
            if let text = kurztext {
                Text(text)
            }
        }
    }

    /// Das Symbol sagt schon etwas, bevor man liest.
    private var symbol: String {
        if case .getrennt = zentrale.lage { return "wifi.exclamationmark" }
        if zentrale.briefing.faellig.isEmpty { return "circle" }
        return "circle.fill"
    }

    private var kurztext: String? {
        guard let t = zentrale.briefing.heute.first else {
            // Nichts mehr heute: dann steht dort auch nichts. Ein „frei" in
            // der Menüleiste ist eine Zeile, die jeden Tag Platz kostet und
            // nichts sagt.
            return zentrale.briefing.faellig.isEmpty
                ? nil
                : "\(zentrale.briefing.faellig.count) fällig"
        }
        let titel = t.titel.count > 22 ? String(t.titel.prefix(21)) + "…" : t.titel
        return t.zeit.isEmpty ? titel : "\(t.zeit)  \(titel)"
    }
}

/// Was beim Klick aufklappt.
private struct Menuinhalt: View {
    @Environment(Zentrale.self) private var zentrale
    @Environment(\.openWindow) private var fensterOeffnen

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Kopf()

            Divider().padding(.vertical, 6)

            if zentrale.briefing.heute.isEmpty {
                Text("Heute nichts mehr")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 4)
            } else {
                ForEach(zentrale.briefing.heute.prefix(4)) { t in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(t.zeit.isEmpty ? "–" : t.zeit)
                            .font(.callout.monospacedDigit())
                            .foregroundStyle(.secondary)
                            .frame(width: 42, alignment: .leading)
                        Text(t.titel)
                            .font(.callout)
                            .lineLimit(1)
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 2)
                }
            }

            if !zentrale.briefing.faellig.isEmpty {
                Divider().padding(.vertical, 6)
                ForEach(zentrale.briefing.faellig.prefix(3)) { e in
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.circle")
                            .foregroundStyle(.orange)
                        Text(e.titel)
                            .font(.callout)
                            .lineLimit(1)
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 2)
                }
            }

            Divider().padding(.vertical, 6)

            HStack {
                Button("Öffnen") {
                    // Bringt das Hauptfenster nach vorn. Ohne das Aktivieren
                    // öffnet es sich hinter dem gerade benutzten Programm,
                    // weil ein Menüleisten-Programm selbst nicht im
                    // Vordergrund ist.
                    NSApp.activate(ignoringOtherApps: true)
                    fensterOeffnen(id: "haupt")
                }
                .keyboardShortcut("o")

                Spacer()

                Button {
                    Task { await zentrale.alleslLaden() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .keyboardShortcut("r")
                .help("Aktualisieren")

                Button {
                    NSApp.terminate(nil)
                } label: {
                    Image(systemName: "power")
                }
                .help("Mia OS beenden")
            }
            .buttonStyle(.borderless)
        }
        .padding(12)
        .frame(width: 280)
        .task { await zentrale.briefingLaden() }
    }
}

private struct Kopf: View {
    @Environment(Zentrale.self) private var zentrale

    var body: some View {
        HStack {
            Text("Heute")
                .font(.headline)
            Spacer()
            if zentrale.briefing.offen > 0 {
                Text("\(zentrale.briefing.offen) offen")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

#endif
