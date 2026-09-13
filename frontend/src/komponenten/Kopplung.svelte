<script lang="ts">
  /**
   * Apps mit Mia OS verbinden.
   *
   * Ein Knopf erzeugt einen sechsstelligen Code, darunter stehen die Geräte,
   * die schon gekoppelt sind. Der Code gilt zehn Minuten und genau einmal.
   *
   * Warum der Code hier steht und nicht in der App: er ist der Nachweis, dass
   * jemand schon drin ist. Wer diese Seite sehen kann, kommt aus dem Heimnetz
   * oder hat bereits einen Schlüssel — und könnte die Daten ohnehin sehen.
   */
  import { api, ApiFehler } from "../lib/api";
  import type { GekoppeltesGeraet } from "../lib/types";
  import Abschnitt from "./Abschnitt.svelte";
  import Symbol from "./Symbol.svelte";

  let code = $state("");
  let giltBis = $state<Date | null>(null);
  let restSekunden = $state(0);
  let geraete = $state<GekoppeltesGeraet[]>([]);
  let laeuft = $state(false);
  let fehler = $state("");

  let ticker: ReturnType<typeof setInterval> | undefined;

  $effect(() => {
    void laden();
    // Der Zähler läuft, solange die Seite offen ist. Aufräumen ist Pflicht:
    // ein Intervall, das nach dem Verlassen der Seite weiterläuft, hält die
    // ganze Komponente im Speicher.
    ticker = setInterval(() => {
      if (!giltBis) return;
      const rest = Math.max(0, Math.round((giltBis.getTime() - Date.now()) / 1000));
      restSekunden = rest;
      if (rest === 0) {
        code = "";
        giltBis = null;
      }
    }, 1000);
    return () => clearInterval(ticker);
  });

  async function laden() {
    try {
      geraete = (await api.gekoppelteGeraete()).geraete;
    } catch (e) {
      fehler = e instanceof ApiFehler ? e.message : "Geräte nicht abrufbar";
    }
  }

  async function codeHolen() {
    laeuft = true;
    fehler = "";
    try {
      const antwort = await api.kopplungscode();
      code = antwort.code;
      giltBis = new Date(antwort.gilt_bis);
      restSekunden = Math.max(0, Math.round((giltBis.getTime() - Date.now()) / 1000));
    } catch (e) {
      fehler = e instanceof Error ? e.message : "Kein Code";
    } finally {
      laeuft = false;
    }
  }

  async function abmelden(g: GekoppeltesGeraet) {
    if (!confirm(`${g.name} abmelden? Die App braucht danach einen neuen Code.`)) return;
    try {
      await api.geraetAbmelden(g.id);
      // Sofort aus der Liste, nicht erst nach dem Neuladen: ein Eintrag, der
      // nach dem Klick noch dasteht, sieht aus wie ein fehlgeschlagener Klick.
      geraete = geraete.filter((x) => x.id !== g.id);
    } catch (e) {
      fehler = e instanceof Error ? e.message : "Abmelden ging nicht";
      void laden();
    }
  }

  /** "vor 3 Minuten", "gestern". Ohne Bibliothek, es sind fünf Fälle. */
  function wann(text: string): string {
    if (!text) return "nie";
    const sekunden = Math.round((Date.now() - new Date(text).getTime()) / 1000);
    if (sekunden < 90) return "gerade eben";
    if (sekunden < 3600) return `vor ${Math.round(sekunden / 60)} Minuten`;
    if (sekunden < 86400) return `vor ${Math.round(sekunden / 3600)} Stunden`;
    if (sekunden < 172800) return "gestern";
    return `vor ${Math.round(sekunden / 86400)} Tagen`;
  }

  function symbolFuer(plattform: string): string {
    return plattform === "macos" ? "laptop" : "phone";
  }

  const restText = $derived(
    restSekunden > 0
      ? `noch ${Math.floor(restSekunden / 60)}:${String(restSekunden % 60).padStart(2, "0")}`
      : "",
  );
</script>

<Abschnitt
  titel="Apps"
  hinweis="Die App fragt beim ersten Start nach diesem Code. Danach hat sie ihren eigenen Schlüssel und braucht ihn nie wieder."
>
  <div class="border-b border-linie-weich px-3.5 py-3 last:border-0">
    {#if code}
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p
            class="m-0 font-mono text-[2rem] font-medium leading-none tracking-[0.18em] tabular-nums"
          >
            {code}
          </p>
          <p class="m-0 mt-1.5 text-xs text-gedaempft">{restText}</p>
        </div>
        <button
          type="button"
          onclick={codeHolen}
          class="rounded-full bg-erhoben px-3.5 py-2 text-[0.8125rem] font-medium
                 text-gedaempft transition-colors hover:bg-erhoben-2 hover:text-text"
        >
          Neuer Code
        </button>
      </div>
    {:else}
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="min-w-0 flex-1 basis-40">
          <p class="m-0 text-[0.9375rem] font-medium">Neues Gerät verbinden</p>
          <p class="m-0 mt-0.5 text-xs leading-snug text-gedaempft">
            Erzeugt einen Code für Mac oder iPhone.
          </p>
        </div>
        <button
          type="button"
          onclick={codeHolen}
          disabled={laeuft}
          class="rounded-full bg-akzent px-4 py-2 text-[0.8125rem] font-medium text-white
                 transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {laeuft ? "Moment…" : "Code erzeugen"}
        </button>
      </div>
    {/if}
  </div>

  {#each geraete as g (g.id)}
    <div class="flex items-center gap-3 border-b border-linie-weich px-3.5 py-3 last:border-0">
      <span class="text-gedaempft"><Symbol name={symbolFuer(g.plattform)} groesse={19} /></span>
      <div class="min-w-0 flex-1">
        <p class="m-0 truncate text-[0.9375rem]">{g.name}</p>
        <p class="m-0 mt-0.5 text-xs text-gedaempft">
          zuletzt {wann(g.zuletzt_at)}{g.adresse ? ` · ${g.adresse}` : ""}
        </p>
      </div>
      <button
        type="button"
        onclick={() => abmelden(g)}
        class="shrink-0 rounded-full px-3 py-1.5 text-xs font-medium text-fehler
               transition-colors hover:bg-erhoben"
      >
        Abmelden
      </button>
    </div>
  {/each}

  {#if fehler}
    <p class="m-0 px-3.5 py-3 text-xs text-fehler">{fehler}</p>
  {/if}
</Abschnitt>
