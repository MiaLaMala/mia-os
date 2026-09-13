/**
 * Der Seitenbaum. Mias eigene Struktur, nicht meine feste Navigation.
 *
 * In Notion ist alles eine Seite und die Seitenleiste gehoert dem Nutzer.
 * Genau das hat gefehlt: vorher standen Übersicht, Termine und Sammlung
 * fest verdrahtet da und man konnte nichts eigenes anlegen.
 */

import { api } from "./api";
import type { Seite } from "./types";

/** Eine Seite mit ihren Kindern, fuer die Darstellung als Baum. */
export interface Baumknoten extends Seite {
  kinder: Baumknoten[];
  tiefe: number;
}

function erstelleSeiten() {
  let alle = $state<Seite[]>([]);
  let offen = $state<Set<number>>(new Set());
  let geladen = false;

  /** Aus der flachen Liste einen Baum bauen. */
  function baum(): Baumknoten[] {
    const nach = new Map<number, Baumknoten[]>();
    for (const s of alle) {
      const schluessel = s.parent_id ?? 0;
      if (!nach.has(schluessel)) nach.set(schluessel, []);
      nach.get(schluessel)!.push({ ...s, kinder: [], tiefe: 0 });
    }

    const bauen = (elternId: number, tiefe: number): Baumknoten[] =>
      (nach.get(elternId) ?? []).map((k: Baumknoten) => ({
        ...k,
        tiefe,
        kinder: bauen(k.id, tiefe + 1),
      }));

    return bauen(0, 0);
  }

  return {
    get alle() {
      return alle;
    },
    get baum() {
      return baum();
    },
    get offen() {
      return offen;
    },

    istOffen(id: number) {
      return offen.has(id);
    },

    umschalten(id: number) {
      const neu = new Set(offen);
      neu.has(id) ? neu.delete(id) : neu.add(id);
      offen = neu;
      localStorage.setItem("seiten-offen", JSON.stringify([...neu]));
    },

    async laden(erzwingen = false) {
      if (geladen && !erzwingen) return;
      try {
        alle = (await api.seiten()).seiten;
        geladen = true;
        // Welche Zweige aufgeklappt waren, ueberlebt den Seitenwechsel.
        const gemerkt = localStorage.getItem("seiten-offen");
        if (gemerkt) offen = new Set(JSON.parse(gemerkt) as number[]);
      } catch {
        // Ohne Seiten laeuft der Rest weiter.
      }
    },

    async anlegen(titel: string, parentId: number | null = null, hatSammlung = false) {
      const { seite } = await api.seiteAnlegen(titel, parentId, hatSammlung);
      alle = [...alle, seite];
      // Der neue Zweig soll sichtbar sein, sonst verschwindet die Seite.
      if (parentId) {
        const neu = new Set(offen);
        neu.add(parentId);
        offen = neu;
      }
      return seite;
    },

    async aendern(id: number, felder: Record<string, unknown>) {
      const vorher = alle;
      alle = alle.map((s) => (s.id === id ? { ...s, ...felder } : s));
      try {
        const { seite } = await api.seiteAendern(id, felder);
        alle = alle.map((s) => (s.id === id ? seite : s));
      } catch {
        alle = vorher;
      }
    },

    async loeschen(id: number) {
      // Unterseiten gehen mit: sonst haengen sie an einer Seite, die es
      // nicht mehr gibt, und verschwinden aus dem Baum.
      const weg = new Set<number>([id]);
      let gewachsen = true;
      while (gewachsen) {
        gewachsen = false;
        for (const s of alle) {
          if (s.parent_id && weg.has(s.parent_id) && !weg.has(s.id)) {
            weg.add(s.id);
            gewachsen = true;
          }
        }
      }

      const vorher = alle;
      alle = alle.filter((s) => !weg.has(s.id));
      try {
        await api.seiteLoeschen(id);
      } catch {
        alle = vorher;
      }
    },
  };
}

export const seiten = erstelleSeiten();
