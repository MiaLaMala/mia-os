<script lang="ts">
  /**
   * Eine Zeile in einer Karte: Symbol, Titel, Untertitel, rechts ein Wert
   * oder Bedienelement. Als Link, Knopf oder stumm.
   */
  import type { Snippet } from "svelte";
  import { link } from "svelte-spa-router";
  import Symbol from "./Symbol.svelte";

  let {
    titel,
    untertitel = "",
    symbol = "",
    symbolFarbe = "",
    href = "",
    extern = false,
    klick,
    pfeil = false,
    rechts,
    children,
  }: {
    titel: string;
    untertitel?: string;
    symbol?: string;
    symbolFarbe?: string;
    href?: string;
    extern?: boolean;
    klick?: () => void;
    pfeil?: boolean;
    rechts?: Snippet;
    children?: Snippet;
  } = $props();

  const interaktiv = $derived(!!href || !!klick);
  const klassen =
    "flex min-h-12 w-full items-center gap-3 border-b border-linie-weich px-3.5 py-2.5 text-left " +
    "transition-colors duration-150 last:border-0";
  const aktivKlassen = " hover:bg-erhoben active:bg-erhoben-2";
</script>

{#snippet innen()}
  {#if symbol}
    <span
      class="grid size-8 shrink-0 place-items-center rounded-element"
      style="background: color-mix(in srgb, {symbolFarbe || 'var(--color-gedaempft)'} 14%, transparent);
             color: {symbolFarbe || 'var(--color-gedaempft)'}"
    >
      <Symbol name={symbol} groesse={17} />
    </span>
  {/if}
  <span class="min-w-0 flex-1">
    <span class="block truncate text-[0.9375rem] font-medium leading-tight">{titel}</span>
    {#if untertitel}
      <span class="mt-0.5 block truncate text-[0.8125rem] text-gedaempft">{untertitel}</span>
    {/if}
    {#if children}
      {@render children()}
    {/if}
  </span>
  {#if rechts}
    <span class="flex shrink-0 items-center gap-2">{@render rechts()}</span>
  {/if}
  {#if pfeil || (interaktiv && !rechts)}
    <span class="shrink-0 text-leise"><Symbol name="chevron-right" groesse={16} /></span>
  {/if}
{/snippet}

{#if href && extern}
  <a {href} class={klassen + aktivKlassen}>
    {@render innen()}
  </a>
{:else if href}
  <a {href} use:link class={klassen + aktivKlassen}>
    {@render innen()}
  </a>
{:else if klick}
  <button type="button" onclick={klick} class={klassen + aktivKlassen}>
    {@render innen()}
  </button>
{:else}
  <div class={klassen}>
    {@render innen()}
  </div>
{/if}
