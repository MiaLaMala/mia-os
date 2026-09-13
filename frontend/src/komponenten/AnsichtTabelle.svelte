<script lang="ts">
  /**
   * Tabellenansicht. Eine Zeile je Eintrag, eine Spalte je Eigenschaft.
   */
  import { sammlung } from "../lib/sammlung.svelte";
  import type { Eintrag } from "../lib/types";
  import { kurzesDatum } from "../lib/datum";
  import Marke from "./Marke.svelte";

  let { oeffnen }: { oeffnen: (e: Eintrag) => void } = $props();
</script>

<div class="karte ohne-scrollbalken -mx-4 overflow-x-auto rounded-none border-x-0 lg:mx-0 lg:rounded-karte lg:border-x">
  <table class="w-full min-w-[36rem] border-collapse text-sm">
    <thead>
      <tr class="border-b border-linie text-left">
        <th class="py-2.5 pl-3.5 pr-3 text-xs font-medium text-gedaempft">Name</th>
        {#each sammlung.eigenschaften as prop (prop.key)}
          <th class="whitespace-nowrap px-3 py-2.5 text-xs font-medium text-gedaempft">
            {prop.name}
          </th>
        {/each}
        <th class="px-3 py-2.5 pr-3.5 text-right text-xs font-medium text-gedaempft">Datum</th>
      </tr>
    </thead>
    <tbody>
      {#each sammlung.eintraege as e, i (e.id)}
        <tr
          class="auftauchen cursor-pointer border-b border-linie-weich transition-colors duration-150
                 last:border-0 hover:bg-erhoben"
          style="animation-delay: {Math.min(i, 14) * 20}ms"
          onclick={() => oeffnen(e)}
        >
          <td class="max-w-64 truncate py-2.5 pl-3.5 pr-3 font-medium">{e.titel}</td>
          {#each sammlung.eigenschaften as prop (prop.key)}
            <td class="px-3 py-2.5">
              {#if e.eigenschaften[prop.key]}
                <Marke {prop} wert={e.eigenschaften[prop.key]} klein />
              {:else}
                <span class="text-leise">·</span>
              {/if}
            </td>
          {/each}
          <td class="ziffern whitespace-nowrap px-3 py-2.5 pr-3.5 text-right text-xs text-gedaempft">
            {e.datum ? kurzesDatum(e.datum) : ""}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
