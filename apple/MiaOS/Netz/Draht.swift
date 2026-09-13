// Wie die App mit Mia OS redet.
//
// Eine Schicht, kein Framework. Die Schnittstelle liefert JSON, `URLSession`
// holt es, `Codable` liest es. Alles dazwischen wäre Gewicht ohne Gegenwert.
//
// **Was hier die eigentliche Arbeit ist:** der Schlüssel und wo er liegt.
// Ein Geräteschlüssel gehört in die Keychain, nicht in `UserDefaults`. In
// den Defaults liegt er als lesbare Datei im App-Container, und ein Backup
// trägt ihn ungefragt mit. Die Keychain-Klasse
// `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` verlässt das Gerät nie,
// auch nicht in ein iCloud-Backup.

import Foundation

// MARK: - Fehler

enum NetzFehler: LocalizedError, Equatable {
    /// Kein Schlüssel und kein Heimnetz: die App muss sich erst koppeln.
    case nichtGekoppelt
    /// Der Server war nicht erreichbar. Trägt den Grund mit, damit die
    /// Oberfläche „kein Netz" von „Server aus" unterscheiden kann.
    case nichtErreichbar(String)
    /// Der Server hat geantwortet, aber mit einem Fehler.
    case serverFehler(status: Int, text: String)
    /// Die Antwort ließ sich nicht lesen.
    case unlesbar(String)

    var errorDescription: String? {
        switch self {
        case .nichtGekoppelt:
            return "Nicht gekoppelt. Der Kopplungscode steht in Mia OS unter Einstellungen."
        case .nichtErreichbar(let grund):
            return "Mia OS ist nicht erreichbar. \(grund)"
        case .serverFehler(let status, let text):
            return text.isEmpty ? "Der Server meldet Fehler \(status)." : text
        case .unlesbar(let was):
            return "Antwort nicht lesbar: \(was)"
        }
    }
}

// MARK: - Schlüsselbund

/// Wo der Geräteschlüssel liegt.
///
/// Eigener Typ statt einer Handvoll `SecItem`-Aufrufe zwischen dem
/// Netzwerkcode: so gibt es genau eine Stelle, an der die
/// Zugriffsklasse steht, und man kann sie nicht an einer Stelle vergessen.
struct Schluesselbund {
    private let dienst = "dev.mia-gruenwald.mia-os"
    private let konto = "geraeteschluessel"

    /// Die geteilte Schlüsselbund-Gruppe für iPhone und Uhr.
    ///
    /// Ohne sie hat jede App ihren eigenen Schlüsselbund, und die Uhr müsste
    /// sich einzeln koppeln: sechs Ziffern auf einem 40-mm-Bildschirm
    /// einzutippen ist eine Zumutung. Mit ihr erbt die Uhr den Schlüssel, den
    /// das iPhone schon hat.
    ///
    /// **Braucht die Entitlement `keychain-access-groups`, und die verlangt
    /// ein bezahltes Apple Developer Program.** Ohne Programm bleibt der Wert
    /// `nil`, jede App hat ihren eigenen Bund, und die Uhr sagt „Am iPhone
    /// koppeln" statt selbst zu fragen. Das ist der ehrliche Zustand, bis Mia
    /// entscheidet, ob ihr die Uhr die 99 USD im Jahr wert ist.
    private var gruppe: String? {
        guard let wert = Bundle.main.object(forInfoDictionaryKey: "MiaOSKeychainGruppe") as? String,
              !wert.isEmpty
        else { return nil }
        return wert
    }

    func lesen() -> String? {
        var frage: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: dienst,
            kSecAttrAccount as String: konto,
            kSecReturnData as String: true,
        ]
        if let gruppe { frage[kSecAttrAccessGroup as String] = gruppe }
        frage[kSecMatchLimit as String] = kSecMatchLimitOne

        var fund: CFTypeRef?
        guard SecItemCopyMatching(frage as CFDictionary, &fund) == errSecSuccess,
              let daten = fund as? Data,
              let text = String(data: daten, encoding: .utf8)
        else { return nil }
        return text
    }

    func schreiben(_ schluessel: String) {
        // Erst weg, dann neu. `SecItemUpdate` bräuchte einen zweiten Pfad für
        // den Fall, dass noch nichts da ist, und der wäre selten genug, um
        // ungetestet zu bleiben.
        loeschen()
        let eintrag: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: dienst,
            kSecAttrAccount as String: konto,
            kSecValueData as String: Data(schluessel.utf8),
            // Nicht `WhenUnlocked`: ein Widget oder eine
            // Hintergrundaktualisierung läuft auch, wenn das iPhone in der
            // Tasche liegt. Nicht ohne `ThisDeviceOnly`: sonst wandert der
            // Schlüssel ins iCloud-Backup und damit auf jedes Gerät, das
            // dieses Backup einspielt.
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]
        var mitGruppe = eintrag
        if let gruppe { mitGruppe[kSecAttrAccessGroup as String] = gruppe }
        SecItemAdd(mitGruppe as CFDictionary, nil)
    }

    func loeschen() {
        var frage: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: dienst,
            kSecAttrAccount as String: konto,
        ]
        if let gruppe { frage[kSecAttrAccessGroup as String] = gruppe }
        SecItemDelete(frage as CFDictionary)
    }
}

// MARK: - Der Draht

/// Redet mit Mia OS.
///
/// `actor`, damit Schlüssel und laufende Anfragen nicht von mehreren Stellen
/// gleichzeitig angefasst werden. Die Oberfläche ruft von `@MainActor` aus,
/// die Anfragen selbst laufen daneben.
actor Draht {
    /// Wo Mia OS steht. Änderbar, weil die Adresse im Heimnetz eine andere
    /// sein kann als von unterwegs.
    private(set) var adresse: URL
    private let bund = Schluesselbund()
    private let sitzung: URLSession

    init(adresse: URL = Einstellungen.standardAdresse, sitzung: URLSession? = nil) {
        self.adresse = adresse
        if let sitzung {
            self.sitzung = sitzung
        } else {
            let k = URLSessionConfiguration.default
            // Kurz halten: der Server steht im Heimnetz. Antwortet er nach
            // zehn Sekunden nicht, ist er nicht langsam, sondern weg, und
            // die App soll das sagen statt zu drehen.
            k.timeoutIntervalForRequest = 10
            k.timeoutIntervalForResource = 30
            // Die Schnittstelle liefert Zustand. Eine zwischengespeicherte
            // Antwort wäre hier immer die falsche.
            k.requestCachePolicy = .reloadIgnoringLocalCacheData
            self.sitzung = URLSession(configuration: k)
        }
    }

    func adresseSetzen(_ neu: URL) {
        adresse = neu
    }

    var istGekoppelt: Bool { bund.lesen() != nil }

    func abmelden() {
        bund.loeschen()
    }

    // MARK: Kopplung

    /// Einen Kopplungscode gegen einen Schlüssel tauschen.
    ///
    /// Läuft genau einmal pro Gerät. Der Schlüssel landet sofort in der
    /// Keychain und wird nie zurückgegeben: was ihn braucht, holt ihn dort.
    func koppeln(code: String, name: String, plattform: String) async throws {
        struct Antwort: Decodable { let schluessel: String }
        let antwort: Antwort = try await hole(
            "/api/kopplung/einloesen",
            methode: "POST",
            koerper: ["code": code, "name": name, "plattform": plattform]
        )
        bund.schreiben(antwort.schluessel)
    }

    // MARK: Abrufe

    func briefing() async throws -> Briefing {
        try await hole("/api/briefing")
    }

    func termine(von: Date, bis: Date) async throws -> [Termin] {
        struct Huelle: Decodable { let termine: [Termin] }
        let tag = ISO8601DateFormatter()
        tag.formatOptions = [.withFullDate]
        let huelle: Huelle = try await hole(
            "/api/termine?von=\(tag.string(from: von))&bis=\(tag.string(from: bis))"
        )
        return huelle.termine
    }

    /// Der Tag in Kurzform, für die Uhr.
    func handgelenk() async throws -> Handgelenk {
        try await hole("/api/handgelenk")
    }

    func sammlung() async throws -> Sammlung {
        try await hole("/api/sammlung")
    }

    /// Welche Fassung der Apps auf dem Server bereitsteht.
    ///
    /// Die App vergleicht selbst mit ihrer eigenen Nummer. Der Server weiß
    /// nicht, was auf welchem Gerät läuft, und soll es nicht wissen müssen.
    func neuesteApp() async throws -> AppStand {
        try await hole("/api/app/neueste")
    }

    /// Ein Feld, Enter. Der Server deutet den Text selbst.
    ///
    /// „AU abgeben Freitag" wird ein Eintrag mit Datum, „88,4 kg" ein Gewicht
    /// in wger. Die Deutung bleibt auf dem Server: sie steht dort schon, und
    /// ein zweites Mal in Swift hieße zwei Stellen, die auseinanderlaufen.
    func schnell(_ text: String) async throws -> SchnellAntwort {
        try await hole("/api/schnell", methode: "POST", koerper: ["text": text])
    }

    func seiten() async throws -> [Seite] {
        struct Huelle: Decodable { let seiten: [Seite] }
        let huelle: Huelle = try await hole("/api/seiten")
        return huelle.seiten
    }

    /// Einen Eintrag anlegen und die ID zurückgeben.
    func eintragAnlegen(titel: String) async throws -> Int {
        struct Huelle: Decodable { let eintrag: Kennung }
        struct Kennung: Decodable { let id: Int }
        let h: Huelle = try await hole("/api/sammlung", methode: "POST", koerper: ["titel": titel])
        return h.eintrag.id
    }

    /// Einen gescannten Beleg hochladen und an einen Eintrag hängen.
    ///
    /// `multipart/form-data` von Hand gebaut. Es gibt dafür keine Bibliothek
    /// in der Standardausstattung, und eine dazuzuholen wäre für zwei Felder
    /// unverhältnismäßig.
    ///
    /// `scannen=false`: das Blatt kommt bereits entzerrt und ausgeleuchtet von
    /// der Systemkamera. Es ein zweites Mal durch OpenCV zu schicken würde
    /// Kanten suchen, wo keine mehr sind, und im schlimmsten Fall in ein
    /// bereits beschnittenes Bild hineinschneiden.
    @discardableResult
    func belegHochladen(eintragID: Int, jpeg: Data, name: String) async throws -> String {
        guard let ziel = URL(string: "/api/sammlung/\(eintragID)/beleg", relativeTo: adresse)
        else { throw NetzFehler.unlesbar("Adresse") }

        let grenze = "Grenze-\(UUID().uuidString)"
        var koerper = Data()
        func schreibe(_ text: String) { koerper.append(Data(text.utf8)) }

        schreibe("--\(grenze)\r\n")
        schreibe("Content-Disposition: form-data; name=\"datei\"; filename=\"\(name)\"\r\n")
        schreibe("Content-Type: image/jpeg\r\n\r\n")
        koerper.append(jpeg)
        schreibe("\r\n--\(grenze)\r\n")
        schreibe("Content-Disposition: form-data; name=\"scannen\"\r\n\r\nfalse\r\n")
        schreibe("--\(grenze)--\r\n")

        var anfrage = URLRequest(url: ziel)
        anfrage.httpMethod = "POST"
        anfrage.setValue("multipart/form-data; boundary=\(grenze)",
                         forHTTPHeaderField: "Content-Type")
        if let schluessel = bund.lesen() {
            anfrage.setValue("Bearer \(schluessel)", forHTTPHeaderField: "Authorization")
        }
        anfrage.httpBody = koerper

        let (daten, antwort): (Data, URLResponse)
        do {
            (daten, antwort) = try await sitzung.data(for: anfrage)
        } catch let fehler as URLError {
            throw NetzFehler.nichtErreichbar(fehler.localizedDescription)
        }
        guard let http = antwort as? HTTPURLResponse else {
            throw NetzFehler.unlesbar("keine HTTP-Antwort")
        }
        if http.statusCode == 401 {
            bund.loeschen()
            throw NetzFehler.nichtGekoppelt
        }
        guard (200..<300).contains(http.statusCode) else {
            throw NetzFehler.serverFehler(status: http.statusCode, text: fehlertext(daten))
        }
        return name
    }

    /// Einen Eintrag abhaken oder wieder öffnen.
    @discardableResult
    func eintragAendern(id: Int, felder: [String: Any]) async throws -> Bool {
        struct Ok: Decodable { let ok: Bool? }
        let _: Ok = try await hole("/api/sammlung/\(id)", methode: "PATCH", koerper: felder)
        return true
    }

    // MARK: Der eine Weg nach draußen

    /// Jede Anfrage läuft hier durch.
    ///
    /// Eine einzige Stelle, an der der Schlüssel angehängt wird, an der 401
    /// zu `nichtGekoppelt` wird und an der ein Netzwerkfehler seinen Namen
    /// bekommt. Verteilte man das auf die Aufrufer, fehlte es irgendwo.
    private func hole<T: Decodable>(
        _ pfad: String,
        methode: String = "GET",
        koerper: [String: Any]? = nil
    ) async throws -> T {
        guard let ziel = URL(string: pfad, relativeTo: adresse) else {
            throw NetzFehler.unlesbar("Adresse \(pfad)")
        }
        var anfrage = URLRequest(url: ziel)
        anfrage.httpMethod = methode
        if let schluessel = bund.lesen() {
            anfrage.setValue("Bearer \(schluessel)", forHTTPHeaderField: "Authorization")
        }
        if let koerper {
            anfrage.setValue("application/json", forHTTPHeaderField: "Content-Type")
            anfrage.httpBody = try JSONSerialization.data(withJSONObject: koerper)
        }

        let daten: Data
        let antwort: URLResponse
        do {
            (daten, antwort) = try await sitzung.data(for: anfrage)
        } catch let fehler as URLError {
            throw NetzFehler.nichtErreichbar(fehler.localizedDescription)
        }

        guard let http = antwort as? HTTPURLResponse else {
            throw NetzFehler.unlesbar("keine HTTP-Antwort")
        }
        // 401 heißt hier immer dasselbe: der Schlüssel fehlt oder gilt nicht
        // mehr, weil Mia das Gerät abgemeldet hat. Beides endet in der
        // Kopplung, also wird hier auch gleich aufgeräumt: ein Schlüssel, der
        // nicht mehr gilt, soll nicht als „gekoppelt" durchgehen.
        if http.statusCode == 401 {
            bund.loeschen()
            throw NetzFehler.nichtGekoppelt
        }
        guard (200..<300).contains(http.statusCode) else {
            throw NetzFehler.serverFehler(status: http.statusCode, text: fehlertext(daten))
        }

        do {
            return try JSONDecoder().decode(T.self, from: daten)
        } catch {
            throw NetzFehler.unlesbar(String(describing: error))
        }
    }

    /// Den `detail`-Text aus einer FastAPI-Fehlerantwort ziehen.
    private func fehlertext(_ daten: Data) -> String {
        struct Detail: Decodable { let detail: String? }
        return (try? JSONDecoder().decode(Detail.self, from: daten))?.detail ?? ""
    }
}
