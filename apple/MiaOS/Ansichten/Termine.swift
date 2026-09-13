// Die Termine der nächsten Wochen.
//
// Eine Liste nach Tagen, kein Raster. Ein Monatsraster auf einem Telefon
// zeigt zwölf Kästchen mit Punkten darin und beantwortet die Frage „was ist
// heute" schlechter als drei Zeilen Text.

import SwiftUI

struct Termine: View {
    @Environment(Zentrale.self) private var zentrale
    @State private var wochen = 2

    private var nachTag: [(tag: Date, termine: [Termin])] {
        let kal = Calendar.current
        var gruppen: [Date: [Termin]] = [:]
        for t in zentrale.termine {
            guard let d = t.beginn else { continue }
            gruppen[kal.startOfDay(for: d), default: []].append(t)
        }
        return gruppen
            .sorted { $0.key < $1.key }
            .map { (tag: $0.key, termine: $0.value.sorted { ($0.beginn ?? .distantPast) < ($1.beginn ?? .distantPast) }) }
    }

    var body: some View {
        List {
            if nachTag.isEmpty && !zentrale.laedtTermine {
                Leer(symbol: "calendar", text: "Nichts in den nächsten \(wochen) Wochen")
                    .listRowBackground(Color.clear)
            }

            ForEach(nachTag, id: \.tag) { gruppe in
                Section {
                    ForEach(gruppe.termine) { t in
                        Kalenderzeile(termin: t)
                    }
                } header: {
                    Text(tagestitel(gruppe.tag))
                }
            }

            if !nachTag.isEmpty {
                Button("Zwei Wochen mehr") {
                    wochen += 2
                    Task { await laden() }
                }
                .font(.callout)
            }
        }
        .navigationTitle("Termine")
        .refreshable { await laden() }
        .task {
            if zentrale.termine.isEmpty { await laden() }
        }
    }

    private func laden() async {
        let heute = Calendar.current.startOfDay(for: Date())
        let bis = Calendar.current.date(byAdding: .weekOfYear, value: wochen, to: heute) ?? heute
        await zentrale.termineLaden(von: heute, bis: bis)
    }

    /// „Heute", „Morgen", sonst „Montag, 21. September".
    ///
    /// Die zwei Sonderfälle sind die, die man täglich liest. Ein Datum, das
    /// „heute" heißt, muss man nicht im Kopf mit dem Kalender abgleichen.
    private func tagestitel(_ tag: Date) -> String {
        let kal = Calendar.current
        if kal.isDateInToday(tag) { return "Heute" }
        if kal.isDateInTomorrow(tag) { return "Morgen" }
        let f = DateFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = "EEEE, d. MMMM"
        return f.string(from: tag)
    }
}

private struct Kalenderzeile: View {
    let termin: Termin
    @Environment(Zentrale.self) private var zentrale

    var body: some View {
        HStack(alignment: .top, spacing: Mass.abstand) {
            // Der Balken in Kalenderfarbe statt eines Punkts: bei mehreren
            // Terminen am selben Tag sieht man so auf einen Blick, welche
            // zusammengehören.
            RoundedRectangle(cornerRadius: 2)
                .fill(Color(hex: termin.farbe))
                .frame(width: 3)
                .frame(maxHeight: .infinity)

            VStack(alignment: .leading, spacing: 3) {
                Text(termin.title)
                    .strikethrough(istAbgehakt)
                    .foregroundStyle(istAbgehakt ? .secondary : .primary)

                HStack(spacing: 8) {
                    Text(zeitraum)
                    if !termin.ort.isEmpty {
                        Label(termin.ort, systemImage: "mappin")
                    }
                    if termin.offene_aufgaben > 0 {
                        Label("\(termin.offene_aufgaben)", systemImage: "checklist")
                    }
                    if termin.hat_notiz {
                        Image(systemName: "note.text")
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 3)
        .swipeActions(edge: .leading, allowsFullSwipe: true) {
            // Nur Sammlungseinträge lassen sich abhaken. Ein echter
            // CalDAV-Termin hat keinen Status: ihn „fertig" zu nennen wäre
            // eine Erfindung der App.
            if let id = termin.eintragsID,
               let e = zentrale.sammlung.eintraege.first(where: { $0.id == id }) {
                Button {
                    Task { await zentrale.abhaken(e) }
                } label: {
                    Label(e.istFertig ? "Öffnen" : "Fertig",
                          systemImage: e.istFertig ? "arrow.uturn.backward" : "checkmark")
                }
                .tint(e.istFertig ? .orange : .green)
            }
        }
    }

    private var istAbgehakt: Bool {
        guard let id = termin.eintragsID else { return false }
        return zentrale.sammlung.eintraege.first { $0.id == id }?.istFertig ?? false
    }

    private var zeitraum: String {
        if termin.allDay { return "ganztägig" }
        let f = DateFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = "HH:mm"
        guard let von = termin.beginn else { return "" }
        guard let endeText = termin.end, let bis = Termin.datum(aus: endeText) else {
            return f.string(from: von)
        }
        return "\(f.string(from: von)) bis \(f.string(from: bis))"
    }
}
