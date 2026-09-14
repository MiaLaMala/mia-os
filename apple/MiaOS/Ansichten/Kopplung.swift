// Der erste Bildschirm: dieses Gerät mit Mia OS verbinden.
//
// **Der Code ist der Fokus, alles andere tritt zurück.** Bis zum 14.09.2026
// stand hier nur das Codefeld und die Adresse kam ausschließlich über einen
// `miaos://`-Link. Ohne Link stand dort `localhost`, der Code ging ans eigene
// Gerät und war verbraucht. Mein erster Versuch, das zu beheben, legte dann
// Suchliste, Adressfeld, Prüfen-Knopf und zwei Hilfetexte gleichzeitig auf
// den Bildschirm. Mias Urteil: *„viel zu viel auf einmal da"*, und sie hat
// recht. DESIGN.md sagt es selbst: „Ruhe zuerst, Tiefe auf Abruf" und „je
// kleiner der Schirm, desto weniger steht drauf."
//
// Also drei Ebenen:
//
// 1. **Code und Verbinden.** Mehr braucht es im Normalfall nicht.
// 2. **Gefundene Server** als Liste, wenn Bonjour welche findet. Ein Tippen
//    setzt die Adresse, prüft sie und springt ins Codefeld.
// 3. **Eine ruhige Zeile unten**, die zeigt, welcher Server gewählt ist.
//    Ausklappbar, darin Adresse, Port und Prüfen.
//
// Das Ausklappen ist der Weg für unterwegs: über WireGuard reicht kein
// Multicast, Bonjour findet dort nichts, und die Adresse muss getippt werden.

import SwiftUI

struct Kopplung: View {
    @Environment(Zentrale.self) private var zentrale
    @State private var suche = Serversuche()

    @State private var code = ""
    @State private var adresstext = ""
    @State private var porttext = ""

    @State private var offen = false
    @State private var laeuft = false
    @State private var pruefeAdresse = false
    @State private var fehler = ""
    /// Was die Prüfung ergeben hat. Leer heißt: noch nicht geprüft.
    @State private var bestaetigt = ""
    /// Ob Mia den Port selbst gesetzt hat. Dann wird er beim Tippen in der
    /// Adresse nicht mehr überschrieben.
    @State private var portVonHand = false

    @FocusState private var imCodefeld: Bool

    private var codeGueltig: Bool {
        code.count == 6 && code.allSatisfy(\.isNumber)
    }

    private var port: Int? { Int(porttext) }

    private var adresse: URL? {
        Einstellungen.adresseAus(adresstext, port: port)
    }

    /// Was in der Zeile unten steht.
    ///
    /// Nach dem Prüfen der Name mit Version, sonst die Adresse, und ohne
    /// alles ein ehrliches „Kein Server". Ein `localhost` an dieser Stelle
    /// wäre die Lüge, die den ganzen Ärger ausgelöst hat.
    private var serverzeile: String {
        if !bestaetigt.isEmpty { return bestaetigt }
        if let adresse { return adresse.host() ?? adresstext }
        return "Kein Server"
    }

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(spacing: Mass.abstandGross) {
                    Spacer(minLength: Mass.abstandGross)
                    kopf
                    codefeld
                    verbindenKnopf

                    if !fehler.isEmpty {
                        Text(fehler)
                            .font(.callout)
                            .foregroundStyle(.red)
                            .multilineTextAlignment(.center)
                    }

                    gefundene
                    Spacer(minLength: Mass.abstand)
                }
                .padding(.horizontal, Mass.abstandGross)
                .frame(maxWidth: 420)
                .frame(maxWidth: .infinity)
            }

            serverleiste
        }
        .onAppear(perform: starten)
        .onDisappear { suche.stoppen() }
    }

    // MARK: Oben

    private var kopf: some View {
        VStack(spacing: 6) {
            Image(systemName: "square.stack.3d.up")
                // Waechst mit Dynamic Type mit. Eine feste Punktzahl bliebe
                // stehen, waehrend der Text darunter groesser wird.
                .font(.system(.largeTitle, weight: .light))
                .foregroundStyle(.tint)
                .padding(.bottom, 6)
            Text("Mia OS")
                .font(.largeTitle.weight(.semibold))
            Text("Code aus Mia OS, Einstellungen")
                .font(.callout)
                .foregroundStyle(.secondary)
        }
    }

    private var codefeld: some View {
        TextField("000000", text: $code)
            // Der Code ist das Wichtigste auf diesem Bildschirm und muss beim
            // Abtippen gut lesbar sein: `.title` waechst mit Dynamic Type,
            // `size: 34` nicht. Monospaced, damit die sechs Ziffern beim
            // Tippen nicht springen.
            .font(.system(.title, design: .monospaced).weight(.medium))
            .multilineTextAlignment(.center)
            .textFieldStyle(.plain)
            .focused($imCodefeld)
            #if os(iOS)
            // Ziffernblock statt voller Tastatur: der Code hat keine
            // Buchstaben, und eine Tastatur mit Buchstaben lädt dazu ein,
            // welche zu tippen.
            .keyboardType(.numberPad)
            .textContentType(.oneTimeCode)
            #endif
            .onChange(of: code) { _, neu in
                // Nur Ziffern, höchstens sechs. Filtern statt meckern: eine
                // Fehlermeldung für ein Zeichen, das ohnehin nicht hingehört,
                // ist eine Meldung zu viel.
                let sauber = String(neu.filter(\.isNumber).prefix(6))
                if sauber != neu { code = sauber }
                fehler = ""
            }
            .padding(.vertical, Mass.abstand)
            .frame(maxWidth: 280)
            .background(
                RoundedRectangle(cornerRadius: Mass.ecke)
                    .fill(.quaternary.opacity(0.5))
            )
    }

    private var verbindenKnopf: some View {
        Button {
            Task { await koppeln() }
        } label: {
            if laeuft {
                ProgressView().controlSize(.small)
            } else {
                Text("Verbinden")
            }
        }
        .frame(maxWidth: 280)
        .buttonStyle(.borderedProminent)
        .controlSize(.large)
        .disabled(!codeGueltig || adresse == nil || laeuft)
    }

    @ViewBuilder
    private var gefundene: some View {
        // Nur zeigen, wenn es etwas zu zeigen gibt. Ein leerer Kasten „Nichts
        // gefunden" wäre über den Tunnel der Normalfall und damit nur Lärm.
        if suche.laeuft || !suche.gefunden.isEmpty {
            VStack(alignment: .leading, spacing: Mass.abstand) {
                HStack(spacing: 6) {
                    Text("Im Netz gefunden")
                        .font(.footnote.weight(.medium))
                        .foregroundStyle(.secondary)
                    if suche.laeuft {
                        ProgressView().controlSize(.mini)
                    }
                }

                ForEach(suche.gefunden) { server in
                    Button {
                        uebernehmen(server)
                    } label: {
                        HStack(spacing: Mass.abstand) {
                            Image(systemName: "desktopcomputer")
                                .foregroundStyle(.tint)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(server.name)
                                Text(server.beschreibung)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .padding(Mass.abstand)
                    .background(
                        RoundedRectangle(cornerRadius: Mass.ecke)
                            .fill(.quaternary.opacity(0.4))
                    )
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: Unten

    private var serverleiste: some View {
        VStack(spacing: 0) {
            Divider()

            Button {
                withAnimation(.snappy(duration: 0.2)) { offen.toggle() }
            } label: {
                HStack {
                    Text("Server")
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text(serverzeile)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .foregroundStyle(bestaetigt.isEmpty ? .secondary : .primary)
                    Image(systemName: "chevron.up")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.tertiary)
                        .rotationEffect(.degrees(offen ? 0 : 180))
                }
                .font(.footnote)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(.horizontal, Mass.abstandGross)
            .padding(.vertical, Mass.abstand)

            if offen {
                ausklappung
            }
        }
        .background(.bar)
    }

    private var ausklappung: some View {
        VStack(alignment: .leading, spacing: Mass.abstand) {
            Text("Adresse")
                .font(.caption.weight(.medium))
                .foregroundStyle(.secondary)

            TextField("mia.beispiel.de", text: $adresstext)
                .textFieldStyle(.plain)
                #if os(iOS)
                .keyboardType(.URL)
                .textInputAutocapitalization(.never)
                #endif
                .autocorrectionDisabled()
                .onChange(of: adresstext) { _, neu in
                    bestaetigt = ""
                    fehler = ""
                    // Den Port mitziehen, solange Mia ihn nicht selbst
                    // angefasst hat: wer von einem Namen auf eine IP wechselt,
                    // will 8080, nicht 443. Sobald dort etwas Eigenes steht,
                    // bleibt es stehen.
                    let vorschlag = Einstellungen.portVorschlag(fuer: neu)
                    if porttext.isEmpty || !portVonHand {
                        porttext = String(vorschlag)
                    }
                }
                .padding(Mass.abstand)
                .background(
                    RoundedRectangle(cornerRadius: Mass.ecke)
                        .fill(.quaternary.opacity(0.5))
                )

            Text("Port")
                .font(.caption.weight(.medium))
                .foregroundStyle(.secondary)

            HStack(spacing: Mass.abstand) {
                TextField("443", text: $porttext)
                    .textFieldStyle(.plain)
                    #if os(iOS)
                    .keyboardType(.numberPad)
                    #endif
                    .onChange(of: porttext) { _, neu in
                        let sauber = String(neu.filter(\.isNumber).prefix(5))
                        if sauber != neu { porttext = sauber }
                        portVonHand = true
                        bestaetigt = ""
                    }
                    .frame(width: 90)
                    .padding(Mass.abstand)
                    .background(
                        RoundedRectangle(cornerRadius: Mass.ecke)
                            .fill(.quaternary.opacity(0.5))
                    )

                Button {
                    Task { await adressePruefen() }
                } label: {
                    if pruefeAdresse {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Prüfen")
                    }
                }
                .buttonStyle(.bordered)
                .disabled(adresse == nil || pruefeAdresse)

                if !bestaetigt.isEmpty {
                    Label("erreichbar", systemImage: "checkmark.circle.fill")
                        .font(.caption)
                        .foregroundStyle(.green)
                        .labelStyle(.titleAndIcon)
                }
                Spacer()
            }
        }
        .padding(.horizontal, Mass.abstandGross)
        .padding(.bottom, Mass.abstandGross)
        .frame(maxWidth: 420)
        .frame(maxWidth: .infinity)
    }

    // MARK: Handlungen

    private func starten() {
        if Einstellungen.adresseGesetzt {
            let vorhanden = Einstellungen.adresse
            adresstext = (vorhanden.host() ?? "")
            porttext = String(Einstellungen.portVon(vorhanden))
            imCodefeld = true
        } else {
            // Ohne Adresse bringt das Codefeld nichts: der Code liefe gegen
            // `localhost` und wäre verbraucht. Also gleich aufgeklappt.
            offen = true
            porttext = "443"
        }
        suche.starten()
    }

    /// Einen gefundenen Server übernehmen. **Nur auf Antippen.**
    ///
    /// Prüft sofort und springt ins Codefeld, damit ein Fund ein Tippen
    /// kostet und nicht drei.
    ///
    /// Die Betonung liegt auf „auf Antippen": beim ersten Entwurf setzte die
    /// Suche die Adresse selbst, sobald sie etwas fand. Im Simulator stand
    /// dadurch prompt eine fremde Adresse aus dem Heimnetz in der Zeile,
    /// ohne dass jemand sie gewählt hatte, und das Ausklappen schloss sich
    /// von allein. Eine App, die sich ungefragt mit einem Server im Netz
    /// verbindet, ist das Gegenteil von dem, was dieser Bildschirm leisten
    /// soll.
    private func uebernehmen(_ server: GefundenerServer) {
        adresstext = server.adresse.host() ?? ""
        porttext = String(Einstellungen.portVon(server.adresse))
        portVonHand = true
        bestaetigt = ""
        fehler = ""
        Task { await adressePruefen() }
    }

    private func adressePruefen() async {
        guard let url = adresse else { return }
        pruefeAdresse = true
        fehler = ""
        defer { pruefeAdresse = false }

        switch await Draht.pruefen(url) {
        case .success(let version):
            // Gleich merken: wer geprüft hat, will die Adresse auch benutzen.
            Einstellungen.adresse = url
            await zentrale.adresseSetzen(url)
            bestaetigt = version.isEmpty ? "Mia OS" : "Mia OS \(version)"
            // Zuklappen und in den Code springen: die Adresse ist erledigt,
            // der Bildschirm soll wieder ruhig werden.
            withAnimation(.snappy(duration: 0.2)) { offen = false }
            imCodefeld = true
        case .failure(let grund):
            bestaetigt = ""
            fehler = grund.localizedDescription
            offen = true
        }
    }

    private func koppeln() async {
        guard let url = adresse else { return }
        laeuft = true
        fehler = ""
        defer { laeuft = false }

        // Die Adresse in jedem Fall setzen, auch ohne vorheriges Prüfen:
        // sonst ginge der Code an die alte.
        Einstellungen.adresse = url
        await zentrale.adresseSetzen(url)

        do {
            try await zentrale.koppeln(code: code)
        } catch {
            fehler = error.localizedDescription
            // Das Feld leeren: ein Code gilt genau einmal, der im Feld ist
            // nach einem Fehlversuch in jedem Fall verbraucht.
            code = ""
            imCodefeld = true
        }
    }
}
