<script lang="ts">
  /** Wenn nichts da ist: ein Symbol, ein Satz. Keine leere Fläche. */
  import Symbol from "./Symbol.svelte";
  let { text = "Nichts gefunden", symbol = "sparkles" }: { text?: string; symbol?: string } =
    $props();
</script>

<div class="flex flex-col items-center gap-2 py-12 text-center">
  <span class="text-leise"><Symbol name={symbol} groesse={26} /></span>
  <p class="m-0 text-sm text-gedaempft">{text}</p>
</div>
