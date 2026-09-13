<script lang="ts">
  /**
   * Der Seitenbaum. Mias eigene Struktur: anlegen, verschachteln,
   * umbenennen. `gross` schaltet auf Handy-Maße mit mehr Fläche zum Tippen.
   */
  import { link, router } from "svelte-spa-router";
  import { slide } from "svelte/transition";
  import { seiten, type Baumknoten } from "../lib/seiten.svelte";
  import Symbol from "./Symbol.svelte";
  import Seitenbaum from "./Seitenbaum.svelte";

  let { knoten, gross = false }: { knoten: Baumknoten; gross?: boolean } = $props();

  let umbenennen = $state(false);
  let entwurf = $state("");

  const aktiv = $derived(router.location === `/seite/${knoten.id}`);
  const hatKinder = $derived(knoten.kinder.length > 0);
  const offen = $derived(seiten.istOffen(knoten.id));

  async function unterseite() {
    const neu = await seiten.anlegen("Neue Seite", knoten.id, false);
    window.location.hash = `#/seite/${neu.id}`;
  }

  function starteUmbenennen() {
    entwurf = knoten.titel;
    umbenennen = true;
  }

  async function speichern() {
    const titel = entwurf.trim();
    umbenennen = false;
    if (titel && titel !== knoten.titel) await seiten.aendern(knoten.id, { titel });
  }
</script>

<li>
  <div
    class="group flex items-center gap-0.5 rounded-element pr-1 transition-colors duration-150"
    class:h-8={!gross}
    class:h-10={gross}
    class:bg-erhoben={aktiv}
    class:hover:bg-erhoben={!aktiv}
    style="padding-left: {knoten.tiefe * 0.875 + 0.125}rem"
  >
    {#if hatKinder}
      <button
        type="button"
        onclick={() => seiten.umschalten(knoten.id)}
        aria-label={offen ? "Zuklappen" : "Aufklappen"}
        aria-expanded={offen}
        class="grid size-5 shrink-0 place-items-center rounded text-leise
               transition-transform duration-200 ease-ruhig hover:text-text"
        class:rotate-90={offen}
      >
        <Symbol name="chevron-right" groesse={13} />
      </button>
    {:else}
      <span class="w-5 shrink-0"></span>
    {/if}

    {#if umbenennen}
      <!-- svelte-ignore a11y_autofocus -->
      <input
        bind:value={entwurf}
        onblur={speichern}
        onkeydown={(e) => {
          if (e.key === "Enter") speichern();
          if (e.key === "Escape") umbenennen = false;
        }}
        autofocus
        class="min-w-0 flex-1 rounded-klein border border-akzent bg-grund px-1.5 py-0.5
               text-[0.8125rem] outline-none"
      />
    {:else}
      <a
        href="/seite/{knoten.id}"
        use:link
        ondblclick={starteUmbenennen}
        class="flex min-w-0 flex-1 items-center gap-2 self-stretch transition-colors duration-150"
        class:text-[0.8125rem]={!gross}
        class:text-[0.9375rem]={gross}
        class:text-text={aktiv}
        class:font-medium={aktiv}
        class:text-gedaempft={!aktiv}
      >
        <span class="shrink-0" class:text-akzent={aktiv}>
          <Symbol name={knoten.symbol} groesse={gross ? 17 : 15} />
        </span>
        <span class="truncate">{knoten.titel}</span>
      </a>

      <button
        type="button"
        onclick={unterseite}
        aria-label="Unterseite in {knoten.titel}"
        title="Unterseite anlegen"
        class="grid size-6 shrink-0 place-items-center rounded-klein text-leise
               transition-opacity duration-150 hover:bg-erhoben-2 hover:text-text
               focus:opacity-100 group-hover:opacity-100"
        class:opacity-0={!gross}
      >
        <Symbol name="plus" groesse={13} />
      </button>
    {/if}
  </div>

  {#if hatKinder && offen}
    <ul
      class="m-0 list-none border-l border-linie p-0"
      style="margin-left: {knoten.tiefe * 0.875 + 0.75}rem"
      transition:slide={{ duration: 180 }}
    >
      {#each knoten.kinder as kind (kind.id)}
        <Seitenbaum knoten={{ ...kind, tiefe: 0 }} {gross} />
      {/each}
    </ul>
  {/if}
</li>
