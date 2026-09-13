<script lang="ts">
  /**
   * Ein Abschnitt: kleine Überschrift in Kapitälchen, darunter eine Karte
   * mit dem Inhalt. Das Grundmuster der iOS-Einstellungen.
   */
  import type { Snippet } from "svelte";

  let {
    titel = "",
    hinweis = "",
    aktion,
    ohneKarte = false,
    children,
  }: {
    titel?: string;
    hinweis?: string;
    aktion?: Snippet;
    ohneKarte?: boolean;
    children: Snippet;
  } = $props();
</script>

<section class="mb-6 last:mb-0">
  {#if titel || aktion}
    <div class="mb-2 flex items-center justify-between px-1">
      <h2 class="m-0 text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-leise">
        {titel}
      </h2>
      {#if aktion}
        {@render aktion()}
      {/if}
    </div>
  {/if}

  {#if ohneKarte}
    {@render children()}
  {:else}
    <div class="karte overflow-hidden">
      {@render children()}
    </div>
  {/if}

  {#if hinweis}
    <p class="mt-2 px-1 text-xs leading-snug text-gedaempft">{hinweis}</p>
  {/if}
</section>
