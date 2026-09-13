/**
 * Routen und Navigation an einer Stelle.
 *
 * Eine neue Seite ist eine neue Datei plus ein Eintrag hier. Sonst nichts.
 */

import Heute from "../seiten/Heute.svelte";
import Termine from "../seiten/Termine.svelte";
import SeitenAnsicht from "../seiten/SeitenAnsicht.svelte";
import Gesundheit from "../seiten/Gesundheit.svelte";
import Homelab from "../seiten/Homelab.svelte";
import Dokumente from "../seiten/Dokumente.svelte";
import Berichtsheft from "../seiten/Berichtsheft.svelte";
import Einstellungen from "../seiten/Einstellungen.svelte";
import Ueber from "../seiten/Ueber.svelte";
import NichtGefunden from "../seiten/NichtGefunden.svelte";

export const routen = {
  "/": Heute,
  "/termine": Termine,
  "/seite/:id": SeitenAnsicht,
  "/gesundheit": Gesundheit,
  "/homelab": Homelab,
  "/dokumente": Dokumente,
  "/berichtsheft": Berichtsheft,
  "/einstellungen": Einstellungen,
  "/ueber": Ueber,
  "*": NichtGefunden,
};

export interface NavEintrag {
  pfad: string;
  titel: string;
  symbol: string;
}

/** Die festen Bereiche, in der Reihenfolge der Seitenleiste. */
export const NAVIGATION: NavEintrag[] = [
  { pfad: "/", titel: "Heute", symbol: "home" },
  { pfad: "/termine", titel: "Termine", symbol: "calendar" },
  { pfad: "/dokumente", titel: "Dokumente", symbol: "document" },
  { pfad: "/berichtsheft", titel: "Berichtsheft", symbol: "book" },
  { pfad: "/gesundheit", titel: "Gesundheit", symbol: "heart" },
  { pfad: "/homelab", titel: "Homelab", symbol: "server" },
];

export const EINSTELLUNGEN: NavEintrag = {
  pfad: "/einstellungen",
  titel: "Einstellungen",
  symbol: "settings",
};

/** Steht unten bei den Einstellungen, nicht in der Hauptnavigation:
 * eine Seite, die man einmal im Monat aufmacht, gehört nicht neben
 * "Heute" und "Termine". */
export const UEBER: NavEintrag = {
  pfad: "/ueber",
  titel: "Über Mia OS",
  symbol: "info",
};

/** Was auf dem Handy unten in der Leiste steht. Vier Ziele plus "Mehr". */
export const LEISTE = ["/", "/termine", "/dokumente"];
