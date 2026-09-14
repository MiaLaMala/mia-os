// Wo Mia OS steht, und wie das Geraet das herausfindet.
//
// Drei Wege, absichtlich in dieser Reihenfolge:
//
// 1. **Bonjour.** Im Heimnetz kuendigt sich Mia OS als `_miaos._tcp` an. Die
//    App fragt nach und zeigt, was sie findet. Ein Tippen genuegt.
// 2. **Von Hand eintippen.** Der einzige Weg, der auch ueber den Tunnel
//    funktioniert: von unterwegs gibt es keinen Multicast, Bonjour findet
//    dort nichts.
// 3. **Ein `miaos://koppeln?adresse=…&code=…`-Link.** Bleibt wie er war.
//
// **Warum es Weg 2 trotz Bonjour braucht:** Mia arbeitet in einem fremden
// Netz und kommt ueber WireGuard nach Hause. mDNS ist auf das lokale Netz
// begrenzt und wird von keinem Tunnel weitergereicht. Eine App, die nur
// Bonjour kennt, waere genau dort blind, wo sie am meisten hilft.

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
    /// ins Programm, und dieses Repo ist öffentlich.
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

    /// Ob überhaupt schon eine Adresse gesetzt wurde.
    ///
    /// Wird gebraucht, um beim ersten Start die Suche zu öffnen statt das
    /// Codefeld: ein Kopplungscode gilt genau einmal und zehn Minuten, und
    /// ihn gegen `localhost` zu verbrauchen ist die ärgerlichste Art, ihn
    /// zu verlieren. Genau das ist Mia am 14.09.2026 passiert.
    static var adresseGesetzt: Bool {
        UserDefaults.standard.string(forKey: adresseSchluessel) != nil
    }

    /// Aus einer Eingabe eine brauchbare Adresse machen.
    ///
    /// Was Mia tippt, ist selten eine vollständige URL. `mia.mia-gruenwald.dev`
    /// soll `https://mia.mia-gruenwald.dev` werden, `172.16.30.230` dagegen
    /// `http://172.16.30.230:8080`: eine IP im Heimnetz hat kein Zertifikat,
    /// ein Name schon.
    ///
    /// Gibt `nil` zurück, wenn daraus nichts wird. Lieber ein abgeblendeter
    /// Knopf als eine Anfrage an eine Adresse, die niemand gemeint hat.
    static func adresseAus(_ eingabe: String) -> URL? {
        let roh = eingabe.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !roh.isEmpty else { return nil }

        let mitSchema: String
        if roh.hasPrefix("http://") || roh.hasPrefix("https://") {
            mitSchema = roh
        } else if istIPAdresse(ersterTeil(roh)) {
            // Eine nackte IP: im Heimnetz, also Klartext und der bekannte
            // Port. Mit https käme eine Zertifikatswarnung für eine Adresse,
            // für die es kein Zertifikat geben kann.
            mitSchema = roh.contains(":") ? "http://\(roh)" : "http://\(roh):8080"
        } else {
            mitSchema = "https://\(roh)"
        }

        guard var teile = URLComponents(string: mitSchema),
              let host = teile.host, !host.isEmpty
        else { return nil }

        // Einen angehängten Pfad wegwerfen: die App hängt ihre eigenen Pfade
        // an, und `https://mia.../app` würde zu `/app/api/briefing`.
        teile.path = ""
        teile.query = nil
        teile.fragment = nil
        return teile.url
    }

    private static func ersterTeil(_ text: String) -> String {
        text.split(separator: ":").first.map(String.init) ?? text
    }

    private static func istIPAdresse(_ text: String) -> Bool {
        let teile = text.split(separator: ".")
        guard teile.count == 4 else { return false }
        return teile.allSatisfy { teil in
            guard let zahl = Int(teil) else { return false }
            return zahl >= 0 && zahl <= 255
        }
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
