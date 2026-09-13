// Was heute ansteht.
//
// Der Bildschirm, den Mia morgens sieht. Termine oben, Fälliges darunter,
// Zettel ganz unten.
//
// **Warum kein Dashboard mit Kacheln:** die Web-Oberfläche hat eins, und es
// ist dort richtig, weil ein Browserfenster breit ist. Auf einem Telefon in
// der Hand ist eine Liste in Lesereihenfolge das, was man wirklich liest.

import SwiftUI

struct Heute: View {
    @Environment(Zentrale.self) private var zentrale

    var body: some View {
        List {
            if let stand = zentrale.stand {
                Section {
                    EmptyView()
                } header: {
                    Text(kopfzeile(stand))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textCase(nil)
                }
            }

            Section("Heute") {
                if zentrale.briefing.heute.isEmpty {
                    Leer(symbol: "calendar", text: "Heute nichts")
                        .listRowBackground(Color.clear)
                } else {
                    ForEach(zentrale.briefing.heute) { t in
                        Terminzeile(termin: t)
                    }
                }
            }

            if !zentrale.briefing.faellig.isEmpty {
                Section("Fällig") {
                    ForEach(zentrale.briefing.faellig) { e in
                        Faelligzeile(eintrag: e)
                    }
                }
            }

            if !zentrale.briefing.morgen.isEmpty {
                Section("Morgen") {
                    ForEach(zentrale.briefing.morgen) { t in
                        Terminzeile(termin: t)
                            // Gedämpft: morgen ist nicht heute, und die
                            // Ansicht soll das zeigen, ohne es zu schreiben.
                            .opacity(0.65)
                    }
                }
            }

            if !zentrale.briefing.hinweise.isEmpty {
                Section("Zettel") {
                    ForEach(zentrale.briefing.hinweise) { h in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(h.text)
                            if !h.von.isEmpty {
                                Text("von \(h.von)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("Heute")
        .refreshable {
            await zentrale.briefingLaden()
        }
        .task {
            // Nur laden, wenn noch nichts da ist. `.task` läuft bei jedem
            // Erscheinen der Ansicht, und ein Abruf beim Zurückwischen aus
            // einem Detail wäre Last ohne neuen Inhalt.
            if zentrale.stand == nil {
                await zentrale.briefingLaden()
            }
        }
    }

    private func kopfzeile(_ stand: Date) -> String {
        // Unter einer Minute nichts ausrechnen lassen: der Formatierer sagt
        // sonst "in 0 Sekunden", weil die Serverzeit ein paar Millisekunden
        // vorgeht und die Differenz negativ wird. Genau das stand im ersten
        // Screenshot auf dem Gerät.
        let alter = Date().timeIntervalSince(stand)
        if alter < 60 { return "gerade aktualisiert" }
        let f = RelativeDateTimeFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.unitsStyle = .full
        return "Stand \(f.localizedString(for: stand, relativeTo: Date()))"
    }
}

// MARK: - Zeilen

private struct Terminzeile: View {
    let termin: Tagestermin

    var body: some View {
        HStack(alignment: .top, spacing: Mass.abstand) {
            // Die Zeit in fester Breite und Ziffernbreite: sonst tanzt die
            // Spalte, weil „9:00" schmaler ist als „11:30".
            Text(termin.zeit.isEmpty ? "ganztags" : termin.zeit)
                .font(.subheadline.monospacedDigit())
                .foregroundStyle(termin.zeit.isEmpty ? .secondary : .primary)
                .frame(width: 62, alignment: .leading)

            VStack(alignment: .leading, spacing: 2) {
                Text(termin.titel)
                if !termin.ort.isEmpty {
                    Text(termin.ort)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 2)
    }
}

private struct Faelligzeile: View {
    let eintrag: OffenerEintrag
    @Environment(Zentrale.self) private var zentrale

    var body: some View {
        HStack(spacing: Mass.abstand) {
            Statuspunkt(farbe: .ausName(farbname), gefuellt: eintrag.status != "offen")
            Text(eintrag.titel)
            Spacer(minLength: 0)
            if !eintrag.datum.isEmpty {
                Text(Datumstext.kurz(eintrag.datum))
                    .font(.caption)
                    .foregroundStyle(eintrag.datum < Datumstext.heute ? .orange : .secondary)
            }
        }
    }

    private var farbname: String {
        zentrale.sammlung.farbe(fuer: eintrag.status, eigenschaft: "status") ?? "grau"
    }
}
