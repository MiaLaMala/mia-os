// Was das Widget und die Uhr lesen, ohne selbst zu fragen.
//
// Ein Widget auf dem Sperrbildschirm wird vom System aufgeweckt, nicht von
// Mia. Es hat Sekunden Zeit und darf nicht auf ein Netz warten, das im Zug
// gerade weg ist. Also schreibt die App bei jedem Laden mit, und das Widget
// liest nur noch.
//
// **App Group statt UserDefaults.standard:** eine Widget-Erweiterung ist ein
// eigener Prozess mit eigenem Container. Ohne die Gruppe liest das Widget
// seinen eigenen, immer leeren Speicher und zeigt dauerhaft Platzhalter.

import Foundation

enum Ablage {
    /// Muss zu `com.apple.security.application-groups` in den Entitlements
    /// passen. Ein Tippfehler hier fällt nicht auf: `UserDefaults(suiteName:)`
    /// gibt dann stillschweigend `nil` zurück und alles bleibt leer.
    static let gruppe = "group.dev.mia-gruenwald.mia-os"

    private static let schluessel = "handgelenk"

    private static var speicher: UserDefaults? {
        UserDefaults(suiteName: gruppe)
    }

    /// Den zuletzt geholten Stand ablegen.
    static func sichern(_ daten: Handgelenk) {
        guard let roh = try? JSONEncoder().encode(daten) else { return }
        speicher?.set(roh, forKey: schluessel)
    }

    /// Was zuletzt da war. `nil`, wenn die App noch nie geladen hat.
    static func lesen() -> Handgelenk? {
        guard let roh = speicher?.data(forKey: schluessel) else { return nil }
        return try? JSONDecoder().decode(Handgelenk.self, from: roh)
    }
}
