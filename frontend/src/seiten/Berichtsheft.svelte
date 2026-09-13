<script lang="ts">
  /**
   * Berichtsheft: das Wochenblatt.
   *
   * Der Entwurf kommt aus dem Kalender, Mia schreibt nur noch dazu, was sie
   * gemacht hat. Tage, Stunden und Hinweise stehen schon da.
   *
   * Bewusst kein Vorschlagstext in den Tätigkeitsfeldern: der Kalender weiß,
   * WANN sie gearbeitet hat, nicht WAS sie gemacht hat. Ein erfundener Satz
   * im Ausbildungsnachweis wäre schlimmer als ein leeres Feld.
   */
  import { onMount } from "svelte";
  import { api } from "../lib/api";
  import type { BerichtsWoche, BerichtsWochenZeile } from "../lib/types";
  import Seitenkopf from "../komponenten/Seitenkopf.svelte";
  import Abschnitt from "../komponenten/Abschnitt.svelte";
  import Knopf from "../komponenten/Knopf.svelte";
  import Ladezustand from "../komponenten/Ladezustand.svelte";
  import Fehlerhinweis from "../komponenten/Fehlerhinweis.svelte";
  import Symbol from "../komponenten/Symbol.svelte";

  let woche = $state<BerichtsWoche | null>(null);
  let wochen = $state<BerichtsWochenZeile[]>([]);
  let montag = $state("");
  let laedt = $state(true);
  let fehler = $state("");
  let meldung = $state("");
  let listeOffen = $state(false);
  let sichertGerade = $state(false);
  let sicherTimer: ReturnType<typeof setTimeout>;

  const ART_TEXT: Record<string, string> = {
    betrieb: "Betrieb",
    schule: "Berufsschule",
    "schule+betrieb": "Schule und Betrieb",
    krank: "Krank",
    urlaub: "Urlaub",
    feiertag: "Feiertag",
    frei: "Frei",
  };

  const STATUS_TEXT: Record<string, string> = {
    entwurf: "Entwurf",
    bearbeitet: "In Arbeit",
    fertig: "Fertig",
  };

  const arbeitstage = $derived(woche ? woche.tage.filter((t) => t.stunden > 0) : []);
  const offeneTage = $derived(
    arbeitstage.filter((t) => !t.taetigkeiten.some((z) => z.trim())).length,
  );

  function stundentext(h: number): string {
    return h.toFixed(2).replace(/\.?0+$/, "").replace(".", ",") + " h";
  }

  function tagestext(iso: string): string {
    return new Date(iso + "T12:00:00").toLocaleDateString("de-DE", {
      day: "numeric",
      month: "short",
    });
  }

  function spannetext(w: { montag: string; sonntag: string }): string {
    return `${tagestext(w.montag)} bis ${tagestext(w.sonntag)}`;
  }

  async function laden(ziel = "") {
    laedt = true;
    fehler = "";
    try {
      woche = await api.berichtsheft(ziel);
      montag = woche.montag;
    } catch (e) {
      fehler = e instanceof Error ? e.message : "Berichtsheft nicht erreichbar";
    } finally {
      laedt = false;
    }
  }

  async function listeLaden() {
    try {
      wochen = (await api.berichtsheftWochen(12)).wochen;
    } catch {
      // Ohne Liste bleibt das Blatt bedienbar.
    }
  }

  /** Speichert verzögert, damit nicht jeder Tastendruck einen Aufruf macht. */
  function spaeterSichern(felder: Record<string, unknown>) {
    clearTimeout(sicherTimer);
    sicherTimer = setTimeout(() => void sichern(felder), 600);
  }

  async function sichern(felder: Record<string, unknown>) {
    if (!woche) return;
    sichertGerade = true;
    try {
      // Der Status springt beim ersten Tippen von selbst auf "in Arbeit":
      // sonst müsste Mia daran denken, und das ist genau die Sorte Pflicht,
      // die liegen bleibt.
      const status = woche.status === "entwurf" ? "bearbeitet" : undefined;
      const antwort = await api.berichtsheftSichern(woche.montag, {
        ...felder,
        ...(status ? { status } : {}),
      });
      woche.status = antwort.status;
      meldung = "Gesichert";
      setTimeout(() => (meldung = ""), 1400);
      void listeLaden();
    } catch (e) {
      meldung = e instanceof Error ? e.message : "Konnte nicht sichern";
    } finally {
      sichertGerade = false;
    }
  }

  function tagGetippt(datum: string, text: string) {
    if (!woche) return;
    const tag = woche.tage.find((t) => t.datum === datum);
    if (!tag) return;
    tag.taetigkeiten = text.split("\n");
    spaeterSichern({
      inhalt: { [datum]: { taetigkeiten: tag.taetigkeiten, stunden: tag.stunden, art: tag.art } },
    });
  }

  function hinweisUebernehmen(datum: string, text: string) {
    if (!woche) return;
    const tag = woche.tage.find((t) => t.datum === datum);
    if (!tag) return;
    const vorhanden = tag.taetigkeiten.filter((z) => z.trim());
    if (vorhanden.includes(text)) return;
    tag.taetigkeiten = [...vorhanden, text];
    spaeterSichern({
      inhalt: { [datum]: { taetigkeiten: tag.taetigkeiten, stunden: tag.stunden, art: tag.art } },
    });
  }

  async function statusSetzen(neu: string) {
    if (!woche) return;
    woche.status = neu;
    await sichern({ status: neu });
  }

  function blaettern(schritte: number) {
    if (!woche) return;
    const d = new Date(woche.montag + "T12:00:00");
    d.setDate(d.getDate() + schritte * 7);
    void laden(d.toISOString().slice(0, 10));
  }

  onMount(() => {
    void laden();
    void listeLaden();
  });
</script>

<Seitenkopf
  titel="Berichtsheft"
  ueberzeile={woche ? `KW ${woche.kw}` : ""}
  untertitel={woche ? spannetext(woche) : "Wochenblatt aus dem Kalender"}
>
  {#snippet werkzeuge()}
    <Knopf symbol="chevron-left" beschriftung="Woche zurück" klick={() => blaettern(-1)} />
    <Knopf symbol="chevron-right" beschriftung="Woche vor" klick={() => blaettern(1)} />
    <Knopf
      symbol="list"
      beschriftung="Alle Wochen"
      aktiv={listeOffen}
      klick={() => (listeOffen = !listeOffen)}
    />
  {/snippet}
</Seitenkopf>

{#if fehler}
  <Fehlerhinweis text={fehler} />
{/if}

{#if listeOffen}
  <Abschnitt titel="Wochen">
    <ul class="m-0 list-none p-0">
      {#each wochen as w (w.montag)}
        <li>
          <button
            type="button"
            onclick={() => {
              listeOffen = false;
              void laden(w.montag);
            }}
            class="flex w-full items-center gap-3 border-b border-linie-weich px-3.5 py-2.5
                   text-left transition-colors last:border-0 hover:bg-erhoben"
            class:bg-erhoben={w.montag === montag}
          >
            <span class="ziffern w-14 shrink-0 text-[0.9375rem]">KW {w.kw}</span>
            <span class="min-w-0 flex-1 truncate text-sm text-gedaempft">{spannetext(w)}</span>
            {#if w.hat_daten}
              <span class="ziffern shrink-0 text-xs text-gedaempft">{stundentext(w.stunden)}</span>
              <span
                class="shrink-0 rounded-full px-2 py-0.5 text-[0.6875rem] font-medium"
                class:bg-erhoben-2={w.status !== "fertig"}
                class:text-gedaempft={w.status !== "fertig"}
                class:text-gut={w.status === "fertig"}
                style={w.status === "fertig"
                  ? "background: color-mix(in srgb, currentColor 15%, transparent)"
                  : ""}
              >
                {STATUS_TEXT[w.status] ?? w.status}
              </span>
            {:else}
              <!-- Der Kalender reicht nur 45 Tage zurueck. "0 h" waere hier
                   eine falsche Aussage, keine fehlende. -->
              <span class="shrink-0 text-[0.6875rem] text-leise">keine Kalenderdaten</span>
            {/if}
          </button>
        </li>
      {/each}
    </ul>
  </Abschnitt>
{/if}

{#if laedt}
  <Ladezustand />
{:else if woche && !listeOffen}
  <!-- Svelte verengt den Typ in Callbacks nicht: eine lokale Konstante tut es. -->
  {@const w = woche}
  <!-- Die Zahlen der Woche -->
  <div class="karte mb-6 flex flex-wrap items-baseline gap-x-8 gap-y-3 px-5 py-4">
    <div>
      <p class="m-0 text-[0.6875rem] font-medium uppercase tracking-[0.08em] text-leise">Gesamt</p>
      <p class="anzeige ziffern m-0 mt-1 text-[2rem] leading-none">{stundentext(woche.stunden)}</p>
    </div>
    <div>
      <p class="m-0 text-[0.6875rem] font-medium uppercase tracking-[0.08em] text-leise">Betrieb</p>
      <p class="ziffern m-0 mt-1 text-[1.125rem]">{stundentext(woche.betrieb_stunden)}</p>
    </div>
    <div>
      <p class="m-0 text-[0.6875rem] font-medium uppercase tracking-[0.08em] text-leise">Schule</p>
      <p class="ziffern m-0 mt-1 text-[1.125rem]">{stundentext(woche.schule_stunden)}</p>
    </div>
    <div class="ml-auto flex items-center gap-2 text-sm">
      {#if meldung}
        <span class="text-gedaempft">{meldung}</span>
      {:else if offeneTage}
        <span class="text-gedaempft">
          {offeneTage} von {arbeitstage.length}
          {offeneTage === 1 ? "Tag offen" : "Tagen offen"}
        </span>
      {:else if arbeitstage.length}
        <span class="text-gut">Alle Tage ausgefüllt</span>
      {/if}
      <button
        type="button"
        onclick={() => statusSetzen(w.status === "fertig" ? "bearbeitet" : "fertig")}
        disabled={sichertGerade}
        class="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[0.8125rem] font-medium
               transition-[background,color] duration-200 ease-ruhig disabled:opacity-40"
        class:bg-akzent={woche.status !== "fertig"}
        class:text-akzent-text={woche.status !== "fertig"}
        class:bg-erhoben={woche.status === "fertig"}
        class:text-gedaempft={woche.status === "fertig"}
      >
        {#if woche.status === "fertig"}
          <Symbol name="check" groesse={14} />
          Fertig
        {:else}
          Als fertig markieren
        {/if}
      </button>
    </div>
  </div>

  <!-- Die Tage -->
  <Abschnitt titel="Tätigkeiten">
    <ul class="m-0 list-none p-0">
      {#each woche.tage as tag (tag.datum)}
        <!-- Freie Tage weglassen: eine Zeile "Frei" ohne Inhalt ist nur Rauschen.
             Ein Geburtstag am Sonntag gehört nicht in den Ausbildungsnachweis. -->
        {#if tag.stunden > 0 || (tag.art !== "frei" && tag.art !== "betrieb")}
          <li class="border-b border-linie-weich px-3.5 py-3 last:border-0">
            <div class="mb-2 flex items-baseline gap-3">
              <span class="w-[5.5rem] shrink-0 text-[0.9375rem] font-medium">{tag.wochentag}</span>
              <span class="ziffern shrink-0 text-[0.8125rem] text-gedaempft">
                {tagestext(tag.datum)}
              </span>
              <span class="min-w-0 flex-1 truncate text-[0.8125rem] text-leise">
                {ART_TEXT[tag.art] ?? tag.art}
              </span>
              {#if tag.stunden > 0}
                <span class="ziffern shrink-0 text-[0.8125rem] text-gedaempft">
                  {stundentext(tag.stunden)}
                </span>
              {/if}
            </div>

            {#if tag.art === "krank" || tag.art === "urlaub" || tag.art === "feiertag"}
              <p class="m-0 pl-[6.75rem] text-sm text-gedaempft">
                {ART_TEXT[tag.art]}, keine Ausbildungszeit.
              </p>
            {:else if tag.stunden > 0}
              <textarea
                value={tag.taetigkeiten.join("\n")}
                oninput={(e) => tagGetippt(tag.datum, e.currentTarget.value)}
                rows={Math.max(2, tag.taetigkeiten.length)}
                placeholder="Was hast du gemacht? Eine Zeile je Tätigkeit."
                aria-label={`Tätigkeiten am ${tag.wochentag}`}
                class="w-full resize-y rounded-element bg-erhoben px-3 py-2 text-[0.9375rem]
                       leading-relaxed outline-none placeholder:text-leise
                       focus:ring-2 focus:ring-akzent/60"
              ></textarea>

              {#if tag.hinweise.length}
                <div class="mt-2 flex flex-wrap items-center gap-1.5">
                  <span class="text-[0.6875rem] text-leise">Aus deinem Tag:</span>
                  {#each tag.hinweise as h (h)}
                    <button
                      type="button"
                      onclick={() => hinweisUebernehmen(tag.datum, h)}
                      class="rounded-full bg-erhoben px-2.5 py-1 text-xs text-gedaempft
                             transition-colors hover:bg-erhoben-2 hover:text-text"
                    >
                      {h}
                    </button>
                  {/each}
                </div>
              {/if}
            {/if}
          </li>
        {/if}
      {/each}
    </ul>
  </Abschnitt>

  <Abschnitt titel="Berufsschule: Themen der Woche">
    <div class="px-3.5 py-3">
      <textarea
        value={woche.themen_schule}
        oninput={(e) => {
          w.themen_schule = e.currentTarget.value;
          spaeterSichern({ themen_schule: e.currentTarget.value });
        }}
        rows="2"
        placeholder="Welche Themen kamen dran?"
        aria-label="Themen der Berufsschule"
        class="w-full resize-y rounded-element bg-erhoben px-3 py-2 text-[0.9375rem]
               leading-relaxed outline-none placeholder:text-leise focus:ring-2 focus:ring-akzent/60"
      ></textarea>
    </div>
  </Abschnitt>

  <Abschnitt titel="Bemerkung">
    <div class="px-3.5 py-3">
      <textarea
        value={woche.bemerkung}
        oninput={(e) => {
          w.bemerkung = e.currentTarget.value;
          spaeterSichern({ bemerkung: e.currentTarget.value });
        }}
        rows="2"
        placeholder="Alles, was sonst noch dazugehört."
        aria-label="Bemerkung zur Woche"
        class="w-full resize-y rounded-element bg-erhoben px-3 py-2 text-[0.9375rem]
               leading-relaxed outline-none placeholder:text-leise focus:ring-2 focus:ring-akzent/60"
      ></textarea>
    </div>
  </Abschnitt>
{/if}
