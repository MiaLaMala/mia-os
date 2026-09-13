<script lang="ts">
  /**
   * Schnelleingabe. Ein Feld, Enter, fertig.
   *
   * "AU abgeben Freitag" wird ein Eintrag mit Datum, "88,4 kg" landet in
   * wger, "Skyr 200g" als Mahlzeit. Der Server deutet den Text, das Blatt
   * zeigt nur, was daraus wurde.
   */
  import { tick } from "svelte";
  import { fade } from "svelte/transition";
  import { api } from "../lib/api";
  import type { SchnellAntwort, Zutat } from "../lib/types";
  import { sammlung } from "../lib/sammlung.svelte";
  import Blatt from "./Blatt.svelte";
  import Scanblatt from "./Scanblatt.svelte";
  import Symbol from "./Symbol.svelte";

  let {
    offen,
    schliessen,
    pageId = 0,
  }: { offen: boolean; schliessen: () => void; pageId?: number } = $props();

  let text = $state("");
  let sendet = $state(false);
  let meldung = $state("");
  let fehler = $state("");
  let wahl = $state<{ gramm: number; zutaten: Zutat[] } | null>(null);
  let feld: HTMLInputElement | undefined = $state();
  let dateiFeld: HTMLInputElement | undefined = $state();
  let scanDatei = $state<File | null>(null);
  let angehaengt = $state<File | null>(null);

  const BEISPIELE = ["AU abgeben Freitag", "88,4 kg", "Skyr 200g", "Zahnarzt 14.10. 9 Uhr"];

  $effect(() => {
    if (offen) {
      text = "";
      meldung = "";
      fehler = "";
      wahl = null;
      scanDatei = null;
      angehaengt = null;
      tick().then(() => feld?.focus());
    }
  });

  /**
   * Ein Foto auswählen. Bilder gehen erst ins Scan-Blatt, PDFs direkt dran.
   *
   * Angehängt wird nur gemerkt, nicht sofort geschickt: der Eintrag, an dem
   * es hängen soll, entsteht erst beim Absenden.
   */
  function fotoGewaehlt(ereignis: Event) {
    const eingabe = ereignis.currentTarget as HTMLInputElement;
    const gewaehlt = eingabe.files?.[0];
    // Zurücksetzen, sonst löst dieselbe Datei beim zweiten Mal kein
    // change-Ereignis aus und der Knopf wirkt kaputt.
    eingabe.value = "";
    if (!gewaehlt) return;

    fehler = "";
    if (gewaehlt.type === "application/pdf") {
      angehaengt = gewaehlt;
      scanEinstellung = null;
      feld?.focus();
    } else {
      scanDatei = gewaehlt;
    }
  }

  /** Wie das Foto aufbereitet werden soll. null heißt: unverändert ablegen. */
  let scanEinstellung = $state<{ staerke: string; ecken: string } | null>(null);

  async function scanUebernehmen(scan: { staerke: string; ecken: string } | null) {
    angehaengt = scanDatei;
    scanEinstellung = scan;
    scanDatei = null;
    await tick();
    feld?.focus();
  }

  async function absenden() {
    const t = text.trim();
    // Ohne Text, aber mit Foto: der Eintrag braucht trotzdem einen Namen.
    // „Beleg vom 09.09.2026" ist unschön, aber ehrlich, und Mia kann ihn im
    // Eintragsblatt sofort ändern. Ein erfundener Titel wäre schlimmer.
    const titel = t || (angehaengt ? `Beleg vom ${new Date().toLocaleDateString("de-DE")}` : "");
    if (!titel || sendet) return;

    sendet = true;
    fehler = "";
    try {
      const antwort: SchnellAntwort = await api.schnell(titel, pageId);

      if (antwort.art === "essen_wahl") {
        wahl = { gramm: antwort.gramm, zutaten: antwort.zutaten };
        return;
      }

      if (angehaengt) {
        if (antwort.art !== "eintrag") {
          // „88,4 kg" mit Foto ergibt keinen Sinn: ein Gewicht landet in
          // wger, dort gibt es nichts zum Anhängen.
          fehler = "Ein Foto passt nur an einen Eintrag, nicht an Gewicht oder Essen.";
          return;
        }
        try {
          await api.belegHochladen(
            antwort.eintrag.id,
            angehaengt,
            scanEinstellung ?? undefined,
          );
        } catch (e) {
          // Der Eintrag steht zu diesem Zeitpunkt schon. Ihn wieder zu
          // löschen wäre schlimmer: der getippte Text wäre weg. Also bleibt
          // er, und die Meldung sagt genau das, statt nur den Fehler zu
          // zeigen und offenzulassen, was jetzt gilt.
          sammlung.uebernehmen(antwort.eintrag);
          const grund = e instanceof Error ? e.message : "unbekannter Fehler";
          fehler = `Eintrag angelegt, aber der Anhang ging nicht: ${grund}`;
          text = "";
          return;
        }
      }

      if (antwort.art === "eintrag") {
        // Steht die Sammlung gerade offen, soll der Eintrag sofort da sein.
        sammlung.uebernehmen(antwort.eintrag);
      }
      meldung = angehaengt ? `${antwort.meldung}, mit Anhang` : antwort.meldung;
      text = "";
      angehaengt = null;
      setTimeout(schliessen, 900);
    } catch (e) {
      fehler = e instanceof Error ? e.message : "Ging nicht";
    } finally {
      sendet = false;
    }
  }

  async function zutatWaehlen(z: Zutat) {
    if (!wahl) return;
    sendet = true;
    try {
      await api.essenSetzen(z.id, wahl.gramm);
      meldung = `${Math.round(wahl.gramm)} g ${z.name} eingetragen`;
      wahl = null;
      text = "";
      setTimeout(schliessen, 900);
    } catch (e) {
      fehler = e instanceof Error ? e.message : "Ging nicht";
    } finally {
      sendet = false;
    }
  }
</script>

<Blatt {offen} {schliessen} titel="Schnelleingabe">
  <div class="px-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-2">
    <form
      onsubmit={(e) => {
        e.preventDefault();
        absenden();
      }}
      class="flex h-12 items-center gap-2.5 rounded-element bg-erhoben px-3.5
             transition-[box-shadow] duration-200 focus-within:ring-2 focus-within:ring-akzent/60"
    >
      <span class="text-gedaempft"><Symbol name="sparkles" groesse={17} /></span>
      <input
        bind:this={feld}
        bind:value={text}
        placeholder={angehaengt ? "Worum geht es?" : "Was ist los?"}
        enterkeyhint="done"
        autocomplete="off"
        class="w-full border-0 bg-transparent text-[1rem] outline-none placeholder:text-leise"
      />

      <!-- capture bleibt weg: mit Attribut springt iOS direkt in die Kamera
           und Mia kommt nicht mehr an ein Foto, das sie schon gemacht hat. -->
      <input
        bind:this={dateiFeld}
        type="file"
        accept="image/*,application/pdf"
        onchange={fotoGewaehlt}
        class="hidden"
      />
      <button
        type="button"
        onclick={() => dateiFeld?.click()}
        aria-label="Foto oder PDF anhängen"
        title="Foto oder PDF anhängen"
        class="grid size-8 shrink-0 place-items-center rounded-full transition-colors"
        class:text-akzent={!!angehaengt}
        class:text-gedaempft={!angehaengt}
        class:hover:text-text={!angehaengt}
      >
        <Symbol name="camera" groesse={17} />
      </button>

      <button
        type="submit"
        aria-label="Eintragen"
        disabled={(!text.trim() && !angehaengt) || sendet}
        class="grid size-8 shrink-0 place-items-center rounded-full bg-akzent text-akzent-text
               transition-[opacity,transform] duration-150 active:scale-95 disabled:opacity-30"
      >
        <span class:animate-spin={sendet}>
          <Symbol name={sendet ? "refresh" : "arrow-up"} groesse={16} />
        </span>
      </button>
    </form>

    {#if angehaengt}
      <!-- Was gleich mitgeht. Ohne diese Zeile wüsste Mia nach dem Schließen
           des Scan-Blattes nicht, ob das Foto noch dranhängt. -->
      <div
        class="mt-2 flex items-center gap-2 rounded-element bg-erhoben px-3 py-2 text-xs"
        transition:fade={{ duration: 150 }}
      >
        <span class="text-akzent"><Symbol name="paperclip" groesse={14} /></span>
        <span class="min-w-0 flex-1 truncate text-gedaempft">
          {scanEinstellung ? "Gescannt" : "Original"} · {angehaengt.name}
        </span>
        <button
          type="button"
          onclick={() => {
            angehaengt = null;
            scanEinstellung = null;
          }}
          aria-label="Anhang entfernen"
          class="shrink-0 text-leise transition-colors hover:text-text"
        >
          <Symbol name="close" groesse={13} />
        </button>
      </div>
    {/if}

    {#if meldung}
      <p class="m-0 mt-3 flex items-center gap-2 px-1 text-sm text-gut" transition:fade={{ duration: 150 }}>
        <Symbol name="check" groesse={15} />
        {meldung}
      </p>
    {:else if fehler}
      <p class="m-0 mt-3 px-1 text-sm text-schlecht">{fehler}</p>
    {:else if wahl}
      <p class="m-0 mt-3 px-1 text-xs text-gedaempft">Welche Zutat, {Math.round(wahl.gramm)} g?</p>
      <ul class="karte m-0 mt-2 list-none p-0">
        {#each wahl.zutaten as z (z.id)}
          <li class="border-b border-linie-weich last:border-0">
            <button
              type="button"
              onclick={() => zutatWaehlen(z)}
              class="flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left
                     text-[0.9375rem] transition-colors hover:bg-erhoben"
            >
              <span class="truncate">{z.name}</span>
              <span class="ziffern shrink-0 text-xs text-gedaempft">{z.kcal} kcal/100 g</span>
            </button>
          </li>
        {/each}
      </ul>
    {:else}
      <div class="mt-3 flex flex-wrap gap-1.5 px-0.5">
        {#each BEISPIELE as b (b)}
          <button
            type="button"
            onclick={() => {
              text = b;
              feld?.focus();
            }}
            class="rounded-full bg-erhoben px-2.5 py-1 text-xs text-gedaempft transition-colors
                   hover:bg-erhoben-2 hover:text-text"
          >
            {b}
          </button>
        {/each}
      </div>
      <p class="m-0 mt-3 px-1 text-xs text-leise">
        Datum, Wochentag oder Uhrzeit im Satz werden erkannt. Gewicht mit „kg", Essen mit „g".
      </p>
    {/if}
  </div>
</Blatt>

<Scanblatt
  datei={scanDatei}
  schliessen={() => (scanDatei = null)}
  uebernehmen={scanUebernehmen}
/>
