// Belege scannen mit der Systemkamera.
//
// **Das Dritte, was eine Website nicht kann.** `VNDocumentCameraViewController`
// ist dieselbe Kamera, die die Notizen-App benutzt: sie findet die Blattkanten
// live, entzerrt perspektivisch, gleicht die Beleuchtung aus und nimmt
// mehrere Seiten hintereinander auf.
//
// In Mia OS gibt es dafür bereits einen Scanner (`src/scanner.py`, OpenCV).
// Der bleibt für den Browser und für Fotos aus der Mediathek. Auf dem iPhone
// ist Apples Kamera besser, und zwar aus einem Grund, den Software nicht
// aufholt: sie korrigiert **während** man das Blatt anvisiert, nicht danach.
// Ein schiefes Foto lässt sich entzerren, ein unscharfes nicht.

#if os(iOS)

import SwiftUI
import VisionKit

/// Die Systemkamera als SwiftUI-Ansicht.
struct Blattkamera: UIViewControllerRepresentable {
    /// Bekommt die aufgenommenen Seiten als JPEG.
    let fertig: ([Data]) -> Void
    @Environment(\.dismiss) private var schliessen

    func makeUIViewController(context: Context) -> VNDocumentCameraViewController {
        let kamera = VNDocumentCameraViewController()
        kamera.delegate = context.coordinator
        return kamera
    }

    func updateUIViewController(_ c: VNDocumentCameraViewController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(fertig: fertig, schliessen: { schliessen() })
    }

    final class Coordinator: NSObject, VNDocumentCameraViewControllerDelegate {
        private let fertig: ([Data]) -> Void
        private let schliessen: () -> Void

        init(fertig: @escaping ([Data]) -> Void, schliessen: @escaping () -> Void) {
            self.fertig = fertig
            self.schliessen = schliessen
        }

        func documentCameraViewController(
            _ controller: VNDocumentCameraViewController,
            didFinishWith scan: VNDocumentCameraScan
        ) {
            var seiten: [Data] = []
            for i in 0..<scan.pageCount {
                // JPEG mit 0,85 statt PNG: ein entzerrtes A4-Blatt ist als PNG
                // gut 8 MB und als JPEG unter 1. Über WLAN im Zug ist das der
                // Unterschied zwischen „hochgeladen" und „abgebrochen", und
                // Text auf Papier verliert dabei nichts Sichtbares.
                if let daten = scan.imageOfPage(at: i).jpegData(compressionQuality: 0.85) {
                    seiten.append(daten)
                }
            }
            fertig(seiten)
            schliessen()
        }

        func documentCameraViewControllerDidCancel(_ c: VNDocumentCameraViewController) {
            schliessen()
        }

        func documentCameraViewController(
            _ c: VNDocumentCameraViewController, didFailWithError error: Error
        ) {
            schliessen()
        }
    }
}

/// Der Knopf und was danach passiert.
struct Scannen: View {
    @Environment(Zentrale.self) private var zentrale
    @State private var kameraOffen = false
    @State private var laeuft = false
    @State private var meldung = ""

    var body: some View {
        VStack(spacing: Mass.abstandGross) {
            Spacer()

            Image(systemName: "doc.viewfinder")
                .font(.system(size: 46, weight: .light))
                .foregroundStyle(.tint)

            VStack(spacing: 6) {
                Text("Beleg scannen")
                    .font(.title2.weight(.semibold))
                Text("Kanten und Ausleuchtung macht die Kamera.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            if laeuft {
                ProgressView()
            } else {
                Button {
                    kameraOffen = true
                } label: {
                    Label("Kamera", systemImage: "camera")
                        .frame(maxWidth: 240)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            }

            if !meldung.isEmpty {
                Text(meldung)
                    .font(.callout)
                    .foregroundStyle(meldung.hasPrefix("Fehler") ? .red : .secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, Mass.abstandGross)
            }

            Spacer()
        }
        .padding(Mass.abstandGross)
        .navigationTitle("Scannen")
        .fullScreenCover(isPresented: $kameraOffen) {
            Blattkamera { seiten in
                Task { await hochladen(seiten) }
            }
            .ignoresSafeArea()
        }
    }

    private func hochladen(_ seiten: [Data]) async {
        guard !seiten.isEmpty else { return }
        laeuft = true
        defer { laeuft = false }
        do {
            let namen = try await zentrale.belegeHochladen(seiten)
            meldung = namen.count == 1
                ? "\(namen[0]) abgelegt"
                : "\(namen.count) Seiten abgelegt"
        } catch {
            meldung = "Fehler: \(error.localizedDescription)"
        }
    }
}

#endif
