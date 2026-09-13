<script lang="ts">
  /**
   * Heute. Die Startseite.
   *
   * Nicht vier gleiche Kacheln, sondern der Tag: was ansteht, was dran
   * ist, und darunter die Zahlen der Bereiche in einem Blick. Jede Zeile
   * führt dorthin, wo mehr steht.
   */
  import { onMount } from "svelte";
  import { link } from "svelte-spa-router";
  import { api } from "../lib/api";
  import type { Kachel, KalenderTermin, Eintrag, Eigenschaft } from "../lib/types";
  import { heute as heuteTag, tagPlus, langesDatum, uhrzeit, gruss, tagwort } from "../lib/datum";
  import { farbeVon } from "../lib/sammlung.svelte";
  import { einstellungen } from "../lib/stores.svelte";
  import Seitenkopf from "../komponenten/Seitenkopf.svelte";
  import Abschnitt from "../komponenten/Abschnitt.svelte";
  import Zeile from "../komponenten/Zeile.svelte";
  import Knopf from "../komponenten/Knopf.svelte";
  import Fehlerhinweis from "../komponenten/Fehlerhinweis.svelte";
  import Symbol from "../komponenten/Symbol.svelte";
  import Zaehlzahl from "../komponenten/Zaehlzahl.svelte";

  let kacheln = $state<Kachel[]>([]);
  let termineHeute = $state<KalenderTermin[]>([]);
  let termineMorgen = $state<KalenderTermin[]>([]);
  let offene = $state<Eintrag[]>([]);
  let eigenschaften = $state<Eigenschaft[]>([]);
  let laedt = $state(true);
  let sammelt = $state(false);
  let fehler = $state("");

  const tag = heuteTag();
  const vorname = $derived((einstellungen.owner || "Mia").split(" ")[0]);
  const jetzt = new Date();

  // Termine, die noch kommen, zuerst; vergangene bleiben, aber gedämpft.
  const naechster = $derived(
    termineHeute.find((t) => !t.allDay && new Date(t.start) > jetzt) ?? null,
  );

  function vorbei(t: KalenderTermin): boolean {
    if (t.allDay) return false;
    const ende = t.end ? new Date(t.end) : new Date(t.start);
    return ende < jetzt;
  }

  async function laden() {
    try {
      const [u, th, tm, s] = await Promise.all([
        api.uebersicht(),
        api.termine(tag, tag),
        api.termine(tagPlus(tag, 1), tagPlus(tag, 1)),
        api.sammlung(),
      ]);
      kacheln = u.kacheln;
      termineHeute = th.termine.filter((t) => !t.eintrag_id);
      termineMorgen = tm.termine.filter((t) => !t.eintrag_id);
      eigenschaften = s.eigenschaften;
      offene = s.eintraege
        .filter((e) => !e.archiviert && e.eigenschaften.status !== "fertig")
        .sort((a, b) => (a.datum || "9") .localeCompare(b.datum || "9"))
        .slice(0, 6);
      fehler = "";
    } catch (e) {
      fehler = e instanceof Error ? e.message : "Nicht erreichbar";
    } finally {
      laedt = false;
    }
  }

  async function aktualisieren() {
    sammelt = true;
    try {
      await api.sammeln();
      await laden();
    } catch {
      fehler = "Sammeln fehlgeschlagen";
    } finally {
      sammelt = false;
    }
  }

  const gesundheit = $derived(kacheln.find((k) => k.key === "gesundheit"));
  const homelab = $derived(kacheln.find((k) => k.key === "homelab"));
  const dokumente = $derived(kacheln.find((k) => k.key === "dokumente"));

  const gewicht = $derived.by(() => {
    const roh = gesundheit?.lead?.display;
    const t = roh?.match(/^(\d+(?:[.,]\d+)?)\s*(.*)$/);
    return t ? { wert: parseFloat(t[1].replace(",", ".")), einheit: t[2] } : null;
  });

  const homelabGut = $derived(!!homelab?.lead && !homelab.lead.lang);
  const homelabVerfuegbarkeit = $derived(
    homelab?.details.find((d) => d.label.startsWith("Verfügbarkeit"))?.display ?? "",
  );
  const statusProp = $derived(eigenschaften.find((p) => p.key === "status"));

  onMount(laden);
</script>

<Seitenkopf ueberzeile={langesDatum(tag)} titel="{gruss()}, {vorname}">
  {#snippet werkzeuge()}
    <Knopf symbol="refresh" beschriftung="Aktualisieren" klick={aktualisieren} dreht={sammelt} />
  {/snippet}
</Seitenkopf>

{#if fehler}
  <Fehlerhinweis text={fehler} />
{/if}

<!-- Der nächste Termin, groß. Das ist die eine Zahl, die morgens zählt. -->
{#if naechster}
  <a
    href="/termine"
    use:link
    class="karte auftauchen mb-6 flex items-center gap-4 px-4 py-3.5 transition-colors
           duration-150 hover:bg-erhoben"
  >
    <span class="ziffern anzeige text-[1.75rem] leading-none" style="color: {naechster.farbe}">
      {uhrzeit(naechster.start)}
    </span>
    <span class="min-w-0 flex-1">
      <span class="block truncate text-[0.9375rem] font-semibold">{naechster.title}</span>
      <span class="block text-[0.8125rem] text-gedaempft">
        als Nächstes{naechster.end ? `, bis ${uhrzeit(naechster.end)}` : ""}
      </span>
    </span>
    <span class="text-leise"><Symbol name="chevron-right" groesse={16} /></span>
  </a>
{/if}

<!-- Heute -->
<Abschnitt titel={termineHeute.length ? `Heute, ${termineHeute.length} Termine` : "Heute"}>
  {#snippet aktion()}
    <a href="/termine" use:link class="text-xs font-medium text-akzent">Kalender</a>
  {/snippet}

  {#if termineHeute.length}
    <ul class="m-0 list-none p-0">
      {#each termineHeute as t, i (t.id)}
        <li
          class="auftauchen flex items-center gap-3 border-b border-linie-weich px-3.5 py-2.5 last:border-0"
          class:opacity-45={vorbei(t)}
          style="animation-delay: {Math.min(i, 8) * 30}ms"
        >
          <span class="ziffern w-12 shrink-0 text-[0.8125rem] text-gedaempft" class:text-[0.6875rem]={t.allDay}>
            {t.allDay ? "ganztags" : uhrzeit(t.start)}
          </span>
          <span class="h-5 w-[3px] shrink-0 rounded-full" style="background: {t.farbe}"></span>
          <span class="min-w-0 flex-1 truncate text-[0.9375rem]">{t.title}</span>
          {#if t.end && !t.allDay}
            <span class="ziffern shrink-0 text-xs text-leise">{uhrzeit(t.end)}</span>
          {/if}
        </li>
      {/each}
    </ul>
  {:else if !laedt}
    <p class="m-0 px-3.5 py-4 text-sm text-gedaempft">Nichts eingetragen. Ein freier Tag.</p>
  {:else}
    <div class="h-24"></div>
  {/if}
</Abschnitt>

<!-- Offen: die eigenen Einträge, die noch nicht fertig sind -->
{#if offene.length}
  <Abschnitt titel="Offen">
    {#snippet aktion()}
      <a href="/seite/1" use:link class="text-xs font-medium text-akzent">Alle</a>
    {/snippet}
    <ul class="m-0 list-none p-0">
      {#each offene as e (e.id)}
        {@const status = e.eigenschaften.status ?? ""}
        <li class="border-b border-linie-weich last:border-0">
          <a
            href="/seite/{e.page_id || 1}"
            use:link
            class="flex items-center gap-3 px-3.5 py-2.5 transition-colors duration-150 hover:bg-erhoben"
          >
            <span
              class="size-2.5 shrink-0 rounded-full"
              style="background: {farbeVon(statusProp, status)}"
            ></span>
            <span class="min-w-0 flex-1 truncate text-[0.9375rem]">{e.titel}</span>
            {#if e.datum}
              <span
                class="ziffern shrink-0 text-xs"
                class:text-schlecht={e.datum < tag}
                class:text-gedaempft={e.datum >= tag}
              >
                {tagwort(e.datum)}
              </span>
            {/if}
          </a>
        </li>
      {/each}
    </ul>
  </Abschnitt>
{/if}

<!-- Morgen, kompakt -->
{#if termineMorgen.length}
  <Abschnitt titel="Morgen">
    <ul class="m-0 list-none p-0">
      {#each termineMorgen.slice(0, 4) as t (t.id)}
        <li class="flex items-center gap-3 border-b border-linie-weich px-3.5 py-2 last:border-0">
          <span class="ziffern w-12 shrink-0 text-[0.8125rem] text-gedaempft" class:text-[0.6875rem]={t.allDay}>
            {t.allDay ? "ganztags" : uhrzeit(t.start)}
          </span>
          <span class="size-1.5 shrink-0 rounded-full" style="background: {t.farbe}"></span>
          <span class="min-w-0 flex-1 truncate text-[0.875rem] text-gedaempft">{t.title}</span>
        </li>
      {/each}
      {#if termineMorgen.length > 4}
        <li class="px-3.5 py-2 text-xs text-leise">und {termineMorgen.length - 4} weitere</li>
      {/if}
    </ul>
  </Abschnitt>
{/if}

<!-- Die Bereiche: je eine Zahl -->
<Abschnitt titel="Bereiche">
  <div class="grid grid-cols-2 gap-px bg-linie-weich sm:grid-cols-3">
    <a
      href="/gesundheit"
      use:link
      class="flex flex-col gap-1 bg-flaeche p-3.5 transition-colors duration-150 hover:bg-erhoben"
    >
      <span class="flex items-center gap-1.5 text-xs font-medium text-gedaempft">
        <Symbol name="heart" groesse={14} />
        Gewicht
      </span>
      <span class="anzeige ziffern text-[1.5rem] leading-none">
        {#if gewicht}
          <Zaehlzahl wert={gewicht.wert} einheit={gewicht.einheit} />
        {:else}
          <span class="text-leise">·</span>
        {/if}
      </span>
      {#if gesundheit?.caption?.display}
        <span class="flex items-center gap-1 text-xs text-gedaempft">
          {#if gesundheit.caption.trend}
            <span class={gesundheit.caption.trend === "down" ? "text-gut" : "text-warn"}>
              <Symbol
                name={gesundheit.caption.trend === "down" ? "arrow-down" : "arrow-up"}
                groesse={12}
              />
            </span>
          {/if}
          {gesundheit.caption.display}
        </span>
      {/if}
    </a>

    <a
      href="/homelab"
      use:link
      class="flex flex-col gap-1 bg-flaeche p-3.5 transition-colors duration-150 hover:bg-erhoben"
    >
      <span class="flex items-center gap-1.5 text-xs font-medium text-gedaempft">
        <Symbol name="server" groesse={14} />
        Homelab
      </span>
      <span class="flex items-center gap-2">
        <span
          class="size-2.5 rounded-full"
          class:bg-gut={homelabGut}
          class:bg-schlecht={homelab?.lead && !homelabGut}
          class:bg-leise={!homelab?.lead}
        ></span>
        <span class="anzeige ziffern text-[1.5rem] leading-none">
          {homelabVerfuegbarkeit || "·"}
        </span>
      </span>
      <span class="truncate text-xs text-gedaempft">
        {homelab?.lead?.display ?? "keine Daten"}
      </span>
    </a>

    <a
      href="/dokumente"
      use:link
      class="col-span-2 flex flex-col gap-1 bg-flaeche p-3.5 transition-colors duration-150
             hover:bg-erhoben sm:col-span-1"
    >
      <span class="flex items-center gap-1.5 text-xs font-medium text-gedaempft">
        <Symbol name="document" groesse={14} />
        Dokumente
      </span>
      <span class="anzeige ziffern text-[1.5rem] leading-none">
        {dokumente?.lead?.display ?? "·"}
      </span>
      <span class="truncate text-xs text-gedaempft">
        {dokumente?.caption?.display ?? ""}
      </span>
    </a>
  </div>
</Abschnitt>
