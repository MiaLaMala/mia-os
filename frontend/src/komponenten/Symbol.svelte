<script lang="ts">
  /**
   * Ein Symbol aus dem eigenen Satz.
   *
   * Erbt currentColor, damit es sich der Umgebung anpasst, statt eine eigene
   * Farbe mitzubringen.
   */
  import { SYMBOLE } from "../lib/symbole";

  let {
    name,
    groesse = 20,
    klasse = "",
  }: {
    name: string;
    groesse?: number;
    klasse?: string;
  } = $props();

  const pfad = $derived(SYMBOLE[name] ?? "");
</script>

{#if pfad}
  <svg
    width={groesse}
    height={groesse}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    class={klasse}
    aria-hidden="true"
  >
    {@html pfad}
  </svg>
{/if}
