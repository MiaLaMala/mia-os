// Mia OS für Siri und die Kurzbefehle-App.
//
// **Das Zweite, was eine Website nicht kann.** „Hey Siri, was steht an" und
// „Hey Siri, Termin eintragen" ohne die App zu öffnen. Dazu tauchen diese
// Befehle in Kurzbefehlen auf und lassen sich mit allem verketten, was iOS
// sonst kann: an einen Fokus hängen, an eine Uhrzeit, an einen NFC-Sticker.
//
// Die Beschreibungen sind das, was Siri vorliest, und die Titel das, was in
// der Kurzbefehle-App steht. Beides also in ganzen deutschen Sätzen und nicht
// in Entwicklersprache.

import AppIntents
import SwiftUI
import WidgetKit

// MARK: - Was steht an

struct WasStehtAn: AppIntent {
    static let title: LocalizedStringResource = "Was steht an"
    static let description = IntentDescription(
        "Zeigt den nächsten Termin und wie viel heute noch fällig ist.",
        categoryName: "Mia OS"
    )

    // Siri antwortet direkt, ohne die App zu öffnen. Genau dafür ist der
    // schlanke Endpunkt da.
    static let openAppWhenRun: Bool = false

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let draht = Draht(adresse: Einstellungen.adresse)
        let daten: Handgelenk
        do {
            daten = try await draht.handgelenk()
            Ablage.sichern(daten)
            WidgetCenter.shared.reloadAllTimelines()
        } catch {
            // Beim Scheitern der letzte bekannte Stand. Siri „ich kann Mia OS
            // nicht erreichen" antworten zu lassen, wenn die Antwort von vor
            // zehn Minuten noch stimmt, wäre unnötig.
            guard let alt = Ablage.lesen() else {
                return .result(dialog: "Ich komme gerade nicht an Mia OS.")
            }
            daten = alt
        }

        return .result(dialog: IntentDialog(stringLiteral: satz(daten)))
    }

    /// Ein Satz, der sich vorlesen lässt.
    ///
    /// Keine Aufzählung und keine Zahlen ohne Einheit: Siri spricht das, und
    /// „3, 6" klingt wie ein Fehler.
    private func satz(_ d: Handgelenk) -> String {
        var teile: [String] = []
        if let t = d.naechster {
            if t.zeit.isEmpty {
                teile.append("Heute: \(t.titel)")
            } else {
                teile.append("Um \(t.zeit) \(t.titel)")
            }
            if d.spaeter_heute == 1 {
                teile.append("danach kommt noch einer")
            } else if d.spaeter_heute > 1 {
                teile.append("danach kommen noch \(d.spaeter_heute)")
            }
        } else {
            teile.append("Heute steht nichts mehr an")
        }
        if d.faellig == 1 {
            teile.append("eine Sache ist fällig")
        } else if d.faellig > 1 {
            teile.append("\(d.faellig) Sachen sind fällig")
        }
        return teile.joined(separator: ", ") + "."
    }
}

// MARK: - Schnell eintragen

struct SchnellEintragen: AppIntent {
    static let title: LocalizedStringResource = "In Mia OS eintragen"
    static let description = IntentDescription(
        "Legt einen Eintrag an. Mia OS liest Datum und Uhrzeit selbst heraus.",
        categoryName: "Mia OS"
    )
    static let openAppWhenRun: Bool = false

    @Parameter(title: "Was", requestValueDialog: "Was soll ich eintragen?")
    var text: String

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let draht = Draht(adresse: Einstellungen.adresse)
        do {
            // Derselbe Weg wie die Schnelleingabe im Browser: der Server
            // deutet „morgen 9 Uhr Zahnarzt" selbst. Die Deutung gehört
            // dorthin, wo sie schon steht, nicht ein zweites Mal in Swift.
            let antwort = try await draht.schnell(text)
            WidgetCenter.shared.reloadAllTimelines()
            return .result(dialog: IntentDialog(stringLiteral: antwort.meldung))
        } catch {
            return .result(dialog: "Das hat nicht geklappt. \(error.localizedDescription)")
        }
    }
}

// MARK: - Abhaken

struct NaechstesAbhaken: AppIntent {
    static let title: LocalizedStringResource = "Fälliges abhaken"
    static let description = IntentDescription(
        "Hakt den ältesten fälligen Eintrag ab.",
        categoryName: "Mia OS"
    )
    static let openAppWhenRun: Bool = false

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let draht = Draht(adresse: Einstellungen.adresse)
        let sammlung = try await draht.sammlung()
        let heute = ISO8601DateFormatter.tagesformat().string(from: Date())

        // Der älteste fällige zuerst: was am längsten liegt, drückt am
        // meisten. Ohne Datum ist nichts fällig, das sind Ideen und keine
        // Verpflichtungen.
        let faellig = sammlung.eintraege
            .filter { !$0.istFertig && !$0.archiviert && !$0.datum.isEmpty && $0.datum <= heute }
            .sorted { $0.datum < $1.datum }

        guard let erster = faellig.first else {
            return .result(dialog: "Nichts fällig.")
        }
        try await draht.eintragAendern(
            id: erster.id,
            felder: ["eigenschaften": ["status": "fertig"]]
        )
        WidgetCenter.shared.reloadAllTimelines()
        return .result(dialog: IntentDialog(stringLiteral: "\(erster.titel) ist abgehakt."))
    }
}

extension ISO8601DateFormatter {
    /// Nur das Datum, zum Vergleichen mit den Feldern vom Server.
    ///
    /// Eine Funktion und keine statische Eigenschaft: `ISO8601DateFormatter`
    /// ist nicht `Sendable`, und Swift 6 verbietet ihn deshalb als geteilten
    /// globalen Zustand. Ein Formatierer pro Aufruf kostet nichts, hier
    /// laufen keine Schleifen über Tausende Zeilen.
    static func tagesformat() -> ISO8601DateFormatter {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withFullDate]
        return f
    }
}

// MARK: - Was Siri von allein anbietet

struct MiaOSKurzbefehle: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: WasStehtAn(),
            phrases: [
                "Was steht an in \(.applicationName)",
                "\(.applicationName) was steht an",
                "Frag \(.applicationName) nach meinem Tag",
            ],
            shortTitle: "Was steht an",
            systemImageName: "sun.max"
        )
        AppShortcut(
            intent: SchnellEintragen(),
            phrases: [
                "In \(.applicationName) eintragen",
                "\(.applicationName) neuer Eintrag",
            ],
            shortTitle: "Eintragen",
            systemImageName: "plus.circle"
        )
        AppShortcut(
            intent: NaechstesAbhaken(),
            phrases: [
                "In \(.applicationName) abhaken",
                "\(.applicationName) erledigt",
            ],
            shortTitle: "Abhaken",
            systemImageName: "checkmark.circle"
        )
    }
}
