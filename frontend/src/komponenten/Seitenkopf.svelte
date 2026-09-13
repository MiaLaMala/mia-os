<script lang="ts">
  /**
   * Der Kopf jeder Seite: großer Titel, darunter eine Zeile Kontext,
   * rechts Platz für Werkzeuge. Immer gleich gebaut, damit nichts wackelt.
   */
  import type { Snippet } from "svelte";

  let {
    titel,
    untertitel = "",
    ueberzeile = "",
    werkzeuge,
  }: { titel: string; untertitel?: string; ueberzeile?: string; werkzeuge?: Snippet } =
    $props();
</script>

<header class="mb-5 flex items-end justify-between gap-4 lg:mb-7">
  <div class="min-w-0">
    {#if ueberzeile}
      <p class="mb-1 text-[0.8125rem] font-medium text-gedaempft">{ueberzeile}</p>
    {/if}
    <h1 class="anzeige m-0 text-[1.75rem] leading-none lg:text-[2rem]">{titel}</h1>
    {#if untertitel}
      <p class="mt-1.5 text-sm text-gedaempft">{untertitel}</p>
    {/if}
  </div>
  {#if werkzeuge}
    <div class="flex shrink-0 items-center gap-1.5">
      {@render werkzeuge()}
    </div>
  {/if}
</header>
