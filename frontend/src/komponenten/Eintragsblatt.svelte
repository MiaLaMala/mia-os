<script lang="ts">
  /**
   * Ein Eintrag als Blatt. Titel, Eigenschaften als Zeilen, freier Text.
   * Alles direkt bearbeitbar, ohne Speichern-Knopf.
   */
  import { fade } from "svelte/transition";
  import Blatt from "./Blatt.svelte";
  import { api } from "../lib/api";
  import { sammlung } from "../lib/sammlung.svelte";
  import { seiten } from "../lib/seiten.svelte";
  import type {
    Anhang,
    Dokument,
    Eintrag,
    Namensvorschlag,
    Ordnervorschlag,
  } from "../lib/types";
  import Dokumentbild from "./Dokumentbild.svelte";
  import Dokumentwahl from "./Dokumentwahl.svelte";
  import Scanblatt from "./Scanblatt.svelte";
  import Marke from "./Marke.svelte";
  import Symbol from "./Symbol.svelte";

  let { eintrag, schliessen }: { eintrag: Eintrag | null; schliessen: () => void } =
    $props();

  let titel = $state("");
  let inhalt = $state("");
  let gesichert = $state(false);
  let offenesFeld = $state("");
  let anhaenge = $state<Anhang[]>([]);
  let wahlOffen = $state(false);
  let laedtHoch = $state(false);
  let hochladeFehler = $state("");
  // Kurze Rückmeldung nach dem Scannen, dass der Text gelesen wurde.
  let ocrHinweis = $state("");
  let ocrTimer: ReturnType<typeof setTimeout>;
  // Wohin der frische Beleg gehören könnte. null heißt: kein Ordner passt
  // klar genug, dann wird auch nichts gefragt.
  let vorschlag = $state<Ordnervorschlag | null>(null);
  let verschiebt = $state(false);
  let verschiebeFehler = $state("");
  // Wie der Beleg heißen könnte, gelesen vom Blatt selbst. null heißt: zu
  // wenig erkannt, oder der Vorschlag hieße genauso wie die Datei jetzt.
  let namensvorschlag = $state<Namensvorschlag | null>(null);
  let benenntUm = $state(false);
  let umbenennFehler = $state("");
  let dateiFeld: HTMLInputElement | undefined = $state();
  let scanDatei = $state<File | null>(null);
  let timer: ReturnType<typeof setTimeout>;

  // Nur Seiten mit Sammlung, die nicht selbst alles sammeln: dorthin kann
  // ein Eintrag gehoeren. "Alles" ist kein Ort, sondern ein Blick.
  const zielSeiten = $derived(seiten.alle.filter((s) => s.hat_sammlung && !s.sammelt_alles));

  $effect(() => {
    if (!eintrag) {
      anhaenge = [];
      vorschlag = null;
      namensvorschlag = null;
      return;
    }
    titel = eintrag.titel;
    inhalt = eintrag.inhalt;
    // Der Vorschlag gehört zu genau einem Upload. Beim Blattwechsel muss er
    // weg, sonst böte er an, den Beleg des vorigen Eintrags zu verschieben.
    vorschlag = null;
    verschiebeFehler = "";
    namensvorschlag = null;
    umbenennFehler = "";
    // Die Anhänge kommen erst beim Öffnen dazu: die Liste lädt sie nicht mit,
    // dort steht nur die Zahl.
    anhaengeLaden(eintrag.id);
  });

  async function anhaengeLaden(id: number) {
    try {
      anhaenge = (await api.anhaenge(id)).dokumente;
    } catch {
      // Ein Fehler hier darf das Blatt nicht sperren: Titel und
      // Eigenschaften bleiben bedienbar, die Anhänge fehlen eben.
      anhaenge = [];
    }
  }

  async function anhaengen(d: Dokument) {
    if (!eintrag) return;
    anhaenge = (await api.anhaengen(eintrag.id, d.id)).dokumente;
    wahlOffen = false;
  }

  /**
   * Ein Foto oder PDF hochladen. Landet in Nextcloud und hängt sofort dran.
   *
   * Bilder gehen erst ins Scan-Blatt: Mia sieht das aufbereitete Ergebnis
   * und kann die Ecken korrigieren, bevor irgendwas gespeichert wird. PDFs
   * laufen direkt durch, die sind schon Dokumente.
   */
  function hochladen(ereignis: Event) {
    const feld = ereignis.currentTarget as HTMLInputElement;
    const gewaehlt = feld.files?.[0];
    // Zurücksetzen, sonst löst dieselbe Datei beim zweiten Mal kein
    // change-Ereignis aus und der Knopf wirkt kaputt.
    feld.value = "";
    if (!gewaehlt || !eintrag) return;

    hochladeFehler = "";
    if (gewaehlt.type === "application/pdf") {
      void ablegen(gewaehlt, null);
    } else {
      scanDatei = gewaehlt;
    }
  }

  /**
   * Die Datei wirklich hochladen.
   *
   * Der Fehlertext kommt vom Server und wird angezeigt, statt still zu
   * scheitern: „größer als 25 MB" ist etwas, das Mia beheben kann, ein
   * Spinner, der einfach aufhört, nicht.
   */
  async function ablegen(datei: File, scan: { staerke: string; ecken: string } | null) {
    if (!eintrag) return;
    laedtHoch = true;
    hochladeFehler = "";
    try {
      const antwort = await api.belegHochladen(eintrag.id, datei, scan ?? undefined);
      anhaenge = antwort.dokumente;
      scanDatei = null;
      // Kurz sagen, dass der Text gelesen wurde: sonst weiß Mia nicht, dass
      // sie den Beleg ab jetzt über ein Wort darauf wiederfindet. Verschwindet
      // von selbst, es ist eine Beiläufigkeit und keine Meldung.
      ocrHinweis = antwort.ocr_zeichen > 0 ? "Text gelesen, ist jetzt durchsuchbar" : "";
      if (ocrHinweis) {
        clearTimeout(ocrTimer);
        ocrTimer = setTimeout(() => (ocrHinweis = ""), 4000);
      }
      // Der Ordnervorschlag bleibt stehen, bis Mia ihn annimmt oder wegtippt.
      // Anders als der OCR-Hinweis ist er kein Nebensatz, sondern eine Frage.
      vorschlag = antwort.vorschlag;
      verschiebeFehler = "";
      namensvorschlag = antwort.namensvorschlag;
      umbenennFehler = "";
    } catch (fehler) {
      hochladeFehler = fehler instanceof Error ? fehler.message : "Hochladen ging schief.";
      // Weiterwerfen, damit das Scan-Blatt seinen eigenen Zustand kennt und
      // nicht zumacht, als wäre alles gut gegangen.
      throw fehler;
    } finally {
      laedtHoch = false;
    }
  }

  /**
   * Den Vorschlag annehmen: der Beleg wandert in den vorgeschlagenen Ordner.
   *
   * Erst nach dem Klick, nie von selbst. Ein Vorschlag, der bei 88 % Treffern
   * automatisch verschiebt, räumt Mias Ablage in jedem achten Fall falsch auf,
   * und sie merkt es erst, wenn sie das Blatt sucht.
   */
  async function vorschlagAnnehmen() {
    if (!vorschlag || !eintrag) return;
    verschiebt = true;
    verschiebeFehler = "";
    try {
      await api.dokumentVerschieben(vorschlag.pfad, vorschlag.ordner);
      // Neu holen statt lokal umzubiegen: der Server hat den Namen womöglich
      // durchnummeriert, weil im Zielordner schon einer so hieß.
      anhaenge = (await api.anhaenge(eintrag.id)).dokumente;
      vorschlag = null;
    } catch (fehler) {
      verschiebeFehler =
        fehler instanceof Error ? fehler.message : "Verschieben ging schief.";
    } finally {
      verschiebt = false;
    }
  }

  /**
   * Den Namensvorschlag annehmen: der Beleg heißt danach nach dem, was auf
   * ihm steht.
   *
   * Auch hier erst nach dem Klick. Ein Beleg, der sich beim Hochladen selbst
   * umbenennt, ist unter dem Namen weg, unter dem Mia ihn abgelegt hat, und
   * der Name aus dem Eintrag ist oft der bessere.
   */
  async function namenAnnehmen() {
    if (!namensvorschlag || !eintrag) return;
    benenntUm = true;
    umbenennFehler = "";
    try {
      const antwort = await api.dokumentUmbenennen(
        namensvorschlag.pfad,
        namensvorschlag.name,
      );
      anhaenge = (await api.anhaenge(eintrag.id)).dokumente;
      // Der Ordnervorschlag zeigt auf den alten Pfad. Nach dem Umbenennen
      // heißt die Datei anders, und ein Verschieben liefe ins Leere.
      if (vorschlag) vorschlag = { ...vorschlag, pfad: antwort.pfad };
      namensvorschlag = null;
    } catch (fehler) {
      umbenennFehler =
        fehler instanceof Error ? fehler.message : "Umbenennen ging schief.";
    } finally {
      benenntUm = false;
    }
  }

  async function loesen(a: Anhang) {
    if (!eintrag) return;
    const vorher = anhaenge;
    anhaenge = anhaenge.filter((x) => x.path !== a.path || x.source !== a.source);
    try {
      await api.anhangLoesen(eintrag.id, a.source, a.path);
    } catch {
      anhaenge = vorher;
    }
  }

  function getippt(feld: "titel" | "inhalt") {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!eintrag) return;
      const wert = feld === "titel" ? titel.trim() : inhalt;
      if (feld === "titel" && !wert) return;
      await sammlung.aendern(eintrag.id, { [feld]: wert });
      gesichert = true;
      setTimeout(() => (gesichert = false), 1200);
    }, 600);
  }

  async function setzen(key: string, wert: string) {
    if (!eintrag) return;
    const neu = eintrag.eigenschaften[key] === wert ? "" : wert;
    await sammlung.setzeEigenschaft(eintrag.id, key, neu);
    offenesFeld = "";
  }

  async function loeschen() {
    if (!eintrag) return;
    if (!confirm(`„${eintrag.titel}" löschen?`)) return;
    await sammlung.loeschen(eintrag.id);
    schliessen();
  }

  function taste(e: KeyboardEvent) {
    if (e.key === "Escape" && offenesFeld) offenesFeld = "";
  }
</script>

<svelte:window onkeydown={taste} />

<Blatt offen={!!eintrag} {schliessen} breit titel={eintrag?.titel}>
  {#if eintrag}
    <!-- Kopf -->
    <div class="flex items-center gap-2 px-4 pb-2 pt-1 sm:pt-4">
      <button
        type="button"
        onclick={schliessen}
        aria-label="Schließen"
        class="grid size-8 shrink-0 place-items-center rounded-full bg-erhoben text-gedaempft
               transition-colors duration-200 hover:text-text"
      >
        <Symbol name="close" groesse={15} />
      </button>
      <span class="flex-1"></span>
      {#if gesichert}
        <span class="text-xs text-gut" transition:fade={{ duration: 150 }}>gespeichert</span>
      {/if}
      <button
        type="button"
        onclick={loeschen}
        aria-label="Eintrag löschen"
        title="Löschen"
        class="grid size-8 shrink-0 place-items-center rounded-full text-gedaempft
               transition-colors duration-200 hover:bg-erhoben hover:text-schlecht"
      >
        <Symbol name="trash" groesse={16} />
      </button>
    </div>

    <div
      data-blatt-inhalt
      class="min-h-0 flex-1 overflow-y-auto px-5 pb-[max(1.5rem,env(safe-area-inset-bottom))]"
    >
      <input
        bind:value={titel}
        oninput={() => getippt("titel")}
        class="anzeige mb-3 w-full border-0 bg-transparent text-[1.5rem] leading-tight outline-none
               placeholder:text-leise"
        placeholder="Ohne Titel"
      />

      <!-- Eigenschaften -->
      <div class="karte mb-4 overflow-visible">
        {#each sammlung.eigenschaften as prop (prop.key)}
          {@const wert = eintrag.eigenschaften[prop.key] ?? ""}
          <div class="relative flex min-h-11 items-center gap-3 border-b border-linie-weich px-3.5 last:border-0">
            <span class="w-20 shrink-0 text-[0.8125rem] text-gedaempft">{prop.name}</span>
            <div class="min-w-0 flex-1 py-2">
              {#if prop.art === "auswahl"}
                <button
                  type="button"
                  onclick={() => (offenesFeld = offenesFeld === prop.key ? "" : prop.key)}
                  class="flex w-full items-center text-left"
                >
                  {#if wert}
                    <Marke {prop} {wert} />
                  {:else}
                    <span class="text-sm text-leise">leer</span>
                  {/if}
                  <span class="ml-auto text-leise"><Symbol name="chevron-down" groesse={14} /></span>
                </button>

                {#if offenesFeld === prop.key}
                  <div
                    class="absolute left-[5.5rem] right-3 top-full z-10 mt-1 flex flex-col gap-0.5
                           rounded-element bg-erhoben p-1 shadow-menue"
                    transition:fade={{ duration: 120 }}
                  >
                    {#each prop.optionen as o (o.wert)}
                      <button
                        type="button"
                        onclick={() => setzen(prop.key, o.wert)}
                        class="flex items-center justify-between rounded-klein px-2 py-1.5 text-left
                               transition-colors hover:bg-erhoben-2"
                      >
                        <Marke {prop} wert={o.wert} />
                        {#if wert === o.wert}
                          <span class="text-akzent"><Symbol name="check" groesse={14} /></span>
                        {/if}
                      </button>
                    {/each}
                  </div>
                {/if}
              {:else if prop.art === "datum"}
                <input
                  type="date"
                  value={wert}
                  onchange={(e) => sammlung.setzeEigenschaft(eintrag.id, prop.key, e.currentTarget.value)}
                  class="w-full border-0 bg-transparent text-sm outline-none"
                />
              {:else}
                <input
                  value={wert}
                  onchange={(e) => sammlung.setzeEigenschaft(eintrag.id, prop.key, e.currentTarget.value)}
                  placeholder="leer"
                  class="w-full border-0 bg-transparent text-sm outline-none placeholder:text-leise"
                />
              {/if}
            </div>
          </div>
        {/each}

        <div class="flex min-h-11 items-center gap-3 border-t border-linie-weich px-3.5">
          <span class="w-20 shrink-0 text-[0.8125rem] text-gedaempft">Datum</span>
          <input
            type="date"
            value={eintrag.datum}
            onchange={(e) => sammlung.aendern(eintrag.id, { datum: e.currentTarget.value })}
            class="flex-1 border-0 bg-transparent py-2 text-sm outline-none"
          />
          {#if eintrag.datum}
            <button
              type="button"
              onclick={() => sammlung.aendern(eintrag.id, { datum: "" })}
              aria-label="Datum entfernen"
              class="text-leise hover:text-text"
            >
              <Symbol name="close" groesse={13} />
            </button>
          {/if}
        </div>

        <div class="flex min-h-11 items-center gap-3 border-t border-linie-weich px-3.5">
          <span class="w-20 shrink-0 text-[0.8125rem] text-gedaempft">Seite</span>
          <select
            value={String(eintrag.page_id || 0)}
            onchange={(e) => sammlung.aendern(eintrag.id, { page_id: Number(e.currentTarget.value) })}
            aria-label="Auf welcher Seite"
            class="flex-1 cursor-pointer border-0 bg-transparent py-2 text-sm outline-none"
          >
            <option value="0">Keine (nur in „Alles")</option>
            {#each zielSeiten as s (s.id)}
              <option value={String(s.id)}>{s.titel}</option>
            {/each}
          </select>
        </div>
      </div>

      <textarea
        bind:value={inhalt}
        oninput={() => getippt("inhalt")}
        rows="6"
        placeholder="Notizen"
        class="w-full resize-y rounded-element border-0 bg-transparent text-[0.9375rem] leading-relaxed
               outline-none placeholder:text-leise"
      ></textarea>

      <!-- Dokumente -->
      <div class="mt-5">
        <div class="mb-1.5 flex items-center gap-2 px-1">
          <span class="text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-leise">
            Dokumente
          </span>

          <!-- Zwei Wege: etwas Vorhandenes verknüpfen oder ein Foto machen.
               Der Kamera-Knopf kommt zuerst, weil das der häufigere Fall ist:
               der Bescheid liegt auf dem Tisch, nicht in Nextcloud. -->
          <button
            type="button"
            onclick={() => dateiFeld?.click()}
            disabled={laedtHoch}
            class="ml-auto flex items-center gap-1 text-xs text-gedaempft transition-colors
                   hover:text-text disabled:opacity-50"
          >
            <span class:animate-spin={laedtHoch}>
              <Symbol name={laedtHoch ? "refresh" : "camera"} groesse={14} />
            </span>
            {laedtHoch ? "Lädt…" : "Foto"}
          </button>

          <button
            type="button"
            onclick={() => (wahlOffen = true)}
            class="flex items-center gap-1 text-xs text-gedaempft transition-colors
                   hover:text-text"
          >
            <Symbol name="plus" groesse={13} />
            Anhängen
          </button>
        </div>

        <!-- capture bleibt weg: mit Attribut springt iOS direkt in die Kamera
             und Mia kommt nicht mehr an ein Foto, das sie schon gemacht hat.
             Ohne das Attribut fragt iOS, ob Kamera oder Mediathek. -->
        <input
          bind:this={dateiFeld}
          type="file"
          accept="image/*,application/pdf"
          onchange={hochladen}
          class="hidden"
        />

        {#if hochladeFehler}
          <p class="m-0 mb-2 px-1 text-xs text-schlecht">{hochladeFehler}</p>
        {:else if ocrHinweis}
          <p class="m-0 mb-2 px-1 text-xs text-gedaempft">{ocrHinweis}</p>
        {/if}

        <!-- Der Namensvorschlag. Steht über dem Ordnervorschlag: erst weiß
             Mia, was das Blatt ist, dann wohin es gehört. Beide können
             gleichzeitig dastehen, beide sind Fragen und keine Ansage. -->
        {#if namensvorschlag}
          <div class="karte mb-2 px-3 py-2.5" transition:fade={{ duration: 150 }}>
            <p class="m-0 text-xs text-gedaempft">Soll das heißen</p>
            <p class="m-0 mt-0.5 break-words text-[0.9375rem]">{namensvorschlag.name}</p>
            {#if umbenennFehler}
              <p class="m-0 mt-1 text-xs text-schlecht">{umbenennFehler}</p>
            {/if}
            <div class="mt-2.5 flex gap-2">
              <button
                type="button"
                onclick={namenAnnehmen}
                disabled={benenntUm}
                class="rounded-element bg-akzent px-3 py-1.5 text-[0.8125rem] text-akzent-text
                       transition-transform active:scale-95 disabled:opacity-50"
              >
                {benenntUm ? "Benenne um…" : "Ja, so"}
              </button>
              <button
                type="button"
                onclick={() => (namensvorschlag = null)}
                class="rounded-element px-3 py-1.5 text-[0.8125rem] text-gedaempft
                       transition-colors hover:text-text"
              >
                Name bleibt
              </button>
            </div>
          </div>
        {/if}

        <!-- Der Ordnervorschlag. Zwei Knöpfe, kein Automatismus: Mia OS hat
             den Beleg im Belegordner abgelegt und fragt, ob er woandershin
             soll. Kommt gar kein Vorschlag, steht hier nichts. -->
        {#if vorschlag}
          <div class="karte mb-2 px-3 py-2.5" transition:fade={{ duration: 150 }}>
            <p class="m-0 text-xs text-gedaempft">Gehört das nach</p>
            <p class="m-0 mt-0.5 truncate text-[0.9375rem]">{vorschlag.ordner}?</p>
            {#if verschiebeFehler}
              <p class="m-0 mt-1 text-xs text-schlecht">{verschiebeFehler}</p>
            {/if}
            <div class="mt-2.5 flex gap-2">
              <button
                type="button"
                onclick={vorschlagAnnehmen}
                disabled={verschiebt}
                class="rounded-element bg-akzent px-3 py-1.5 text-[0.8125rem] text-akzent-text
                       transition-transform active:scale-95 disabled:opacity-50"
              >
                {verschiebt ? "Verschiebe…" : "Ja, dorthin"}
              </button>
              <button
                type="button"
                onclick={() => (vorschlag = null)}
                class="rounded-element px-3 py-1.5 text-[0.8125rem] text-gedaempft
                       transition-colors hover:text-text"
              >
                Hier lassen
              </button>
            </div>
          </div>
        {/if}

        {#if anhaenge.length}
          <div class="karte overflow-hidden">
            {#each anhaenge as a (a.source + a.path)}
              <div
                class="flex items-center gap-3 border-b border-linie-weich px-3 py-2.5 last:border-0"
              >
                <span class="h-9 w-7 shrink-0 overflow-hidden rounded-klein bg-erhoben text-[0.5rem]">
                  <Dokumentbild quelle={a.vorschau} kuerzel={a.ext} />
                </span>

                {#if a.link}
                  <a href={a.link} class="min-w-0 flex-1">
                    <span class="block truncate text-[0.9375rem]">{a.name}</span>
                    <span class="block truncate text-xs text-gedaempft">{a.folder}</span>
                  </a>
                {:else}
                  <span class="min-w-0 flex-1">
                    <span class="block truncate text-[0.9375rem]" class:text-gedaempft={a.fehlt}>
                      {a.name}
                    </span>
                    <span class="block truncate text-xs" class:text-warn={a.fehlt} class:text-gedaempft={!a.fehlt}>
                      {a.fehlt ? "nicht mehr am alten Ort" : a.folder}
                    </span>
                  </span>
                {/if}

                <button
                  type="button"
                  onclick={() => loesen(a)}
                  aria-label="Dokument abhängen"
                  title="Verknüpfung lösen, Datei bleibt"
                  class="grid size-7 shrink-0 place-items-center rounded-full text-leise
                         transition-colors duration-200 hover:bg-erhoben hover:text-text"
                >
                  <Symbol name="close" groesse={13} />
                </button>
              </div>
            {/each}
          </div>
        {:else}
          <p class="m-0 px-1 py-3 text-xs text-leise">
            Noch nichts angehängt. Foto machen oder etwas aus Nextcloud verknüpfen.
          </p>
        {/if}
      </div>
    </div>
  {/if}
</Blatt>

<Scanblatt
  datei={scanDatei}
  schliessen={() => (scanDatei = null)}
  uebernehmen={(scan) => ablegen(scanDatei!, scan)}
/>

<Dokumentwahl
  offen={wahlOffen}
  schliessen={() => (wahlOffen = false)}
  waehlen={anhaengen}
  schon={anhaenge.map((a) => a.path)}
/>
