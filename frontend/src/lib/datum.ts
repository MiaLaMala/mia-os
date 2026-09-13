/** Datumshelfer. Lokale Zeit, nie toISOString (rechnet UTC, zeigte den Vortag). */

export function alsTag(d: Date): string {
  const z = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
}

export function heute(): string {
  return alsTag(new Date());
}

export function tagPlus(tag: string, tage: number): string {
  const d = new Date(`${tag}T12:00`);
  d.setDate(d.getDate() + tage);
  return alsTag(d);
}

export function uhrzeit(iso: string): string {
  return iso.length >= 16 ? iso.slice(11, 16) : "";
}

const TAGE = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"];
const MONATE = [
  "Januar", "Februar", "März", "April", "Mai", "Juni",
  "Juli", "August", "September", "Oktober", "November", "Dezember",
];

/** "Montag, 7. September" */
export function langesDatum(tag: string): string {
  const d = new Date(`${tag}T12:00`);
  return `${TAGE[d.getDay()]}, ${d.getDate()}. ${MONATE[d.getMonth()]}`;
}

/** "7. Sep." */
export function kurzesDatum(tag: string): string {
  const d = new Date(`${tag}T12:00`);
  return `${d.getDate()}. ${MONATE[d.getMonth()].slice(0, 3)}.`;
}

/** "Heute", "Morgen", sonst Wochentag oder Datum. */
export function tagwort(tag: string): string {
  const h = heute();
  if (tag === h) return "Heute";
  if (tag === tagPlus(h, 1)) return "Morgen";
  if (tag === tagPlus(h, -1)) return "Gestern";
  const d = new Date(`${tag}T12:00`);
  const abstand = Math.round((d.getTime() - new Date(`${h}T12:00`).getTime()) / 86_400_000);
  if (abstand > 1 && abstand < 7) return TAGE[d.getDay()];
  return kurzesDatum(tag);
}

/** Begrüßung nach Tageszeit. */
export function gruss(): string {
  const h = new Date().getHours();
  if (h < 5) return "Gute Nacht";
  if (h < 11) return "Guten Morgen";
  if (h < 18) return "Hallo";
  return "Guten Abend";
}
