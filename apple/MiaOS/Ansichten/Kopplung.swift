// Der erste Bildschirm: dieses Gerät mit Mia OS verbinden.
//
// Zwei Schritte, und zwar in dieser Reihenfolge: **erst die Adresse, dann
// der Code.** Bis zum 14.09.2026 gab es nur das Codefeld, die Adresse kam
// ausschließlich über einen `miaos://`-Link. Ohne Link stand dort
// `localhost`, der Code ging ans eigene Gerät und war verbraucht. Ein
// Kopplungscode gilt genau einmal und zehn Minuten; ihn an eine falsche
// Adresse zu verlieren ist ärgerlicher als ein Feld mehr.
//
// Die Adresse lässt sich auf drei Wegen setzen: aus der Bonjour-Liste
// antippen, von Hand tippen, oder über den `miaos://`-Link. Bonjour findet
// nichts über den Tunnel, deshalb steht das Tippfeld gleichberechtigt
// daneben und nicht in einem Untermenü.

import SwiftUI

struct Kopplung: View {
    @Environment(Zentrale.self) private var zentrale
    @State private var suche = Serversuche()

    @State private var adresstext = ""
    @State private var code = ""
    @State private var laeuft = false
    @State private var pruefeAdresse = false
    @State private var fehler = ""
    /// Was die Prüfung ergeben hat. Leer heißt: noch nicht geprüft.
    @State private var adresseBestaetigt = ""
    @FocusState private var imCodefeld: Bool

    private var codeGueltig: Bool {
        code.count == 6 && code.allSatisfy(\.isNumber)
    }

    private var adresseGueltig: Bool {
        Einstellungen.adresseAus(adresstext) != nil
    }

    var body: some View {
        ScrollView {
            VStack(spacing: Mass.abstandGross) {
                kopf

                gefundene

                adressfeld

                codefeld

                if !fehler.isEmpty {
                    Text(fehler)
                        .font(.callout)
                        .foregroundStyle(.red)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, Mass.abstandGross)
                }

                verbindenKnopf
            }
            .padding(Mass.abstandGross)
            .frame(maxWidth: 420)
            .frame(maxWidth: .infinity)
        }
        .onAppear {
            // Die zuletzt benutzte Adresse vorbelegen, aber nur wenn eine
            // gesetzt wurde: sonst stünde hier „localhost" und lüde dazu ein,
            // genau den Fehler zu wiederholen, gegen den dieses Feld existiert.
            if Einstellungen.adresseGesetzt {
                adresstext = Einstellungen.adresse.absoluteString
            }
            suche.starten()
        }
        .onDisappear { suche.stoppen() }
    }

    // MARK: Teile

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
            Text("Erst den Server wählen, dann den Code eingeben.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(.top, Mass.abstandGross)
    }

    @ViewBuilder
    private var gefundene: some View {
        if suche.laeuft || !suche.gefunden.isEmpty {
            VStack(alignment: .leading, spacing: Mass.abstand) {
                HStack {
                    Text("Im Netz gefunden")
                        .font(.footnote.weight(.medium))
                        .foregroundStyle(.secondary)
                    Spacer()
                    if suche.laeuft {
                        ProgressView().controlSize(.small)
                    }
                }

                ForEach(suche.gefunden) { server in
                    Button {
                        adresstext = server.adresse.absoluteString
                        adresseBestaetigt = ""
                        fehler = ""
                        Task { await adressePruefen() }
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(server.name)
                                Text(server.beschreibung)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.caption)
                                .foregroundStyle(.tertiary)
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
        } else if suche.fertigOhneTreffer {
            // Kein Drama daraus machen: über den Tunnel findet Bonjour nie
            // etwas, und das ist der Normalfall, wenn Mia unterwegs ist.
            HStack(spacing: 6) {
                Text("Nichts im Netz gefunden.")
                Button("Nochmal suchen") { suche.starten() }
            }
            .font(.footnote)
            .foregroundStyle(.secondary)
        }
    }

    private var adressfeld: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Adresse")
                .font(.footnote.weight(.medium))
                .foregroundStyle(.secondary)

            HStack {
                TextField("mia.beispiel.de", text: $adresstext)
                    .textFieldStyle(.plain)
                    #if os(iOS)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    #endif
                    .autocorrectionDisabled()
                    .onChange(of: adresstext) { _, _ in
                        adresseBestaetigt = ""
                        fehler = ""
                    }

                if pruefeAdresse {
                    ProgressView().controlSize(.small)
                } else if !adresseBestaetigt.isEmpty {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                } else {
                    Button("Prüfen") {
                        Task { await adressePruefen() }
                    }
                    .font(.callout)
                    .disabled(!adresseGueltig)
                }
            }
            .padding(Mass.abstand)
            .background(
                RoundedRectangle(cornerRadius: Mass.ecke)
                    .fill(.quaternary.opacity(0.5))
            )

            if !adresseBestaetigt.isEmpty {
                Text(adresseBestaetigt)
                    .font(.caption)
                    .foregroundStyle(.green)
            } else {
                Text("Name oder IP. Ohne https:// davor wird ergänzt.")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
    }

    private var codefeld: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Kopplungscode")
                .font(.footnote.weight(.medium))
                .foregroundStyle(.secondary)

            TextField("000000", text: $code)
                // Der Code ist das Wichtigste auf diesem Bildschirm und muss
                // beim Abtippen gut lesbar sein: `.title` waechst mit Dynamic
                // Type, `size: 34` nicht. Monospaced, damit die sechs Ziffern
                // beim Tippen nicht springen.
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
                    // Nur Ziffern, höchstens sechs. Filtern statt meckern:
                    // eine Fehlermeldung für ein Zeichen, das ohnehin nicht
                    // hingehört, ist eine Meldung zu viel.
                    let sauber = String(neu.filter(\.isNumber).prefix(6))
                    if sauber != neu { code = sauber }
                    fehler = ""
                }
                .padding(.vertical, Mass.abstand)
                .frame(maxWidth: .infinity)
                .background(
                    RoundedRectangle(cornerRadius: Mass.ecke)
                        .fill(.quaternary.opacity(0.5))
                )

            Text("Steht in Mia OS unter Einstellungen. Gilt zehn Minuten.")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
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
        .frame(maxWidth: .infinity)
        .buttonStyle(.borderedProminent)
        .controlSize(.large)
        .disabled(!codeGueltig || !adresseGueltig || laeuft)
    }

    // MARK: Handlungen

    private func adressePruefen() async {
        guard let url = Einstellungen.adresseAus(adresstext) else { return }
        pruefeAdresse = true
        fehler = ""
        defer { pruefeAdresse = false }

        switch await Draht.pruefen(url) {
        case .success(let version):
            // Gleich merken: wer die Adresse geprüft hat, will sie auch
            // benutzen, und ein zweiter Knopf dafür wäre ein Klick zu viel.
            Einstellungen.adresse = url
            adresstext = url.absoluteString
            await zentrale.adresseSetzen(url)
            adresseBestaetigt = version.isEmpty
                ? "Mia OS erreichbar"
                : "Mia OS \(version) erreichbar"
            imCodefeld = true
        case .failure(let grund):
            adresseBestaetigt = ""
            fehler = grund.localizedDescription
        }
    }

    private func koppeln() async {
        guard let url = Einstellungen.adresseAus(adresstext) else { return }
        laeuft = true
        fehler = ""
        defer { laeuft = false }

        // Die Adresse in jedem Fall setzen, auch wenn nicht vorher geprüft
        // wurde: sonst ginge der Code an die alte.
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
