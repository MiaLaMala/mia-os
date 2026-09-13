#!/usr/bin/env bash
# Beide Plattformen übersetzen, nicht nur die, auf der man gerade sitzt.
#
# Anlass: `swift build` läuft auf dem Mac und übersetzt deshalb nur die
# `#if os(macOS)`-Zweige. Der iPhone-Zweig blieb dabei komplett ungeprüft,
# und darin stand eine `Tab`-Syntax, die es erst ab iOS 18 gibt. Ein grüner
# Mac-Build sagt über die iPhone-App genau nichts.
#
# Aufruf:  bash scripts/beide_pruefen.sh
# Rückgabe: 0 = beide übersetzen.

set -uo pipefail
cd "$(dirname "$0")/.."

export DEVELOPER_DIR=${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}

# Muss zu `platforms:` in Package.swift passen. Steht hier noch einmal, weil
# `swiftc -typecheck` das Paketmanifest nicht liest: ohne ausdrückliches
# Ziel nimmt es die SDK-Version, und die ist immer die neueste. Genau dadurch
# fiel die iOS-18-API nicht auf.
IOS_MIN=17.0
MAC_MIN=14.0

FEHLER=0

pruefe() {
    local name="$1" sdk="$2" ziel="$3"
    printf '  %-22s' "$name"
    local pfad ausgabe
    pfad=$(xcrun --sdk "$sdk" --show-sdk-path 2>/dev/null)
    if [ -z "$pfad" ]; then
        echo "SDK fehlt, übersprungen"
        return
    fi
    # `find` statt `**`: das Globstern-Muster braucht in bash ein gesetztes
    # globstar und liefert sonst still eine leere Liste. Ein Lauf über null
    # Dateien meldet Erfolg.
    ausgabe=$(xcrun swiftc -sdk "$pfad" -target "$ziel" -typecheck \
        $(find MiaOS -name '*.swift') 2>&1)
    if echo "$ausgabe" | grep -q "error:"; then
        echo "FEHLER"
        echo "$ausgabe" | grep "error:" | grep -v "^ " | head -8 | sed 's/^/      /'
        FEHLER=$((FEHLER + 1))
    else
        echo "ok"
    fi
}

echo "Übersetzt auf beiden Plattformen:"
pruefe "iPhone (iOS $IOS_MIN)" iphoneos "arm64-apple-ios$IOS_MIN"
pruefe "Simulator" iphonesimulator "arm64-apple-ios$IOS_MIN-simulator"
pruefe "Mac (macOS $MAC_MIN)" macosx "arm64-apple-macos$MAC_MIN"

echo
printf '  %-22s' "Tests"
if AUSGABE=$(swift test 2>&1); then
    # Aus der Zusammenfassung von Swift Testing ("Test run with 10 tests ...").
    # Ein blosses "[0-9]+ tests" traf vorher die erste Zeile ohne Zahl und
    # meldete "0 tests ok", obwohl zehn liefen: eine Zahl, die immer gut
    # aussieht, prueft nichts.
    ANZAHL=$(echo "$AUSGABE" | grep -oE "Test run with [0-9]+ test" | grep -oE "[0-9]+" | head -1)
    echo "${ANZAHL:-?} Tests ok"
else
    echo "FEHLER"
    echo "$AUSGABE" | grep -E "✘|error:" | head -10 | sed 's/^/      /'
    FEHLER=$((FEHLER + 1))
fi

echo
[ $FEHLER -eq 0 ] && echo "ALLES GRÜN" || echo "$FEHLER Problem(e)"
exit $FEHLER
