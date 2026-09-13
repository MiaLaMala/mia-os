<script lang="ts">
  /**
   * Board-Ansicht: Spalten nach einer Auswahleigenschaft.
   * Ziehen verschiebt zwischen den Spalten und setzt damit den Wert.
   */
  import { flip } from "svelte/animate";
  import { sammlung, farbeVon } from "../lib/sammlung.svelte";
  import type { Eintrag } from "../lib/types";
  import { tagwort, heute } from "../lib/datum";
  import Marke from "./Marke.svelte";

  let {
    gruppeNach = "status",
    oeffnen,
  }: { gruppeNach?: string; oeffnen: (e: Eintrag) => void } = $props();

  let gezogen = $state<number | null>(null);
  let ueber = $state("");
  const h = heute();

  const prop = $derived(sammlung.prop(gruppeNach));

  const spalten = $derived.by(() => {
    const optionen = prop?.optionen ?? [];
    const liste = optionen.map((o) => ({
      wert: o.wert,
      farbe: farbeVon(prop, o.wert),
      eintraege: sammlung.eintraege.filter((e) => e.eigenschaften[gruppeNach] === o.wert),
    }));
    const ohne = sammlung.eintraege.filter((e) => !e.eigenschaften[gruppeNach]);
    if (ohne.length) {
      liste.unshift({ wert: "", farbe: "var(--color-gedaempft)", eintraege: ohne });
    }
    return liste;
  });

  function ablegen(wert: string) {
    if (gezogen !== null) sammlung.setzeEigenschaft(gezogen, gruppeNach, wert);
    gezogen = null;
    ueber = "";
  }
</script>

<div class="ohne-scrollbalken -mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-2 lg:mx-0 lg:px-0">
  {#each spalten as spalte (spalte.wert)}
    <div
      class="flex w-[17rem] shrink-0 snap-start flex-col rounded-karte p-2 transition-colors duration-200"
      class:bg-erhoben={gezogen !== null && ueber === spalte.wert}
      style="background: {gezogen !== null && ueber === spalte.wert
        ? ''
        : 'color-mix(in srgb, var(--color-flaeche) 60%, var(--color-grund))'}"
      role="list"
      ondragover={(e) => {
        e.preventDefault();
        if (gezogen !== null) ueber = spalte.wert;
      }}
      ondragleave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) ueber = "";
      }}
      ondrop={() => ablegen(spalte.wert)}
    >
      <div class="mb-2 flex items-center justify-between px-1.5 pt-1">
        {#if spalte.wert}
          <Marke {prop} wert={spalte.wert} />
        {:else}
          <span class="text-xs text-gedaempft">ohne</span>
        {/if}
        <span class="ziffern text-xs text-leise">{spalte.eintraege.length}</span>
      </div>

      <div class="flex min-h-12 flex-col gap-1.5">
        {#each spalte.eintraege as e (e.id)}
          <div animate:flip={{ duration: 220 }}>
            <button
              type="button"
              draggable="true"
              ondragstart={() => (gezogen = e.id)}
              ondragend={() => {
                gezogen = null;
                ueber = "";
              }}
              onclick={() => oeffnen(e)}
              class="karte w-full cursor-grab p-3 text-left transition-[transform,box-shadow]
                     duration-200 ease-ruhig hover:ring-1 hover:ring-gedaempft/40
                     active:cursor-grabbing active:scale-[0.98]"
              class:opacity-40={gezogen === e.id}
            >
              <span class="block text-[0.875rem] font-medium leading-snug">{e.titel}</span>
              {#if e.inhalt}
                <span class="mt-1 line-clamp-2 block text-xs leading-snug text-gedaempft">{e.inhalt}</span>
              {/if}

              {#if e.datum || sammlung.eigenschaften.some((p) => p.key !== gruppeNach && e.eigenschaften[p.key])}
                <span class="mt-2 flex flex-wrap items-center gap-1">
                  {#each sammlung.eigenschaften.filter((p) => p.key !== gruppeNach) as p (p.key)}
                    {#if e.eigenschaften[p.key]}
                      <Marke prop={p} wert={e.eigenschaften[p.key]} klein />
                    {/if}
                  {/each}
                  {#if e.datum}
                    <span
                      class="ziffern ml-auto text-[0.6875rem]"
                      class:text-schlecht={e.datum < h && e.eigenschaften.status !== "fertig"}
                      class:text-gedaempft={!(e.datum < h && e.eigenschaften.status !== "fertig")}
                    >
                      {tagwort(e.datum)}
                    </span>
                  {/if}
                </span>
              {/if}
            </button>
          </div>
        {/each}
      </div>
    </div>
  {/each}
</div>
