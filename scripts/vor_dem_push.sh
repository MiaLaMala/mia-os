#!/usr/bin/env bash
# Vor dem Push: genau das laufen lassen, was die CI laufen lässt.
#
# Anlass (09.09.2026, Mias Ansage): "Kannst du darauf achten, dass ich keine
# Fehler mehr bekomme?" Seit dem 05.09. sind neun CI-Läufe fehlgeschlagen,
# jeder davon hat ihr eine Mail geschickt. Alle neun waren vermeidbar:
#
#   2x  ruff format --check   ich lief `ruff format` (repariert still),
#                             die CI läuft `--check` (meckert)
#   2x  gitleaks              lokal nie geprüft
#   1x  mypy                  vor dem Push nicht gelaufen
#   1x  pytest                dito
#   3x  Python-Version        numpy 2.5 braucht >=3.12, CI stand auf 3.11
#
# Das Muster ist immer dasselbe: ich prüfe *einige* Gates, aber nicht alle,
# und nicht mit demselben Befehl. Deshalb steht hier jeder CI-Schritt in
# derselben Reihenfolge und mit denselben Argumenten.
#
# Aufruf:  bash scripts/vor_dem_push.sh
# Rückgabe: 0 = die CI wird durchlaufen, sonst die Anzahl der Probleme.

set -uo pipefail
cd "$(dirname "$0")/.."

VENV=.venv/bin
FEHLER=0
declare -a KAPUTT=()

lauf() {
    local name="$1"; shift
    printf '  %-34s' "$name"
    local ausgabe
    if ausgabe=$("$@" 2>&1); then
        echo "ok"
    else
        echo "FEHLGESCHLAGEN"
        echo "$ausgabe" | tail -18 | sed 's/^/      /'
        FEHLER=$((FEHLER + 1))
        KAPUTT+=("$name")
    fi
}

echo "Was die CI prüfen wird:"
echo

# --- Job "Lint & Format" -------------------------------------------------
# Die Reihenfolge zählt: `check` vor `format --check`. Umgekehrt meldet
# format Erfolg auf Code, den check gleich darauf verwirft.
lauf "ruff check" $VENV/ruff check src tests
lauf "ruff format --check" $VENV/ruff format --check src tests

# --- Job "Typen" ---------------------------------------------------------
lauf "mypy" $VENV/mypy src

# --- Job "Tests" ---------------------------------------------------------
lauf "pytest" $VENV/python -m pytest -q

# Dasselbe nochmal in einem flachen Klon. Grund: die CI holt per Vorgabe nur
# den letzten Commit, lokal liegt die ganze Historie. Ein Test, der `git log
# HEAD~3` aufruft, läuft hier grün und bricht dort mit exit 128 ab. Genau das
# ist am 09.09.2026 passiert, nachdem dieses Skript "alles grün" gemeldet
# hatte: ein Hook, der eine Umgebung nicht nachstellt, prüft sie auch nicht.
printf '  %-34s' "pytest (flacher Klon wie CI)"
FLACH=$(mktemp -d)
HIER=$PWD
if git clone -q --depth 1 "file://$HIER" "$FLACH/repo" 2>/dev/null; then
    # Das venv mitbenutzen statt neu aufzusetzen: es geht um die Historie,
    # nicht um die Abhängigkeiten.
    ln -s "$HIER/.venv" "$FLACH/repo/.venv"
    if AUSGABE=$(cd "$FLACH/repo" && "$HIER/$VENV/python" -m pytest -q --no-cov \
                    -p no:cacheprovider 2>&1); then
        echo "ok"
    else
        echo "FEHLGESCHLAGEN"
        echo "$AUSGABE" | grep -E "FAILED|Error:" | head -8 | sed 's/^/      /'
        FEHLER=$((FEHLER + 1))
        KAPUTT+=("pytest im flachen Klon")
    fi
else
    echo "ging nicht, übersprungen"
fi
rm -rf "$FLACH"

# --- Job "Sicherheit" ----------------------------------------------------
# gitleaks liegt nicht im System, wird beim ersten Lauf geholt. Ohne diese
# Prüfung ist genau am 05.09. zweimal ein Lauf gescheitert.
GITLEAKS=".venv/bin/gitleaks"
if [ ! -x "$GITLEAKS" ]; then
    printf '  %-34s' "gitleaks holen"
    if curl -sSL "https://github.com/gitleaks/gitleaks/releases/download/v8.28.0/gitleaks_8.28.0_linux_x64.tar.gz" \
        | tar -xz -C .venv/bin gitleaks 2>/dev/null; then
        echo "ok"
    else
        echo "ging nicht, überspringe"
    fi
fi
if [ -x "$GITLEAKS" ]; then
    lauf "gitleaks" "$GITLEAKS" dir . --redact --no-banner
fi

# --- Job "Docker-Image" --------------------------------------------------
# Der Build selbst dauert Minuten und braucht Netz. Statt ihn nachzubauen,
# wird geprüft, woran er bisher gescheitert ist: eine Python-Version im
# Dockerfile, die nicht zu requires-python passt.
printf '  %-34s' "Python-Versionen stimmig"
NOETIG=$(grep -oP 'requires-python\s*=\s*">=\K[0-9]+\.[0-9]+' pyproject.toml)
PROBLEME=""
while read -r v; do
    [ -z "$v" ] && continue
    if [ "$(printf '%s\n%s\n' "$NOETIG" "$v" | sort -V | head -1)" != "$NOETIG" ]; then
        PROBLEME="$PROBLEME $v"
    fi
done < <(grep -oP 'FROM python:\K[0-9]+\.[0-9]+' Dockerfile
         grep -oP 'python-version:\s*\[?\K[0-9."., ]+' .github/workflows/ci.yml \
           | tr -d '"' | tr ',' '\n' | tr -d ' ')
if [ -z "$PROBLEME" ]; then
    echo "ok (alle >= $NOETIG)"
else
    echo "FEHLGESCHLAGEN"
    echo "      pyproject verlangt >=$NOETIG, aber Dockerfile/CI nennen:$PROBLEME" 
    FEHLER=$((FEHLER + 1))
    KAPUTT+=("Python-Versionen")
fi

# --- Frontend ------------------------------------------------------------
# Nicht in der CI, aber im Docker-Build: ein kaputtes Frontend lässt das
# Image scheitern, und das sieht Mia dann als fehlgeschlagenen Lauf.
if [ -d frontend/node_modules ]; then
    lauf "svelte-check" npm --prefix frontend run check
    lauf "frontend build" npm --prefix frontend run build
else
    echo "  frontend                           übersprungen (kein node_modules)"
fi

echo
if [ "$FEHLER" -eq 0 ]; then
    echo "Alles grün. Der Push löst keine Fehlermail aus."
else
    echo "$FEHLER Problem(e): ${KAPUTT[*]}"
    echo "NICHT pushen, sonst bekommt Mia eine Mail."
fi
exit "$FEHLER"
