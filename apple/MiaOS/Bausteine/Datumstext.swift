// Datumsangaben, wie Menschen sie lesen.
//
// Der Server liefert `2026-09-12`. Das ist richtig für eine Datenbank und
// falsch für einen Bildschirm: es steht eine Zeile unter „Fällig", und dort
// will man wissen, ob das gestern war oder nächste Woche, nicht welcher Tag
// im Jahr es ist. Genau so stand es im ersten Lauf auf dem Gerät.

import Foundation

enum Datumstext {
    /// Heute als ISO-Tag, zum Vergleichen mit den Feldern vom Server.
    static var heute: String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: Date())
    }

    /// „gestern", „heute", „Fr", „12.9."
    ///
    /// Vier Stufen, weil sie verschiedene Fragen beantworten. Bei etwas
    /// Überfälligem zählt, wie lange es schon liegt. Bei etwas in dieser
    /// Woche reicht der Wochentag. Alles darüber braucht ein Datum.
    static func kurz(_ iso: String) -> String {
        guard let tag = tagAus(iso) else { return iso }
        let kal = Calendar.current

        if kal.isDateInToday(tag) { return "heute" }
        if kal.isDateInYesterday(tag) { return "gestern" }
        if kal.isDateInTomorrow(tag) { return "morgen" }

        let tage = kal.dateComponents([.day], from: kal.startOfDay(for: Date()),
                                      to: kal.startOfDay(for: tag)).day ?? 0

        if tage < 0 {
            let her = -tage
            return her < 7 ? "vor \(her) Tagen" : "vor \(her / 7) Wochen"
        }
        if tage < 7 {
            let f = DateFormatter()
            f.locale = Locale(identifier: "de_DE")
            f.dateFormat = "EEEE"
            return f.string(from: tag)
        }
        let f = DateFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = "d. MMM"
        return f.string(from: tag)
    }

    private static func tagAus(_ iso: String) -> Date? {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f.date(from: String(iso.prefix(10)))
    }
}
