// Was Farben angeht, aber nicht in farben.json gehoert.
//
// Farben.swift wird aus farben.json ERZEUGT und bei jedem Lauf ueberschrieben.
// Hier steht, was von Hand geschrieben ist: die Zuordnung der Farbnamen, die
// die Schnittstelle liefert, der Hex-Init fuer Kalenderfarben, und die Masse.
//
// **Warum keine festen Hexwerte fuer die Statusfarben:** ein `#3fa66a`, das
// auf Weiss gut aussieht, verschwindet auf Schwarz. Die Farben aus
// `farben.json` tragen ihre helle und dunkle Fassung selbst.

import SwiftUI

extension Color {
    /// Die Farbe zu einem Namen, wie die Sammlung ihn liefert.
    ///
    /// Unbekannte Namen werden grau statt bunt: eine neue Option, die Mia in
    /// den Einstellungen anlegt, soll keine zufällige Farbe bekommen.
    static func ausName(_ name: String) -> Color {
        switch name {
        case "gruen": return .green
        case "rot": return .red
        case "gelb": return .orange
        case "blau": return .blue
        case "lila": return .purple
        case "rosa": return .pink
        case "grau": return .secondary
        default: return .secondary
        }
    }

    /// Eine Farbe aus `#rrggbb`, wie der Kalender sie schickt.
    ///
    /// Fällt auf Blau zurück statt auf Schwarz: ein unsichtbarer Punkt sieht
    /// aus wie ein fehlender, ein blauer nur wie ein unerwarteter.
    init(hex: String) {
        let roh = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard roh.count == 6, let zahl = UInt32(roh, radix: 16) else {
            self = .blue
            return
        }
        self.init(
            .sRGB,
            red: Double((zahl >> 16) & 0xFF) / 255,
            green: Double((zahl >> 8) & 0xFF) / 255,
            blue: Double(zahl & 0xFF) / 255
        )
    }
}

enum Mass {
    /// Der Abstand, der überall gilt. Eine Zahl statt fünf: uneinheitliche
    /// Abstände sieht man sofort, ohne benennen zu können, was stört.
    static let abstand: CGFloat = 12
    static let abstandGross: CGFloat = 20
    static let ecke: CGFloat = 12
}
