// Dokumente suchen.
//
// **Der Bildschirm, der bewusst wenig zeigt.** Ein leeres Suchfeld listet
// Ordner und Anzahl, keinen einzigen Dateinamen. In Mias Ablage liegen
// Ausweise, Behördenpost und medizinische Unterlagen, auch von anderen
// Menschen. Ein Telefon liegt auf Tischen, jemand schaut mit, und der
// Sperrbildschirm zeigt Vorschauen.
//
// Das ist keine Gestaltungsfrage, sondern eine Festlegung aus
// `docs/apple-zuschnitt.md`. Sie steht an drei Stellen gleichzeitig:
//
// 1. `store.search_documents()` gibt bei leerer Anfrage nichts zurück.
// 2. `/api/dokumente?nur_ordner=1` listet ohne Suchbegriff nicht auf.
// 3. Diese Ansicht ruft ausschließlich mit diesem Schalter auf.
//
// Die App wirft die Namen also nicht weg, sie bekommt sie gar nicht. Der
// Unterschied zählt: was über die Leitung geht, liegt danach im `URLCache`
// des Geräts.
//
// **Ein angetippter Ordner zeigt weiterhin keine Namen** (Mias Entscheidung
// vom 14.09.2026). Er ist der Einstieg, nicht das Ziel: ein Fingertipp ist
// keine Absicherung gegen jemanden, der mitliest.

import SwiftUI

struct Dokumentensuche: View {
    @Environment(Zentrale.self) private var zentrale
    @State private var suche = ""
    /// Der gewählte Ordner, als Pfad wie ihn der Server liefert.
    @State private var ordner = ""

    var body: some View {
        List {
            if suche.isEmpty {
                ordneransicht
            } else {
                trefferansicht
            }
        }
        .navigationTitle("Dokumente")
        // Die Platzierung nur auf dem iPhone festnageln: `navigationBarDrawer`
        // gibt es auf dem Mac nicht, dort setzt das System das Feld selbst in
        // die Werkzeugleiste.
        #if os(iOS)
        .searchable(
            text: $suche,
            placement: .navigationBarDrawer(displayMode: .always),
            prompt: "Name oder Inhalt"
        )
        #else
        .searchable(text: $suche, prompt: "Name oder Inhalt")
        #endif
        // Erst suchen, wenn Mia fertig getippt hat. Ein Abruf je Tastendruck
        // wären bei „meldebescheinigung“ neunzehn Anfragen, von denen achtzehn
        // niemand sieht.
        .onSubmit(of: .search) {
            Task { await zentrale.dokumenteLaden(suche: suche, ordner: ordner) }
        }
        .onChange(of: suche) { _, neu in
            // Das Leeren des Feldes führt sofort zurück zu den Ordnern. Auf
            // die alten Treffer stehen zu lassen, während das Feld leer ist,
            // wäre genau der Zustand, den die Regel verbietet.
            if neu.isEmpty {
                Task { await zentrale.dokumenteLaden() }
            }
        }
        .refreshable {
            await zentrale.dokumenteLaden(suche: suche, ordner: ordner)
        }
        .task {
            if zentrale.dokumente.ordner.isEmpty {
                await zentrale.dokumenteLaden()
            }
        }
    }

    // MARK: Ohne Suchbegriff

    @ViewBuilder
    private var ordneransicht: some View {
        Section {
            // Ein ganzer Satz statt einer nackten Zahl, und er sagt, was zu
            // tun ist. „187“ allein beantwortet keine Frage.
            Text(einstiegssatz)
                .font(.callout)
                .foregroundStyle(.secondary)
                .listRowBackground(Color.clear)
        }

        if zentrale.dokumente.ordner.isEmpty {
            Section {
                Leer(symbol: "magnifyingglass", text: "Noch nichts im Index")
                    .listRowBackground(Color.clear)
            }
        } else {
            Section("Ordner") {
                ForEach(zentrale.dokumente.ordner) { o in
                    Button {
                        // Nochmal tippen hebt die Wahl auf.
                        ordner = (ordner == o.top) ? "" : o.top
                        Task { await zentrale.dokumenteLaden(ordner: ordner) }
                    } label: {
                        HStack {
                            Text(o.name)
                                .foregroundStyle(.primary)
                            Spacer(minLength: Mass.abstand)
                            Text("\(o.n)")
                                .font(.subheadline.monospacedDigit())
                                .foregroundStyle(.secondary)
                            if ordner == o.top {
                                Image(systemName: "checkmark")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.tint)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private var einstiegssatz: String {
        let n = zentrale.dokumente.gesamt
        if n == 0 { return "Hier steht nichts, solange nichts gesucht wird." }
        let wo = ordner.isEmpty ? "im Index" : "in diesem Ordner"
        return "\(n) Dokumente \(wo). Namen erscheinen erst zur Suche."
    }

    // MARK: Mit Suchbegriff

    @ViewBuilder
    private var trefferansicht: some View {
        // Der Ordnerfilter greift hier in der App und nicht im Server:
        // `search_documents` sucht bewusst über den ganzen Index, weil wer
        // einen Namen kennt ihn finden soll, auch wenn er woanders liegt.
        // Die Namen sind an dieser Stelle bereits legitim geholt, ein Filter
        // darüber gibt also nichts preis, was nicht schon da wäre.
        let treffer = ordner.isEmpty
            ? zentrale.dokumente.treffer
            : zentrale.dokumente.treffer.filter { $0.folder.hasPrefix(ordner) }

        if zentrale.laedtDokumente && treffer.isEmpty {
            Section {
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .listRowBackground(Color.clear)
            }
        } else if treffer.isEmpty {
            Section {
                // Sagt, was man stattdessen tun kann, statt nur „0 Treffer“.
                Leer(
                    symbol: "magnifyingglass",
                    text: "Nichts für „\(suche)“. Weniger Wörter finden mehr."
                )
                .listRowBackground(Color.clear)
            }
        } else {
            Section("\(treffer.count) gefunden") {
                ForEach(treffer) { d in
                    Trefferzeile(treffer: d)
                }
            }
        }
    }
}

// MARK: - Eine Trefferzeile

private struct Trefferzeile: View {
    let treffer: Dokumenttreffer

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(treffer.name)
                .lineLimit(2)

            if treffer.stelle.isEmpty {
                Text("\(treffer.ordnerkurz) · \(treffer.groesse)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                // Die Fundstelle aus dem gelesenen Text. Der Server markiert
                // den Treffer mit eckigen Klammern, hier wird daraus
                // Halbfettes: Klammern mitten im Satz sehen aus wie ein
                // Tippfehler.
                Text(hervorgehoben(treffer.stelle))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 2)
    }

    /// `[Buxtehude]` wird halbfett, der Rest bleibt stehen.
    ///
    /// Von Hand durchlaufen statt mit einem regulären Ausdruck: der Text kommt
    /// aus gescannten Belegen und enthält selbst eckige Klammern, sobald die
    /// Texterkennung sich vertut. Ein Muster würde die dann mitfärben.
    private func hervorgehoben(_ text: String) -> AttributedString {
        var raus = AttributedString()
        var rest = Substring(text)

        while let auf = rest.firstIndex(of: "["),
              let zu = rest[rest.index(after: auf)...].firstIndex(of: "]") {
            raus.append(AttributedString(String(rest[..<auf])))

            var markiert = AttributedString(String(rest[rest.index(after: auf)..<zu]))
            markiert.font = .caption.weight(.semibold)
            markiert.foregroundColor = Farbe.text
            raus.append(markiert)

            rest = rest[rest.index(after: zu)...]
        }

        raus.append(AttributedString(String(rest)))
        return raus
    }
}
