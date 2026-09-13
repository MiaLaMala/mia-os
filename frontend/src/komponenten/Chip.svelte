<script lang="ts">
  /** Ein Filterknopf. Aktiv trägt die Akzentfarbe, sonst eine ruhige Fläche. */
  import type { Snippet } from "svelte";

  let {
    aktiv = false,
    klick,
    farbe = "",
    children,
  }: { aktiv?: boolean; klick: () => void; farbe?: string; children: Snippet } = $props();
</script>

<button
  type="button"
  onclick={klick}
  aria-pressed={aktiv}
  class="flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-[0.8125rem] font-medium
         transition-[background,color] duration-200 ease-ruhig active:scale-[0.97]"
  class:bg-akzent={aktiv && !farbe}
  class:text-akzent-text={aktiv && !farbe}
  class:bg-erhoben={!aktiv}
  class:text-gedaempft={!aktiv}
  class:hover:text-text={!aktiv}
  style={aktiv && farbe ? `background: ${farbe}; color: #fff` : ""}
>
  {#if farbe && !aktiv}
    <span class="size-2 rounded-full" style="background: {farbe}"></span>
  {/if}
  {@render children()}
</button>
