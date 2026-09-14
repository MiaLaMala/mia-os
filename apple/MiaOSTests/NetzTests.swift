// Die Netzschicht.
//
// Gegen einen eingesetzten `URLProtocol` statt gegen den echten Server: die
// Tests sollen auch laufen, wenn Mia OS gerade aus ist oder der Tunnel steht.
// Geprüft wird, was die App tut, nicht was der Server antwortet.

import Foundation
import Testing

@testable import MiaOSKern

// MARK: - Ein Server, den es nicht gibt

/// Fängt jede Anfrage ab und antwortet mit dem, was gerade hinterlegt ist.
///
/// Die hinterlegte Antwort ist statisch, weil `URLProtocol` von `URLSession`
/// selbst erzeugt wird und sich nichts mitgeben lässt. Deshalb läuft die
/// Draht-Suite unten `.serialized`: Swift Testing führt Tests sonst
/// nebenläufig aus, und drei Tests, die sich reihum dieselbe Antwort
/// überschreiben, schlagen zufällig fehl. Genau das ist beim ersten Lauf
/// passiert.
final class FalscherServer: URLProtocol, @unchecked Sendable {
    /// Was die nächste Anfrage bekommt: Status und Rumpf.
    nonisolated(unsafe) static var antwort: (Int, Data) = (200, Data())
    /// Die letzte gesehene Anfrage, für Prüfungen an den Kopfzeilen.
    nonisolated(unsafe) static var letzte: URLRequest?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.letzte = request
        let (status, rumpf) = Self.antwort
        let antwort = HTTPURLResponse(
            url: request.url!,
            statusCode: status,
            httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: antwort, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: rumpf)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}

    static func sitzung() -> URLSession {
        let k = URLSessionConfiguration.ephemeral
        k.protocolClasses = [FalscherServer.self]
        return URLSession(configuration: k)
    }

    static func antworte(_ status: Int, _ json: String) {
        antwort = (status, Data(json.utf8))
    }
}

private func neuerDraht() -> Draht {
    Draht(adresse: URL(string: "http://test.local")!, sitzung: FalscherServer.sitzung())
}

// MARK: - Was die App mit Antworten macht

@Suite("Draht", .serialized)
struct DrahtTests {

    @Test("Ein Briefing wird gelesen, auch wenn Listen leer sind")
    func briefingLesen() async throws {
        FalscherServer.antworte(200, """
        {"datum":"2026-09-13","heute":[{"titel":"Zahnarzt","zeit":"09:00",
        "ende":"09:30","ort":"Buxtehude","kalender":"Privat"}],
        "morgen":[],"faellig":[],"offen":3,"hinweise":[],
        "geraet":{"theme":"gesicht"},"text":"Heute: Zahnarzt"}
        """)
        let b = try await neuerDraht().briefing()
        #expect(b.offen == 3)
        #expect(b.heute.count == 1)
        #expect(b.heute[0].zeitraum == "09:00 bis 09:30")
        // `geraet` steht in der Antwort, aber nicht im Typ. Ein unbekanntes
        // Feld darf das Lesen NICHT scheitern lassen: sonst bricht die App,
        // sobald der Server etwas dazulernt.
    }

    @Test("401 heisst nicht gekoppelt, nicht irgendein Serverfehler")
    func einundvierzig() async throws {
        FalscherServer.antworte(401, #"{"detail":"Nicht gekoppelt"}"#)
        await #expect(throws: NetzFehler.nichtGekoppelt) {
            _ = try await neuerDraht().briefing()
        }
    }

    @Test("Der Fehlertext des Servers kommt bei Mia an")
    func fehlertext() async throws {
        FalscherServer.antworte(400, #"{"detail":"bis liegt vor von"}"#)
        do {
            _ = try await neuerDraht().briefing()
            Issue.record("Hätte werfen müssen")
        } catch let fehler as NetzFehler {
            // Nicht „Fehler 400": der Server weiss, was schiefging, und die
            // Meldung ist bereits auf Deutsch und für Menschen geschrieben.
            #expect(fehler.errorDescription == "bis liegt vor von")
        }
    }

    @Test("Kaputtes JSON wird als unlesbar gemeldet, nicht als Absturz")
    func kaputtesJSON() async throws {
        FalscherServer.antworte(200, "{das ist kein json")
        do {
            _ = try await neuerDraht().briefing()
            Issue.record("Hätte werfen müssen")
        } catch let fehler as NetzFehler {
            guard case .unlesbar = fehler else {
                Issue.record("Falsche Fehlerart: \(fehler)")
                return
            }
        }
    }

    @Test("Ohne Schluessel geht kein Authorization-Kopf raus")
    func ohneSchluessel() async throws {
        Schluesselbund().loeschen()
        FalscherServer.antworte(200, #"{"datum":"","heute":[],"morgen":[],"faellig":[],"offen":0,"hinweise":[],"text":""}"#)
        _ = try await neuerDraht().briefing()
        #expect(FalscherServer.letzte?.value(forHTTPHeaderField: "Authorization") == nil)
    }

    // MARK: Dokumente

    // Diese beiden gehoeren inhaltlich zur Suite "Dokumente" weiter unten,
    // stehen aber HIER, weil sie den `FalscherServer` benutzen. `.serialized`
    // gilt nur innerhalb einer Suite: zwei Suiten laufen nebenlaeufig und
    // ueberschreiben sich reihum die hinterlegte Antwort. Beim ersten Lauf
    // bekam `briefing()` prompt die Dokumentenliste.

    @Test("Ohne Suchbegriff geht nur_ordner mit raus")
    func nurOrdner() async throws {
        FalscherServer.antworte(200, #"""
        {"treffer":[],"gesamt":187,"seite":1,"seiten":1,
         "ordner":[{"top":"/Dokumente/02 Medizinisch","n":14}]}
        """#)
        let a = try await neuerDraht().dokumente()

        let url = FalscherServer.letzte?.url?.absoluteString ?? ""
        // Der Schalter ist der ganze Schutz. Ohne ihn listet der Server die
        // zuletzt geaenderten Dateien MIT Namen auf, und dann liegen sie im
        // URLCache des Telefons, egal was die Ansicht danach anzeigt.
        #expect(url.contains("nur_ordner=1"))
        #expect(a.treffer.isEmpty)
        #expect(a.gesamt == 187)
        #expect(a.ordner.first?.name == "02 Medizinisch")
    }

    @Test("Auch mit Ordnerfilter bleibt der Schalter gesetzt")
    func ordnerfilter() async throws {
        FalscherServer.antworte(200, #"""
        {"treffer":[],"gesamt":14,"seite":1,"seiten":1,"ordner":[]}
        """#)
        _ = try await neuerDraht().dokumente(ordner: "/Dokumente/02 Medizinisch")

        let url = FalscherServer.letzte?.url?.absoluteString ?? ""
        // Mias Entscheidung vom 14.09.2026: ein angetippter Ordner ist der
        // Einstieg, nicht die Freigabe. Ein Fingertipp haelt niemanden ab,
        // der ueber die Schulter schaut.
        #expect(url.contains("nur_ordner=1"))
    }
}

// MARK: - Termine

@Suite("Termin")
struct TerminTests {

    @Test("Ein Sammlungseintrag im Kalender wird als solcher erkannt")
    func eintragErkennen() {
        let t = Termin(
            id: "eintrag-42", title: "Steuer", start: "2026-09-13", end: nil,
            allDay: true, kalender: "Sammlung", ort: "", farbe: "#5b8def",
            hat_notiz: false, offene_aufgaben: 0
        )
        #expect(t.istEintrag)
        #expect(t.eintragsID == 42)
    }

    @Test("Ein echter Termin ist kein Eintrag")
    func echterTermin() {
        let t = Termin(
            id: "abc-123-uid", title: "Zahnarzt", start: "2026-09-13T09:00:00",
            end: "2026-09-13T09:30:00", allDay: false, kalender: "Privat",
            ort: "", farbe: "#3fa66a", hat_notiz: false, offene_aufgaben: 0
        )
        #expect(!t.istEintrag)
        #expect(t.eintragsID == nil)
    }

    @Test("Beide Datumsformen werden gelesen")
    func datumsformen() {
        // Der Server liefert ganztägige Termine ohne Zeit und normale mit.
        // Ein Formatierer mit festen Optionen scheitert an der jeweils
        // anderen Form — genau das prüft dieser Test.
        #expect(Termin.datum(aus: "2026-09-13") != nil)
        #expect(Termin.datum(aus: "2026-09-13T09:00:00") != nil)
        #expect(Termin.datum(aus: "2026-09-13T09:00:00+02:00") != nil)
        #expect(Termin.datum(aus: "völliger Unsinn") == nil)
    }
}

// MARK: - Aktualisierung

@Suite("AppStand")
struct AppStandTests {

    private func stand(_ version: String) -> AppStand {
        AppStand(version: version, gebaut_am: "", mac: nil, ios: nil)
    }

    @Test("Zweistellige Zahlen werden richtig verglichen")
    func zweistellig() {
        // Der Grund für den ganzen Typ: als Text ist "0.1.9" größer als
        // "0.1.10". Ohne Zahlenvergleich würde ab dem zehnten Commit nie
        // wieder ein Update angeboten.
        #expect(stand("0.1.10").istNeuerAls("0.1.9"))
        #expect(!stand("0.1.9").istNeuerAls("0.1.10"))
        #expect(stand("0.1.100").istNeuerAls("0.1.99"))
    }

    @Test("Gleiche Fassung ist kein Update")
    func gleich() {
        #expect(!stand("0.1.42").istNeuerAls("0.1.42"))
    }

    @Test("Eine neue Nebenversion schlaegt jede Patchzahl")
    func nebenversion() {
        #expect(stand("0.2.0").istNeuerAls("0.1.999"))
        #expect(stand("1.0.0").istNeuerAls("0.9.9"))
    }

    @Test("Unterschiedlich viele Stellen gehen gut")
    func stellen() {
        #expect(stand("0.2").istNeuerAls("0.1.5"))
        #expect(!stand("0.1").istNeuerAls("0.1.0"))
    }

    @Test("Unsinn stuerzt nicht ab und meldet kein Update")
    func unsinn() {
        // Eine leere oder kaputte Nummer kommt vom Server, wenn der Zweig
        // noch nicht existiert. Dann ist die Antwort: kein Update.
        #expect(!stand("").istNeuerAls("0.1.0"))
        #expect(!stand("kaputt").istNeuerAls("0.1.0"))
    }

    @Test("Die Groesse wird lesbar angezeigt")
    func groesse() {
        let d = AppDatei(datei: "MiaOS-Mac.zip", groesse: 12_400_000, sha256: "")
        #expect(d.lesbareGroesse.contains("MB"))
    }
}

// MARK: - Sammlung

@Suite("Sammlung")
struct SammlungTests {

    @Test("Die Farbe zu einem Statuswert wird gefunden")
    func farbeFinden() {
        let s = Sammlung(
            eintraege: [],
            eigenschaften: [
                Eigenschaft(
                    key: "status", name: "Status", art: "auswahl",
                    optionen: [
                        Option(wert: "offen", farbe: "grau"),
                        Option(wert: "fertig", farbe: "gruen"),
                    ],
                    sortierung: 1
                )
            ]
        )
        #expect(s.farbe(fuer: "fertig", eigenschaft: "status") == "gruen")
        #expect(s.farbe(fuer: "gibtsnicht", eigenschaft: "status") == nil)
        #expect(s.farbe(fuer: "fertig", eigenschaft: "bereich") == nil)
    }

    @Test("Ein Eintrag ohne Status ist nicht fertig")
    func ohneStatus() {
        let e = Eintrag(
            id: 1, titel: "X", inhalt: "", eigenschaften: [:], datum: "", zeit: "",
            page_id: 0, sortierung: 1, archiviert: false
        )
        #expect(!e.istFertig)
        #expect(e.status == "")
    }
}

// MARK: - Dokumente bleiben, wo sie hingehoeren

/// Die Festlegung aus `docs/apple-zuschnitt.md`, als Test statt als Kommentar.
///
/// Drei Saetze, die dort stehen: leeres Suchfeld zeigt keine Dateinamen,
/// Dokumente tauchen nie im Widget auf, Dokumente tauchen nie in einer
/// Siri-Antwort auf. Ein Kommentar haelt das nicht. Ein Test schlaegt fehl,
/// sobald jemand in einem halben Jahr ein Dokumentenfeld einbaut, weil es
/// gerade praktisch waere.
///
/// **Hier stehen nur Tests ohne Server.** Die beiden, die den `FalscherServer`
/// brauchen, sitzen in der Suite `Draht`: `.serialized` gilt nur INNERHALB
/// einer Suite. Zwei Suiten laufen nebenlaeufig, ueberschreiben sich reihum
/// die hinterlegte Antwort, und dann bekommt `briefing()` die Dokumentenliste.
/// Genau das ist beim ersten Lauf passiert.
@Suite("Dokumente")
struct DokumenteTests {

    @Test("Das Widget kennt keine Dokumente")
    func widgetOhneDokumente() throws {
        // `Handgelenk` ist der EINZIGE Typ, den das Widget und die Uhr lesen
        // (siehe `Ablage` und `MiaOSWidget`). Was hier nicht drin steht, kann
        // dort nicht landen. Geprueft wird ueber die kodierten Schluessel und
        // nicht ueber eine Aufzaehlung im Kopf: eine neue Eigenschaft faellt
        // so von selbst auf.
        //
        // Mit gesetztem `naechster`, nicht mit `.leer`: ein `nil` laesst der
        // Encoder weg, und der Schluessel fehlte dann aus dem falschen Grund.
        let voll = Handgelenk(
            naechster: Kurztermin(titel: "Zahnarzt", zeit: "09:00", ort: "Buxtehude"),
            spaeter_heute: 2, faellig: 1, offen: 3, stand: "2026-09-14T11:00:00Z"
        )
        let roh = try JSONEncoder().encode(voll)
        let felder = try JSONSerialization.jsonObject(with: roh) as? [String: Any] ?? [:]

        #expect(felder["dokumente"] == nil)
        #expect(felder["dokument"] == nil)
        #expect(felder["dateien"] == nil)
        #expect(
            Set(felder.keys) == ["naechster", "spaeter_heute", "faellig", "offen", "stand"],
            "Neues Feld in Handgelenk: gehoert es wirklich aufs Widget und auf die Uhr?"
        )
    }

    @Test("Ein Kurztermin traegt keinen Dateibezug")
    func kurzterminOhneDatei() throws {
        let roh = try JSONEncoder().encode(
            Kurztermin(titel: "Zahnarzt", zeit: "09:00", ort: "Buxtehude")
        )
        let felder = try JSONSerialization.jsonObject(with: roh) as? [String: Any] ?? [:]
        #expect(Set(felder.keys) == ["titel", "zeit", "ort"])
    }
}

