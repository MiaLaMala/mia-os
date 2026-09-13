<script lang="ts">
  /**
   * Suche über alles. Ein Feld für Seiten, Einträge, Termine, Dokumente.
   *
   * Desktop: Cmd+K oder Ctrl+K. Handy: Lupe im "Mehr"-Blatt. Ergebnisse in
   * Gruppen, Pfeiltasten und Enter gehen. Dokumente tauchen nur auf Suche
   * auf, nie als Vorschlag: im Index stehen Arztbriefe.
   */
  import { tick } from "svelte";
  import { push } from "svelte-spa-router";
  import { api } from "../lib/api";
  import type { Suchergebnis } from "../lib/types";
  import { tagwort, uhrzeit } from "../lib/datum";
  import Blatt from "./Blatt.svelte";
  import Symbol from "./Symbol.svelte";

  let { offen, schliessen }: { offen: boolean; schliessen: () => void } = $props();

  let frage = $state("");
  let ergebnis = $state<Suchergebnis | null>(null);
  let sucht = $state(false);
  let markiert = $state(0);
  let feld: HTMLInputElement | undefined = $state();
  let timer: ReturnType<typeof setTimeout>;

  interface Treffer {
    gruppe: string;
    titel: string;
    neben: string;
    symbol: string;
    farbe?: string;
    ziel: string;
    extern?: boolean;
  }

  const treffer = $derived.by((): Treffer[] => {
    if (!ergebnis) return [];
    const liste: Treffer[] = [];
    for (const s of ergebnis.seiten)
      liste.push({ gruppe: "Seiten", titel: s.titel, neben: "", symbol: s.symbol, ziel: `/seite/${s.id}` });
    for (const e of ergebnis.eintraege)
      liste.push({
        gruppe: "Einträge",
        titel: e.titel,
        neben: e.datum ? tagwort(e.datum) : e.status,
        symbol: "check",
        ziel: `/seite/${e.page_id || 1}`,
      });
    for (const t of ergebnis.termine)
      liste.push({
        gruppe: "Termine",
        titel: t.titel,
        neben: `${tagwort(t.start.slice(0, 10))}${t.ganztags ? "" : ", " + uhrzeit(t.start)}`,
        symbol: "calendar",
        farbe: t.farbe,
        ziel: `/termine?tag=${t.start.slice(0, 10)}`,
      });
    for (const d of ergebnis.dokumente)
      liste.push({
        gruppe: "Dokumente",
        titel: d.name,
        // Die Fundstelle schlägt den Ordner: wer nach einem Aktenzeichen
        // sucht, will sehen, dass es auf dem Blatt steht.
        //
        // Hier beginnt sie beim Treffer selbst, anders als auf der
        // Dokumentenseite. Am gerenderten Bild gefunden: neben dem Dateinamen
        // bleibt so wenig Breite, dass der Anlauf davor genau den Wert
        // abschnitt, wegen dem gesucht wurde („Aktenzeichen: 4…“).
        neben: fundstelle(d.stelle) || d.folder,
        symbol: "document",
        ziel: `/bearbeiten/${d.id}`,
        extern: true,
      });
    return liste;
  });

  /**
   * Die Fundstelle ab dem ersten Treffer, ohne die Markierungen.
   *
   * Hervorheben geht in dieser einzeiligen Nebenspalte nicht, die Klammern
   * aus SQLite wären dort sichtbarer Müll.
   */
  function fundstelle(stelle: string | undefined): string {
    if (!stelle) return "";
    const ab = stelle.indexOf("[");
    return (ab > 0 ? stelle.slice(ab) : stelle).replace(/[[\]]/g, "");
  }

  const gruppen = $derived.by(() => {
    const g: { name: string; ab: number; bis: number }[] = [];
    treffer.forEach((t, i) => {
      const letzte = g[g.length - 1];
      if (letzte && letzte.name === t.gruppe) letzte.bis = i;
      else g.push({ name: t.gruppe, ab: i, bis: i });
    });
    return g;
  });

  $effect(() => {
    if (offen) {
      frage = "";
      ergebnis = null;
      markiert = 0;
      tick().then(() => feld?.focus());
    }
  });

  function getippt() {
    clearTimeout(timer);
    const q = frage.trim();
    if (q.length < 2) {
      ergebnis = null;
      return;
    }
    timer = setTimeout(async () => {
      sucht = true;
      try {
        ergebnis = await api.suche(q);
        markiert = 0;
      } finally {
        sucht = false;
      }
    }, 180);
  }

  function oeffnen(t: Treffer) {
    schliessen();
    if (t.extern) window.location.href = t.ziel;
    else push(t.ziel);
  }

  function taste(e: KeyboardEvent) {
    if (!treffer.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      markiert = (markiert + 1) % treffer.length;
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      markiert = (markiert - 1 + treffer.length) % treffer.length;
    } else if (e.key === "Enter") {
      e.preventDefault();
      oeffnen(treffer[markiert]);
    }
  }
</script>

<Blatt {offen} {schliessen} titel="Suche" breit>
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
        onkeydown={taste}
        placeholder="Seiten, Einträge, Termine, Dokumente"
        autocomplete="off"
        enterkeyhint="search"
        class="w-full border-0 bg-transparent text-[1rem] outline-none placeholder:text-leise"
      />
      {#if frage}
        <button
          type="button"
          onclick={() => {
            frage = "";
            ergebnis = null;
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

  <div data-blatt-inhalt class="min-h-0 flex-1 overflow-y-auto px-3 pb-[max(1rem,env(safe-area-inset-bottom))] pt-2 sm:px-4">
    {#if treffer.length}
      {#each gruppen as g (g.name)}
        <p class="m-0 px-1 pb-1 pt-3 text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-leise">
          {g.name}
        </p>
        <ul class="karte m-0 list-none overflow-hidden p-0">
          {#each treffer.slice(g.ab, g.bis + 1) as t, j (g.ab + j)}
            {@const i = g.ab + j}
            <li class="border-b border-linie-weich last:border-0">
              <button
                type="button"
                onclick={() => oeffnen(t)}
                onmouseenter={() => (markiert = i)}
                class="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors"
                class:bg-erhoben={markiert === i}
              >
                <span class="shrink-0" style={t.farbe ? `color: ${t.farbe}` : ""} class:text-gedaempft={!t.farbe}>
                  <Symbol name={t.symbol} groesse={16} />
                </span>
                <span class="min-w-0 flex-1 truncate text-[0.9375rem]">{t.titel}</span>
                {#if t.neben}
                  <span class="max-w-[45%] shrink-0 truncate text-xs text-gedaempft">{t.neben}</span>
                {/if}
              </button>
            </li>
          {/each}
        </ul>
      {/each}
    {:else if frage.trim().length >= 2 && ergebnis && !sucht}
      <p class="m-0 px-1 py-6 text-center text-sm text-gedaempft">Nichts gefunden.</p>
    {:else if !frage}
      <p class="m-0 px-1 py-5 text-center text-xs text-leise">
        Tippen, um zu suchen. Pfeile und Enter zum Öffnen.
      </p>
    {/if}
  </div>
</Blatt>
