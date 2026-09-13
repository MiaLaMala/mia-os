/**
 * Termine zwischenspeichern.
 *
 * Ohne das geht jedes Blaettern zum Server: gemessen 230 Millisekunden, in
 * denen die Seite still steht. Nicht langsam, aber es fuehlt sich zaeh an,
 * weil nichts passiert.
 *
 * Der Speicher haelt Monate einzeln vor. Bereits besuchte Monate erscheinen
 * sofort, im Hintergrund wird trotzdem frisch geholt: so ist die Anzeige
 * schnell UND aktuell.
 */

import { api } from "./api";
import type { KalenderTermin } from "./types";

/** Ein Datum als YYYY-MM-DD in lokaler Zeit. */
function alsTag(d: Date): string {
  const z = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
}


interface Eintrag {
  termine: KalenderTermin[];
  kalender: string[];
  /** Wie viele Aufgaben je Tag faellig sind, fuer die Marken im Blatt. */
  aufgaben_je_tag: Record<string, number>;
  geholt: number;
}

// Nach dieser Zeit gilt ein Eintrag als alt und wird im Hintergrund erneuert.
const FRISCH_MS = 60_000;

const speicher = new Map<string, Eintrag>();

function schluessel(von: string, bis: string, kalender: string): string {
  return `${von}|${bis}|${kalender}`;
}

/** Was im Speicher liegt, ohne zu laden. Null, wenn nichts da ist. */
export function ausSpeicher(von: string, bis: string, kalender = ""): Eintrag | null {
  return speicher.get(schluessel(von, bis, kalender)) ?? null;
}

/** Termine holen. Nutzt den Speicher, wenn er frisch genug ist. */
export async function termineHolen(
  von: string,
  bis: string,
  kalender = "",
): Promise<Eintrag> {
  const k = schluessel(von, bis, kalender);
  const da = speicher.get(k);

  if (da && Date.now() - da.geholt < FRISCH_MS) return da;

  const daten = await api.termine(von, bis, kalender);
  const neu: Eintrag = {
    ...daten,
    aufgaben_je_tag: daten.aufgaben_je_tag ?? {},
    geholt: Date.now(),
  };
  speicher.set(k, neu);
  return neu;
}

/**
 * Den naechsten und vorherigen Monat im Hintergrund holen.
 *
 * Damit ist Blaettern in beide Richtungen sofort da, statt jedes Mal zu
 * warten. Fehler werden verschluckt: es ist nur ein Vorgriff.
 */
export function nachbarnVorladen(anker: Date, kalender = ""): void {
  for (const versatz of [-1, 1]) {
    const ziel = new Date(anker.getFullYear(), anker.getMonth() + versatz, 1);
    const von = new Date(ziel.getFullYear(), ziel.getMonth(), 1);
    const bis = new Date(ziel.getFullYear(), ziel.getMonth() + 1, 0);
    // Rand mitnehmen, das Monatsblatt zeigt auch Nachbartage.
    von.setDate(von.getDate() - 7);
    bis.setDate(bis.getDate() + 7);

    // Lokal rechnen, nicht toISOString(): das nimmt UTC und verschiebt das
    // Fenster nachts um einen Tag.
    const vonIso = alsTag(von);
    const bisIso = alsTag(bis);
    if (speicher.has(schluessel(vonIso, bisIso, kalender))) continue;

    void termineHolen(vonIso, bisIso, kalender).catch(() => {});
  }
}

/** Nach einer Aenderung: alles vergessen, damit frisch geladen wird. */
export function speicherLeeren(): void {
  speicher.clear();
}
