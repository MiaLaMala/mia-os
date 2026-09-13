<script lang="ts">
  /**
   * Eine Seite. Das Grundelement, wie in Notion.
   *
   * Brotkrumen, großer Titel, freier Text, darunter die Sammlung mit
   * Ansichtswahl, dann Unterseiten. Alles direkt bearbeitbar.
   */
  import { onMount } from "svelte";
  import { fade } from "svelte/transition";
  import { link, push } from "svelte-spa-router";
  import { api } from "../lib/api";
  import { seiten } from "../lib/seiten.svelte";
  import { sammlung } from "../lib/sammlung.svelte";
  import type { Eintrag, Seite } from "../lib/types";
  import Ladezustand from "../komponenten/Ladezustand.svelte";
  import Fehlerhinweis from "../komponenten/Fehlerhinweis.svelte";
  import Leerzustand from "../komponenten/Leerzustand.svelte";
  import Abschnitt from "../komponenten/Abschnitt.svelte";
  import Zeile from "../komponenten/Zeile.svelte";
  import Segment from "../komponenten/Segment.svelte";
  import AnsichtTabelle from "../komponenten/AnsichtTabelle.svelte";
  import AnsichtBoard from "../komponenten/AnsichtBoard.svelte";
  import AnsichtListe from "../komponenten/AnsichtListe.svelte";
  import Eintragsblatt from "../komponenten/Eintragsblatt.svelte";
  import Symbol from "../komponenten/Symbol.svelte";

  let { params }: { params: { id: string } } = $props();

  const ANSICHTEN = [
    { key: "liste", name: "Liste" },
    { key: "board", name: "Board" },
    { key: "tabelle", name: "Tabelle" },
  ];

  let seite = $state<Seite | null>(null);
  let weg = $state<{ id: number; titel: string }[]>([]);
  let unterseiten = $state<Seite[]>([]);
  let laedt = $state(true);
  let fehler = $state("");
  let titel = $state("");
  let inhalt = $state("");
  let gesichert = $state(false);
  let neuerEintrag = $state("");
  let offener = $state<Eintrag | null>(null);
  let menueOffen = $state(false);
  let timer: ReturnType<typeof setTimeout>;
  let textfeld: HTMLTextAreaElement | undefined = $state();

  const seitenId = $derived(Number(params.id));
  const aktueller = $derived(
    offener ? (sammlung.eintraege.find((e) => e.id === offener!.id) ?? offener) : null,
  );
  const auswahlProps = $derived(sammlung.eigenschaften.filter((p) => p.art === "auswahl"));
  const offen = $derived(
    sammlung.eintraege.filter((e) => e.eigenschaften.status !== "fertig").length,
  );

  async function laden() {
    laedt = true;
    try {
      const daten = await api.seite(seitenId);
      seite = daten.seite;
      weg = daten.weg;
      unterseiten = daten.unterseiten;
      titel = daten.seite.titel;
      inhalt = daten.seite.inhalt;
      sammlung.setzeEintraege(daten.eintraege, daten.eigenschaften, daten.anhaenge);
      fehler = "";
      requestAnimationFrame(hoeheAnpassen);
    } catch (e) {
      fehler = e instanceof Error ? e.message : "Seite nicht erreichbar";
    } finally {
      laedt = false;
    }
  }

  $effect(() => {
    if (seitenId) laden();
  });

  function hoeheAnpassen() {
    if (!textfeld) return;
    textfeld.style.height = "auto";
    textfeld.style.height = `${textfeld.scrollHeight}px`;
  }

  function getippt(feld: "titel" | "inhalt") {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const wert = feld === "titel" ? titel.trim() : inhalt;
      if (feld === "titel" && !wert) return;
      await seiten.aendern(seitenId, { [feld]: wert });
      gesichert = true;
      setTimeout(() => (gesichert = false), 1200);
    }, 600);
  }

  async function eintragAnlegen() {
    const t = neuerEintrag.trim();
    if (!t) return;
    neuerEintrag = "";
    offener = await sammlung.anlegen({ titel: t, page_id: seitenId });
  }

  async function sammlungAnschalten() {
    await seiten.aendern(seitenId, { hat_sammlung: true });
    if (seite) seite = { ...seite, hat_sammlung: true };
  }

  async function unterseiteAnlegen() {
    menueOffen = false;
    const neu = await seiten.anlegen("Neue Seite", seitenId, false);
    push(`/seite/${neu.id}`);
  }

  async function loeschen() {
    menueOffen = false;
    if (!confirm(`„${seite?.titel}" und alle Unterseiten löschen?`)) return;
    await seiten.loeschen(seitenId);
    push(weg.length > 1 ? `/seite/${weg[weg.length - 2].id}` : "/");
  }

  function wechseln(key: string) {
    if (seite) seite = { ...seite, ansicht: key };
    seiten.aendern(seitenId, { ansicht: key });
  }

  onMount(() => seiten.laden());
</script>

{#if fehler}
  <Fehlerhinweis text={fehler} />
{/if}

{#if laedt && !seite}
  <Ladezustand />
{:else if seite}
  <!-- Brotkrumen und Menü -->
  <div class="mb-3 flex items-center gap-1 text-[0.8125rem] text-gedaempft">
    <a href="/" use:link class="transition-colors hover:text-text">Seiten</a>
    {#each weg.slice(0, -1) as teil (teil.id)}
      <span class="text-leise"><Symbol name="chevron-right" groesse={13} /></span>
      <a href="/seite/{teil.id}" use:link class="truncate transition-colors hover:text-text">
        {teil.titel}
      </a>
    {/each}

    <span class="relative ml-auto">
      <button
        type="button"
        onclick={() => (menueOffen = !menueOffen)}
        aria-label="Seitenmenü"
        aria-expanded={menueOffen}
        class="grid size-8 place-items-center rounded-full text-gedaempft transition-colors
               hover:bg-erhoben hover:text-text"
      >
        <Symbol name="more" groesse={18} />
      </button>
      {#if menueOffen}
        <div
          class="absolute right-0 top-full z-20 mt-1 w-48 overflow-hidden rounded-element bg-erhoben
                 p-1 shadow-menue"
          transition:fade={{ duration: 120 }}
        >
          <button
            type="button"
            onclick={unterseiteAnlegen}
            class="flex w-full items-center gap-2 rounded-klein px-2.5 py-2 text-left text-sm
                   text-text transition-colors hover:bg-erhoben-2"
          >
            <Symbol name="plus" groesse={15} />
            Unterseite
          </button>
          {#if !seite.hat_sammlung}
            <button
              type="button"
              onclick={() => {
                menueOffen = false;
                sammlungAnschalten();
              }}
              class="flex w-full items-center gap-2 rounded-klein px-2.5 py-2 text-left text-sm
                     text-text transition-colors hover:bg-erhoben-2"
            >
              <Symbol name="table" groesse={15} />
              Sammlung hinzufügen
            </button>
          {/if}
          <button
            type="button"
            onclick={loeschen}
            class="flex w-full items-center gap-2 rounded-klein px-2.5 py-2 text-left text-sm
                   text-fehler transition-colors hover:bg-erhoben-2"
          >
            <Symbol name="trash" groesse={15} />
            Seite löschen
          </button>
        </div>
      {/if}
    </span>
  </div>

  {#if menueOffen}
    <div class="fixed inset-0 z-10" onclick={() => (menueOffen = false)} role="presentation"></div>
  {/if}

  <!-- Titel -->
  <div class="mb-1 flex items-start gap-3">
    <span class="mt-1.5 shrink-0 text-gedaempft"><Symbol name={seite.symbol} groesse={26} /></span>
    <input
      bind:value={titel}
      oninput={() => getippt("titel")}
      class="anzeige min-w-0 flex-1 border-0 bg-transparent text-[1.75rem] leading-tight outline-none
             placeholder:text-leise lg:text-[2rem]"
      placeholder="Ohne Titel"
    />
    {#if gesichert}
      <span class="mt-3 shrink-0 text-xs text-gut" transition:fade={{ duration: 150 }}>
        gespeichert
      </span>
    {/if}
  </div>

  <!-- Freier Text -->
  <textarea
    bind:this={textfeld}
    bind:value={inhalt}
    rows="1"
    placeholder="Schreib etwas..."
    oninput={() => {
      getippt("inhalt");
      hoeheAnpassen();
    }}
    class="mb-6 w-full resize-none overflow-hidden border-0 bg-transparent pl-[2.4rem] text-[0.9375rem]
           leading-relaxed outline-none placeholder:text-leise"
  ></textarea>

  <!-- Sammlung -->
  {#if seite.hat_sammlung}
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <Segment optionen={ANSICHTEN} wert={seite.ansicht} waehlen={wechseln} />

      {#if seite.ansicht !== "tabelle" && auswahlProps.length}
        <label class="ml-auto flex items-center gap-1 text-xs text-gedaempft">
          <Symbol name="filter" groesse={13} />
          <select
            value={seite.gruppe_nach}
            onchange={(e) => seiten.aendern(seitenId, { gruppe_nach: e.currentTarget.value })}
            aria-label="Gruppieren nach"
            class="cursor-pointer border-0 bg-transparent text-xs text-gedaempft outline-none hover:text-text"
          >
            {#each auswahlProps as p (p.key)}
              <option value={p.key}>nach {p.name}</option>
            {/each}
          </select>
        </label>
      {/if}
      <span class="ziffern text-xs text-leise" class:ml-auto={seite.ansicht === "tabelle" || !auswahlProps.length}>
        {offen} offen
      </span>
    </div>

    <form
      onsubmit={(e) => {
        e.preventDefault();
        eintragAnlegen();
      }}
      class="mb-3 flex h-10 items-center gap-2.5 rounded-element bg-erhoben px-3
             transition-[box-shadow] duration-200 focus-within:ring-2 focus-within:ring-akzent/60"
    >
      <span class="text-gedaempft"><Symbol name="plus" groesse={16} /></span>
      <input
        bind:value={neuerEintrag}
        placeholder="Neuer Eintrag"
        class="w-full border-0 bg-transparent text-[0.9375rem] outline-none placeholder:text-leise"
      />
    </form>

    {#if sammlung.eintraege.length}
      {#key seite.ansicht}
        <div in:fade={{ duration: 180 }}>
          {#if seite.ansicht === "tabelle"}
            <AnsichtTabelle oeffnen={(e) => (offener = e)} />
          {:else if seite.ansicht === "board"}
            <AnsichtBoard gruppeNach={seite.gruppe_nach} oeffnen={(e) => (offener = e)} />
          {:else}
            <AnsichtListe gruppeNach={seite.gruppe_nach} oeffnen={(e) => (offener = e)} />
          {/if}
        </div>
      {/key}
    {:else}
      <Leerzustand text="Noch nichts drin. Oben etwas eintragen." symbol="list" />
    {/if}
  {/if}

  <!-- Unterseiten -->
  {#if unterseiten.length}
    <div class="mt-8">
      <Abschnitt titel="Unterseiten">
        {#each unterseiten as u (u.id)}
          <Zeile titel={u.titel} symbol={u.symbol} href="/seite/{u.id}" />
        {/each}
      </Abschnitt>
    </div>
  {/if}
{/if}

<Eintragsblatt eintrag={aktueller} schliessen={() => (offener = null)} />
