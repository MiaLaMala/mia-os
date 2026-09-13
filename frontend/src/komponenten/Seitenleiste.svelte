<script lang="ts">
  /**
   * Die Seitenleiste am Desktop.
   *
   * Oben Mias Name, dann die festen Bereiche, dann ihr eigener Seitenbaum,
   * unten die Einstellungen. Einklappbar auf eine Symbolspalte.
   */
  import { link, router } from "svelte-spa-router";
  import { NAVIGATION, EINSTELLUNGEN, UEBER } from "../lib/routen";
  import { einstellungen, blaetter } from "../lib/stores.svelte";
  import { seiten } from "../lib/seiten.svelte";
  import Seitenbaum from "./Seitenbaum.svelte";
  import Symbol from "./Symbol.svelte";

  let { eingeklappt, umschalten }: { eingeklappt: boolean; umschalten: () => void } =
    $props();

  const vorname = $derived((einstellungen.owner || "Mia Grünwald").split(" ")[0]);
  const initiale = $derived(vorname.slice(0, 1));
  const einstAktiv = $derived(router.location === EINSTELLUNGEN.pfad);
  const ueberAktiv = $derived(router.location === UEBER.pfad);

  async function neueSeite() {
    const seite = await seiten.anlegen("Neue Seite", null, true);
    window.location.hash = `#/seite/${seite.id}`;
  }
</script>

<aside
  class="sticky top-0 flex h-dvh shrink-0 flex-col border-r border-linie bg-flaeche/60
         transition-[width] duration-220 ease-ruhig"
  style="width: {eingeklappt ? '3.75rem' : '15rem'}"
>
  <!-- Kopf: Name und Einklappen -->
  <div class="flex h-14 items-center gap-2.5 px-3">
    <span
      class="grid size-7 shrink-0 place-items-center rounded-full bg-akzent text-[0.8125rem]
             font-semibold text-akzent-text"
    >
      {initiale}
    </span>
    {#if !eingeklappt}
      <span class="min-w-0 flex-1 truncate text-[0.9375rem] font-semibold tracking-tight">
        {vorname}
      </span>
    {/if}
    <button
      type="button"
      onclick={umschalten}
      aria-label={eingeklappt ? "Leiste ausklappen" : "Leiste einklappen"}
      title={eingeklappt ? "Ausklappen" : "Einklappen"}
      class="grid size-7 shrink-0 place-items-center rounded-klein text-leise
             transition-colors duration-150 hover:bg-erhoben hover:text-text"
      class:ml-auto={!eingeklappt}
      class:hidden={eingeklappt}
    >
      <Symbol name="sidebar" groesse={16} />
    </button>
  </div>

  <nav class="min-h-0 flex-1 overflow-y-auto px-2 pb-3 ohne-scrollbalken" aria-label="Bereiche">
    <!-- Suche und Schnelleingabe: die beiden Dinge, die man von überall will -->
    <ul class="m-0 mb-2 flex list-none flex-col gap-px p-0">
      <li>
        <button
          type="button"
          onclick={blaetter.sucheOeffnen}
          title={eingeklappt ? "Suche (⌘K)" : undefined}
          class="flex h-8 w-full items-center gap-2.5 rounded-element px-2 text-[0.8125rem]
                 text-gedaempft transition-colors duration-150 hover:bg-erhoben hover:text-text"
          class:justify-center={eingeklappt}
        >
          <span class="shrink-0"><Symbol name="search" groesse={17} /></span>
          {#if !eingeklappt}
            <span class="flex-1 truncate text-left">Suche</span>
            <kbd class="ziffern rounded border border-linie px-1 text-[0.625rem] text-leise">⌘K</kbd>
          {/if}
        </button>
      </li>
      <li>
        <button
          type="button"
          onclick={blaetter.schnellOeffnen}
          title={eingeklappt ? "Schnelleingabe (⌘J)" : undefined}
          class="flex h-8 w-full items-center gap-2.5 rounded-element px-2 text-[0.8125rem]
                 text-gedaempft transition-colors duration-150 hover:bg-erhoben hover:text-text"
          class:justify-center={eingeklappt}
        >
          <span class="shrink-0"><Symbol name="plus" groesse={17} /></span>
          {#if !eingeklappt}
            <span class="flex-1 truncate text-left">Eintragen</span>
            <kbd class="ziffern rounded border border-linie px-1 text-[0.625rem] text-leise">⌘J</kbd>
          {/if}
        </button>
      </li>
    </ul>

    <ul class="m-0 flex list-none flex-col gap-px p-0">
      {#each NAVIGATION as eintrag (eintrag.pfad)}
        {@const aktiv = router.location === eintrag.pfad}
        <li>
          <a
            href={eintrag.pfad}
            use:link
            aria-current={aktiv ? "page" : undefined}
            title={eingeklappt ? eintrag.titel : undefined}
            class="flex h-8 items-center gap-2.5 rounded-element px-2 text-[0.8125rem]
                   transition-colors duration-150"
            class:bg-erhoben={aktiv}
            class:text-text={aktiv}
            class:font-medium={aktiv}
            class:text-gedaempft={!aktiv}
            class:hover:bg-erhoben={!aktiv}
            class:hover:text-text={!aktiv}
            class:justify-center={eingeklappt}
          >
            <span class="shrink-0" class:text-akzent={aktiv}>
              <Symbol name={eintrag.symbol} groesse={17} />
            </span>
            {#if !eingeklappt}
              <span class="truncate">{eintrag.titel}</span>
            {/if}
          </a>
        </li>
      {/each}
    </ul>

    {#if eingeklappt}
      <div class="mx-2 my-3 border-t border-linie"></div>
      <button
        type="button"
        onclick={umschalten}
        aria-label="Leiste ausklappen"
        title="Seiten"
        class="grid h-8 w-full place-items-center rounded-element text-gedaempft
               transition-colors duration-150 hover:bg-erhoben hover:text-text"
      >
        <Symbol name="layers" groesse={17} />
      </button>
    {:else}
      <!-- Mias eigener Baum -->
      <div class="mt-5 flex items-center justify-between px-2 pb-1.5">
        <span class="text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-leise">
          Seiten
        </span>
        <button
          type="button"
          onclick={neueSeite}
          aria-label="Neue Seite"
          title="Neue Seite"
          class="grid size-5 place-items-center rounded text-leise
                 transition-colors duration-150 hover:bg-erhoben hover:text-text"
        >
          <Symbol name="plus" groesse={13} />
        </button>
      </div>

      <ul class="m-0 flex list-none flex-col gap-px p-0">
        {#each seiten.baum as knoten (knoten.id)}
          <Seitenbaum {knoten} />
        {/each}
      </ul>

      {#if !seiten.baum.length}
        <button
          type="button"
          onclick={neueSeite}
          class="mx-2 mt-1 flex w-[calc(100%-1rem)] items-center gap-2 rounded-element
                 border border-dashed border-linie px-2 py-1.5 text-xs text-leise
                 transition-colors hover:border-gedaempft hover:text-text"
        >
          <Symbol name="plus" groesse={13} />
          Erste Seite anlegen
        </button>
      {/if}
    {/if}
  </nav>

  <!-- Fuß: Einstellungen -->
  <div class="border-t border-linie p-2">
    <a
      href={EINSTELLUNGEN.pfad}
      use:link
      aria-current={einstAktiv ? "page" : undefined}
      title={eingeklappt ? EINSTELLUNGEN.titel : undefined}
      class="flex h-8 items-center gap-2.5 rounded-element px-2 text-[0.8125rem]
             transition-colors duration-150"
      class:bg-erhoben={einstAktiv}
      class:text-text={einstAktiv}
      class:text-gedaempft={!einstAktiv}
      class:hover:bg-erhoben={!einstAktiv}
      class:hover:text-text={!einstAktiv}
      class:justify-center={eingeklappt}
    >
      <span class="shrink-0" class:text-akzent={einstAktiv}>
        <Symbol name={EINSTELLUNGEN.symbol} groesse={17} />
      </span>
      {#if !eingeklappt}
        <span class="truncate">{EINSTELLUNGEN.titel}</span>
      {/if}
    </a>

    <a
      href={UEBER.pfad}
      use:link
      aria-current={ueberAktiv ? "page" : undefined}
      title={eingeklappt ? UEBER.titel : undefined}
      class="flex h-8 items-center gap-2.5 rounded-element px-2 text-[0.8125rem]
             transition-colors duration-150"
      class:bg-erhoben={ueberAktiv}
      class:text-text={ueberAktiv}
      class:text-gedaempft={!ueberAktiv}
      class:hover:bg-erhoben={!ueberAktiv}
      class:hover:text-text={!ueberAktiv}
      class:justify-center={eingeklappt}
    >
      <span class="shrink-0" class:text-akzent={ueberAktiv}>
        <Symbol name={UEBER.symbol} groesse={17} />
      </span>
      {#if !eingeklappt}
        <span class="truncate">{UEBER.titel}</span>
      {/if}
    </a>
  </div>
</aside>
