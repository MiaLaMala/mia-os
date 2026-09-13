// Der Einstiegspunkt für beide Apps.
//
// Eine Datei für Mac und iPhone: der Unterschied steckt in den Ansichten und
// in den Fenstern, nicht im Start.

import SwiftUI

@main
struct MiaOSApp: App {
    /// Einmal angelegt und an alle Ansichten weitergereicht. `@State` und
    /// nicht `@StateObject`: `Zentrale` ist ein `@Observable`, und das ist
    /// der Weg dafür seit iOS 17.
    @State private var zentrale = Zentrale()

    var body: some Scene {
        // Der ganze Aufbau steht einmal je Plattform, statt ein `#if` mitten
        // in die Kette der Modifikatoren zu setzen. Grund: ein `#if`, das
        // eine zweite Scene (`Settings`) einschließen soll, ist innerhalb
        // eines SceneBuilders kein gültiger Ausdruck — der Compiler meldet
        // „unexpected tokens in '#if' expression body". Zwei getrennte
        // Blöcke sind länger, aber sie übersetzen.
        #if os(macOS)
        WindowGroup(id: "haupt") {
            Wurzel()
                .environment(zentrale)
        }
        // Die Titelleiste verschmilzt mit dem Inhalt, wie in Mail und
        // Notizen.
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified)
        .defaultSize(width: 980, height: 680)
        .commands {
            MiaOSBefehle(zentrale: zentrale)
        }

        // Die Schnelleingabe als eigenes Fenster.
        //
        // `Window` und nicht `WindowGroup`: es soll genau eines davon geben.
        // Eine Gruppe würde bei jedem Aufruf ein weiteres öffnen, und nach
        // dem dritten Gedanken stünden drei Felder übereinander.
        Window("Schnell eintragen", id: "schnell") {
            Schnelleingabe()
                .environment(zentrale)
        }
        .windowResizability(.contentSize)
        .defaultPosition(.center)
        // Kein `.windowLevel(.floating)`: das gibt es erst ab macOS 15, und
        // die App läuft ab 14. Das Schweben übernimmt stattdessen
        // `NSApp.activate` beim Öffnen, siehe MiaOSBefehle: das holt das
        // Fenster nach vorn, auch wenn gerade ein anderes Programm aktiv ist.
        // Über allem bleibt es damit nicht, aber genau das braucht es auch
        // nicht: es schließt sich nach dem Absenden von selbst.

        Menuleiste(zentrale: zentrale)

        Settings {
            Geraet()
                .environment(zentrale)
                .frame(width: 420)
        }
        #else
        WindowGroup {
            Wurzel()
                .environment(zentrale)
        }
        #endif
    }
}

#if os(macOS)
/// Die Menüpunkte, die ein Mac-Nutzer sucht.
///
/// Ohne sie wirkt eine App portiert, auch wenn sie es nicht ist: die
/// Menüleiste ist das Erste, wo jemand nachsieht, was ein Programm kann.
private struct MiaOSBefehle: Commands {
    let zentrale: Zentrale
    @Environment(\.openWindow) private var fensterOeffnen

    var body: some Commands {
        // „Neues Fenster" ergibt hier keinen Sinn: die App zeigt einen
        // Zustand, kein Dokument. Zwei Fenster mit demselben Inhalt sind nur
        // zwei Fenster. Der Platz gehört der Schnelleingabe.
        CommandGroup(replacing: .newItem) {
            Button("Schnell eintragen") {
                NSApp.activate(ignoringOtherApps: true)
                fensterOeffnen(id: "schnell")
            }
            .keyboardShortcut("n")
        }

        CommandGroup(after: .toolbar) {
            Button("Aktualisieren") {
                Task { await zentrale.alleslLaden() }
            }
            .keyboardShortcut("r")

            Divider()
        }
    }
}
#endif
