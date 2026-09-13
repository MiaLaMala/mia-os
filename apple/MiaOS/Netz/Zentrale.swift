// Der Zustand, den die Oberfläche sieht.
//
// Ein `@Observable` auf dem Hauptthread, der den `Draht` benutzt. Die
// Ansichten lesen hier und rufen hier an; keine Ansicht redet selbst mit dem
// Netz.
//
// **Warum der Ladezustand pro Bereich und nicht global:** ein einzelnes
// `istAmLaden` ließe die ganze App drehen, wenn nur die Termine nachladen.
// Auf dem iPhone in der S-Bahn ist das der Normalfall.

import Foundation
import Observation

@MainActor
@Observable
final class Zentrale {
    // MARK: Daten

    private(set) var briefing: Briefing = .leer
    private(set) var sammlung: Sammlung = .leer
    private(set) var termine: [Termin] = []
    private(set) var seiten: [Seite] = []

    // MARK: Zustand

    enum Lage: Equatable {
        case unbekannt
        case nichtGekoppelt
        case bereit
        /// Der Server war nicht erreichbar. Die Daten von vorhin bleiben
        /// stehen: eine leere Ansicht mit „kein Netz" ist schlechter als die
        /// Termine von vor zehn Minuten mit einem Hinweis darüber.
        case getrennt(String)
    }

    private(set) var lage: Lage = .unbekannt
    /// Eine neuere Fassung, wenn es eine gibt. Sonst `nil`.
    private(set) var update: AppStand?
    private(set) var laedtBriefing = false
    private(set) var laedtSammlung = false
    private(set) var laedtTermine = false
    /// Wann die Daten zuletzt wirklich vom Server kamen.
    private(set) var stand: Date?

    private let draht: Draht

    init(draht: Draht = Draht(adresse: Einstellungen.adresse)) {
        self.draht = draht
    }

    // MARK: Kopplung

    func lagePruefen() async {
        lage = await draht.istGekoppelt ? .bereit : .nichtGekoppelt
    }

    /// Koppeln. Wirft weiter, damit die Ansicht den Grund anzeigen kann.
    func koppeln(code: String) async throws {
        try await draht.koppeln(
            code: code.trimmingCharacters(in: .whitespaces),
            name: Einstellungen.geraetename,
            plattform: Einstellungen.plattform
        )
        lage = .bereit
        await alleslLaden()
    }

    func abmelden() async {
        await draht.abmelden()
        briefing = .leer
        sammlung = .leer
        termine = []
        seiten = []
        stand = nil
        lage = .nichtGekoppelt
    }

    // MARK: Laden

    func alleslLaden() async {
        // Nebenläufig: drei Abrufe, die nichts voneinander wissen. Nacheinander
        // wären es drei Umläufe zum Server statt einem.
        async let a: Void = briefingLaden()
        async let b: Void = sammlungLaden()
        async let c: Void = seitenLaden()
        _ = await (a, b, c)
        await nachUpdateSehen()
    }

    func briefingLaden() async {
        laedtBriefing = true
        defer { laedtBriefing = false }
        do {
            briefing = try await draht.briefing()
            erfolg()
        } catch {
            fehler(error)
        }
    }

    func sammlungLaden() async {
        laedtSammlung = true
        defer { laedtSammlung = false }
        do {
            sammlung = try await draht.sammlung()
            erfolg()
        } catch {
            fehler(error)
        }
    }

    /// Nachsehen, ob der Server eine neuere Fassung hat.
    ///
    /// Still: findet sich nichts oder ist der Server weg, passiert nichts.
    /// Ein Fehler beim Suchen nach Updates ist kein Fehler, den Mia sehen
    /// muss, und `lage` wird hier bewusst nicht angefasst.
    func nachUpdateSehen() async {
        guard let laufend = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
        else { return }
        guard let stand = try? await draht.neuesteApp() else { return }
        update = stand.istNeuerAls(laufend) ? stand : nil
    }

    func seitenLaden() async {
        do {
            seiten = try await draht.seiten()
            erfolg()
        } catch {
            fehler(error)
        }
    }

    func termineLaden(von: Date, bis: Date) async {
        laedtTermine = true
        defer { laedtTermine = false }
        do {
            termine = try await draht.termine(von: von, bis: bis)
            erfolg()
        } catch {
            fehler(error)
        }
    }

    // MARK: Ändern

    /// Einen Eintrag abhaken oder wieder öffnen.
    ///
    /// Ändert die Anzeige SOFORT und schickt erst danach. Ein Haken, der eine
    /// halbe Sekunde wartet, fühlt sich kaputt an. Geht das Schicken schief,
    /// springt er zurück und die Ansicht zeigt den Grund.
    func abhaken(_ eintrag: Eintrag) async {
        let neuerStatus = eintrag.istFertig ? "offen" : "fertig"
        let vorher = sammlung

        if let i = sammlung.eintraege.firstIndex(where: { $0.id == eintrag.id }) {
            var felder = sammlung.eintraege[i].eigenschaften
            felder["status"] = neuerStatus
            var neu = sammlung.eintraege
            neu[i] = Eintrag(
                id: eintrag.id,
                titel: eintrag.titel,
                inhalt: eintrag.inhalt,
                eigenschaften: felder,
                datum: eintrag.datum,
                zeit: eintrag.zeit,
                page_id: eintrag.page_id,
                sortierung: eintrag.sortierung,
                archiviert: eintrag.archiviert
            )
            sammlung = Sammlung(eintraege: neu, eigenschaften: sammlung.eigenschaften)
        }

        do {
            try await draht.eintragAendern(
                id: eintrag.id,
                felder: ["eigenschaften": ["status": neuerStatus]]
            )
            erfolg()
            // Das Briefing zählt die offenen mit: ohne das bleibt die Zahl
            // oben stehen, obwohl der Haken schon sitzt.
            await briefingLaden()
        } catch {
            sammlung = vorher
            fehler(error)
        }
    }

    /// Gescannte Seiten hochladen.
    ///
    /// Jede Seite bekommt einen eigenen Eintrag. Ein Beleg hängt in Mia OS
    /// immer an einem Vorgang, und beim Scannen unterwegs gibt es den noch
    /// nicht: „Beleg vom 13.09." ist ein ehrlicher Platzhalter, den Mia
    /// umbenennen kann. Mia OS schlägt nach dem Lesen ohnehin einen Namen aus
    /// dem Blatt selbst vor.
    func belegeHochladen(_ seiten: [Data]) async throws -> [String] {
        let f = DateFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = "dd.MM.yyyy"
        let heute = f.string(from: Date())

        var namen: [String] = []
        for (nr, jpeg) in seiten.enumerated() {
            let titel = seiten.count == 1
                ? "Beleg vom \(heute)"
                : "Beleg vom \(heute), Seite \(nr + 1)"
            let id = try await draht.eintragAnlegen(titel: titel)
            try await draht.belegHochladen(
                eintragID: id, jpeg: jpeg, name: "\(titel).jpg"
            )
            namen.append(titel)
        }
        await sammlungLaden()
        return namen
    }

    /// Einen hingeworfenen Satz eintragen. Gibt die Meldung des Servers zurück.
    func schnellEintragen(_ text: String) async throws -> String {
        let antwort = try await draht.schnell(text)
        erfolg()
        // Das Briefing zählt die offenen mit, und die Menüleiste liest es.
        await briefingLaden()
        await sammlungLaden()
        return antwort.meldung
    }

    // MARK: Innen

    private func erfolg() {
        stand = Date()
        // Das Widget liest nur, es fragt nie selbst: eine Widget-Erweiterung
        // hat Sekunden und darf nicht auf ein Netz warten, das im Zug weg ist.
        // Also schreibt die App bei jedem erfolgreichen Laden mit.
        Ablage.sichern(
            Handgelenk(
                naechster: briefing.heute.first.map {
                    Kurztermin(titel: $0.titel, zeit: $0.zeit, ort: $0.ort)
                },
                spaeter_heute: max(0, briefing.heute.count - 1),
                faellig: briefing.faellig.count,
                offen: briefing.offen,
                stand: ISO8601DateFormatter().string(from: Date())
            )
        )
        if case .getrennt = lage { lage = .bereit }
        if case .unbekannt = lage { lage = .bereit }
    }

    private func fehler(_ error: Error) {
        if case NetzFehler.nichtGekoppelt = error {
            lage = .nichtGekoppelt
            return
        }
        lage = .getrennt(error.localizedDescription)
    }
}
