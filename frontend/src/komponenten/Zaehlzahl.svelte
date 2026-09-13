<script lang="ts">
  /**
   * Eine Zahl, die beim Erscheinen hochzählt.
   *
   * Nur für echte Zahlen: bei Text wäre es albern. Tabellenziffern
   * verhindern, dass die Breite beim Zählen springt.
   */
  import { onMount } from "svelte";

  let {
    wert,
    einheit = "",
    dauer = 650,
    klasse = "",
  }: {
    wert: number;
    einheit?: string;
    dauer?: number;
    klasse?: string;
  } = $props();

  let gezeigt = $state(0);

  // Nachkommastellen aus dem Zielwert übernehmen, sonst zählt 88.7 zu 89.
  const stellen = $derived(String(wert).includes(".") ? String(wert).split(".")[1].length : 0);

  onMount(() => {
    const reduziert = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduziert) {
      gezeigt = wert;
      return;
    }

    const start = performance.now();
    let laeuft = true;

    const schritt = (jetzt: number) => {
      if (!laeuft) return;
      const anteil = Math.min(1, (jetzt - start) / dauer);
      // Am Ende auslaufen lassen, nicht linear: wirkt ruhiger.
      const weich = 1 - Math.pow(1 - anteil, 3);
      gezeigt = wert * weich;
      if (anteil < 1) requestAnimationFrame(schritt);
      else gezeigt = wert;
    };

    requestAnimationFrame(schritt);
    return () => {
      laeuft = false;
    };
  });
</script>

<span class="ziffern {klasse}">
  {gezeigt.toFixed(stellen).replace(".", ",")}{#if einheit}&nbsp;{einheit}{/if}
</span>
