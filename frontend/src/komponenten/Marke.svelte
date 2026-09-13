<script lang="ts">
  /**
   * Ein Eigenschaftswert als farbige Marke, wie ein Notion-Select.
   * Die Farbe kommt aus der Eigenschaft, nicht aus der Ansicht.
   */
  import { farbeVon } from "../lib/sammlung.svelte";
  import type { Eigenschaft } from "../lib/types";

  let {
    prop,
    wert,
    klein = false,
  }: { prop: Eigenschaft | undefined; wert: string; klein?: boolean } = $props();

  const farbe = $derived(farbeVon(prop, wert));
</script>

{#if wert}
  <span
    class="inline-flex shrink-0 items-center gap-1 rounded-full font-medium leading-none"
    class:px-2={!klein}
    class:py-1={!klein}
    class:text-xs={!klein}
    class:px-1.5={klein}
    class:py-0.5={klein}
    class:text-[0.6875rem]={klein}
    style="background: color-mix(in srgb, {farbe} 16%, transparent); color: {farbe}"
  >
    {wert}
  </span>
{/if}
