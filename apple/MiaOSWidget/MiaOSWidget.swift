// Mia OS auf dem Sperrbildschirm und dem Home-Bildschirm.
//
// **Das ist der Grund für eine native App.** Eine Website kann das nicht:
// eine Zahl, die schon da ist, bevor man etwas öffnet. Der halbe Nutzen von
// Mia OS ist „was steht als Nächstes an", und diese Frage soll man nicht
// stellen müssen.
//
// Vier Größen, jede mit einer eigenen Aufgabe:
//
//   Sperrbildschirm, rund      die Zahl der fälligen Sachen
//   Sperrbildschirm, Zeile     der nächste Termin als eine Zeile
//   Home-Bildschirm, klein     Zeit und Titel des nächsten Termins
//   Home-Bildschirm, mittel    dazu die Zahlen und was danach kommt
//
// Alle lesen aus der App Group, keine holt selbst. Ein Widget hat Sekunden
// und darf nicht auf ein Netz warten, das gerade weg ist.

import SwiftUI
import WidgetKit

// MARK: - Nachschub

/// Ein Zeitpunkt in der Widget-Zeitleiste.
///
/// Nicht `Eintrag`: so heisst in den Modellen bereits ein Sammlungseintrag,
/// und beide liegen im selben Ziel. Der Compiler meldete "invalid
/// redeclaration" und danach ein Dutzend Folgefehler.
struct Zeitpunkt: TimelineEntry {
    let date: Date
    let daten: Handgelenk

    static let beispiel = Zeitpunkt(
        date: Date(),
        daten: Handgelenk(
            naechster: Kurztermin(titel: "Berufsschule", zeit: "19:30", ort: "BBW Hamburg"),
            spaeter_heute: 1,
            faellig: 3,
            offen: 6,
            stand: ISO8601DateFormatter().string(from: Date())
        )
    )
}

struct Nachschub: TimelineProvider {
    func placeholder(in context: Context) -> Zeitpunkt { .beispiel }

    func getSnapshot(in context: Context, completion: @escaping (Zeitpunkt) -> Void) {
        // In der Widget-Galerie zeigt iOS den Snapshot. Dort echte Daten zu
        // zeigen ist besser als Platzhalter: Mia sieht beim Aussuchen, was
        // das Widget wirklich kann.
        completion(Zeitpunkt(date: Date(), daten: Ablage.lesen() ?? Zeitpunkt.beispiel.daten))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<Zeitpunkt>) -> Void) {
        let jetzt = Date()
        let daten = Ablage.lesen() ?? .leer

        // In 15 Minuten wieder nachsehen. Öfter lässt iOS ohnehin nicht zu
        // (das Budget liegt bei rund 40 bis 70 Aktualisierungen am Tag), und
        // seltener hieße, dass ein abgehakter Punkt zu lange stehen bleibt.
        let naechste = jetzt.addingTimeInterval(15 * 60)
        completion(Timeline(entries: [Zeitpunkt(date: jetzt, daten: daten)], policy: .after(naechste)))
    }
}

// MARK: - Sperrbildschirm

/// Der runde Kreis neben der Uhrzeit: wie viel ist fällig.
struct RundeAnsicht: View {
    let daten: Handgelenk

    var body: some View {
        Gauge(value: Double(min(daten.faellig, 9)), in: 0...9) {
            Image(systemName: "checklist")
        } currentValueLabel: {
            Text("\(daten.faellig)")
        }
        .gaugeStyle(.accessoryCircular)
    }
}

/// Die Zeile unter der Uhrzeit: der nächste Termin.
struct ZeilenAnsicht: View {
    let daten: Handgelenk

    var body: some View {
        if let t = daten.naechster {
            // Nicht `Label`: auf dem Sperrbildschirm ist der Platz so knapp,
            // dass ein Symbol den halben Titel frisst. Die Zeit sagt schon,
            // dass es ein Termin ist.
            Text(t.zeit.isEmpty ? t.titel : "\(t.zeit)  \(t.titel)")
                .widgetAccentable()
        } else if daten.faellig > 0 {
            Text("\(daten.faellig) fällig")
        } else {
            Text("nichts mehr heute")
        }
    }
}

// MARK: - Home-Bildschirm

struct KleineAnsicht: View {
    let daten: Handgelenk

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            if let t = daten.naechster {
                if !t.zeit.isEmpty {
                    Text(t.zeit)
                        .font(.system(.title2, design: .rounded).weight(.semibold).monospacedDigit())
                        .foregroundStyle(.tint)
                }
                Text(t.titel)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(2)
                if !t.ort.isEmpty {
                    Text(t.ort)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            } else {
                Text("Nichts mehr")
                    .font(.headline)
                Text("heute")
                    .font(.headline)
                    .foregroundStyle(.secondary)
            }

            Spacer(minLength: 0)

            if daten.faellig > 0 {
                Text("\(daten.faellig) fällig")
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(.orange)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct MittlereAnsicht: View {
    let daten: Handgelenk

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            VStack(alignment: .leading, spacing: 4) {
                if let t = daten.naechster {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        if !t.zeit.isEmpty {
                            Text(t.zeit)
                                .font(.system(.title3, design: .rounded).weight(.semibold)
                                    .monospacedDigit())
                                .foregroundStyle(.tint)
                        }
                        Text(t.titel)
                            .font(.headline)
                            .lineLimit(1)
                    }
                    if !t.ort.isEmpty {
                        Label(t.ort, systemImage: "mappin")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if daten.spaeter_heute > 0 {
                        Text("danach noch \(daten.spaeter_heute)")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                } else {
                    Text("Nichts mehr heute")
                        .font(.headline)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }

            VStack(alignment: .trailing, spacing: 8) {
                Zahl(wert: daten.faellig, wort: "fällig", farbe: daten.faellig > 0 ? .orange : .secondary)
                Zahl(wert: daten.offen, wort: "offen", farbe: .secondary)
            }
        }
    }
}

private struct Zahl: View {
    let wert: Int
    let wort: String
    let farbe: Color

    var body: some View {
        VStack(alignment: .trailing, spacing: -2) {
            Text("\(wert)")
                .font(.system(.title2, design: .rounded).weight(.semibold).monospacedDigit())
                .foregroundStyle(farbe)
            Text(wort)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }
}

// MARK: - Das Widget selbst

struct MiaOSWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "MiaOSWidget", provider: Nachschub()) { eintrag in
            Inhalt(daten: eintrag.daten)
                // Ohne das bleibt der Hintergrund auf iOS 17 schwarz statt in
                // der Systemfarbe des Home-Bildschirms.
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Mia OS")
        .description("Was als Nächstes ansteht.")
        .supportedFamilies([
            .systemSmall, .systemMedium,
            .accessoryCircular, .accessoryInline, .accessoryRectangular,
        ])
    }
}

private struct Inhalt: View {
    @Environment(\.widgetFamily) private var groesse
    let daten: Handgelenk

    var body: some View {
        switch groesse {
        case .accessoryCircular:
            RundeAnsicht(daten: daten)
        case .accessoryInline:
            ZeilenAnsicht(daten: daten)
        case .accessoryRectangular:
            KleineAnsicht(daten: daten)
        case .systemMedium:
            MittlereAnsicht(daten: daten)
        default:
            KleineAnsicht(daten: daten)
        }
    }
}

@main
struct MiaOSWidgets: WidgetBundle {
    var body: some Widget {
        MiaOSWidget()
    }
}
