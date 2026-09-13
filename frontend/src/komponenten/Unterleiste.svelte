<script lang="ts">
  /**
   * Die untere Leiste auf dem Handy.
   *
   * Vier Ziele in Daumenreichweite plus das Plus in der Mitte: ein Tipp,
   * ein Feld, Enter. Das aktive Ziel trägt eine weiche Fläche hinter dem
   * Symbol, nicht nur eine andere Farbe: das sieht man auch im Halbdunkel
   * um sieben Uhr früh.
   */
  import { link, router } from "svelte-spa-router";
  import { NAVIGATION, LEISTE } from "../lib/routen";
  import Symbol from "./Symbol.svelte";

  let {
    mehr,
    mehrOffen,
    plus,
  }: { mehr: () => void; mehrOffen: boolean; plus: () => void } = $props();

  const eintraege = $derived(
    LEISTE.map((pfad) => NAVIGATION.find((n) => n.pfad === pfad)).filter(
      (n): n is (typeof NAVIGATION)[number] => !!n,
    ),
  );

  // Das Plus sitzt in der Mitte: links zwei Ziele, rechts der Rest.
  const links = $derived(eintraege.slice(0, 2));
  const rechts = $derived(eintraege.slice(2));

  // "Mehr" ist aktiv, wenn das Blatt offen ist oder eine Seite dahinter.
  const mehrAktiv = $derived(mehrOffen || !LEISTE.includes(router.location));
</script>

{#snippet ziel(e: (typeof NAVIGATION)[number])}
  {@const aktiv = router.location === e.pfad && !mehrOffen}
  <li class="flex-1">
    <a
      href={e.pfad}
      use:link
      aria-current={aktiv ? "page" : undefined}
      class="flex flex-col items-center gap-0.5 pb-1.5 pt-1.5 text-[0.625rem] font-medium
             transition-colors duration-150 active:opacity-70"
      class:text-akzent={aktiv}
      class:text-gedaempft={!aktiv}
    >
      <span
        class="grid h-7 w-12 place-items-center rounded-full transition-colors duration-200 ease-ruhig"
        style={aktiv ? "background: color-mix(in srgb, var(--color-akzent) 16%, transparent)" : ""}
      >
        <Symbol name={e.symbol} groesse={21} />
      </span>
      <span class="truncate">{e.titel}</span>
    </a>
  </li>
{/snippet}

<nav
  class="fixed inset-x-0 bottom-0 z-40 border-t border-linie
         pb-[env(safe-area-inset-bottom)]"
  style="background: color-mix(in srgb, var(--color-flaeche) 88%, transparent);
         backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px)"
  aria-label="Hauptbereiche"
>
  <ul class="m-0 flex list-none items-stretch p-0">
    {#each links as e (e.pfad)}
      {@render ziel(e)}
    {/each}

    <li class="flex flex-1 items-center justify-center">
      <button
        type="button"
        onclick={plus}
        aria-label="Schnelleingabe"
        class="grid size-11 -translate-y-1 place-items-center rounded-full bg-akzent text-akzent-text
               shadow-blatt transition-transform duration-150 active:scale-95"
      >
        <Symbol name="plus" groesse={22} />
      </button>
    </li>

    {#each rechts as e (e.pfad)}
      {@render ziel(e)}
    {/each}

    <li class="flex-1">
      <button
        type="button"
        onclick={mehr}
        aria-label="Mehr"
        aria-expanded={mehrOffen}
        class="flex w-full flex-col items-center gap-0.5 pb-1.5 pt-1.5 text-[0.625rem]
               font-medium transition-colors duration-150 active:opacity-70"
        class:text-akzent={mehrAktiv}
        class:text-gedaempft={!mehrAktiv}
      >
        <span
          class="grid h-7 w-12 place-items-center rounded-full transition-colors duration-200 ease-ruhig"
          style={mehrAktiv
            ? "background: color-mix(in srgb, var(--color-akzent) 16%, transparent)"
            : ""}
        >
          <Symbol name="layers" groesse={21} />
        </span>
        <span class="truncate">Mehr</span>
      </button>
    </li>
  </ul>
</nav>
