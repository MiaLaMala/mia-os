// swift-tools-version: 6.0
//
// Der Kern der App als Paket: Netz, Modelle, Ansichten.
//
// **Warum ein Paket und nicht nur ein Xcode-Projekt:** so lässt sich der Code
// mit `swift build` auf der Kommandozeile übersetzen und testen, ohne Xcode
// zu öffnen. Das Xcode-Projekt daneben baut die eigentlichen Apps (Mac und
// iPhone) und benutzt dieses Paket.

import PackageDescription

let package = Package(
    name: "MiaOSKern",
    // macOS 14 und iOS 17: darunter gibt es `@Observable` nicht, und ohne das
    // müsste jeder Zustand über `ObservableObject` und `@Published` laufen.
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [
        .library(name: "MiaOSKern", targets: ["MiaOSKern"])
    ],
    targets: [
        .target(
            name: "MiaOSKern",
            path: "MiaOS",
            // MiaOSApp.swift traegt das `@main` der fertigen Apps. In einer
            // Bibliothek, gegen die getestet wird, ist das ein zweites
            // `_main` neben dem des Test-Runners, und der Linker bricht mit
            // "duplicate symbol '_main'" ab. Die Datei gehoert nur in die
            // Xcode-Ziele, nicht hierher.
            //
            // Der Asset-Katalog ebenso: SwiftPM kann ihn ohne eigene
            // Ressourcen-Deklaration nicht einordnen und warnt bei jedem
            // Lauf. Gebraucht wird er nur beim Bau der Apps, und den macht
            // Xcode.
            exclude: ["MiaOSApp.swift", "Assets.xcassets"]
        ),
        .testTarget(
            name: "MiaOSKernTests",
            dependencies: ["MiaOSKern"],
            path: "MiaOSTests"
        ),
    ]
)
