<script lang="ts">
  /**
   * Ein Dokument aus dem Index suchen und an einen Eintrag hängen.
   *
   * Ohne Suchbegriff bleibt die Liste leer. Das ist Absicht und dieselbe
   * Regel wie in der Suche: im Index stehen Ausweise und Arztberichte, eine
   * Startansicht mit den zuletzt geänderten Dateien legt sie offen, sobald
   * jemand das Blatt aufmacht.
   */
  import { tick } from "svelte";
  import { api } from "../lib/api";
  import type { Dokument } from "../lib/types";
  import Blatt from "./Blatt.svelte";
  import Dokumentbild from "./Dokumentbild.svelte";
  import Symbol from "./Symbol.svelte";

  let {
    offen,
    schliessen,
    waehlen,
    schon = [],
  }: {
    offen: boolean;
    schliessen: () => void;
    waehlen: (d: Dokument) => Promise<void> | void;
    /** Pfade, die schon hängen. Werden als angehängt markiert. */
    schon?: string[];
  } = $props();

  let frage = $state("");
  let treffer = $state<Dokument[]>([]);
  let sucht = $state(false);
  let laeuft = $state(0);
  let feld: HTMLInputElement | undefined = $state();
  let timer: ReturnType<typeof setTimeout>;

  /** "/Dokumente/02 Medizinisch" wird zu "Medizinisch". */
  const kurz = (pfad: string) =>
    pfad
      .split("/")
      .filter(Boolean)
      .pop()
      ?.replace(/^\d+\s+/, "") ?? pfad;

  $effect(() => {
    if (offen) {
      frage = "";
      treffer = [];
      tick().then(() => feld?.focus());
    }
  });

  function getippt() {
    clearTimeout(timer);
    const q = frage.trim();
    if (q.length < 2) {
      treffer = [];
      return;
    }
    timer = setTimeout(async () => {
      sucht = true;
      try {
        treffer = (await api.dokumente(q)).treffer;
      } finally {
        sucht = false;
      }
    }, 200);
  }

  async function nehmen(d: Dokument) {
    // Die ID mitführen, nicht nur einen Schalter: sonst hängt der Spinner an
    // jeder Zeile, wenn Mia zweimal schnell tippt.
    laeuft = d.id;
    try {
      await waehlen(d);
    } finally {
      laeuft = 0;
    }
  }
</script>

<Blatt {offen} {schliessen} titel="Dokument anhängen" breit>
  <div class="px-3 pt-1 sm:px-4 sm:pt-3">
    <div
      class="flex h-11 items-center gap-2.5 rounded-element bg-erhoben px-3.5
             transition-[box-shadow] duration-200 focus-within:ring-2 focus-within:ring-akzent/60"
    >
      <span class="text-gedaempft" class:animate-spin={sucht}>
        <Symbol name={sucht ? "refresh" : "search"} groesse={17} />
      </span>
      <input
        bind:this={feld}
        bind:value={frage}
        oninput={getippt}
        placeholder="Dokument suchen"
        autocomplete="off"
        enterkeyhint="search"
        class="w-full border-0 bg-transparent text-[1rem] outline-none placeholder:text-leise"
      />
      {#if frage}
        <button
          type="button"
          onclick={() => {
            frage = "";
            treffer = [];
            feld?.focus();
          }}
          aria-label="Leeren"
          class="text-leise hover:text-text"
        >
          <Symbol name="close" groesse={15} />
        </button>
      {/if}
    </div>
  </div>

  <div
    data-blatt-inhalt
    class="min-h-0 flex-1 overflow-y-auto px-3 pb-[max(1rem,env(safe-area-inset-bottom))] pt-2 sm:px-4"
  >
    {#if treffer.length}
      <ul class="karte m-0 list-none overflow-hidden p-0">
        {#each treffer as d (d.id)}
          {@const haengt = schon.includes(d.path)}
          <li class="border-b border-linie-weich last:border-0">
            <button
              type="button"
              onclick={() => nehmen(d)}
              disabled={haengt || laeuft === d.id}
              class="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors
                     hover:bg-erhoben disabled:opacity-50"
            >
              <span class="h-9 w-7 shrink-0 overflow-hidden rounded-klein bg-erhoben text-[0.5rem]">
                <Dokumentbild quelle={d.vorschau} kuerzel={d.ext} />
              </span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-[0.9375rem]">{d.name}</span>
                <span class="block truncate text-xs text-gedaempft">
                  <!-- Mia legt entpackte Archive neben dem Original ab. Zwei
                       gleiche Namen sind dann kein Fehler, sehen aber so aus. -->
                  {d.kopie ? `${kurz(d.folder)} · Kopie` : kurz(d.folder)}
                </span>
              </span>
              {#if haengt}
                <span class="shrink-0 text-akzent"><Symbol name="check" groesse={16} /></span>
              {:else}
                <span class="shrink-0 text-leise"><Symbol name="plus" groesse={16} /></span>
              {/if}
            </button>
          </li>
        {/each}
      </ul>
    {:else if frage.trim().length >= 2 && !sucht}
      <p class="m-0 px-1 py-6 text-center text-sm text-gedaempft">Nichts gefunden.</p>
    {:else}
      <p class="m-0 px-1 py-5 text-center text-xs text-leise">
        Namen tippen, um im Dokumenten-Index zu suchen.
      </p>
    {/if}
  </div>
</Blatt>
