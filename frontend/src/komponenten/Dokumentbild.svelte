<script lang="ts">
  /**
   * Die Miniatur eines Dokuments: Vorschaubild, sonst das Kürzel.
   *
   * Der Rückfall auf das Kürzel passiert auch, wenn das Bild ins Leere läuft.
   * Nextcloud liefert nicht für jede Datei eine Vorschau, und wenn der Dienst
   * gerade weg ist, stand vorher das kaputte Bildsymbol des Browsers da:
   * ein fremdes Icon in einer Oberfläche, die eigene Symbole hat.
   */
  let {
    quelle = "",
    kuerzel = "",
    hoch = false,
  }: {
    /** URL des Vorschaubilds. Leer heißt: gleich das Kürzel zeigen. */
    quelle?: string;
    /** Dateiendung ohne Punkt, etwa "pdf". */
    kuerzel?: string;
    /** Große Kachel statt kleiner Zeilen-Miniatur. */
    hoch?: boolean;
  } = $props();

  let gescheitert = $state(false);

  // Wechselt das Dokument, gilt der alte Fehlschlag nicht mehr.
  $effect(() => {
    void quelle;
    gescheitert = false;
  });
</script>

{#if quelle && !gescheitert}
  <img
    src={quelle}
    alt=""
    loading="lazy"
    onerror={() => (gescheitert = true)}
    class="size-full object-cover"
    class:object-top={hoch}
  />
{:else}
  <span
    class="grid size-full place-items-center font-semibold uppercase text-leise"
    class:text-sm={hoch}
  >
    {kuerzel}
  </span>
{/if}
