/**
 * Die Sammlung: eine Datenbank, vier Ansichten.
 *
 * Das Notion-Modell. Kalender, Tabelle, Board und Liste greifen auf
 * DIESELBEN Zeilen zu und werden nur anders angeordnet. Deshalb liegt der
 * Zustand hier und nicht in den einzelnen Ansichten.
 */

import { api } from "./api";
import type { Eigenschaft, Eintrag, PropOption } from "./types";

function erstelleSammlung() {
  let eintraege = $state<Eintrag[]>([]);
  let eigenschaften = $state<Eigenschaft[]>([]);
  // Wie viele Dokumente an welchem Eintrag hängen. Nur die Zahl, nicht die
  // Dateien: die Liste soll keine Dateinamen aus dem Index zeigen.
  let anhaenge = $state<Record<string, number>>({});
  let laedt = $state(false);
  let fehler = $state("");
  let geladen = false;

  return {
    get eintraege() {
      return eintraege;
    },
    get eigenschaften() {
      return eigenschaften;
    },

    /** Wie viele Dokumente an einem Eintrag hängen. */
    anhangZahl(id: number): number {
      return anhaenge[String(id)] ?? 0;
    },
    get laedt() {
      return laedt;
    },
    get fehler() {
      return fehler;
    },

    /** Eine Eigenschaft anhand ihres Schluessels. */
    prop(key: string): Eigenschaft | undefined {
      return eigenschaften.find((p) => p.key === key);
    },

    /** Die Eintraege einer Seite uebernehmen, ohne selbst zu laden. */
    setzeEintraege(neue: Eintrag[], props: Eigenschaft[], zahlen: Record<string, number> = {}) {
      eintraege = neue;
      eigenschaften = props;
      anhaenge = zahlen;
      geladen = true;
    },

    async laden(erzwingen = false) {
      if (geladen && !erzwingen) return;
      laedt = true;
      try {
        const daten = await api.sammlung();
        eintraege = daten.eintraege;
        eigenschaften = daten.eigenschaften;
        anhaenge = daten.anhaenge ?? {};
        geladen = true;
        fehler = "";
      } catch (e) {
        fehler = e instanceof Error ? e.message : "Sammlung nicht erreichbar";
      } finally {
        laedt = false;
      }
    },

    async anlegen(felder: Partial<Eintrag> & { titel: string }) {
      const { eintrag } = await api.eintragAnlegen(felder);
      eintraege = [...eintraege, eintrag];
      return eintrag;
    },

    /** Einen Eintrag, der woanders angelegt wurde, in die Anzeige nehmen. */
    uebernehmen(eintrag: Eintrag) {
      if (eintraege.some((e) => e.id === eintrag.id)) return;
      eintraege = [...eintraege, eintrag];
    },

    /**
     * Aendern mit sofortiger Anzeige.
     *
     * Erst umschalten, dann sichern: sonst haengt jeder Klick 200
     * Millisekunden. Schlaegt es fehl, wird zurueckgedreht.
     */
    async aendern(id: number, felder: Record<string, unknown>) {
      const vorher = eintraege;
      eintraege = eintraege.map((e) => (e.id === id ? { ...e, ...felder } : e));
      try {
        const { eintrag } = await api.eintragAendern(id, felder);
        eintraege = eintraege.map((e) => (e.id === id ? eintrag : e));
      } catch {
        eintraege = vorher;
      }
    },

    /** Eine einzelne Eigenschaft setzen, ohne die anderen zu verlieren. */
    async setzeEigenschaft(id: number, key: string, wert: unknown) {
      const vorher = eintraege;
      eintraege = eintraege.map((e) => {
        if (e.id !== id) return e;
        const neue = { ...e.eigenschaften };
        if (wert === "" || wert === null) delete neue[key];
        else neue[key] = wert as string;
        return { ...e, eigenschaften: neue };
      });
      try {
        const { eintrag } = await api.eintragAendern(id, {
          eigenschaft: key,
          wert,
        });
        eintraege = eintraege.map((e) => (e.id === id ? eintrag : e));
      } catch {
        eintraege = vorher;
      }
    },

    async loeschen(id: number) {
      const vorher = eintraege;
      eintraege = eintraege.filter((e) => e.id !== id);
      try {
        await api.eintragLoeschen(id);
      } catch {
        eintraege = vorher;
      }
    },

    async eigenschaftAnlegen(name: string, art: string, optionen: unknown[] = []) {
      const daten = await api.eigenschaftAnlegen(name, art, optionen);
      eigenschaften = daten.eigenschaften;
    },
  };
}

export const sammlung = erstelleSammlung();

/** Farbnamen auf CSS-Werte. Die Oberflaeche entscheidet, wie Blau aussieht. */
export const FARBEN: Record<string, string> = {
  grau: "var(--color-gedaempft)",
  blau: "#0a84ff",
  gruen: "#30d158",
  gelb: "#ffd60a",
  rot: "#ff453a",
  lila: "#bf5af2",
  rosa: "#ff375f",
  orange: "#ff9f0a",
};

export function farbeVon(prop: Eigenschaft | undefined, wert: string): string {
  const treffer = prop?.optionen?.find((o: PropOption) => o.wert === wert);
  return FARBEN[treffer?.farbe ?? "grau"] ?? FARBEN.grau;
}
