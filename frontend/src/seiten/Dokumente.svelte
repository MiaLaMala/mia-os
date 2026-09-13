<script lang="ts">
  /**
   * Dokumente: Suche oben, Ordner als Chips, dann die Kachelwand mit
   * Vorschau. Umschaltbar auf eine Liste, die Ordner und Datum zeigt.
   */
  import { onMount } from "svelte";
  import { api } from "../lib/api";
  import type { Dokument, OrdnerZaehler } from "../lib/types";
  import Seitenkopf from "../komponenten/Seitenkopf.svelte";
  import Ladezustand from "../komponenten/Ladezustand.svelte";
  import Fehlerhinweis from "../komponenten/Fehlerhinweis.svelte";
  import Leerzustand from "../komponenten/Leerzustand.svelte";
  import Chip from "../komponenten/Chip.svelte";
  import Dokumentbild from "../komponenten/Dokumentbild.svelte";
  import Knopf from "../komponenten/Knopf.svelte";
  import Symbol from "../komponenten/Symbol.svelte";
  import Fundstelle from "../komponenten/Fundstelle.svelte";

  let treffer = $state<Dokument[]>([]);
  let ordnerliste = $state<OrdnerZaehler[]>([]);
  let gesamt = $state(0);
  let seite = $state(1);
  let seiten = $state(1);
  let suche = $state("");
  let ordner = $state("");
  let laedt = $state(true);
  let fehler = $state("");
  let alsListe = $state(localStorage.getItem("dokumente-ansicht") === "liste");

  let tippTimer: ReturnType<typeof setTimeout>;

  // Zustand in der Adresse, damit der Editor hierher zurueckfindet:
  // "#/dokumente?ordner=...&q=...&seite=2". Sonst sprang die Filterleiste
  // nach jedem Dokument auf "Alle" zurueck (Mia, 05.09.2026).
  function zustandLesen() {
    const frage = window.location.hash.split("?")[1] ?? "";
    const p = new URLSearchParams(frage);
    suche = p.get("q") ?? "";
    ordner = p.get("ordner") ?? "";
    seite = Math.max(1, Number(p.get("seite") ?? 1) || 1);
  }

  const zustand = $derived.by(() => {
    const p = new URLSearchParams();
    if (suche) p.set("q", suche);
    if (ordner) p.set("ordner", ordner);
    if (seite > 1) p.set("seite", String(seite));
    return p.toString();
  });

  function zustandSchreiben() {
    const ziel = zustand ? `#/dokumente?${zustand}` : "#/dokumente";
    if (window.location.hash !== ziel) history.replaceState(null, "", ziel);
  }

  const editorLink = (d: Dokument) => (zustand ? `${d.link}?zurueck=${encodeURIComponent(zustand)}` : d.link);

  /** "/Dokumente/02 Medizinisch" wird zu "Medizinisch". */
  const kurz = (pfad: string) =>
    pfad
      .split("/")
      .filter(Boolean)
      .pop()
      ?.replace(/^\d+\s+/, "") ?? pfad;

  async function laden() {
    laedt = true;
    zustandSchreiben();
    try {
      const daten = await api.dokumente(suche, ordner, seite);
      treffer = daten.treffer;
      gesamt = daten.gesamt;
      seiten = daten.seiten;
      seite = daten.seite;
      ordnerliste = daten.ordner;
      fehler = "";
    } catch (e) {
      fehler = e instanceof Error ? e.message : "Dokumente nicht erreichbar";
    } finally {
      laedt = false;
    }
  }

  function getippt() {
    clearTimeout(tippTimer);
    tippTimer = setTimeout(() => {
      seite = 1;
      laden();
    }, 300);
  }

  function filtern(top: string) {
    ordner = ordner === top ? "" : top;
    seite = 1;
    laden();
  }

  function blaettern(richtung: number) {
    seite = Math.min(seiten, Math.max(1, seite + richtung));
    laden();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function ansichtWechseln() {
    alsListe = !alsListe;
    localStorage.setItem("dokumente-ansicht", alsListe ? "liste" : "wand");
  }

  onMount(() => {
    zustandLesen();
    laden();
  });
</script>

<Seitenkopf titel="Dokumente" untertitel="{gesamt} Dateien aus der Nextcloud">
  {#snippet werkzeuge()}
    <Knopf
      symbol={alsListe ? "grid" : "list"}
      beschriftung={alsListe ? "Als Kacheln" : "Als Liste"}
      klick={ansichtWechseln}
    />
  {/snippet}
</Seitenkopf>

<!-- Suche -->
<label
  class="mb-3 flex h-11 items-center gap-2.5 rounded-element bg-erhoben px-3.5
         transition-[box-shadow] duration-200 focus-within:ring-2 focus-within:ring-akzent/60"
>
  <span class="text-gedaempft"><Symbol name="search" groesse={17} /></span>
  <input
    bind:value={suche}
    oninput={getippt}
    type="search"
    placeholder="Suchen"
    class="w-full border-0 bg-transparent text-[0.9375rem] outline-none placeholder:text-leise"
  />
  {#if suche}
    <button
      type="button"
      onclick={() => {
        suche = "";
        getippt();
      }}
      aria-label="Suche leeren"
      class="grid size-6 place-items-center rounded-full bg-linie text-gedaempft hover:text-text"
    >
      <Symbol name="close" groesse={12} />
    </button>
  {/if}
</label>

{#if ordnerliste.length}
  <div class="ohne-scrollbalken -mx-4 mb-5 flex gap-1.5 overflow-x-auto px-4 pb-1 lg:mx-0 lg:flex-wrap lg:px-0">
    <Chip aktiv={!ordner} klick={() => filtern("")}>Alle</Chip>
    {#each ordnerliste as o (o.top)}
      <Chip aktiv={ordner === o.top} klick={() => filtern(o.top)}>
        {kurz(o.top)}
        <span class="ziffern opacity-60">{o.n}</span>
      </Chip>
    {/each}
  </div>
{/if}

{#if fehler}
  <Fehlerhinweis text={fehler} />
{/if}

{#if laedt && !treffer.length}
  <Ladezustand />
{:else if treffer.length}
  {#if alsListe}
    <div class="karte overflow-hidden">
      {#each treffer as d (d.id)}
        <a
          href={editorLink(d)}
          class="flex items-center gap-3 border-b border-linie-weich px-3.5 py-2.5 transition-colors
                 duration-150 last:border-0 hover:bg-erhoben active:bg-erhoben-2"
        >
          <span class="h-10 w-8 shrink-0 overflow-hidden rounded-klein bg-erhoben text-[0.5625rem]">
            <Dokumentbild quelle={d.vorschau} kuerzel={d.ext} />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-[0.9375rem]">{d.name}</span>
            {#if d.stelle}
              <Fundstelle stelle={d.stelle} />
            {:else}
              <span class="block truncate text-xs text-gedaempft">
                {d.eintraege?.length ? d.eintraege.map((e) => e.titel).join(", ") : `${kurz(d.folder)} · ${d.groesse}`}
              </span>
            {/if}
          </span>
          {#if d.eintraege?.length}
            <span class="shrink-0 text-leise" title="Hängt an einem Eintrag">
              <Symbol name="paperclip" groesse={13} />
            </span>
          {/if}
          <span class="ziffern shrink-0 text-xs text-leise">{d.datum}</span>
        </a>
      {/each}
    </div>
  {:else}
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {#each treffer as d, i (d.id)}
        <a
          href={editorLink(d)}
          class="auftauchen group flex flex-col overflow-hidden rounded-karte bg-flaeche
                 ring-1 ring-linie transition-[transform,box-shadow] duration-200 ease-ruhig
                 hover:ring-gedaempft/50 active:scale-[0.98]"
          style="animation-delay: {Math.min(i, 12) * 25}ms"
        >
          <span
            class="relative block aspect-[3/4] overflow-hidden bg-erhoben transition-transform
                   duration-300 ease-ruhig group-hover:scale-[1.03]"
          >
            <Dokumentbild quelle={d.vorschau} kuerzel={d.ext} hoch />
            <span
              class="absolute left-2 top-2 rounded-full px-1.5 py-0.5 text-[0.5625rem] font-semibold
                     uppercase tracking-wide text-white"
              style="background: rgba(0,0,0,.55); backdrop-filter: blur(6px)"
            >
              {d.ext}
            </span>
          </span>
          <span class="flex flex-col gap-0.5 p-2.5">
            <span class="line-clamp-2 text-xs font-medium leading-snug">{d.name}</span>
            {#if d.stelle}
              <Fundstelle stelle={d.stelle} zeilen={2} />
            {:else if d.eintraege?.length}
              <span class="flex items-center gap-1 truncate text-[0.6875rem] text-gedaempft">
                <Symbol name="paperclip" groesse={11} />
                <span class="truncate">{d.eintraege.map((e) => e.titel).join(", ")}</span>
              </span>
            {:else}
              <span class="truncate text-[0.6875rem] text-leise">{kurz(d.folder)}</span>
            {/if}
          </span>
        </a>
      {/each}
    </div>
  {/if}

  {#if seiten > 1}
    <div class="mt-6 flex items-center justify-center gap-4">
      <Knopf symbol="chevron-left" beschriftung="Vorherige Seite" klick={() => blaettern(-1)} />
      <span class="ziffern text-sm text-gedaempft">{seite} von {seiten}</span>
      <Knopf symbol="chevron-right" beschriftung="Nächste Seite" klick={() => blaettern(1)} />
    </div>
  {/if}
{:else}
  <Leerzustand
    symbol="document"
    text={suche ? `Nichts gefunden für „${suche}"` : "Noch keine Dokumente"}
  />
{/if}

