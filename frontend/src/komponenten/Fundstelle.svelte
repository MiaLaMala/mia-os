<!--
  Die Fundstelle im gelesenen Text, mit hervorgehobenen Treffern.

  SQLite liefert das Stück als Text mit `[` und `]` um die Treffer. Genau so
  wird es hier zerlegt und als Textknoten gesetzt.

  **Nie `{@html}`.** Der Text kommt aus einem Foto, das Tesseract gelesen hat:
  ein Blatt Papier, auf dem `<img onerror=...>` steht, wäre sonst ein
  eingebautes Loch. Der Umweg über eine Liste von Teilstücken kostet drei
  Zeilen und schließt das ab.
-->
<script lang="ts">
  interface Props {
    /** Der Ausschnitt aus dem Text, Treffer in eckigen Klammern. */
    stelle: string;
    /** Auf der Kachel sind zwei Zeilen Platz, in der Liste nur eine. */
    zeilen?: 1 | 2;
  }

  let { stelle, zeilen = 1 }: Props = $props();

  /**
   * In abwechselnd normale und hervorgehobene Stücke zerlegen.
   *
   * `split` mit einer Gruppe im Muster liefert die Trenner mit: an geraden
   * Positionen steht normaler Text, an ungeraden der Treffer.
   */
  const teile = $derived(stelle.split(/\[(.*?)\]/g));
</script>

<!--
  `display: -webkit-box` statt `block`: die Zeilenbegrenzung braucht genau
  diesen Anzeigetyp. Am gerenderten Bild aufgefallen, die Fundstelle lief
  über drei Zeilen und schob die Kachel auseinander.
-->
<span
  class="text-[0.6875rem] leading-snug text-gedaempft {zeilen === 2
    ? 'line-clamp-2'
    : 'block truncate'}"
>
  {#each teile as teil, i (i)}{#if i % 2}<mark
        class="rounded-[3px] bg-akzent/15 px-0.5 text-akzent">{teil}</mark
      >{:else}{teil}{/if}{/each}
</span>
