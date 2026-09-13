#!/bin/bash
# Alle Gates vor dem Push. Bricht beim ersten Fehler ab und meldet ihn.
#
# Grund: Ich hatte mypy mit ">/dev/null" laufen lassen und dabei den
# Exit-Code verschluckt. Der Fehler stand lokal die ganze Zeit da, aufgefallen
# ist er erst, als die CI rot wurde. Hier wird jeder Exit-Code geprueft.

cd /home/openclaw/projects/mia-os || exit 1
FEHLER=0

lauf() {
  local name="$1"; shift
  local aus
  aus=$("$@" 2>&1)
  local code=$?
  if [ $code -ne 0 ]; then
    printf '  %-14s FEHLER (exit %d)\n' "$name" "$code"
    echo "$aus" | tail -12 | sed 's/^/      /'
    FEHLER=1
  else
    printf '  %-14s ok\n' "$name"
  fi
}

echo "Gates:"
# Farben zuerst: wenn die Palette die Kontraste reisst, ist alles Weitere
# egal. Prueft nur, schreibt nicht, sonst haette ein Gate-Lauf Nebenwirkungen.
lauf "farben" .venv/bin/python scripts/farben_bauen.py --pruefen
lauf "ruff format" .venv/bin/ruff format --check backend/src backend/tests
lauf "ruff check" .venv/bin/ruff check backend/src backend/tests
lauf "mypy" .venv/bin/mypy backend/src
lauf "pytest" bash -c "cd backend && ../.venv/bin/python -m pytest --no-cov -q"

# Zeitzonen: daran ist die CI schon einmal gescheitert.
for Z in UTC Pacific/Kiritimati Pacific/Midway; do
  (cd backend && TZ=$Z ../.venv/bin/python -m pytest --no-cov -q >/dev/null 2>&1)
  [ $? -ne 0 ] && { echo "  TZ $Z        FEHLER"; FEHLER=1; }
done
[ $FEHLER -eq 0 ] && echo "  zeitzonen      ok"

# Typen im Frontend. Vite baut OHNE Typpruefung: ein Tippfehler wie "holen"
# statt "hole" landete so unbemerkt im Deploy und brach erst im Browser mit
# "holen is not defined". Der Build war die ganze Zeit gruen.
lauf "svelte-check" bash -c "cd frontend && npx --no-install svelte-check --threshold error"

# NUR die Quellen pruefen, nicht das gebaute Frontend: unter
# src/web/static/gebaut liegt generierter Code, den niemand von Hand
# schreibt. Impeccable meldete dort "monotonous-spacing" in Vites HTML.
sh .github/skills/impeccable/scripts/impeccable detect backend/src/web/templates/ >/tmp/imp.log 2>&1
sh .github/skills/impeccable/scripts/impeccable detect frontend/src/ >>/tmp/imp.log 2>&1
if [ -s /tmp/imp.log ] && grep -q "anti-pattern" /tmp/imp.log; then
  echo "  impeccable     FEHLER"; cat /tmp/imp.log | tail -6 | sed 's/^/      /'; FEHLER=1
else
  echo "  impeccable     ok"
fi
rm -f /tmp/imp.log

echo
[ $FEHLER -eq 0 ] && echo "ALLE GATES GRÜN" || echo "GATES ROT — nicht pushen"
exit $FEHLER
