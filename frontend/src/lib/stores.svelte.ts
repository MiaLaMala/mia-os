/**
 * Gemeinsamer Zustand.
 *
 * Nur was wirklich mehrere Seiten brauchen: Einstellungen und Thema. Alles
 * andere gehört in die Seite, die es benutzt.
 */

import { api } from "./api";
import type { Einstellung } from "./types";

interface EinstellungsZustand {
  posten: Einstellung[];
  werte: Record<string, string>;
  owner: string;
  geladen: boolean;
}

function erstelleEinstellungen() {
  let zustand = $state<EinstellungsZustand>({
    posten: [],
    werte: {},
    owner: "",
    geladen: false,
  });

  return {
    get posten() {
      return zustand.posten;
    },
    get werte() {
      return zustand.werte;
    },
    get owner() {
      return zustand.owner;
    },
    get geladen() {
      return zustand.geladen;
    },

    async laden() {
      try {
        const daten = await api.einstellungen();
        zustand.posten = daten.posten;
        zustand.werte = daten.werte;
        zustand.geladen = true;
      } catch {
        // Ohne Einstellungen läuft die Seite mit Vorgaben weiter.
        zustand.geladen = true;
      }
    },

    /** Sofort anzeigen, im Hintergrund speichern: kein Speichern-Knopf. */
    async setzen(key: string, wert: string) {
      const vorher = zustand.werte[key];
      zustand.werte = { ...zustand.werte, [key]: wert };

      try {
        await api.einstellungSetzen(key, wert);
        return true;
      } catch {
        // Server hat abgelehnt: zurückdrehen, sonst zeigt die Oberfläche
        // etwas an, was nicht gespeichert ist.
        zustand.werte = { ...zustand.werte, [key]: vorher };
        return false;
      }
    },
  };
}

export const einstellungen = erstelleEinstellungen();

/**
 * Die zwei Blätter, die von überall aufgehen: Schnelleingabe und Suche.
 *
 * Ein Schalter für Leiste, Seitenleiste und Tastatur, sonst hätte jede
 * Stelle ihr eigenes offen/zu.
 */
function erstelleBlaetter() {
  let schnell = $state(false);
  let suche = $state(false);

  return {
    get schnell() {
      return schnell;
    },
    get suche() {
      return suche;
    },
    schnellOeffnen() {
      suche = false;
      schnell = true;
    },
    sucheOeffnen() {
      schnell = false;
      suche = true;
    },
    schliessen() {
      schnell = false;
      suche = false;
    },
  };
}

export const blaetter = erstelleBlaetter();
