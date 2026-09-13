<script lang="ts">
  /**
   * Über Mia OS: Version, Änderungsverlauf, Zahlen, Datenquellen.
   *
   * Die Zahlen kommen aus der echten Datenbank, nicht aus einer gepflegten
   * Liste: eine Aufzählung, die von Hand aktuell gehalten werden muss, ist
   * nach zwei Wochen falsch.
   *
   * Bewusst keine Namen, nur Anzahlen. Auf einer Seite über die Anwendung
   * haben Dokumenttitel und Eintragstexte nichts verloren, dieselbe Regel
   * wie auf der Startseite.
   */
  import { onMount } from "svelte";
  import { slide } from "svelte/transition";
  import { api } from "../lib/api";
  import type { UeberDaten } from "../lib/types";
  import Seitenkopf from "../komponenten/Seitenkopf.svelte";
  import Abschnitt from "../komponenten/Abschnitt.svelte";
  import Ladezustand from "../komponenten/Ladezustand.svelte";
  import Fehlerhinweis from "../komponenten/Fehlerhinweis.svelte";
  import Symbol from "../komponenten/Symbol.svelte";

  let daten = $state<UeberDaten | null>(null);
  let fehler = $state("");
  let offen = $state<string | null>(null);
  let alleZeigen = $state(false);

  // 12 reicht für den Überblick. Alles auf einmal wären hier fast hundert
  // Einträge, und die letzten drei Tage sind das, was jemanden interessiert.
  const ANFANGS = 12;

  onMount(async () => {
    try {
      daten = await api.ueber();
    } catch (e) {
      fehler = e instanceof Error ? e.message : "Konnte die Angaben nicht laden.";
    }
  });

  const sichtbar = $derived(
    daten ? (alleZeigen ? daten.changelog : daten.changelog.slice(0, ANFANGS)) : [],
  );

  /** "2026-09-09" wird "9. Sept." — im Verlauf zählt der Tag, nicht das Jahr. */
  const kurzDatum = (iso: string) => {
    if (!iso) return "";
    const d = new Date(iso);
    return Number.isNaN(d.getTime())
      ? iso
      : d.toLocaleDateString("de-DE", { day: "numeric", month: "short" });
  };

  /**
   * Dasselbe ohne den abschließenden Punkt der Monatsabkürzung.
   *
   * Nur für Datumsangaben mitten im Satz: "seit 5. Sept.." hat sonst zwei
   * Punkte am Ende. In der Tagesüberschrift steht der Punkt dagegen richtig,
   * dort steht das Datum für sich.
   */
  const imSatz = (iso: string) => kurzDatum(iso).replace(/\.$/, "");

  /** Einträge nach Tag bündeln, damit die Liste eine Struktur bekommt. */
  const nachTag = $derived.by(() => {
    const raus = new Map<string, typeof sichtbar>();
    for (const e of sichtbar) {
      if (!raus.has(e.datum)) raus.set(e.datum, []);
      raus.get(e.datum)!.push(e);
    }
    return [...raus.entries()];
  });
</script>

<Seitenkopf titel="Über Mia OS" untertitel="Was drin ist, was sich geändert hat, woher die Daten kommen." />

{#if fehler}
  <Fehlerhinweis text={fehler} />
{:else if !daten}
  <Ladezustand />
{:else}
  <!-- Version. Das Wichtigste zuerst und groß genug, um es vorzulesen,
       wenn mal etwas nicht stimmt. -->
  <div class="karte mb-4 px-4 py-5 text-center">
    <p class="m-0 text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-leise">
      Version
    </p>
    <p class="ziffern anzeige m-0 mt-1 text-[2rem] leading-none">{daten.version}</p>
    <p class="m-0 mt-2 text-xs text-gedaempft">
      {#if daten.commit}
        Stand {daten.commit}{#if daten.gebaut_am}, {imSatz(daten.gebaut_am)}{/if}
      {:else}
        Kein Build-Stand hinterlegt
      {/if}
      {#if daten.laufzeit}
        · läuft {daten.laufzeit}
      {/if}
    </p>
  </div>

  <!-- Zahlen aus dem echten Bestand. -->
  <div class="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
    {#each daten.zahlen as z (z.titel)}
      <div class="karte px-3 py-3 text-center">
        <p class="ziffern m-0 text-[1.375rem] leading-none">{z.wert}</p>
        <p class="m-0 mt-1 text-xs text-gedaempft">{z.titel}</p>
      </div>
    {/each}
  </div>

  <Abschnitt titel="Datenquellen">
    {#each daten.quellen as q (q.name)}
      <!-- Fehlertexte sind mal drei Wörter, mal ein halber Stacktrace.
           Deshalb untereinander statt nebeneinander: eine lange Meldung hat
           sonst den Namen der Quelle zusammengequetscht. -->
      <div class="border-b border-linie-weich px-3.5 py-2.5 last:border-0">
        <div class="flex items-center gap-3">
          <span
            class="size-2 shrink-0 rounded-full"
            class:bg-gut={q.ok}
            class:bg-fehler={!q.ok}
          ></span>
          <span class="flex-1 text-[0.9375rem] capitalize">{q.name}</span>
          <span class="shrink-0 text-xs" class:text-fehler={!q.ok} class:text-gedaempft={q.ok}>
            {q.ok ? "läuft" : "Fehler"}
          </span>
        </div>
        {#if !q.ok && q.fehler}
          <p class="m-0 mt-1 break-words pl-5 text-xs leading-snug text-gedaempft">
            {q.fehler}
          </p>
        {/if}
      </div>
    {:else}
      <p class="m-0 px-3.5 py-3 text-sm text-gedaempft">Noch kein Sammellauf gelaufen.</p>
    {/each}
  </Abschnitt>

  <!-- Änderungsverlauf. Nach Tag gebündelt, der Text zum Warum klappt auf. -->
  <Abschnitt titel="Was sich geändert hat">
    {#each nachTag as [tag, eintraege] (tag)}
      <div class="border-b border-linie-weich last:border-0">
        <p
          class="m-0 bg-erhoben/40 px-3.5 py-1.5 text-[0.6875rem] font-semibold uppercase
                 tracking-[0.06em] text-gedaempft"
        >
          {kurzDatum(tag)}
        </p>
        {#each eintraege as e (e.sha)}
          <div class="border-t border-linie-weich first:border-0">
            <button
              type="button"
              onclick={() => (offen = offen === e.sha ? null : e.sha)}
              disabled={!e.text}
              class="flex w-full items-start gap-2.5 px-3.5 py-2.5 text-left transition-colors
                     hover:bg-erhoben disabled:hover:bg-transparent"
            >
              <!-- Ein Punkt statt eines Wortes: "neu" und "fix" nebeneinander
                   gelesen sind Rauschen, die Farbe reicht zum Überfliegen. -->
              <span
                class="mt-1.5 size-1.5 shrink-0 rounded-full"
                class:bg-akzent={e.art === "neu"}
                class:bg-achtung={e.art === "fix"}
                title={e.art === "fix" ? "Fehler behoben" : "Neu"}
              ></span>
              <span class="min-w-0 flex-1 text-[0.9375rem] leading-snug">{e.titel}</span>
              {#if e.text}
                <span
                  class="mt-0.5 shrink-0 text-leise transition-transform duration-200"
                  class:rotate-180={offen === e.sha}
                >
                  <Symbol name="chevron-down" groesse={14} />
                </span>
              {/if}
            </button>

            {#if offen === e.sha && e.text}
              <!-- Das Warum, so wie es beim Bauen aufgeschrieben wurde.
                   whitespace-pre-line, weil die Absätze die Erklärung tragen. -->
              <p
                class="m-0 whitespace-pre-line px-3.5 pb-3 pl-8 text-xs leading-relaxed text-gedaempft"
                transition:slide={{ duration: 180 }}
              >
                {e.text}
              </p>
            {/if}
          </div>
        {/each}
      </div>
    {/each}
  </Abschnitt>

  {#if daten.changelog.length > ANFANGS}
    <button
      type="button"
      onclick={() => (alleZeigen = !alleZeigen)}
      class="mx-auto mt-3 flex items-center gap-1.5 text-sm text-gedaempft transition-colors
             hover:text-text"
    >
      <span class="transition-transform duration-200" class:rotate-180={alleZeigen}>
        <Symbol name="chevron-down" groesse={14} />
      </span>
      {alleZeigen ? "Weniger" : `Alle ${daten.changelog.length} anzeigen`}
    </button>
  {/if}

  <p class="mb-2 mt-6 text-center text-xs leading-relaxed text-leise">
    Läuft im eigenen Netz, seit {imSatz(daten.seit)}.<br />
    Dokumente bleiben in Nextcloud, Mia OS merkt sich nur, wo sie liegen.
  </p>
{/if}
