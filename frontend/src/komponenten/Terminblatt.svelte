<script lang="ts">
  /**
   * Was zu einem iCloud-Termin gehört: Zeit, Notiz, Aufgaben.
   *
   * Der Kalender kommt aus iCloud und ist dünn. Also legt Mia OS eigene
   * Informationen daneben, statt so zu tun, als wäre mehr da.
   */
  import { fade, slide } from "svelte/transition";
  import { api } from "../lib/api";
  import Blatt from "./Blatt.svelte";
  import Symbol from "./Symbol.svelte";

  export interface Termin {
    uid: string;
    titel: string;
    beginn: string;
    ende: string;
    ganztags: boolean;
    kalender: string;
    farbe: string;
    datum: string;
  }

  interface Aufgabe {
    id: number;
    titel: string;
    erledigt: boolean;
  }

  let {
    termin,
    schliessen,
    geaendert,
  }: { termin: Termin | null; schliessen: () => void; geaendert: () => void } = $props();

  let notiz = $state("");
  let aufgaben = $state<Aufgabe[]>([]);
  let neueAufgabe = $state("");
  let laedt = $state(false);
  let gesichert = $state(false);
  let schreibTimer: ReturnType<typeof setTimeout>;

  $effect(() => {
    const uid = termin?.uid;
    if (!uid) return;
    laedt = true;
    api
      .terminDetails(uid)
      .then((d) => {
        notiz = d.notiz;
        aufgaben = d.aufgaben;
      })
      .catch(() => {
        notiz = "";
        aufgaben = [];
      })
      .finally(() => (laedt = false));
  });

  function notizGetippt() {
    clearTimeout(schreibTimer);
    schreibTimer = setTimeout(async () => {
      if (!termin) return;
      try {
        await api.notizSichern(termin.uid, notiz);
        gesichert = true;
        setTimeout(() => (gesichert = false), 1400);
        geaendert();
      } catch {
        // beim nächsten Tippen erneut
      }
    }, 600);
  }

  async function aufgabeAnlegen() {
    const titel = neueAufgabe.trim();
    if (!titel || !termin) return;
    neueAufgabe = "";
    try {
      const { aufgabe } = await api.aufgabeAnlegen(titel, termin.uid);
      aufgaben = [...aufgaben, aufgabe];
      geaendert();
    } catch {
      neueAufgabe = titel;
    }
  }

  async function abhaken(a: Aufgabe) {
    const vorher = a.erledigt;
    aufgaben = aufgaben.map((x) => (x.id === a.id ? { ...x, erledigt: !vorher } : x));
    try {
      await api.aufgabeAendern(a.id, { erledigt: !vorher });
      geaendert();
    } catch {
      aufgaben = aufgaben.map((x) => (x.id === a.id ? { ...x, erledigt: vorher } : x));
    }
  }

  async function loeschen(a: Aufgabe) {
    const vorher = aufgaben;
    aufgaben = aufgaben.filter((x) => x.id !== a.id);
    try {
      await api.aufgabeLoeschen(a.id);
      geaendert();
    } catch {
      aufgaben = vorher;
    }
  }

  const offen = $derived(aufgaben.filter((a) => !a.erledigt).length);
</script>

<Blatt offen={!!termin} {schliessen} titel={termin?.titel}>
  {#if termin}
    <!-- Kopf -->
    <div class="flex items-start gap-3 px-5 pb-4 pt-2 sm:pt-5">
      <span class="mt-1 h-9 w-1 shrink-0 rounded-full" style="background: {termin.farbe}"></span>
      <div class="min-w-0 flex-1">
        <h2 class="anzeige m-0 text-[1.375rem] leading-tight">{termin.titel}</h2>
        <p class="ziffern m-0 mt-1 text-sm text-gedaempft">
          {termin.datum}{#if !termin.ganztags}, {termin.beginn} bis {termin.ende}{:else}, ganztägig{/if}
        </p>
        <p class="m-0 mt-0.5 text-xs" style="color: {termin.farbe}">{termin.kalender}</p>
      </div>
      <button
        type="button"
        onclick={schliessen}
        aria-label="Schließen"
        class="grid size-8 shrink-0 place-items-center rounded-full bg-erhoben text-gedaempft
               transition-colors duration-200 hover:text-text"
      >
        <Symbol name="close" groesse={15} />
      </button>
    </div>

    <div data-blatt-inhalt class="min-h-0 flex-1 overflow-y-auto px-5 pb-[max(1.5rem,env(safe-area-inset-bottom))]">
      <!-- Notiz -->
      <div class="mb-1.5 flex items-center justify-between px-1">
        <h3 class="m-0 text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-leise">Notiz</h3>
        {#if gesichert}
          <span class="text-xs text-gut" transition:fade={{ duration: 150 }}>gespeichert</span>
        {/if}
      </div>
      <textarea
        bind:value={notiz}
        oninput={notizGetippt}
        rows="3"
        placeholder="Was du dazu wissen musst"
        disabled={laedt}
        class="karte mb-5 w-full resize-y px-3.5 py-2.5 text-sm leading-relaxed outline-none
               transition-[box-shadow] duration-200 placeholder:text-leise
               focus:ring-2 focus:ring-akzent/60 disabled:opacity-50"
      ></textarea>

      <!-- Aufgaben -->
      <div class="mb-1.5 flex items-center gap-2 px-1">
        <h3 class="m-0 text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-leise">Aufgaben</h3>
        {#if offen}
          <span class="ziffern rounded-full bg-akzent px-1.5 text-[0.625rem] font-semibold leading-4 text-akzent-text">
            {offen}
          </span>
        {/if}
      </div>

      <div class="karte overflow-hidden">
        <ul class="m-0 list-none p-0">
          {#each aufgaben as a (a.id)}
            <li
              class="group flex min-h-11 items-center gap-3 border-b border-linie-weich px-3.5"
              transition:slide={{ duration: 180 }}
            >
              <button
                type="button"
                onclick={() => abhaken(a)}
                role="checkbox"
                aria-checked={a.erledigt}
                aria-label={a.titel}
                class="grid size-5 shrink-0 place-items-center rounded-full border-[1.5px]
                       transition-colors duration-200 ease-ruhig"
                class:border-akzent={a.erledigt}
                class:bg-akzent={a.erledigt}
                class:border-linie={!a.erledigt}
                class:hover:border-gedaempft={!a.erledigt}
              >
                {#if a.erledigt}
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5 9.5 17 19 7.5" /></svg>
                {/if}
              </button>
              <span
                class="min-w-0 flex-1 py-2 text-sm transition-colors duration-200"
                class:line-through={a.erledigt}
                class:text-gedaempft={a.erledigt}
              >
                {a.titel}
              </span>
              <button
                type="button"
                onclick={() => loeschen(a)}
                aria-label="{a.titel} löschen"
                class="shrink-0 rounded-full p-1 text-leise transition-colors hover:text-schlecht"
              >
                <Symbol name="close" groesse={13} />
              </button>
            </li>
          {/each}
        </ul>

        <form
          onsubmit={(e) => {
            e.preventDefault();
            aufgabeAnlegen();
          }}
          class="flex min-h-11 items-center gap-3 px-3.5"
        >
          <span class="text-leise"><Symbol name="plus" groesse={16} /></span>
          <input
            bind:value={neueAufgabe}
            placeholder="Aufgabe hinzufügen"
            class="w-full border-0 bg-transparent py-2 text-sm outline-none placeholder:text-leise"
          />
        </form>
      </div>
    </div>
  {/if}
</Blatt>
