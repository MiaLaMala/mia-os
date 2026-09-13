// Die Sammlung: alles, was offen ist.
//
// Gruppiert nach Status, so wie die Web-Oberfläche es in der Listenansicht
// tut. Ein Wisch nach links hakt ab.

import SwiftUI

struct Sammlungsliste: View {
    @Environment(Zentrale.self) private var zentrale
    @State private var zeigeFertige = false

    private var gruppen: [(status: String, eintraege: [Eintrag])] {
        // Die Reihenfolge kommt aus den Eigenschaften des Servers, nicht aus
        // einer Liste hier: legt Mia einen neuen Status an, steht er
        // automatisch an der richtigen Stelle.
        let reihenfolge = zentrale.sammlung.eigenschaften
            .first { $0.key == "status" }?
            .optionen.map(\.wert) ?? []

        let sichtbar = zentrale.sammlung.eintraege.filter { e in
            !e.archiviert && (zeigeFertige || !e.istFertig)
        }
        var nach: [String: [Eintrag]] = [:]
        for e in sichtbar {
            // Kein Status heisst "offen" und nicht "ohne": ein Eintrag ohne
            // gesetzten Status ist inhaltlich offen, und eine eigene Gruppe
            // dafuer spaltet die Liste ohne Gewinn. Genau so stand es beim
            // ersten Lauf auf dem Geraet: ein Punkt unter "Dran", derselbe
            // unter "Ohne".
            nach[e.status.isEmpty ? "offen" : e.status, default: []].append(e)
        }
        // Erst die bekannten Status in ihrer Reihenfolge, dann alles andere.
        var raus = reihenfolge.compactMap { s in
            nach[s].map { (status: s, eintraege: $0) }
        }
        for (s, liste) in nach where !reihenfolge.contains(s) {
            raus.append((status: s, eintraege: liste))
        }
        return raus
    }

    var body: some View {
        List {
            if gruppen.isEmpty {
                Leer(
                    symbol: "checkmark.circle",
                    text: zeigeFertige ? "Noch nichts hier" : "Alles erledigt"
                )
                .listRowBackground(Color.clear)
            }

            ForEach(gruppen, id: \.status) { gruppe in
                Section {
                    ForEach(gruppe.eintraege) { e in
                        Eintragszeile(eintrag: e)
                    }
                } header: {
                    HStack(spacing: 6) {
                        Statuspunkt(farbe: .ausName(farbe(gruppe.status)))
                        Text(gruppe.status.capitalized)
                        Text("\(gruppe.eintraege.count)")
                            .foregroundStyle(.tertiary)
                    }
                }
            }
        }
        .navigationTitle("Sammlung")
        .toolbar {
            Toggle(isOn: $zeigeFertige) {
                Label("Fertige", systemImage: zeigeFertige ? "eye" : "eye.slash")
            }
            .toggleStyle(.button)
        }
        .refreshable { await zentrale.sammlungLaden() }
        .task {
            if zentrale.sammlung.eintraege.isEmpty {
                await zentrale.sammlungLaden()
            }
        }
    }

    private func farbe(_ status: String) -> String {
        zentrale.sammlung.farbe(fuer: status, eigenschaft: "status") ?? "grau"
    }
}

private struct Eintragszeile: View {
    let eintrag: Eintrag
    @Environment(Zentrale.self) private var zentrale

    var body: some View {
        HStack(spacing: Mass.abstand) {
            VStack(alignment: .leading, spacing: 3) {
                Text(eintrag.titel)
                    .strikethrough(eintrag.istFertig, color: .secondary)
                    .foregroundStyle(eintrag.istFertig ? .secondary : .primary)

                HStack(spacing: 6) {
                    if !eintrag.datum.isEmpty {
                        Label(eintrag.datum, systemImage: "calendar")
                    }
                    if let bereich = eintrag.eigenschaften["bereich"], !bereich.isEmpty {
                        Text(bereich)
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .swipeActions(edge: .leading, allowsFullSwipe: true) {
            Button {
                Task { await zentrale.abhaken(eintrag) }
            } label: {
                Label(
                    eintrag.istFertig ? "Öffnen" : "Fertig",
                    systemImage: eintrag.istFertig ? "arrow.uturn.backward" : "checkmark"
                )
            }
            .tint(eintrag.istFertig ? .orange : .green)
        }
    }
}
