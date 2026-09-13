<script lang="ts">
  /**
   * Homelab: Lage oben in einem Satz, Störungen sofort, Kennzahlen als
   * Raster, alle Dienste als Liste mit Suche.
   */
  import { onMount } from "svelte";
  import { slide } from "svelte/transition";
  import { api } from "../lib/api";
  import type { HomelabDaten } from "../lib/types";
  import Seitenkopf from "../komponenten/Seitenkopf.svelte";
  import Abschnitt from "../komponenten/Abschnitt.svelte";
  import Ladezustand from "../komponenten/Ladezustand.svelte";
  import Fehlerhinweis from "../komponenten/Fehlerhinweis.svelte";
  import Zaehlzahl from "../komponenten/Zaehlzahl.svelte";
  import Symbol from "../komponenten/Symbol.svelte";
  import Segment from "../komponenten/Segment.svelte";

  let daten = $state<HomelabDaten | null>(null);
  let laedt = $state(true);
  let fehler = $state("");
  let filter = $state("alle");
  let suche = $state("");

  const punktfarbe = (status: number) =>
    status === 1 ? "bg-gut" : status === 3 ? "bg-achtung" : "bg-fehler";

  const gefiltert = $derived.by(() => {
    if (!daten) return [];
    let liste = daten.dienste;
    if (filter === "stoerungen") liste = liste.filter((d) => d.status !== 1);
    const s = suche.trim().toLowerCase();
    if (s) liste = liste.filter((d) => d.name.toLowerCase().includes(s));
    return liste;
  });

  async function laden() {
    try {
      daten = await api.homelab();
      fehler = "";
    } catch (e) {
      fehler = e instanceof Error ? e.message : "Homelab nicht erreichbar";
    } finally {
      laedt = false;
    }
  }

  onMount(() => {
    laden();
    const takt = setInterval(() => {
      if (document.visibilityState === "visible") laden();
    }, 20_000);
    return () => clearInterval(takt);
  });
</script>

<Seitenkopf titel="Homelab" untertitel={daten ? `Stand ${daten.stand}, alle 20 s` : "Was läuft, was klemmt"} />

{#if fehler}
  <Fehlerhinweis text={fehler} />
{/if}

{#if laedt && !daten}
  <Ladezustand />
{:else if daten}
  <!-- Lage: ein Satz, ein Punkt -->
  <div
    class="karte mb-6 flex items-center gap-3.5 px-4 py-4"
    style={daten.lage.zustand === "unten"
      ? "border-color: color-mix(in srgb, var(--color-fehler) 35%, var(--color-linie))"
      : ""}
  >
    <span class="relative grid size-10 shrink-0 place-items-center">
      <span
        class="absolute inset-0 rounded-full opacity-20"
        class:bg-gut={daten.lage.zustand === "oben"}
        class:bg-fehler={daten.lage.zustand === "unten"}
        class:bg-gedaempft={daten.lage.zustand === "unklar"}
      ></span>
      <span
        class="size-3 rounded-full"
        class:bg-gut={daten.lage.zustand === "oben"}
        class:bg-fehler={daten.lage.zustand === "unten"}
        class:bg-gedaempft={daten.lage.zustand === "unklar"}
      ></span>
    </span>
    <span class="min-w-0 flex-1">
      <span class="block text-[1.0625rem] font-semibold leading-tight">{daten.lage.satz}</span>
      <span class="ziffern mt-0.5 block text-[0.8125rem] text-gedaempft">
        {daten.lage.oben} von {daten.lage.gesamt} Diensten erreichbar{daten.lage.uptime !== null
          ? `, ${daten.lage.uptime.toFixed(1).replace(".", ",")} % Verfügbarkeit`
          : ""}
      </span>
    </span>
  </div>

  {#if daten.stoerungen.length}
    <Abschnitt titel="Störungen">
      <ul class="m-0 list-none p-0">
        {#each daten.stoerungen as s (s.name)}
          <li
            class="flex items-center gap-3 border-b border-linie-weich px-3.5 py-3 last:border-0"
            transition:slide={{ duration: 200 }}
          >
            <span class="size-2.5 shrink-0 rounded-full bg-fehler"></span>
            <span class="min-w-0 flex-1">
              <span class="block text-[0.9375rem] font-medium">{s.name}</span>
              {#if s.meldung}
                <span class="block truncate text-[0.8125rem] text-gedaempft">{s.meldung}</span>
              {/if}
            </span>
            {#if s.uptime !== null}
              <span class="ziffern shrink-0 text-xs text-gedaempft">
                {s.uptime.toFixed(1).replace(".", ",")} %
              </span>
            {/if}
          </li>
        {/each}
      </ul>
    </Abschnitt>
  {/if}

  {#if daten.kennzahlen.length}
    <Abschnitt titel="Kennzahlen">
      <div class="grid grid-cols-2 gap-px bg-linie-weich sm:grid-cols-3">
        {#each daten.kennzahlen as k (k.label)}
          {@const teile = k.wert.match(/^(\d+(?:[.,]\d+)?)\s*(.*)$/)}
          <div class="bg-flaeche px-3.5 py-3">
            <p class="m-0 text-xs font-medium text-gedaempft">{k.label}</p>
            <p class="anzeige ziffern m-0 mt-1 text-[1.375rem] leading-none">
              {#if teile}
                <Zaehlzahl wert={parseFloat(teile[1].replace(",", "."))} einheit={teile[2]} />
              {:else}
                {k.wert}
              {/if}
            </p>
          </div>
        {/each}
      </div>
    </Abschnitt>
  {/if}

  <Abschnitt titel="Dienste, {daten.dienste.length}">
    {#snippet aktion()}
      <Segment
        klein
        wert={filter}
        waehlen={(k) => (filter = k)}
        optionen={[
          { key: "alle", name: "Alle" },
          { key: "stoerungen", name: "Störungen" },
        ]}
      />
    {/snippet}

    <label class="flex items-center gap-2 border-b border-linie-weich px-3.5 py-2">
      <span class="text-leise"><Symbol name="search" groesse={15} /></span>
      <input
        bind:value={suche}
        type="search"
        placeholder="Dienst suchen"
        class="w-full border-0 bg-transparent text-sm outline-none placeholder:text-leise"
      />
    </label>

    {#if gefiltert.length}
      <ul class="m-0 list-none p-0">
        {#each gefiltert as d (d.name)}
          <li class="flex items-center gap-3 border-b border-linie-weich px-3.5 py-2.5 last:border-0">
            <span class="size-2 shrink-0 rounded-full {punktfarbe(d.status)}"></span>
            <span class="min-w-0 flex-1 truncate text-[0.9375rem]">{d.name}</span>
            {#if d.ping}
              <span class="ziffern hidden shrink-0 text-xs text-leise sm:inline">{d.ping} ms</span>
            {/if}
            {#if d.uptime !== null}
              <span class="ziffern w-14 shrink-0 text-right text-xs text-gedaempft">
                {d.uptime.toFixed(1).replace(".", ",")} %
              </span>
            {/if}
          </li>
        {/each}
      </ul>
    {:else}
      <p class="m-0 px-3.5 py-5 text-center text-sm text-gedaempft">
        {filter === "stoerungen" ? "Keine Störungen" : "Nichts gefunden"}
      </p>
    {/if}
  </Abschnitt>
{/if}
