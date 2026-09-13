// Was das Gerät sich merkt, und wo Mia OS steht.
//
// Bewusst getrennt vom Schlüssel: der liegt in der Keychain, hier liegen
// Vorlieben. Eine Adresse ist kein Geheimnis, ein Schlüssel schon.

import Foundation

#if os(iOS)
import UIKit
#else
import AppKit
#endif

enum Einstellungen {
    /// Wo Mia OS steht.
    ///
    /// Bewusst keine echte Adresse im Quelltext: die gehört zur Person, nicht
    /// ins Programm, und dieses Repo ist öffentlich. Beim Koppeln trägt Mia
    /// sie ein, der URL-Aufruf `miaos://koppeln?adresse=…&code=…` bringt sie
    /// gleich mit.
    ///
    /// `localhost` als Platzhalter statt `nil`: so bleibt der Typ `URL` und
    /// jeder Aufrufer funktioniert unverändert. Wer die App ohne Kopplung
    /// startet, bekommt eine ehrliche Fehlermeldung statt einer Verbindung
    /// zu einer fremden Adresse.
    static let standardAdresse = URL(string: "http://localhost:8080")!

    private static let adresseSchluessel = "mia-os.adresse"

    static var adresse: URL {
        get {
            guard let text = UserDefaults.standard.string(forKey: adresseSchluessel),
                  let url = URL(string: text)
            else { return standardAdresse }
            return url
        }
        set { UserDefaults.standard.set(newValue.absoluteString, forKey: adresseSchluessel) }
    }

    /// Wie dieses Gerät in Mias Geräteliste heißen soll.
    ///
    /// Der Gerätename statt eines Tippfelds: „Mias iPhone" steht ohnehin in
    /// den Systemeinstellungen, und ein leeres Feld beim Koppeln wäre eine
    /// Hürde ohne Gewinn. Auf dem Mac liefert `ProcessInfo` den Namen, auf
    /// dem iPhone `UIDevice` — seit iOS 16 allerdings nur noch das Modell
    /// („iPhone"), der echte Name ist dort gesperrt.
    static var geraetename: String {
        #if os(iOS)
        return UIDevice.current.name
        #else
        return Host.current().localizedName ?? ProcessInfo.processInfo.hostName
        #endif
    }

    static var plattform: String {
        #if os(iOS)
        return UIDevice.current.userInterfaceIdiom == .pad ? "ipados" : "ios"
        #else
        return "macos"
        #endif
    }
}
