<script lang="ts">
  /**
   * Gesundheit: Gewicht groß, Verlauf als Linie, Einzelheiten als Zeilen.
   */
  import { onMount } from "svelte";
  import { api } from "../lib/api";
  import type { Kachel, Mahlzeit, Zutat } from "../lib/types";
  import Seitenkopf from "../komponenten/Seitenkopf.svelte";
  import Abschnitt from "../komponenten/Abschnitt.svelte";
  import Knopf from "../komponenten/Knopf.svelte";
  import Ladezustand from "../komponenten/Ladezustand.svelte";
  import Fehlerhinweis from "../komponenten/Fehlerhinweis.svelte";
  import Leerzustand from "../komponenten/Leerzustand.svelte";
  import Zaehlzahl from "../komponenten/Zaehlzahl.svelte";
  import Symbol from "../komponenten/Symbol.svelte";

  interface Verlaufspunkt {
    collected_at: string;
    value: number;
  }

  let karte = $state<Kachel | null>(null);
  let verlauf = $state<Verlaufspunkt[]>([]);
  let laedt = $state(true);
  let fehler = $state("");

  // Eintragen: Gewicht und Essen. wger bleibt die Quelle, hier ist nur die Tür.
  let gewichtOffen = $state(false);
  let gewichtText = $state("");
  let gewichtSendet = $state(false);
  let gewichtMeldung = $state("");
  let gewichtOk = $state(false);
  let mahlzeiten = $state<Mahlzeit[]>([]);
  let kcalHeute = $state(0);
  let essenOffen = $state(false);
  let zutatText = $state("");
  let zutaten = $state<Zutat[]>([]);
  let zutat = $state<Zutat | null>(null);
  let grammText = $state("");
  let essenSendet = $state(false);
  let essenMeldung = $state("");
  let essenOk = $state(false);
  let zutatTimer: ReturnType<typeof setTimeout>;

  const leitzahl = $derived.by(() => {
    const roh = karte?.lead?.display;
    if (!roh) return null;
    const t = roh.match(/^(\d+(?:[.,]\d+)?)\s*(.*)$/);
    return t ? { wert: parseFloat(t[1].replace(",", ".")), einheit: t[2] } : null;
  });

  // Linie plus Fläche darunter. Ein Diagrammpaket wäre für 60 Punkte zu viel.
  const kurve = $derived.by(() => {
    if (verlauf.length < 2) return null;
    const werte = verlauf.map((p) => p.value);
    const min = Math.min(...werte);
    const max = Math.max(...werte);
    const spanne = max - min || 1;
    const punkte = werte.map((w, i) => ({
      x: (i / (werte.length - 1)) * 100,
      y: 34 - ((w - min) / spanne) * 28,
    }));
    const linie = punkte.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");
    const flaeche = `${linie} L100,40 L0,40 Z`;
    return { linie, flaeche, min, max, letzter: punkte[punkte.length - 1] };
  });

  const zeitraum = $derived.by(() => {
    if (verlauf.length < 2) return "";
    const a = new Date(verlauf[0].collected_at);
    const b = new Date(verlauf[verlauf.length - 1].collected_at);
    const f = (d: Date) => d.toLocaleDateString("de-DE", { day: "numeric", month: "short" });
    return `${f(a)} bis ${f(b)}`;
  });

  async function laden() {
    try {
      const daten = await api.gesundheit();
      karte = daten.karte;
      verlauf = daten.verlauf;
    } catch (e) {
      fehler = e instanceof Error ? e.message : "Gesundheit nicht erreichbar";
    } finally {
      laedt = false;
    }
    try {
      const h = await api.gegessenHeute();
      mahlzeiten = h.eintraege;
      kcalHeute = h.kcal;
    } catch {
      // Ohne wger bleibt die Liste leer, die Seite laeuft weiter.
    }
  }

  async function gewichtSpeichern() {
    const kg = parseFloat(gewichtText.replace(",", "."));
    if (!kg || gewichtSendet) return;
    gewichtSendet = true;
    gewichtMeldung = "";
    try {
      await api.gewichtSetzen(kg);
      await api.sammeln();
      await laden();
      gewichtOk = true;
      gewichtMeldung = `${kg.toFixed(1).replace(".", ",")} kg gespeichert`;
      gewichtText = "";
      setTimeout(() => {
        gewichtOffen = false;
        gewichtMeldung = "";
      }, 900);
    } catch (e) {
      gewichtOk = false;
      gewichtMeldung = e instanceof Error ? e.message : "Ging nicht";
    } finally {
      gewichtSendet = false;
    }
  }

  function zutatGetippt() {
    clearTimeout(zutatTimer);
    zutat = null;
    zutatTimer = setTimeout(async () => {
      try {
        zutaten = (await api.zutaten(zutatText)).zutaten;
      } catch {
        zutaten = [];
      }
    }, 150);
  }

  async function essenSpeichern() {
    const gramm = parseFloat(grammText.replace(",", "."));
    if (!zutat || !gramm || essenSendet) return;
    essenSendet = true;
    essenMeldung = "";
    try {
      await api.essenSetzen(zutat.id, gramm);
      essenOk = true;
      essenMeldung = `${Math.round(gramm)} g ${zutat.name} eingetragen`;
      zutat = null;
      zutatText = "";
      grammText = "";
      zutaten = [];
      await laden();
      setTimeout(() => (essenMeldung = ""), 1500);
    } catch (e) {
      essenOk = false;
      essenMeldung = e instanceof Error ? e.message : "Ging nicht";
    } finally {
      essenSendet = false;
    }
  }

  onMount(laden);
</script>

<Seitenkopf titel="Gesundheit" untertitel="Gewicht und Ernährung aus wger">
  {#snippet werkzeuge()}
    <Knopf
      symbol="plus"
      beschriftung="Gewicht eintragen"
      text="Gewicht"
      aktiv={gewichtOffen}
      klick={() => (gewichtOffen = !gewichtOffen)}
    />
  {/snippet}
</Seitenkopf>

{#if fehler}
  <Fehlerhinweis text={fehler} />
{/if}

{#if gewichtOffen}
  <form
    onsubmit={(e) => {
      e.preventDefault();
      gewichtSpeichern();
    }}
    class="karte mb-6 flex items-center gap-3 px-4 py-3"
  >
    <input
      bind:value={gewichtText}
      inputmode="decimal"
      placeholder={leitzahl ? leitzahl.wert.toFixed(1).replace(".", ",") : "88,4"}
      aria-label="Gewicht in Kilogramm"
      class="ziffern w-24 border-0 bg-transparent text-[1.5rem] outline-none placeholder:text-leise"
    />
    <span class="text-gedaempft">kg</span>
    <span class="flex-1 text-sm" class:text-gut={gewichtOk} class:text-fehler={!gewichtOk}>
      {gewichtMeldung}
    </span>
    <button
      type="submit"
      disabled={!gewichtText || gewichtSendet}
      class="rounded-full bg-akzent px-3.5 py-1.5 text-sm font-medium text-akzent-text
             transition-opacity disabled:opacity-30"
    >
      {gewichtSendet ? "…" : "Heute"}
    </button>
  </form>
{/if}

{#if laedt}
  <Ladezustand />
{:else if karte?.has_data}
  <!-- Die Zahl -->
  <div class="karte mb-6 overflow-hidden">
    <div class="px-5 pt-5">
      <p class="m-0 text-[0.8125rem] font-medium text-gedaempft">
        {karte.lead?.label ?? "Gewicht"}
      </p>
      <p class="anzeige m-0 mt-1 text-[2.75rem] leading-none">
        {#if leitzahl}
          <Zaehlzahl wert={leitzahl.wert} einheit={leitzahl.einheit} />
        {:else}
          {karte.lead?.display}
        {/if}
      </p>
      {#if karte.caption?.display}
        <p class="mt-2 flex items-center gap-1.5 text-sm text-gedaempft">
          {#if karte.caption.trend}
            <span
              class="grid size-5 place-items-center rounded-full"
              class:text-gut={karte.caption.trend === "down"}
              class:text-achtung={karte.caption.trend === "up"}
              style="background: color-mix(in srgb, currentColor 15%, transparent)"
            >
              <Symbol
                name={karte.caption.trend === "down" ? "arrow-down" : "arrow-up"}
                groesse={12}
              />
            </span>
          {/if}
          {karte.caption.display} seit der letzten Messung
        </p>
      {/if}
    </div>

    {#if kurve}
      <div class="relative mt-4">
        <svg viewBox="0 0 100 40" preserveAspectRatio="none" class="block h-28 w-full" aria-hidden="true">
          <defs>
            <linearGradient id="gewicht-verlauf" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stop-color="var(--color-akzent)" stop-opacity="0.28" />
              <stop offset="1" stop-color="var(--color-akzent)" stop-opacity="0" />
            </linearGradient>
          </defs>
          <path d={kurve.flaeche} fill="url(#gewicht-verlauf)" />
          <path
            d={kurve.linie}
            fill="none"
            stroke="var(--color-akzent)"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
            vector-effect="non-scaling-stroke"
            pathLength="1"
            class="motion-safe:animate-[zeichnen_.9s_var(--ease-ruhig)]"
            style="stroke-dasharray: 1; stroke-dashoffset: 0"
          />
        </svg>
        <div class="flex items-center justify-between px-5 pb-3 text-[0.6875rem] text-leise">
          <span class="ziffern">{kurve.min.toFixed(1).replace(".", ",")} bis {kurve.max.toFixed(1).replace(".", ",")} kg</span>
          <span>{zeitraum}</span>
        </div>
      </div>
    {:else}
      <div class="h-4"></div>
    {/if}
  </div>

  {#if karte.details.length}
    <Abschnitt titel="Einzelheiten">
      <dl class="m-0">
        {#each karte.details as d (d.key)}
          <div class="flex items-baseline justify-between gap-4 border-b border-linie-weich px-3.5 py-3 last:border-0">
            <dt class="text-[0.9375rem]">{d.label}</dt>
            <dd class="ziffern m-0 text-[0.9375rem] text-gedaempft">{d.display}</dd>
          </div>
        {/each}
      </dl>
    </Abschnitt>
  {/if}

  <!-- Essen heute -->
  <div class="mt-6">
    <Abschnitt titel={kcalHeute ? `Heute gegessen, ${kcalHeute} kcal` : "Heute gegessen"}>
      {#snippet aktion()}
        <button
          type="button"
          onclick={() => (essenOffen = !essenOffen)}
          class="text-xs font-medium text-akzent"
        >
          {essenOffen ? "Fertig" : "Eintragen"}
        </button>
      {/snippet}

      {#if essenOffen}
        <form
          onsubmit={(e) => {
            e.preventDefault();
            essenSpeichern();
          }}
          class="border-b border-linie-weich px-3.5 py-3"
        >
          <div class="flex items-center gap-2">
            <input
              bind:value={zutatText}
              oninput={zutatGetippt}
              onfocus={zutatGetippt}
              placeholder="Was?"
              autocomplete="off"
              class="h-9 min-w-0 flex-1 rounded-element bg-erhoben px-3 text-sm outline-none
                     placeholder:text-leise focus:ring-2 focus:ring-akzent/60"
            />
            <input
              bind:value={grammText}
              inputmode="numeric"
              placeholder="g"
              aria-label="Gramm"
              class="ziffern h-9 w-16 rounded-element bg-erhoben px-3 text-sm outline-none
                     placeholder:text-leise focus:ring-2 focus:ring-akzent/60"
            />
            <button
              type="submit"
              disabled={!zutat || !grammText || essenSendet}
              aria-label="Eintragen"
              class="grid size-9 shrink-0 place-items-center rounded-full bg-akzent text-akzent-text
                     transition-opacity disabled:opacity-30"
            >
              <Symbol name="check" groesse={16} />
            </button>
          </div>
          {#if zutaten.length && !zutat}
            <ul class="m-0 mt-2 max-h-48 list-none overflow-y-auto rounded-element bg-erhoben p-1">
              {#each zutaten as z (z.id)}
                <li>
                  <button
                    type="button"
                    onclick={() => {
                      zutat = z;
                      zutatText = z.name;
                    }}
                    class="flex w-full items-center justify-between gap-3 rounded-klein px-2.5 py-1.5
                           text-left text-sm transition-colors hover:bg-erhoben-2"
                  >
                    <span class="truncate">{z.name}</span>
                    <span class="ziffern shrink-0 text-xs text-gedaempft">{z.kcal} kcal</span>
                  </button>
                </li>
              {/each}
            </ul>
          {:else if zutatText.length > 1 && !zutaten.length && !zutat}
            <p class="m-0 mt-2 text-xs text-gedaempft">Nichts in wger gefunden. Neue Zutaten dort anlegen.</p>
          {/if}
          {#if essenMeldung}
            <p class="m-0 mt-2 text-xs" class:text-gut={essenOk} class:text-fehler={!essenOk}>
              {essenMeldung}
            </p>
          {/if}
        </form>
      {/if}

      {#if mahlzeiten.length}
        <ul class="m-0 list-none p-0">
          {#each mahlzeiten as m (m.id)}
            <li class="flex items-center gap-3 border-b border-linie-weich px-3.5 py-2.5 last:border-0">
              <span class="ziffern w-12 shrink-0 text-[0.8125rem] text-gedaempft">{m.zeit}</span>
              <span class="min-w-0 flex-1 truncate text-[0.9375rem]">{m.name}</span>
              <span class="ziffern shrink-0 text-xs text-gedaempft">{Math.round(m.gramm)} g</span>
              <span class="ziffern w-14 shrink-0 text-right text-xs text-gedaempft">{m.kcal} kcal</span>
            </li>
          {/each}
        </ul>
      {:else if !essenOffen}
        <p class="m-0 px-3.5 py-4 text-sm text-gedaempft">
          Noch nichts eingetragen. Oben „Eintragen" oder unten das Plus: „Skyr 200g".
        </p>
      {/if}
    </Abschnitt>
  </div>
{:else}
  <Leerzustand text="Noch keine Daten aus wger" symbol="heart" />
{/if}

<style>
  @keyframes zeichnen {
    from {
      stroke-dashoffset: 1;
    }
    to {
      stroke-dashoffset: 0;
    }
  }
</style>
