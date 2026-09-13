<script lang="ts">
  /**
   * Ein Segmentschalter wie in iOS: eine Pille, der aktive Teil hebt
   * sich als Fläche ab. Für Ansichtswahl (Monat/Tag, Liste/Board).
   */
  let {
    optionen,
    wert,
    waehlen,
    klein = false,
  }: {
    optionen: { key: string; name: string }[];
    wert: string;
    waehlen: (key: string) => void;
    klein?: boolean;
  } = $props();
</script>

<div class="inline-flex shrink-0 rounded-full bg-erhoben p-0.5" role="tablist">
  {#each optionen as o (o.key)}
    {@const aktiv = wert === o.key}
    <button
      type="button"
      role="tab"
      aria-selected={aktiv}
      onclick={() => waehlen(o.key)}
      class="rounded-full font-medium transition-[background,color,box-shadow] duration-200 ease-ruhig"
      class:px-3={!klein}
      class:py-1={!klein}
      class:text-[0.8125rem]={!klein}
      class:px-2.5={klein}
      class:py-0.5={klein}
      class:text-xs={klein}
      class:bg-flaeche={aktiv}
      class:text-text={aktiv}
      class:shadow-sm={aktiv}
      class:text-gedaempft={!aktiv}
      class:hover:text-text={!aktiv}
    >
      {o.name}
    </button>
  {/each}
</div>
