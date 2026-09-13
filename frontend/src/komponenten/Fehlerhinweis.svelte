<script lang="ts">
  /** Eine Störung, die Mia betrifft. Rot, aber nicht schreiend. */
  import Symbol from "./Symbol.svelte";
  let { text }: { text: string } = $props();
</script>

<p
  class="mb-4 flex items-center gap-2.5 rounded-element px-3.5 py-2.5 text-sm text-fehler"
  style="background: color-mix(in srgb, var(--color-fehler) 10%, transparent)"
  role="alert"
>
  <Symbol name="close" groesse={15} />
  <span class="min-w-0 flex-1">{text}</span>
</p>
