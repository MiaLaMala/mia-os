/**
 * Typen, die das Backend liefert.
 *
 * Eine Stelle für die Form der Daten. Ändert sich das Backend, meckert der
 * Compiler an jeder betroffenen Komponente, statt dass es still bricht.
 */

/** Ein einzelner Wert auf einer Kachel: Zahl mit Einheit oder Text. */
export interface Wert {
  key: string;
  label: string;
  display: string | null;
  empty: boolean;
  /** Sätze statt Zahlen brauchen die kleinere Schriftstufe. */
  lang?: boolean;
  muted?: boolean;
  /** Richtung einer Veränderung. Beim Gewicht ist "down" das Gute. */
  trend?: "up" | "down" | null;
  items?: string[];
}

/** Eine Kategorie in Kartenform. */
export interface Kachel {
  key: string;
  title: string;
  icon: string;
  route: string;
  lead: Wert | null;
  caption: Wert | null;
  details: Wert[];
  has_data: boolean;
  /** Kategorien ohne Datenquelle, z.B. "bald". */
  geplant?: boolean;
}

/** Ein überwachter Dienst aus Uptime Kuma. */
export interface Dienst {
  name: string;
  status: number;
  meldung: string;
  uptime: number | null;
  ping: number | null;
}

export interface Lage {
  zustand: "oben" | "unten" | "unklar";
  satz: string;
  gesamt: number;
  oben: number;
  uptime: number | null;
}

/** Eine Kennzahl auf der Homelab-Seite. Andere Form als ein Kachel-Wert:
 *  label/wert/leit statt key/display. */
export interface Kennzahl {
  label: string;
  wert: string;
  leit: boolean;
}

export interface HomelabDaten {
  lage: Lage;
  stoerungen: Dienst[];
  dienste: Dienst[];
  kennzahlen: Kennzahl[];
  stand: string;
}

/** Ein Termin, in der Form die FullCalendar erwartet. */
export interface KalenderTermin {
  id: string;
  title: string;
  start: string;
  end?: string;
  allDay: boolean;
  /** Kalendername, für Farbe und Filter. */
  kalender: string;
  ort?: string;
  farbe: string;
  /** Haengt eine eigene Notiz dran? */
  hat_notiz?: boolean;
  /** Wie viele Aufgaben sind noch offen? */
  offene_aufgaben?: number;
  /** Gesetzt, wenn das ein eigener Sammlungseintrag ist statt iCloud. */
  eintrag_id?: number;
}

export interface Dokument {
  id: number;
  name: string;
  folder: string;
  ext: string;
  groesse: string;
  datum: string;
  quelle: string;
  eigene: boolean;
  bearbeitbar: boolean;
  anzeigbar: boolean;
  vorschau: string;
  link: string;
  path: string;
  /** Woher die Datei stammt: "nextcloud" oder "jana". Teil des Schlüssels. */
  source?: string;
  /** Liegt in einem Entpack-Ordner neben dem Original. */
  kopie?: boolean;
  /** An welchen Einträgen die Datei hängt. Leer, wenn an keinem. */
  eintraege?: EintragKurz[];
  /**
   * Die Fundstelle im gelesenen Text, mit `[` und `]` um die Treffer.
   *
   * Nur gesetzt, wenn der Suchbegriff *im Text* stand und nicht nur im Namen.
   * Es gibt sie ausschließlich bei selbst gescannten Belegen: für den Bestand
   * wird kein Text gespeichert.
   */
  stelle?: string;
  /** Ob überhaupt gelesener Text zu der Datei vorliegt. */
  hat_text?: boolean;
}

/** Ein Eintrag in Kurzform, wie er neben einem Dokument steht. */
export interface EintragKurz {
  id: number;
  titel: string;
  datum: string;
}

/**
 * Ein Dokument, das an einem Eintrag hängt.
 *
 * ``fehlt`` heißt: die Verknüpfung steht noch, die Datei ist aber nicht mehr
 * im Index. Dann gibt es weder Vorschau noch Editor-Link.
 */
export interface Anhang extends Dokument {
  source: string;
  fehlt: boolean;
}

/**
 * Wohin ein frisch abgelegter Beleg gehört, geschätzt aus den Dateinamen
 * der vorhandenen Ordner.
 *
 * ``abstand`` ist der Vorsprung vor dem zweitbesten Ordner und damit das
 * eigentliche Signal. Kommt gar kein Vorschlag, war der Abstand zu klein:
 * bei Gleichstand zwischen zwei Ordnern ist der beste Vorschlag keiner.
 */
export interface Ordnervorschlag {
  ordner: string;
  pfad: string;
  naehe: number;
  abstand: number;
}

/**
 * Wie ein frisch gescannter Beleg heißen könnte, gelesen von dem Blatt selbst.
 *
 * Aus dem OCR-Text zusammengesetzt aus Datum, Absender und Betreff, mit festen
 * Mustern statt einem Sprachmodell. ``null`` heißt: zu wenig erkannt, oder der
 * Vorschlag hieße genauso wie die Datei jetzt schon.
 */
export interface Namensvorschlag {
  pfad: string;
  name: string;
}

/** Ein Ordner in der Filterleiste. */
export interface OrdnerZaehler {
  top: string;
  n: number;
}

export interface DokumentSeite {
  treffer: Dokument[];
  gesamt: number;
  seite: number;
  seiten: number;
  ordner: OrdnerZaehler[];
}

/** Eine Einstellung, die Mia selbst ändern kann. */
export interface Einstellung {
  key: string;
  titel: string;
  hilfe: string;
  art: "schalter" | "zahl" | "auswahl";
  gruppe: string;
  vorgabe: string;
  minimum?: number;
  maximum?: number;
  optionen?: [string, string][];
}

/** Eine Aufgabe. Frei stehend oder an einem Termin. */
export interface Aufgabe {
  id: number;
  titel: string;
  erledigt: boolean;
  event_uid: string;
  faellig_am: string;
}

/** Eine Option in einem Auswahlfeld. */
export interface PropOption {
  wert: string;
  farbe: string;
}

/** Eine Spalte der Sammlung. Wie eine Notion-Eigenschaft. */
export interface Eigenschaft {
  key: string;
  name: string;
  art: "auswahl" | "mehrfach" | "text" | "zahl" | "datum" | "haken";
  optionen: PropOption[];
  sortierung: number;
}

/**
 * Ein Eintrag in der Sammlung. Das Herzstueck.
 *
 * Kalender, Tabelle, Board und Liste zeigen alle dieselben Eintraege, nur
 * anders angeordnet.
 */
export interface Eintrag {
  id: number;
  titel: string;
  inhalt: string;
  eigenschaften: Record<string, string>;
  /** Leer, wenn der Eintrag nicht im Kalender steht. */
  datum: string;
  zeit: string;
  event_uid: string;
  /** Auf welcher Seite der Eintrag liegt. 0 = Hauptsammlung. */
  page_id: number;
  archiviert: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * Eine Seite. Das Grundelement, wie in Notion.
 *
 * Sie kann Text tragen, eine Sammlung, Unterseiten, oder alles zusammen.
 */
export interface Seite {
  id: number;
  parent_id: number | null;
  titel: string;
  symbol: string;
  inhalt: string;
  hat_sammlung: boolean;
  /** Sammelseite: zeigt alle Einträge, egal wo sie liegen. "Alles" ist so eine. */
  sammelt_alles: boolean;
  ansicht: string;
  gruppe_nach: string;
  sortierung: number;
  created_at: string;
  updated_at: string;
}

/** Eine Zutat aus Mias wger. */
export interface Zutat {
  id: number;
  name: string;
  kcal: number;
  protein: number;
  kh: number;
  fett: number;
}

/** Eine Mahlzeit von heute. */
export interface Mahlzeit {
  id: string;
  name: string;
  gramm: number;
  kcal: number;
  zeit: string;
}

/** Was die Suche über alles zurückgibt. */
export interface Suchergebnis {
  seiten: { id: number; titel: string; symbol: string }[];
  eintraege: { id: number; titel: string; datum: string; page_id: number; status: string }[];
  termine: {
    id: string;
    titel: string;
    start: string;
    ganztags: boolean;
    kalender: string;
    farbe: string;
  }[];
  dokumente: { id: number; name: string; folder: string; ext: string; stelle?: string }[];
}

/** Antwort der Schnelleingabe. */
export type SchnellAntwort =
  | { art: "eintrag"; eintrag: Eintrag; meldung: string }
  | { art: "gewicht"; kg: number; meldung: string }
  | { art: "essen"; meldung: string }
  | { art: "essen_wahl"; gramm: number; zutaten: Zutat[] };

/** Ein Zeitblock im Berichtsheft, so wie er im Kalender steht. */
export interface BerichtsBlock {
  von: string;
  bis: string;
  titel: string;
  kalender: string;
  stunden: number;
}

/** Ein Tag im Wochenblatt. */
export interface BerichtsTag {
  datum: string;
  wochentag: string;
  art: string;
  stunden: number;
  schule_stunden: number;
  betrieb_stunden: number;
  taetigkeiten: string[];
  hinweise: string[];
  bloecke: BerichtsBlock[];
}

/** Ein Wochenblatt des Berichtshefts. */
export interface BerichtsWoche {
  montag: string;
  sonntag: string;
  kw: number;
  jahr: number;
  tage: BerichtsTag[];
  betrieb_stunden: number;
  schule_stunden: number;
  stunden: number;
  status: string;
  bemerkung: string;
  themen_schule: string;
}

/** Eine Zeile in der Wochenuebersicht. */
export interface BerichtsWochenZeile {
  montag: string;
  sonntag: string;
  kw: number;
  jahr: number;
  stunden: number;
  arbeitstage: number;
  status: string;
  gefuellte_tage: number;
  aktuell: boolean;
  /** False, wenn fuer die Woche gar keine Kalenderdaten vorliegen. */
  hat_daten: boolean;
}

/** Ein Eintrag im Änderungsverlauf, aus der Git-Historie erzeugt. */
export interface Aenderung {
  sha: string;
  datum: string;
  titel: string;
  /** Das Warum, mehrzeilig. Leer, wenn der Commit keinen Rumpf hatte. */
  text: string;
  art: "neu" | "fix";
}

export interface UeberDaten {
  version: string;
  commit: string;
  gebaut_am: string;
  commits: number;
  seit: string;
  laufzeit: string;
  changelog: Aenderung[];
  zahlen: { titel: string; wert: number }[];
  quellen: { name: string; ok: boolean; fehler: string; wann: string }[];
}

/**
 * Eine App, die sich gekoppelt hat.
 *
 * Ohne Schlüssel und ohne dessen Abdruck: die Liste geht an die Oberfläche,
 * und dort hat beides nichts zu suchen. Was Mia zum Aufräumen braucht, ist
 * der Name und wann das Gerät zuletzt da war.
 */
export interface GekoppeltesGeraet {
  id: number;
  name: string;
  /** `ios`, `ipados`, `macos`. Leer bei älteren Kopplungen. */
  plattform: string;
  erstellt_at: string;
  zuletzt_at: string;
  adresse: string;
}
