<script lang="ts">
  /**
   * "Mehr" auf dem Handy: alles, was nicht in die untere Leiste passt.
   *
   * Erst die restlichen Bereiche als Kacheln, dann Mias Seitenbaum,
   * unten die Einstellungen. Dasselbe wie die Desktop-Leiste, nur als Blatt.
   */
  import { link, router } from "svelte-spa-router";
  import { NAVIGATION, EINSTELLUNGEN, LEISTE, UEBER } from "../lib/routen";
  import { seiten } from "../lib/seiten.svelte";
  import { blaetter } from "../lib/stores.svelte";
  import Blatt from "./Blatt.svelte";
  import Seitenbaum from "./Seitenbaum.svelte";
  import Symbol from "./Symbol.svelte";

  let { offen, schliessen }: { offen: boolean; schliessen: () => void } = $props();

  const rest = $derived(NAVIGATION.filter((n) => !LEISTE.includes(n.pfad)));
  const einstAktiv = $derived(router.location === EINSTELLUNGEN.pfad);
  const ueberAktiv = $derived(router.location === UEBER.pfad);

  async function neueSeite() {
    const seite = await seiten.anlegen("Neue Seite", null, true);
    schliessen();
    window.location.hash = `#/seite/${seite.id}`;
  }
</script>

<Blatt {offen} {schliessen} titel="Mehr">
  <div data-blatt-inhalt class="min-h-0 flex-1 overflow-y-auto px-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-2">
    <button
      type="button"
      onclick={() => {
        schliessen();
        blaetter.sucheOeffnen();
      }}
      class="mb-3 flex h-11 w-full items-center gap-2.5 rounded-element bg-erhoben px-3.5
             text-[0.9375rem] text-gedaempft transition-colors active:bg-erhoben-2"
    >
      <Symbol name="search" groesse={17} />
      Suchen
    </button>

    <div class="grid grid-cols-2 gap-2">
      {#each rest as e (e.pfad)}
        {@const aktiv = router.location === e.pfad}
        <a
          href={e.pfad}
          use:link
          class="karte flex items-center gap-2.5 px-3 py-3 text-[0.875rem] font-medium
                 transition-colors duration-150 active:bg-erhoben"
          class:border-akzent={aktiv}
        >
          <span class="text-gedaempft" class:text-akzent={aktiv}>
            <Symbol name={e.symbol} groesse={19} />
          </span>
          {e.titel}
        </a>
      {/each}
      <a
        href={EINSTELLUNGEN.pfad}
        use:link
        class="karte flex items-center gap-2.5 px-3 py-3 text-[0.875rem] font-medium
               transition-colors duration-150 active:bg-erhoben"
        class:border-akzent={einstAktiv}
      >
        <span class="text-gedaempft" class:text-akzent={einstAktiv}>
          <Symbol name={EINSTELLUNGEN.symbol} groesse={19} />
        </span>
        {EINSTELLUNGEN.titel}
      </a>
      <a
        href={UEBER.pfad}
        use:link
        class="karte flex items-center gap-2.5 px-3 py-3 text-[0.875rem] font-medium
               transition-colors duration-150 active:bg-erhoben"
        class:border-akzent={ueberAktiv}
      >
        <span class="text-gedaempft" class:text-akzent={ueberAktiv}>
          <Symbol name={UEBER.symbol} groesse={19} />
        </span>
        {UEBER.titel}
      </a>
    </div>

    <div class="mt-6 flex items-center justify-between px-1 pb-1.5">
      <span class="text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-leise">
        Seiten
      </span>
      <button
        type="button"
        onclick={neueSeite}
        aria-label="Neue Seite"
        class="flex items-center gap-1 rounded-full px-2 py-0.5 text-xs text-gedaempft
               transition-colors hover:bg-erhoben hover:text-text"
      >
        <Symbol name="plus" groesse={13} />
        Neu
      </button>
    </div>

    {#if seiten.baum.length}
      <ul class="karte m-0 list-none overflow-hidden p-1">
        {#each seiten.baum as knoten (knoten.id)}
          <Seitenbaum {knoten} gross />
        {/each}
      </ul>
    {:else}
      <p class="px-1 py-3 text-sm text-gedaempft">Noch keine Seiten.</p>
    {/if}
  </div>
</Blatt>
