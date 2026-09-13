// Mausklicks und Tastatureingaben auf den Simulator.
//
// **Warum ein eigenes Werkzeug:** AppleScripts `click at` gibt es in
// System Events nicht (Fehler -25204), und `keystroke` landet nicht
// zuverlässig im Simulator-Fenster. Ein Dialog *im* Gerätebildschirm ist
// außerdem kein macOS-Bedienelement: er lässt sich nicht über die
// Bedienungshilfen-Hierarchie ansprechen, nur über echte Mausereignisse an
// der richtigen Bildschirmstelle.
//
// Braucht die Freigabe unter Bedienungshilfen für den aufrufenden Prozess
// (bei SSH: `sshd-keygen-wrapper`).
//
// Aufruf:
//   swift klick.swift klick <x> <y>      Klick an Bildschirmkoordinate
//   swift klick.swift tippe <text>       Text eintippen
//   swift klick.swift enter              Zeilenschalter

import CoreGraphics
import Foundation

func klick(x: Double, y: Double) {
    let punkt = CGPoint(x: x, y: y)
    let quelle = CGEventSource(stateID: .hidSystemState)

    // Erst bewegen, dann drücken. Ohne die Bewegung landet der Klick zwar an
    // der richtigen Stelle, aber die App unter dem Zeiger bekommt kein
    // Mouse-Entered und hebt den Knopf nicht hervor: bei Oberflächen, die auf
    // Hover reagieren, geht der Klick dann ins Leere.
    CGEvent(mouseEventSource: quelle, mouseType: .mouseMoved,
            mouseCursorPosition: punkt, mouseButton: .left)?.post(tap: .cghidEventTap)
    usleep(120_000)
    CGEvent(mouseEventSource: quelle, mouseType: .leftMouseDown,
            mouseCursorPosition: punkt, mouseButton: .left)?.post(tap: .cghidEventTap)
    usleep(80_000)
    CGEvent(mouseEventSource: quelle, mouseType: .leftMouseUp,
            mouseCursorPosition: punkt, mouseButton: .left)?.post(tap: .cghidEventTap)
}

func tippe(_ text: String) {
    let quelle = CGEventSource(stateID: .hidSystemState)
    for zeichen in text.unicodeScalars {
        // Über Unicode statt über Tastencodes: ein Tastencode hängt am
        // Tastaturlayout, und auf einer deutschen Tastatur sitzen Ziffern und
        // Sonderzeichen woanders als auf einer amerikanischen.
        var einheit = UInt16(zeichen.value)
        for gedrueckt in [true, false] {
            let e = CGEvent(keyboardEventSource: quelle, virtualKey: 0, keyDown: gedrueckt)
            e?.keyboardSetUnicodeString(stringLength: 1, unicodeString: &einheit)
            e?.post(tap: .cghidEventTap)
            usleep(25_000)
        }
    }
}

func taste(_ code: CGKeyCode) {
    let quelle = CGEventSource(stateID: .hidSystemState)
    CGEvent(keyboardEventSource: quelle, virtualKey: code, keyDown: true)?
        .post(tap: .cghidEventTap)
    usleep(40_000)
    CGEvent(keyboardEventSource: quelle, virtualKey: code, keyDown: false)?
        .post(tap: .cghidEventTap)
}

let args = CommandLine.arguments
guard args.count >= 2 else {
    print("Aufruf: klick <x> <y> | tippe <text> | enter")
    exit(1)
}

switch args[1] {
case "klick":
    guard args.count == 4, let x = Double(args[2]), let y = Double(args[3]) else {
        print("klick braucht x und y")
        exit(1)
    }
    klick(x: x, y: y)
case "tippe":
    guard args.count >= 3 else { exit(1) }
    tippe(args[2...].joined(separator: " "))
case "enter":
    taste(36)
default:
    print("Unbekannt: \(args[1])")
    exit(1)
}
