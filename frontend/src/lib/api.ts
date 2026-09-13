/**
 * Ein Ort für alle Serveraufrufe.
 *
 * Keine Komponente ruft fetch selbst auf: sonst liegt die Fehlerbehandlung
 * verstreut und jede Seite erfindet ihre eigene Ladeanzeige.
 */

import type {
  Aufgabe,
  Eigenschaft,
  Eintrag,
  Seite,
  Einstellung,
  HomelabDaten,
  Kachel,
  KalenderTermin,
  Anhang,
  Dokument,
  DokumentSeite,
  Ordnervorschlag,
  Namensvorschlag,
  Zutat,
  Mahlzeit,
  Suchergebnis,
  SchnellAntwort,
  BerichtsWoche,
  BerichtsWochenZeile,
  UeberDaten,
  GekoppeltesGeraet,
} from "./types";

class ApiFehler extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiFehler";
  }
}

async function hole<T>(pfad: string, optionen?: RequestInit): Promise<T> {
  const antwort = await fetch(pfad, {
    headers: { "content-type": "application/json" },
    ...optionen,
  });

  if (!antwort.ok) {
    // Der Text ist oft hilfreicher als der Status allein.
    const text = await antwort.text().catch(() => "");
    throw new ApiFehler(text.slice(0, 200) || antwort.statusText, antwort.status);
  }

  return (await antwort.json()) as T;
}

/** Schreibender Aufruf. Wirft bei Fehlern, damit die Oberflaeche zurueckdrehen kann. */
async function senden<T>(pfad: string, art: string, koerper?: unknown): Promise<T> {
  const antwort = await fetch(pfad, {
    method: art,
    headers: koerper ? { "Content-Type": "application/json" } : undefined,
    body: koerper ? JSON.stringify(koerper) : undefined,
  });
  if (!antwort.ok) {
    const text = await antwort.text().catch(() => "");
    throw new Error(text.slice(0, 120) || `Fehler ${antwort.status}`);
  }
  return antwort.json() as Promise<T>;
}

/**
 * Aus einer fehlgeschlagenen Antwort einen lesbaren Fehler machen.
 *
 * Der Server schickt seinen Grund im detail-Feld ("größer als 25 MB",
 * "kein Bild und kein PDF"). Genau der gehört Mia gezeigt, nicht "400".
 */
async function fehlerAus(antwort: Response): Promise<ApiFehler> {
  const text = await antwort.text().catch(() => "");
  let grund = text.slice(0, 200);
  try {
    grund = (JSON.parse(text) as { detail?: string }).detail ?? grund;
  } catch {
    // Kein JSON: dann steht der Rohtext da, das ist besser als nichts.
  }
  return new ApiFehler(grund || antwort.statusText, antwort.status);
}

export const api = {
  uebersicht: () => hole<{ kacheln: Kachel[]; stand: string }>("/api/uebersicht"),

  kategorie: (schluessel: string) => hole<Kachel>(`/api/categories/${schluessel}`),

  homelab: () => hole<HomelabDaten>("/api/homelab"),

  termine: (von: string, bis: string, kalender?: string) => {
    const p = new URLSearchParams({ von, bis });
    if (kalender) p.set("kalender", kalender);
    return hole<{
      termine: KalenderTermin[];
      kalender: string[];
      aufgaben_je_tag: Record<string, number>;
    }>(`/api/termine?${p}`);
  },

  dokumente: (suche = "", ordner = "", seite = 1) => {
    const p = new URLSearchParams({ seite: String(seite) });
    if (suche) p.set("q", suche);
    if (ordner) p.set("ordner", ordner);
    return hole<DokumentSeite>(`/api/dokumente?${p}`);
  },

  dokument: (id: number) => hole<Dokument>(`/api/documents/${id}`),

  gesundheit: () =>
    hole<{ karte: Kachel; verlauf: { collected_at: string; value: number }[]; stand: string }>(
      "/api/gesundheit",
    ),

  // --- Seiten: Mias eigener Baum ---

  seiten: () => hole<{ seiten: Seite[] }>("/api/seiten"),

  seite: (id: number) =>
    hole<{
      seite: Seite;
      weg: { id: number; titel: string }[];
      unterseiten: Seite[];
      eintraege: Eintrag[];
      eigenschaften: Eigenschaft[];
      seitentitel: Record<string, string>;
      anhaenge: Record<string, number>;
    }>(`/api/seiten/${id}`),

  seiteAnlegen: (titel: string, parentId: number | null = null, hatSammlung = false) =>
    senden<{ seite: Seite }>("/api/seiten", "POST", {
      titel,
      parent_id: parentId,
      hat_sammlung: hatSammlung,
    }),

  seiteAendern: (id: number, felder: Record<string, unknown>) =>
    senden<{ seite: Seite }>(`/api/seiten/${id}`, "PATCH", felder),

  seiteLoeschen: (id: number) => senden<{ ok: boolean }>(`/api/seiten/${id}`, "DELETE"),

  // --- Die Sammlung: eine Datenbank, vier Ansichten ---

  sammlung: (von = "", bis = "", suche = "") => {
    const p = new URLSearchParams();
    if (von) p.set("von", von);
    if (bis) p.set("bis", bis);
    if (suche) p.set("suche", suche);
    return hole<{
      eintraege: Eintrag[];
      eigenschaften: Eigenschaft[];
      anhaenge: Record<string, number>;
    }>(`/api/sammlung?${p}`);
  },

  eintragAnlegen: (felder: Record<string, unknown>) =>
    senden<{ eintrag: Eintrag }>("/api/sammlung", "POST", felder),

  eintragAendern: (id: number, felder: Record<string, unknown>) =>
    senden<{ eintrag: Eintrag }>(`/api/sammlung/${id}`, "PATCH", felder),

  eintragLoeschen: (id: number) => senden<{ ok: boolean }>(`/api/sammlung/${id}`, "DELETE"),

  // --- Dokumente an Einträgen ---

  anhaenge: (entryId: number) =>
    hole<{ dokumente: Anhang[] }>(`/api/sammlung/${entryId}/dokumente`),

  anhaengen: (entryId: number, dokumentId: number) =>
    senden<{ dokumente: Anhang[] }>(`/api/sammlung/${entryId}/dokumente`, "POST", {
      dokument_id: dokumentId,
    }),

  /**
   * Ein Foto oder PDF hochladen: landet in Nextcloud und hängt sofort dran.
   *
   * Kein JSON, sondern FormData. Wichtig: den Content-Type NICHT selbst
   * setzen. Der Browser hängt die multipart-Grenze an den Header, und wer
   * ihn von Hand schreibt, liefert sie nicht mit: der Server sieht dann
   * einen leeren Rumpf und antwortet mit 422.
   */
  belegHochladen: async (
    entryId: number,
    datei: File,
    scan?: { staerke: string; ecken: string },
  ) => {
    const formular = new FormData();
    formular.append("datei", datei);
    if (scan) {
      formular.append("scannen", "true");
      formular.append("staerke", scan.staerke);
      formular.append("ecken", scan.ecken);
    }
    const antwort = await fetch(`/api/sammlung/${entryId}/beleg`, {
      method: "POST",
      body: formular,
    });
    if (!antwort.ok) throw await fehlerAus(antwort);
    // ``ocr_zeichen`` sagt, wie viel Text aus dem Blatt gelesen wurde. 0 heißt
    // entweder nicht gescannt oder nichts erkannt, beides ist kein Fehler.
    //
    // ``vorschlag`` ist null, wenn kein Ordner klar genug passt. Das ist der
    // Normalfall und keine Fehlfunktion: bei knappem Abstand zwischen zwei
    // Ordnern ist der beste Vorschlag keiner.
    return (await antwort.json()) as {
      dokumente: Anhang[];
      ocr_zeichen: number;
      vorschlag: Ordnervorschlag | null;
      namensvorschlag: Namensvorschlag | null;
    };
  },

  /**
   * Einen Beleg in einen anderen Ordner schieben.
   *
   * Nur Dateien aus dem Belegordner: Mia OS legt dort ab und darf dort
   * aufräumen, Mias gewachsene Ablage bleibt sonst unangetastet.
   */
  dokumentVerschieben: async (pfad: string, ordner: string) => {
    const antwort = await fetch("/api/dokumente/verschieben", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pfad, ordner }),
    });
    if (!antwort.ok) throw await fehlerAus(antwort);
    return (await antwort.json()) as { ok: boolean; pfad: string; ordner: string };
  },

  /**
   * Einen Beleg umbenennen, auf den Namen der vom Blatt gelesen wurde.
   *
   * Dieselbe Grenze wie beim Verschieben: nur der Belegordner. Die Endung
   * bleibt so, wie sie beim Hochladen aus dem Dateikopf bestimmt wurde.
   */
  dokumentUmbenennen: async (pfad: string, name: string) => {
    const antwort = await fetch("/api/dokumente/umbenennen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pfad, name }),
    });
    if (!antwort.ok) throw await fehlerAus(antwort);
    return (await antwort.json()) as { ok: boolean; pfad: string; name: string };
  },

  /**
   * Ein Foto aufbereiten und zurückzeigen, ohne etwas zu speichern.
   *
   * Zwei Schritte statt einem, weil die Kantenerkennung scheitern darf:
   * weißes Blatt auf hellem Tisch, geknicktes Papier, schlechtes Licht.
   * Mia sieht das Ergebnis, bevor irgendwas nach Nextcloud geht.
   */
  scanVorschau: async (datei: File, staerke = "weich", ecken = "") => {
    const formular = new FormData();
    formular.append("datei", datei);
    formular.append("staerke", staerke);
    formular.append("ecken", ecken);
    const antwort = await fetch("/api/scan/vorschau", { method: "POST", body: formular });
    if (!antwort.ok) throw await fehlerAus(antwort);
    return (await antwort.json()) as {
      bild: string;
      ecken: [number, number][] | null;
      automatisch: boolean;
      breite: number;
      hoehe: number;
    };
  },

  // Gelöst wird über Quelle und Pfad, nicht über die Index-ID: eine
  // verschwundene Datei muss sich auch dann noch abhängen lassen.
  anhangLoesen: (entryId: number, source: string, path: string) => {
    const p = new URLSearchParams({ source, path });
    return senden<{ ok: boolean }>(`/api/sammlung/${entryId}/dokumente?${p}`, "DELETE");
  },

  eigenschaftAnlegen: (name: string, art: string, optionen: unknown[] = []) =>
    senden<{ eigenschaften: Eigenschaft[] }>("/api/eigenschaften", "POST", {
      name,
      art,
      optionen,
    }),

  terminDetails: (uid: string) =>
    hole<{ uid: string; notiz: string; aufgaben: Aufgabe[] }>(
      `/api/termin/${encodeURIComponent(uid)}`,
    ),

  notizSichern: (uid: string, notiz: string) =>
    senden<{ ok: boolean }>(`/api/termin/${encodeURIComponent(uid)}/notiz`, "PUT", { notiz }),

  aufgaben: (nurOffen = false, nurFreie = false) =>
    hole<{ aufgaben: Aufgabe[]; offen: number }>(
      `/api/aufgaben?offen=${nurOffen}&frei=${nurFreie}`,
    ),

  aufgabeAnlegen: (titel: string, eventUid = "", faelligAm = "") =>
    senden<{ aufgabe: Aufgabe }>("/api/aufgaben", "POST", {
      titel,
      event_uid: eventUid,
      faellig_am: faelligAm,
    }),

  aufgabeAendern: (id: number, felder: Partial<{ titel: string; erledigt: boolean; faellig_am: string }>) =>
    senden<{ ok: boolean }>(`/api/aufgaben/${id}`, "PATCH", felder),

  aufgabeLoeschen: (id: number) => senden<{ ok: boolean }>(`/api/aufgaben/${id}`, "DELETE"),

  einstellungen: () => hole<{ posten: Einstellung[]; werte: Record<string, string> }>(
    "/api/einstellungen",
  ),

  einstellungSetzen: (key: string, wert: string) =>
    hole<{ ok: boolean; key: string; wert: string }>("/api/einstellungen", {
      method: "POST",
      body: JSON.stringify({ key, wert }),
    }),

  sammeln: () => hole<Record<string, boolean>>("/api/collect", { method: "POST" }),

  // --- Schnelleingabe und Suche ---

  schnell: (text: string, pageId = 0) =>
    senden<SchnellAntwort>("/api/schnell", "POST", { text, page_id: pageId }),

  suche: (q: string) => hole<Suchergebnis>(`/api/suche?q=${encodeURIComponent(q)}`),

  // --- Gesundheit schreiben ---

  gewichtSetzen: (kg: number, datum = "") =>
    senden<{ ok: boolean; kg: number }>("/api/gesundheit/gewicht", "POST", { kg, datum }),

  zutaten: (q = "") => hole<{ zutaten: Zutat[] }>(`/api/gesundheit/zutaten?q=${encodeURIComponent(q)}`),

  gegessenHeute: () => hole<{ eintraege: Mahlzeit[]; kcal: number }>("/api/gesundheit/heute"),

  essenSetzen: (zutatId: number, gramm: number) =>
    senden<{ ok: boolean }>("/api/gesundheit/essen", "POST", { zutat_id: zutatId, gramm }),

  // --- Berichtsheft ---

  berichtsheft: (montag = "") =>
    hole<BerichtsWoche>(`/api/berichtsheft${montag ? `?montag=${montag}` : ""}`),

  berichtsheftWochen: (anzahl = 12) =>
    hole<{ wochen: BerichtsWochenZeile[]; diese_woche: string }>(
      `/api/berichtsheft/wochen?anzahl=${anzahl}`,
    ),

  berichtsheftSichern: (montag: string, felder: Record<string, unknown>) =>
    senden<BerichtsWoche>("/api/berichtsheft", "POST", { montag, ...felder }),

  // --- Über Mia OS ---

  ueber: () => hole<UeberDaten>("/api/ueber"),

  /** Apps: einen Kopplungscode erzeugen. Gilt zehn Minuten, genau einmal. */
  kopplungscode: () => senden<{ code: string; gilt_bis: string }>("/api/kopplung/code", "POST"),

  /** Welche Apps gekoppelt sind. Ohne Schluessel und ohne Abdruck. */
  gekoppelteGeraete: () => hole<{ geraete: GekoppeltesGeraet[] }>("/api/kopplung/geraete"),

  /** Eine App abmelden. Ihr Schluessel gilt ab dem naechsten Aufruf nicht mehr. */
  geraetAbmelden: (id: number) => senden<{ ok: boolean }>(`/api/kopplung/geraete/${id}`, "DELETE"),
};

export { ApiFehler };
