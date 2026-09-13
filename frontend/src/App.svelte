<script lang="ts">
  /**
   * Der Rahmen.
   *
   * Desktop: eine schmale Seitenleiste links, Inhalt rechts.
   * Handy: Inhalt oben, vier Ziele unten in Daumenreichweite, der Rest
   * in einem Blatt hinter "Mehr". Ein Stil, keine zweite Sprache.
   */
  import Router, { router } from "svelte-spa-router";
  import { onMount, tick } from "svelte";
  import { fade, fly } from "svelte/transition";
  import { routen, NAVIGATION, EINSTELLUNGEN } from "./lib/routen";
  import { einstellungen, blaetter } from "./lib/stores.svelte";
  import { seiten } from "./lib/seiten.svelte";
  import Seitenleiste from "./komponenten/Seitenleiste.svelte";
  import Unterleiste from "./komponenten/Unterleiste.svelte";
  import MehrBlatt from "./komponenten/MehrBlatt.svelte";
  import Schnelleingabe from "./komponenten/Schnelleingabe.svelte";
  import Suche from "./komponenten/Suche.svelte";

  let mehrOffen = $state(false);
  let breit = $state(false);
  let leisteEingeklappt = $state(false);
  let gescrollt = $state(false);

  const aktiverTitel = $derived.by(() => {
    const pfad = router.location;
    const treffer = [...NAVIGATION, EINSTELLUNGEN].find((n) => n.pfad === pfad);
    if (treffer) return treffer.titel;
    const id = Number(pfad.replace("/seite/", ""));
    return seiten.alle.find((s) => s.id === id)?.titel ?? "Mia OS";
  });

  onMount(() => {
    einstellungen.laden();
    seiten.laden();

    leisteEingeklappt = localStorage.getItem("leiste") === "zu";

    const pruefen = () => (breit = window.innerWidth >= 900);
    pruefen();
    window.addEventListener("resize", pruefen);

    const scrollen = () => (gescrollt = window.scrollY > 28);
    window.addEventListener("scroll", scrollen, { passive: true });

    // Cmd+K / Ctrl+K: Suche. Cmd+J / Ctrl+J: Schnelleingabe.
    const tasten = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key === "k") {
        e.preventDefault();
        blaetter.suche ? blaetter.schliessen() : blaetter.sucheOeffnen();
      } else if (e.key === "j") {
        e.preventDefault();
        blaetter.schnell ? blaetter.schliessen() : blaetter.schnellOeffnen();
      }
    };
    window.addEventListener("keydown", tasten);

    return () => {
      window.removeEventListener("resize", pruefen);
      window.removeEventListener("scroll", scrollen);
      window.removeEventListener("keydown", tasten);
    };
  });

  // Auf welcher Seite die Schnelleingabe landet: auf einer Sammlungsseite
  // dort, sonst in der Hauptsammlung.
  const aktuelleSeite = $derived.by(() => {
    const id = Number(router.location.replace("/seite/", ""));
    if (!router.location.startsWith("/seite/") || !id) return 0;
    const s = seiten.alle.find((x) => x.id === id);
    return s?.hat_sammlung && !s.sammelt_alles ? id : 0;
  });

  function leisteUmschalten() {
    leisteEingeklappt = !leisteEingeklappt;
    localStorage.setItem("leiste", leisteEingeklappt ? "zu" : "auf");
  }

  // Beim Seitenwechsel: Blatt zu, nach oben.
  $effect(() => {
    void router.location;
    tick().then(() => {
      mehrOffen = false;
      window.scrollTo({ top: 0 });
    });
  });
</script>

<div class="flex min-h-dvh">
  {#if breit}
    <Seitenleiste eingeklappt={leisteEingeklappt} umschalten={leisteUmschalten} />
  {/if}

  <div class="flex min-w-0 flex-1 flex-col">
    {#if !breit}
      <!-- Kompakte Kopfzeile, die erst beim Scrollen erscheint: solange der
           große Seitentitel im Bild ist, sagt sie nichts Neues. -->
      <header
        class="pointer-events-none fixed inset-x-0 top-0 z-30 flex h-[calc(2.75rem+env(safe-area-inset-top))]
               items-end justify-center border-b pb-2.5 pt-[env(safe-area-inset-top)]
               transition-[opacity,background] duration-200 ease-ruhig"
        class:opacity-0={!gescrollt}
        class:border-linie={gescrollt}
        class:border-transparent={!gescrollt}
        style="background: color-mix(in srgb, var(--color-grund) 82%, transparent);
               backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px)"
        aria-hidden={!gescrollt}
      >
        <span class="truncate px-4 text-[0.9375rem] font-semibold tracking-tight">
          {aktiverTitel}
        </span>
      </header>
    {/if}

    <main
      class="min-w-0 flex-1 px-4 pt-[calc(1.25rem+env(safe-area-inset-top))]
             pb-[calc(5.5rem+env(safe-area-inset-bottom))] lg:px-10 lg:pb-10 lg:pt-8"
    >
      <div class="mx-auto w-full max-w-3xl">
        {#key router.location}
          <div in:fly={{ y: 6, duration: 220, delay: 20 }}>
            <Router routes={routen} />
          </div>
        {/key}
      </div>
    </main>
  </div>

  {#if !breit}
    <Unterleiste
      mehrOffen={mehrOffen}
      mehr={() => (mehrOffen = !mehrOffen)}
      plus={() => {
        mehrOffen = false;
        blaetter.schnellOeffnen();
      }}
    />
    <MehrBlatt offen={mehrOffen} schliessen={() => (mehrOffen = false)} />
  {/if}

  <Schnelleingabe offen={blaetter.schnell} schliessen={blaetter.schliessen} pageId={aktuelleSeite} />
  <Suche offen={blaetter.suche} schliessen={blaetter.schliessen} />
</div>
