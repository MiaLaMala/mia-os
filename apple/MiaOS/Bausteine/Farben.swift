// Erzeugt aus farben.json. Nicht von Hand aendern.

import SwiftUI

/// Die Farben von Mia OS.
///
/// Jede Farbe kennt ihre helle und ihre dunkle Fassung und waehlt
/// selbst: `Color(light:dark:)` fragt das Farbschema erst beim
/// Zeichnen ab. Ein `if colorScheme == .dark` in den Ansichten waere
/// an jeder einzelnen Stelle noetig und irgendwo vergisst man es.
enum Farbe {
    /// Hintergrund des Fensters
    static let grund = Color(light: "#fdf9f9", dark: "#100b0a")
    /// Karten
    static let flaeche = Color(light: "#ffffff", dark: "#1c1414")
    /// Seitenleiste, Balken
    static let erhoben = Color(light: "#f7f0ef", dark: "#281d1d")
    /// Trenner, Raender
    static let linie = Color(light: "#e6dbdb", dark: "#3d2f2f")
    /// Lesetext, Titel
    static let text = Color(light: "#1b1414", dark: "#f6f0f0")
    /// Nebensaechliches
    static let gedaempft = Color(light: "#695959", dark: "#a29594")
    /// was JETZT dran ist
    static let akzent = Color(light: "#c70030", dark: "#f33e52")
    /// Kante am hervorgehobenen Block
    static let akzent_matt = Color(light: "#ffc6c4", dark: "#72101f")
    /// Flaeche hinter dem Hervorgehobenen
    static let akzent_hauch = Color(light: "#ffeae9", dark: "#371113")
    /// erledigt, laeuft
    static let gut = Color(light: "#1a8a42", dark: "#3ad26a")
    /// faellig, bald
    static let achtung = Color(light: "#a86400", dark: "#ff9f0a")
    /// kaputt
    static let fehler = Color(light: "#c4441f", dark: "#ff7043")
}

extension Color {
    /// Eine Farbe, die dem Systemthema folgt.
    ///
    /// Auf dem Mac über `NSColor(name:dynamicProvider:)`, auf iOS und
    /// watchOS über `UIColor(dynamicProvider:)`. Beide fragen bei
    /// jedem Zeichnen nach, also stimmt die Farbe auch, wenn das Thema
    /// bei geöffneter App umgeschaltet wird.
    init(light: String, dark: String) {
        #if os(macOS)
        self.init(nsColor: NSColor(name: nil) { erscheinung in
            let dunkel = erscheinung.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
            return NSColor(mosHex: dunkel ? dark : light)
        })
        #else
        self.init(uiColor: UIColor { merkmale in
            UIColor(mosHex: merkmale.userInterfaceStyle == .dark ? dark : light)
        })
        #endif
    }
}

#if os(macOS)
private extension NSColor {
    /// Nicht `init(hex:)`: so heisst bereits ein Initialisierer in
    /// Masse.swift für Kalenderfarben. Zwei gleich benannte an
    /// derselben Stelle übersetzen nicht.
    convenience init(mosHex hex: String) {
        let z = UInt64(hex.dropFirst(), radix: 16) ?? 0
        self.init(
            srgbRed: Double((z >> 16) & 0xFF) / 255,
            green: Double((z >> 8) & 0xFF) / 255,
            blue: Double(z & 0xFF) / 255,
            alpha: 1
        )
    }
}
#else
private extension UIColor {
    convenience init(mosHex hex: String) {
        let z = UInt64(hex.dropFirst(), radix: 16) ?? 0
        self.init(
            red: Double((z >> 16) & 0xFF) / 255,
            green: Double((z >> 8) & 0xFF) / 255,
            blue: Double(z & 0xFF) / 255,
            alpha: 1
        )
    }
}
#endif
