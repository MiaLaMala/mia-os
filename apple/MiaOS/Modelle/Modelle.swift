// Was der Server schickt, als Swift-Typen.
//
// Die Feldnamen stehen so, wie die Schnittstelle sie liefert: teils deutsch
// (`titel`, `kalender`), teils englisch (`title`, `start`, `allDay`). Das ist
// gewachsen, weil der Kalender im Browser FullCalendar füttert und dessen
// Felder heißen so. Hier wird das NICHT begradigt: ein `CodingKey`, der
// `start` auf `beginn` dreht, macht jede Fehlersuche zu einer Übersetzung
// zwischen zwei Namen für dieselbe Sache.
//
// Jeder Typ ist `Sendable` und ein `struct`: sie wandern vom Netz-Actor zur
// Oberfläche auf dem Hauptthread, und Swift 6 prüft das.

import Foundation

// MARK: - Briefing

/// Was heute ansteht. Die Grundlage für die erste Ansicht und das Widget.
struct Briefing: Decodable, Sendable, Equatable {
    let datum: String
    let heute: [Tagestermin]
    let morgen: [Tagestermin]
    let faellig: [OffenerEintrag]
    let offen: Int
    let hinweise: [Hinweis]
    /// Zusammengefasst als Fließtext, wie ihn die Morgen-Nachricht nutzt.
    let text: String

    // `geraet` fehlt hier mit Absicht: das sind die Einstellungen des
    // ESP32-Displays (Augenfarbe, Blinzeln). Eine App auf dem iPhone hat
    // damit nichts zu tun, und ein Feld, das niemand liest, verrottet.

    static let leer = Briefing(
        datum: "", heute: [], morgen: [], faellig: [], offen: 0, hinweise: [], text: ""
    )
}

struct Tagestermin: Decodable, Sendable, Equatable, Identifiable {
    let titel: String
    let zeit: String
    let ende: String
    let ort: String
    let kalender: String

    /// Kein `id` vom Server: das Briefing liefert die Termine als reine
    /// Anzeige, ohne Kennung. Titel und Zeit zusammen reichen, um sie in
    /// einer Liste auseinanderzuhalten.
    var id: String { "\(zeit)-\(titel)" }

    /// „9:00 bis 10:30", „ganztägig", oder nur die Anfangszeit.
    var zeitraum: String {
        if zeit.isEmpty { return "ganztägig" }
        if ende.isEmpty { return zeit }
        return "\(zeit) bis \(ende)"
    }
}

struct OffenerEintrag: Decodable, Sendable, Equatable, Identifiable {
    let id: Int
    let titel: String
    let datum: String
    let status: String
}

struct Hinweis: Decodable, Sendable, Equatable, Identifiable {
    let id: Int
    let text: String
    let von: String
}

// MARK: - Termine

/// Ein Termin im Kalenderblatt.
///
/// Kommt aus zwei Quellen: aus dem echten Kalender (CalDAV) und aus der
/// Sammlung, wenn ein Eintrag ein Datum hat. Die zweite Sorte trägt eine
/// Kennung der Form `eintrag-12` — deshalb ist `id` ein String und keine Zahl.
struct Termin: Decodable, Sendable, Equatable, Identifiable {
    let id: String
    let title: String
    let start: String
    let end: String?
    let allDay: Bool
    let kalender: String
    let ort: String
    /// Als `#rrggbb`. Der Server vergibt sie fest pro Kalendername, damit
    /// derselbe Kalender über Neustarts hinweg dieselbe Farbe behält.
    let farbe: String
    let hat_notiz: Bool
    let offene_aufgaben: Int

    /// Ob dieser Termin ein Sammlungseintrag ist und sich abhaken lässt.
    var istEintrag: Bool { id.hasPrefix("eintrag-") }

    /// Die Eintrags-ID, wenn es einer ist.
    var eintragsID: Int? {
        guard istEintrag else { return nil }
        return Int(id.dropFirst("eintrag-".count))
    }

    /// `start` kommt teils mit Uhrzeit (`2026-09-13T09:00:00`), teils ohne
    /// (`2026-09-13`) — ganztägige Einträge haben keine. Ein
    /// `ISO8601DateFormatter` mit festen Optionen scheitert an der jeweils
    /// anderen Form, deshalb beide Versuche.
    var beginn: Date? { Termin.datum(aus: start) }

    static func datum(aus text: String) -> Date? {
        let mitZeit = ISO8601DateFormatter()
        mitZeit.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = mitZeit.date(from: text) { return d }
        mitZeit.formatOptions = [.withInternetDateTime]
        if let d = mitZeit.date(from: text) { return d }
        // Ohne Zeitzone, so wie SQLite es ablegt: `2026-09-13T09:00:00`.
        let ohneZone = DateFormatter()
        ohneZone.locale = Locale(identifier: "en_US_POSIX")
        ohneZone.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        if let d = ohneZone.date(from: text) { return d }
        ohneZone.dateFormat = "yyyy-MM-dd"
        return ohneZone.date(from: text)
    }
}

// MARK: - Sammlung

/// Die Sammlung: Einträge plus die Eigenschaften, die es geben darf.
///
/// Die Eigenschaften kommen mit, weil ein Eintrag seine Werte als reine
/// Zeichenketten trägt (`status: "dran"`). Welche Farbe „dran" hat und
/// welche Werte überhaupt erlaubt sind, steht nur hier.
struct Sammlung: Decodable, Sendable, Equatable {
    let eintraege: [Eintrag]
    let eigenschaften: [Eigenschaft]

    static let leer = Sammlung(eintraege: [], eigenschaften: [])

    /// Die Farbe zu einem Wert, oder `nil`. Für die Punkte in der Liste.
    func farbe(fuer wert: String, eigenschaft key: String) -> String? {
        eigenschaften
            .first { $0.key == key }?
            .optionen.first { $0.wert == wert }?
            .farbe
    }
}

struct Eintrag: Decodable, Sendable, Equatable, Identifiable {
    let id: Int
    let titel: String
    let inhalt: String
    /// Freie Werte: `["status": "dran", "bereich": "Behörden"]`. Der Server
    /// lässt beliebige Schlüssel zu, deshalb ein Dictionary und kein Typ mit
    /// festen Feldern.
    let eigenschaften: [String: String]
    let datum: String
    let zeit: String
    let page_id: Int
    let sortierung: Double
    let archiviert: Bool

    var status: String { eigenschaften["status"] ?? "" }
    var istFertig: Bool { status == "fertig" }
}

struct Eigenschaft: Decodable, Sendable, Equatable, Identifiable {
    let key: String
    let name: String
    let art: String
    let optionen: [Option]
    let sortierung: Int

    var id: String { key }
}

struct Option: Decodable, Sendable, Equatable {
    let wert: String
    /// Ein Farbname, kein Hexwert: `grau`, `blau`, `gruen`, `rot`, `gelb`,
    /// `lila`, `rosa`. Die Zuordnung zu echten Farben macht die Oberfläche,
    /// weil sie je nach Hell- und Dunkelmodus anders ausfällt.
    let farbe: String
}

// MARK: - Homelab

/// Der Zustand der Dienste, wie `/api/homelab` ihn liefert.
///
/// `lage` ist die eine Aussage oben („Alles läuft“). Der Server formuliert
/// sie, nicht die App: er kennt die Zählweise, und ein zweiter Satzbau in
/// Swift liefe irgendwann daneben.
struct Homelablage: Decodable, Sendable, Equatable {
    let lage: Lagemeldung
    let dienste: [Dienst]
    let stand: String

    static let leer = Homelablage(
        lage: Lagemeldung(zustand: "", satz: ""), dienste: [], stand: ""
    )
}

struct Lagemeldung: Decodable, Sendable, Equatable {
    /// `oben`, `unten`, `wartung` oder leer, wenn gar nichts überwacht wird.
    let zustand: String
    let satz: String
}

struct Dienst: Decodable, Sendable, Equatable, Identifiable {
    let name: String
    let zustand: String
    let meldung: String
    /// `nil` heißt: noch keine Messwerte. Nicht null Prozent, und die
    /// Ansicht muss den Unterschied zeigen.
    let uptime: Double?

    var id: String { name }
    var istUnten: Bool { zustand == "unten" }
}

// MARK: - Dokumente

/// Ein Ordner mit Anzahl. Der Einstieg in die Dokumentensuche.
///
/// **Mehr kommt ohne Suchbegriff nicht.** Die App ruft `/api/dokumente` immer
/// mit `nur_ordner=1` auf, und der Server schickt dann eine leere
/// Trefferliste. Der Grund steht in `docs/apple-zuschnitt.md`: in den Ordnern
/// liegen Ausweise und medizinische Unterlagen, auch von anderen Menschen,
/// und ein Telefon liegt auf Tischen.
struct Dokumentordner: Decodable, Sendable, Equatable, Identifiable {
    let top: String
    let n: Int

    var id: String { top }

    /// Der letzte Pfadteil: „/Dokumente/02 Medizinisch“ wird „02 Medizinisch“.
    var name: String {
        top.split(separator: "/").last.map(String.init) ?? top
    }
}

/// Ein Treffer aus der Dokumentensuche.
///
/// Nur die Felder, die die App wirklich zeigt. Der Server schickt mehr
/// (Vorschaubilder, Editor-Links, Nextcloud-Pfade), aber ein Feld, das
/// niemand liest, verrottet, und hier wiegt jedes Feld doppelt: was nicht
/// dekodiert wird, steht auch in keinem Speicherauszug.
struct Dokumenttreffer: Decodable, Sendable, Equatable, Identifiable {
    let id: Int
    let name: String
    let folder: String
    let ext: String
    let groesse: String
    let datum: String
    /// Die Fundstelle im gelesenen Text, mit `[` und `]` um den Treffer.
    /// Steht nur bei selbst gescannten Belegen, der Bestand hat keinen Text.
    let stelle: String

    var ordnerkurz: String {
        folder.split(separator: "/").last.map(String.init) ?? folder
    }
}

/// Was `/api/dokumente` zurückgibt.
struct Dokumentantwort: Decodable, Sendable, Equatable {
    let treffer: [Dokumenttreffer]
    let gesamt: Int
    let ordner: [Dokumentordner]

    static let leer = Dokumentantwort(treffer: [], gesamt: 0, ordner: [])
}

// MARK: - Schnelleingabe

/// Was der Server aus einem hingeworfenen Satz gemacht hat.
///
/// `meldung` ist immer da und in ganzen Worten formuliert („88,4 kg
/// eingetragen"). Genau deshalb liest Siri sie direkt vor, statt dass die App
/// aus `art` und `kg` selbst einen Satz baut: der Server weiß besser, was er
/// getan hat.
struct SchnellAntwort: Decodable, Sendable {
    let art: String
    let meldung: String
}

// MARK: - Für die Uhr

/// Der Tag in der kleinstmöglichen Form.
///
/// Kommt von `/api/handgelenk` und nicht vom Briefing. Der Unterschied ist
/// nicht nur die Größe (gemessen 152 Bytes gegen 1209), sondern der Inhalt:
/// das Briefing zeigt den ganzen Tag, das hier zeigt, was **noch kommt**.
/// Ein Termin um neun ist um halb elf keine nützliche Anzeige mehr.
/// `Codable` und nicht nur `Decodable`: die Uhr schreibt die zuletzt
/// geholten Zahlen in `UserDefaults`, damit sie beim nächsten Heben des Arms
/// sofort etwas zeigen kann statt eines Ladekreises. Dafür muss der Typ sich
/// auch kodieren lassen.
struct Handgelenk: Codable, Sendable, Equatable {
    let naechster: Kurztermin?
    /// Wie viele danach heute noch kommen.
    let spaeter_heute: Int
    let faellig: Int
    let offen: Int
    /// Wann diese Zahlen entstanden sind. Die Uhr zeigt notfalls den letzten
    /// bekannten Stand und muss sagen können, wie alt er ist.
    let stand: String

    static let leer = Handgelenk(
        naechster: nil, spaeter_heute: 0, faellig: 0, offen: 0, stand: ""
    )

    var standDatum: Date? { Termin.datum(aus: stand) }
}

struct Kurztermin: Codable, Sendable, Equatable {
    let titel: String
    /// Leer bei ganztägigen Terminen. Dann zeigt die Uhr keine Zeit statt
    /// „00:00", was gelogen wäre.
    let zeit: String
    let ort: String
}

// MARK: - Aktualisierung

/// Was der Server an gebauten Apps bereithält.
struct AppStand: Decodable, Sendable, Equatable {
    let version: String
    let gebaut_am: String
    let mac: AppDatei?
    let ios: AppDatei?

    /// Die Datei für die Plattform, auf der das hier gerade läuft.
    var fuerDiesesGeraet: AppDatei? {
        #if os(macOS)
        return mac
        #else
        return ios
        #endif
    }

    /// Ob die bereitstehende Fassung neuer ist als die laufende.
    ///
    /// Verglichen wird Zahl für Zahl, nicht als Text: „0.1.9" ist als Text
    /// größer als „0.1.10", als Version aber kleiner. Genau dieser Vergleich
    /// ist der Grund, warum ein Update sonst nie angeboten würde, sobald die
    /// Commit-Zahl zweistellig wird — und das ist sie nach zehn Commits.
    func istNeuerAls(_ laufend: String) -> Bool {
        let a = version.split(separator: ".").map { Int($0) ?? 0 }
        let b = laufend.split(separator: ".").map { Int($0) ?? 0 }
        for i in 0..<max(a.count, b.count) {
            let links = i < a.count ? a[i] : 0
            let rechts = i < b.count ? b[i] : 0
            if links != rechts { return links > rechts }
        }
        return false
    }
}

struct AppDatei: Decodable, Sendable, Equatable {
    let datei: String
    let groesse: Int
    let sha256: String

    /// „12,4 MB". Für den Hinweis, bevor jemand auf Laden tippt.
    var lesbareGroesse: String {
        ByteCountFormatter.string(fromByteCount: Int64(groesse), countStyle: .file)
    }
}

// MARK: - Seiten

/// Eine Seite im Seitenbaum. `parent_id` ist `nil` auf der obersten Ebene.
struct Seite: Decodable, Sendable, Equatable, Identifiable {
    let id: Int
    let parent_id: Int?
    let titel: String
    let symbol: String
    let inhalt: String
    let hat_sammlung: Bool
    let ansicht: String
    let gruppe_nach: String
    let sammelt_alles: Bool
    let sortierung: Double
}
