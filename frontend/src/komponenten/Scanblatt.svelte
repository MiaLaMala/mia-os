<script lang="ts">
  /**
   * Aus einem Handyfoto einen Scan machen, bevor es abgelegt wird.
   *
   * Zwei Ansichten hintereinander: erst das Ergebnis, und wenn das nicht
   * stimmt, das Original mit ziehbaren Ecken. Diese Reihenfolge ist Absicht.
   * Meistens sitzt die Erkennung, dann soll Mia einmal tippen und fertig
   * sein. Nur wenn sie danebenliegt, wird es zur Arbeit.
   *
   * Warum überhaupt ein Zwischenschritt: die Kantenerkennung scheitert
   * verlässlich bei weißem Blatt auf hellem Tisch und bei geknicktem Papier.
   * Ein Bescheid, der so beschnitten wurde, dass das Aktenzeichen fehlt,
   * wäre schlimmer als ein unbearbeitetes Foto.
   */
  import { tick } from "svelte";
  import { api } from "../lib/api";
  import Blatt from "./Blatt.svelte";
  import Segment from "./Segment.svelte";
  import Symbol from "./Symbol.svelte";

  type Punkt = { x: number; y: number };

  let {
    datei,
    schliessen,
    uebernehmen,
  }: {
    datei: File | null;
    schliessen: () => void;
    /** Bekommt Stärke und Ecken, oder null für "ohne Scan ablegen". */
    uebernehmen: (scan: { staerke: string; ecken: string } | null) => Promise<void>;
  } = $props();

  let laedt = $state(false);
  let speichert = $state(false);
  let fehler = $state("");
  let vorschaubild = $state("");
  let automatisch = $state(true);
  let staerke = $state("weich");
  let ecken = $state<Punkt[]>([]);
  let origBreite = $state(0);
  let origHoehe = $state(0);
  let zeigeEcken = $state(false);

  // Das Originalfoto als Data-URL, für die Eckenansicht. Der Browser hat es
  // ohnehin schon, es dafür vom Server zu holen wäre ein unnötiger Weg.
  let originalUrl = $state("");
  let rahmen: HTMLDivElement | undefined = $state();
  let zieht = $state(-1);

  $effect(() => {
    if (!datei) {
      vorschaubild = "";
      originalUrl = "";
      zeigeEcken = false;
      fehler = "";
      return;
    }
    originalUrl = URL.createObjectURL(datei);
    staerke = "weich";
    laden();
    // Der Browser gibt den Speicher sonst erst beim Neuladen der Seite frei.
    return () => URL.revokeObjectURL(originalUrl);
  });

  const eckenText = () => ecken.map((p) => `${Math.round(p.x)},${Math.round(p.y)}`).join(" ");

  async function laden(mitEcken = false) {
    if (!datei) return;
    laedt = true;
    fehler = "";
    try {
      const antwort = await api.scanVorschau(datei, staerke, mitEcken ? eckenText() : "");
      vorschaubild = antwort.bild;
      automatisch = antwort.automatisch;
      origBreite = antwort.breite;
      origHoehe = antwort.hoehe;
      if (antwort.ecken?.length === 4) {
        ecken = antwort.ecken.map(([x, y]) => ({ x, y }));
      } else if (!ecken.length) {
        // Nichts erkannt: als Startpunkt ein Rechteck mit etwas Abstand zum
        // Bildrand. Von dort aus zieht Mia schneller als von vier Punkten,
        // die alle in einer Ecke kleben.
        const rx = antwort.breite * 0.1;
        const ry = antwort.hoehe * 0.1;
        ecken = [
          { x: rx, y: ry },
          { x: antwort.breite - rx, y: ry },
          { x: antwort.breite - rx, y: antwort.hoehe - ry },
          { x: rx, y: antwort.hoehe - ry },
        ];
      }
      if (!antwort.automatisch && !mitEcken) zeigeEcken = true;
    } catch (e) {
      fehler = e instanceof Error ? e.message : "Das Bild ließ sich nicht aufbereiten.";
    } finally {
      laedt = false;
    }
  }

  async function staerkeWechseln(neu: string) {
    staerke = neu;
    await laden(true);
  }

  /** Bildschirmpunkt in Bildkoordinaten umrechnen. */
  function zuBild(ereignis: PointerEvent): Punkt | null {
    if (!rahmen) return null;
    const kasten = rahmen.getBoundingClientRect();
    return {
      x: ((ereignis.clientX - kasten.left) / kasten.width) * origBreite,
      y: ((ereignis.clientY - kasten.top) / kasten.height) * origHoehe,
    };
  }

  function greifen(ereignis: PointerEvent, index: number) {
    ereignis.preventDefault();
    zieht = index;
    (ereignis.currentTarget as HTMLElement).setPointerCapture(ereignis.pointerId);
  }

  function ziehen(ereignis: PointerEvent) {
    if (zieht < 0) return;
    const punkt = zuBild(ereignis);
    if (!punkt) return;
    // Innerhalb des Bildes halten: eine Ecke außerhalb ergibt beim Entzerren
    // einen schwarzen Keil.
    ecken[zieht] = {
      x: Math.max(0, Math.min(origBreite, punkt.x)),
      y: Math.max(0, Math.min(origHoehe, punkt.y)),
    };
  }

  function loslassen() {
    zieht = -1;
  }

  async function eckenUebernehmen() {
    zeigeEcken = false;
    await tick();
    await laden(true);
  }

  async function fertig(mitScan: boolean) {
    speichert = true;
    fehler = "";
    try {
      await uebernehmen(mitScan ? { staerke, ecken: eckenText() } : null);
    } catch (e) {
      fehler = e instanceof Error ? e.message : "Speichern ging schief.";
    } finally {
      speichert = false;
    }
  }
</script>

<Blatt offen={!!datei} {schliessen} titel="Scannen" breit>
  <div
    data-blatt-inhalt
    class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4
           pb-[max(1rem,env(safe-area-inset-bottom))] pt-2"
  >
    {#if fehler}
      <p class="m-0 rounded-element bg-schlecht/10 px-3 py-2 text-sm text-schlecht">{fehler}</p>
    {/if}

    {#if zeigeEcken}
      <!-- Ecken ziehen. Das Originalfoto, darüber ein Viereck mit vier
           Griffen. Nur sichtbar, wenn nötig oder gewünscht. -->
      <p class="m-0 px-1 text-xs text-gedaempft">
        Die vier Ecken des Blattes auf die richtigen Stellen ziehen.
      </p>

      <div
        bind:this={rahmen}
        role="application"
        aria-label="Blattecken verschieben"
        data-kein-wischen
        class="relative w-full touch-none select-none overflow-hidden rounded-element bg-erhoben"
        style="touch-action: none"
        onpointermove={ziehen}
        onpointerup={loslassen}
        onpointercancel={loslassen}
      >
        <img src={originalUrl} alt="Originalfoto" class="block w-full" />

        {#if origBreite && ecken.length === 4}
          <svg
            viewBox="0 0 {origBreite} {origHoehe}"
            class="pointer-events-none absolute inset-0 h-full w-full"
          >
            <polygon
              points={ecken.map((p) => `${p.x},${p.y}`).join(" ")}
              fill="rgb(10 132 255 / 0.14)"
              stroke="rgb(10 132 255)"
              stroke-width={Math.max(origBreite, origHoehe) / 250}
            />
          </svg>

          {#each ecken as punkt, i (i)}
            <!-- Ein Ring mit einem Punkt in der Mitte, nicht eine gefüllte
                 Scheibe. Zwei Gründe, beide am Bild gesehen: die Akzentfarbe
                 ist bei Mia rot und beißt sich mit der blauen Schnittlinie,
                 und ein halbdurchsichtiger Griff lässt die Blattecke
                 durchscheinen, was im Kreis wie ein weißer rechter Winkel
                 aussieht. Der Ring lässt bewusst durchsehen: Mia muss beim
                 Ziehen erkennen, wo die Ecke wirklich liegt. -->
            <button
              type="button"
              aria-label="Ecke {i + 1} verschieben"
              onpointerdown={(e) => greifen(e, i)}
              class="absolute grid size-10 -translate-x-1/2 -translate-y-1/2 place-items-center
                     rounded-full transition-transform active:scale-125"
              style="left: {(punkt.x / origBreite) * 100}%;
                     top: {(punkt.y / origHoehe) * 100}%"
            >
              <span
                class="absolute inset-1.5 rounded-full border-[3px]"
                style="border-color: rgb(10 132 255); box-shadow: 0 0 0 1px rgb(0 0 0 / 0.25)"
              ></span>
              <span
                class="size-1.5 rounded-full"
                style="background: rgb(10 132 255)"
              ></span>
            </button>
          {/each}
        {/if}
      </div>

      <div class="flex gap-2">
        <button
          type="button"
          onclick={() => (zeigeEcken = false)}
          class="h-11 flex-1 rounded-element bg-erhoben text-[0.9375rem] font-medium
                 text-text transition-colors hover:bg-erhoben-2"
        >
          Zurück
        </button>
        <button
          type="button"
          onclick={eckenUebernehmen}
          disabled={laedt}
          class="flex h-11 flex-1 items-center justify-center gap-2 rounded-element bg-akzent
                 text-[0.9375rem] font-medium text-white transition-opacity disabled:opacity-60"
        >
          {#if laedt}<span class="animate-spin"><Symbol name="refresh" groesse={16} /></span>{/if}
          Übernehmen
        </button>
      </div>
    {:else}
      <!-- Ergebnis. Der Normalfall: einmal ansehen, einmal tippen. -->
      {#if !automatisch}
        <p class="m-0 flex items-start gap-2 rounded-element bg-warn/10 px-3 py-2 text-xs text-warn">
          <span class="mt-0.5 shrink-0"><Symbol name="filter" groesse={14} /></span>
          Ich habe die Blattkanten nicht sicher gefunden. Sieh dir das Ergebnis an und
          zieh die Ecken selbst, wenn etwas fehlt.
        </p>
      {/if}

      <div class="relative overflow-hidden rounded-element bg-erhoben">
        {#if vorschaubild}
          <img src={vorschaubild} alt="Aufbereitetes Dokument" class="block w-full" />
        {:else}
          <div class="grid h-64 place-items-center text-gedaempft">
            <span class:animate-spin={laedt}><Symbol name="refresh" groesse={22} /></span>
          </div>
        {/if}
        {#if laedt && vorschaubild}
          <div class="absolute inset-0 grid place-items-center bg-flaeche/50">
            <span class="animate-spin text-gedaempft"><Symbol name="refresh" groesse={22} /></span>
          </div>
        {/if}
      </div>

      <Segment
        optionen={[
          { key: "weich", name: "Weich" },
          { key: "hart", name: "Schwarzweiß" },
        ]}
        wert={staerke}
        waehlen={staerkeWechseln}
      />
      <p class="m-0 px-1 text-xs text-leise">
        {staerke === "weich"
          ? "Behält Graustufen, Stempel und Unterschriften bleiben sichtbar."
          : "Reines Schwarzweiß. Schärfer bei Text, verschluckt aber blasse Stempel."}
      </p>

      <button
        type="button"
        onclick={() => (zeigeEcken = true)}
        class="flex items-center justify-center gap-1.5 py-1 text-sm text-gedaempft
               transition-colors hover:text-text"
      >
        <Symbol name="grid" groesse={14} />
        Ecken selbst setzen
      </button>

      <div class="mt-auto flex flex-col gap-2 pt-2">
        <button
          type="button"
          onclick={() => fertig(true)}
          disabled={speichert || laedt}
          class="flex h-11 items-center justify-center gap-2 rounded-element bg-akzent
                 text-[0.9375rem] font-medium text-white transition-opacity disabled:opacity-60"
        >
          {#if speichert}
            <span class="animate-spin"><Symbol name="refresh" groesse={16} /></span>
          {/if}
          Als Scan anhängen
        </button>
        <!-- Der Ausweg, wenn die Aufbereitung das Bild verschlimmert: bei
             einem Foto mit Farbmarkierungen kann das Original besser sein. -->
        <button
          type="button"
          onclick={() => fertig(false)}
          disabled={speichert}
          class="h-11 rounded-element bg-erhoben text-[0.9375rem] font-medium text-gedaempft
                 transition-colors hover:bg-erhoben-2 hover:text-text disabled:opacity-60"
        >
          Original ohne Scan
        </button>
      </div>
    {/if}
  </div>
</Blatt>
