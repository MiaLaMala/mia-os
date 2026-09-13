<script lang="ts">
  /**
   * Listenansicht: gruppiert nach einer Eigenschaft, untereinander.
   * Die ruhigste Ansicht, auf dem Handy die beste.
   */
  import { slide } from "svelte/transition";
  import { sammlung } from "../lib/sammlung.svelte";
  import type { Eintrag } from "../lib/types";
  import { tagwort, heute } from "../lib/datum";
  import Marke from "./Marke.svelte";
  import Symbol from "./Symbol.svelte";

  let {
    gruppeNach = "bereich",
    oeffnen,
  }: { gruppeNach?: string; oeffnen: (e: Eintrag) => void } = $props();

  const prop = $derived(sammlung.prop(gruppeNach));
  const h = heute();

  const gruppen = $derived.by(() => {
    const nach = new Map<string, Eintrag[]>();
    // Reihenfolge der Optionen beibehalten, Fertiges nach unten.
    for (const o of prop?.optionen ?? []) nach.set(o.wert, []);
    for (const e of sammlung.eintraege) {
      const wert = e.eigenschaften[gruppeNach] ?? "";
      if (!nach.has(wert)) nach.set(wert, []);
      nach.get(wert)!.push(e);
    }
    return [...nach.entries()]
      .filter(([, l]) => l.length)
      .sort((a, b) => (a[0] ? 0 : 1) - (b[0] ? 0 : 1));
  });

  async function abhaken(e: Eintrag, ev: Event) {
    ev.stopPropagation();
    const neu = e.eigenschaften.status === "fertig" ? "offen" : "fertig";
    await sammlung.setzeEigenschaft(e.id, "status", neu);
  }
</script>

<div class="flex flex-col gap-5">
  {#each gruppen as [wert, eintraege] (wert)}
    <section transition:slide={{ duration: 200 }}>
      <div class="mb-1.5 flex items-center gap-2 px-1">
        {#if wert}
          <Marke {prop} {wert} />
        {:else}
          <span class="text-xs text-gedaempft">ohne {prop?.name ?? "Wert"}</span>
        {/if}
        <span class="ziffern text-xs text-leise">{eintraege.length}</span>
      </div>

      <ul class="karte m-0 list-none overflow-hidden p-0">
        {#each eintraege as e, i (e.id)}
          {@const fertig = e.eigenschaften.status === "fertig"}
          <li class="auftauchen border-b border-linie-weich last:border-0" style="animation-delay: {Math.min(i, 10) * 25}ms">
            <div
              class="flex w-full items-center gap-3 px-3 py-2.5 transition-colors duration-150 hover:bg-erhoben"
            >
              {#if sammlung.prop("status")}
                <button
                  type="button"
                  onclick={(ev) => abhaken(e, ev)}
                  aria-label={fertig ? "Wieder öffnen" : "Erledigt"}
                  class="grid size-5 shrink-0 place-items-center rounded-full border-[1.5px]
                         transition-colors duration-150"
                  class:border-linie={!fertig}
                  class:hover:border-gedaempft={!fertig}
                  class:border-akzent={fertig}
                  class:bg-akzent={fertig}
                  class:text-akzent-text={fertig}
                >
                  {#if fertig}
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5 9.5 17 19 7.5" /></svg>
                  {/if}
                </button>
              {/if}

              <button
                type="button"
                onclick={() => oeffnen(e)}
                class="flex min-w-0 flex-1 items-center gap-3 text-left"
              >
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-[0.9375rem]" class:line-through={fertig} class:text-gedaempft={fertig}>
                    {e.titel}
                  </span>
                  {#if e.inhalt}
                    <span class="mt-0.5 block truncate text-xs text-gedaempft">{e.inhalt}</span>
                  {/if}
                </span>

                <span class="flex shrink-0 items-center gap-1.5">
                  {#if sammlung.anhangZahl(e.id)}
                    <span
                      class="flex items-center gap-0.5 text-xs text-leise"
                      title="{sammlung.anhangZahl(e.id)} Dokument(e) angehängt"
                    >
                      <Symbol name="paperclip" groesse={13} />
                      <span class="ziffern">{sammlung.anhangZahl(e.id)}</span>
                    </span>
                  {/if}
                  {#each sammlung.eigenschaften.filter((p) => p.key !== gruppeNach && p.key !== "status") as p (p.key)}
                    {#if e.eigenschaften[p.key]}
                      <Marke prop={p} wert={e.eigenschaften[p.key]} klein />
                    {/if}
                  {/each}
                  {#if e.datum}
                    <span
                      class="ziffern text-xs"
                      class:text-fehler={e.datum < h && !fertig}
                      class:text-gedaempft={e.datum >= h || fertig}
                    >
                      {tagwort(e.datum)}
                    </span>
                  {/if}
                </span>
              </button>
            </div>
          </li>
        {/each}
      </ul>
    </section>
  {/each}
</div>
