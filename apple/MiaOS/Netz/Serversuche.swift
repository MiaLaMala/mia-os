// Mia OS im Netz suchen (Bonjour).
//
// Das Gegenstück zu `backend/src/bonjour.py`: dort kündigt sich der Server
// als `_miaos._tcp` an, hier wird danach gefragt.
//
// **Warum `NWBrowser` und nicht `NetServiceBrowser`:** letzterer ist seit
// iOS 15 abgekündigt und braucht einen RunLoop. `NWBrowser` aus Network.framework
// ist der vorgesehene Weg und liefert die Auflösung gleich mit.
//
// **Warum die Suche von selbst aufhört:** ein Browser, der dauerhaft läuft,
// hält das WLAN wach und kostet Akku. Zehn Sekunden reichen: was in dieser
// Zeit nicht antwortet, ist nicht da.
//
// **Was das NICHT kann:** über den Tunnel finden. mDNS ist auf das lokale
// Netz begrenzt, WireGuard reicht keinen Multicast weiter. Von unterwegs
// bleibt das Eintippen der Adresse der einzige Weg, und deshalb steht das
// Feld gleichberechtigt daneben und nicht in einem Untermenü.

import Foundation
import Network
import Observation

/// Ein gefundener Server.
struct GefundenerServer: Identifiable, Hashable {
    let id: String
    let name: String
    let adresse: URL

    /// Was unter dem Namen steht: die Adresse ohne Schema, kurz genug für
    /// eine Zeile auf dem iPhone.
    var beschreibung: String {
        let host = adresse.host() ?? ""
        guard let port = adresse.port else { return host }
        return "\(host):\(port)"
    }
}

@MainActor
@Observable
final class Serversuche {
    private(set) var gefunden: [GefundenerServer] = []
    private(set) var laeuft = false

    /// `true`, sobald einmal gesucht wurde und nichts kam. Trennt „noch nicht
    /// gesucht" von „gesucht, nichts da": nur im zweiten Fall darf die
    /// Oberfläche „Nichts gefunden" sagen.
    private(set) var fertigOhneTreffer = false

    private var browser: NWBrowser?
    private var abbruch: Task<Void, Never>?

    /// Wie lange gesucht wird. Zehn Sekunden sind im WLAN großzügig: eine
    /// Antwort kommt normal in unter einer.
    private let dauer: Duration = .seconds(10)

    func starten() {
        guard !laeuft else { return }
        gefunden = []
        fertigOhneTreffer = false
        laeuft = true

        let parameter = NWParameters()
        // Nur im lokalen Netz suchen. Ohne das versucht das System auch
        // Wide-Area-Bonjour über den konfigurierten DNS, und das ist hier
        // sinnlose Last.
        parameter.includePeerToPeer = false

        let browser = NWBrowser(
            for: .bonjour(type: "_miaos._tcp", domain: nil),
            using: parameter
        )
        self.browser = browser

        // In allen drei Blöcken `guard let selbst` statt `self?`: Swift 6
        // verlangt bei optionalem `self` in einem asynchronen Kontext
        // ausdrückliches Auspacken („explicit use of 'self' is required when
        // 'self' is optional"). Ein `self?.` sieht kürzer aus und übersetzt
        // hier schlicht nicht.
        browser.browseResultsChangedHandler = { [weak self] treffer, _ in
            Task { @MainActor in
                guard let selbst = self else { return }
                selbst.verarbeiten(treffer)
            }
        }

        browser.stateUpdateHandler = { [weak self] zustand in
            // `.failed` heißt meist: die Erlaubnis für das lokale Netz fehlt.
            // Dann still aufhören, die Oberfläche zeigt das Eingabefeld.
            if case .failed = zustand {
                Task { @MainActor in
                    guard let selbst = self else { return }
                    selbst.stoppen()
                }
            }
        }

        browser.start(queue: .main)

        // `dauer` VOR dem Task lesen, nicht darin.
        //
        // Sonst greift `Task.sleep(for: dauer)` implizit auf `self` zu,
        // während das noch optional ist, und Swift 6 verlangt genau dort
        // ausdrückliches Auspacken. Die Fehlermeldung zeigt dabei auf die
        // `guard`-Zeile darunter, was in die Irre führt: der eigentliche
        // Zugriff steht eine Zeile höher.
        let wartezeit = dauer
        abbruch = Task { [weak self] in
            try? await Task.sleep(for: wartezeit)
            guard let selbst = self else { return }
            await MainActor.run { selbst.stoppen() }
        }
    }

    func stoppen() {
        abbruch?.cancel()
        abbruch = nil
        browser?.cancel()
        browser = nil
        if laeuft {
            laeuft = false
            fertigOhneTreffer = gefunden.isEmpty
        }
    }

    private func verarbeiten(_ treffer: Set<NWBrowser.Result>) {
        var neu: [GefundenerServer] = []
        for eintrag in treffer {
            guard case .service(let name, let typ, let bereich, _) = eintrag.endpoint else {
                continue
            }
            // Der Name aus Bonjour ist schon lesbar („Mia OS"). Die Adresse
            // wird aus dem Hostnamen gebaut statt aus der aufgelösten IP:
            // `mia-os.local` funktioniert auch, wenn der DHCP eine neue
            // Adresse vergibt.
            let kennung = "\(name).\(typ)\(bereich)"
            guard let url = adresseFuer(eintrag, name: name) else { continue }
            neu.append(GefundenerServer(id: kennung, name: name, adresse: url))
        }
        // Nach Namen sortieren, damit die Liste nicht bei jedem Fund springt.
        gefunden = neu.sorted { $0.name < $1.name }
        if !gefunden.isEmpty { fertigOhneTreffer = false }
    }

    private func adresseFuer(_ treffer: NWBrowser.Result, name: String) -> URL? {
        // Port und Rechnername stehen im TXT- und SRV-Satz. `NWBrowser`
        // liefert die Metadaten, die Auflösung macht `URLSession` später
        // selbst über `.local`.
        var port = 8080
        if case .bonjour(let txt) = treffer.metadata,
           let wert = txt.dictionary["port"], let zahl = Int(wert) {
            port = zahl
        }
        let rechner = name.replacingOccurrences(of: " ", with: "-").lowercased()
        return URL(string: "http://\(rechner).local:\(port)")
    }
}
