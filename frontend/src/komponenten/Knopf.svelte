<script lang="ts">
  /** Ein runder Werkzeugknopf mit Symbol, für Seitenköpfe und Leisten. */
  import Symbol from "./Symbol.svelte";

  let {
    symbol,
    beschriftung,
    klick,
    aktiv = false,
    dreht = false,
    text = "",
  }: {
    symbol: string;
    beschriftung: string;
    klick: () => void;
    aktiv?: boolean;
    dreht?: boolean;
    text?: string;
  } = $props();
</script>

<button
  type="button"
  onclick={klick}
  aria-label={beschriftung}
  title={beschriftung}
  aria-pressed={aktiv || undefined}
  class="flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-full bg-erhoben
         text-[0.8125rem] font-medium transition-[background,color,transform] duration-200
         ease-ruhig hover:bg-erhoben-2 hover:text-text active:scale-95"
  class:w-9={!text}
  class:px-3.5={!!text}
  class:text-akzent={aktiv}
  class:text-gedaempft={!aktiv}
>
  <span class:animate-spin={dreht}><Symbol name={symbol} groesse={17} /></span>
  {#if text}<span>{text}</span>{/if}
</button>
