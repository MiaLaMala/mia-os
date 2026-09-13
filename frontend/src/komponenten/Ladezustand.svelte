<script lang="ts">
  /** Erst nach kurzer Pause sichtbar: bei schnellen Antworten blitzt sonst etwas auf. */
  import { fade } from "svelte/transition";
  let { hoehe = "min-h-40" }: { hoehe?: string } = $props();
</script>

<div
  class="grid place-items-center {hoehe}"
  in:fade={{ duration: 150, delay: 260 }}
  out:fade={{ duration: 100 }}
  role="status"
  aria-label="Lädt"
>
  <span class="size-5 animate-spin rounded-full border-2 border-linie border-t-akzent"></span>
</div>
