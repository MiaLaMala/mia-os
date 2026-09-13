<script lang="ts">
  /**
   * Ein Blatt, das von unten kommt und sich wegwischen lässt.
   *
   * Handy: von unten, Griff oben, wischbar. Desktop: mittig als Dialog.
   * Ein Bauteil für alles, was kurz über dem Inhalt liegt.
   */
  import type { Snippet } from "svelte";
  import { fade } from "svelte/transition";

  let {
    offen,
    schliessen,
    breit = false,
    titel = "",
    children,
  }: {
    offen: boolean;
    schliessen: () => void;
    breit?: boolean;
    titel?: string;
    children: Snippet;
  } = $props();

  let blatt: HTMLElement | undefined = $state();
  let zieht = $state(false);
  let versatz = $state(0);
  let startY = 0;
  let startZeit = 0;

  const SCHWELLE = 110;
  const SCHWUNG = 0.5;

  function anfang(e: TouchEvent) {
    const inhalt = blatt?.querySelector("[data-blatt-inhalt]");
    if (inhalt && inhalt.scrollTop > 0) return;

    // Bereiche, in denen selbst gezogen wird, dürfen das Blatt nicht
    // wegwischen. Sonst schließt die Geste, mit der Mia eine untere
    // Blattecke nach unten zieht, das Scan-Blatt: ihr Fund am 09.09.2026,
    // "ich hab die Möglichkeit, versehentlich das Popup zu schließen".
    const ziel = e.target as Element | null;
    if (ziel?.closest("[data-kein-wischen]")) return;

    startY = e.touches[0].clientY;
    startZeit = Date.now();
    zieht = true;
  }

  function bewegt(e: TouchEvent) {
    if (!zieht) return;
    versatz = Math.max(0, e.touches[0].clientY - startY);
  }

  function ende() {
    if (!zieht) return;
    const tempo = versatz / Math.max(1, Date.now() - startZeit);
    zieht = false;
    if (versatz > SCHWELLE || tempo > SCHWUNG) {
      versatz = 0;
      schliessen();
    } else {
      versatz = 0;
    }
  }

  function taste(e: KeyboardEvent) {
    if (e.key === "Escape" && offen) schliessen();
  }
</script>

<svelte:window onkeydown={taste} />

{#if offen}
  <div
    class="fixed inset-0 z-50 bg-black/50"
    transition:fade={{ duration: 180 }}
    style="opacity: {Math.max(0.25, 1 - versatz / 320)}; backdrop-filter: blur(3px);
           -webkit-backdrop-filter: blur(3px)"
    onclick={schliessen}
    onkeydown={(e) => e.key === "Enter" && schliessen()}
    role="button"
    tabindex="-1"
    aria-label="Schließen"
  ></div>

  <div
    bind:this={blatt}
    class="fixed inset-x-0 bottom-0 z-50 flex max-h-[92dvh] flex-col rounded-t-[22px]
           bg-flaeche shadow-blatt
           sm:inset-x-auto sm:bottom-auto sm:left-1/2 sm:top-1/2 sm:max-h-[84dvh]
           sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-karte sm:border sm:border-linie"
    class:sm:w-[32rem]={breit}
    class:sm:w-[26rem]={!breit}
    style="transform: translateY({versatz}px); transition: {zieht
      ? 'none'
      : 'transform .3s var(--ease-ruhig)'}"
    in:fade={{ duration: 200 }}
    out:fade={{ duration: 140 }}
    ontouchstart={anfang}
    ontouchmove={bewegt}
    ontouchend={ende}
    ontouchcancel={ende}
    role="dialog"
    aria-modal="true"
    aria-label={titel || undefined}
    tabindex="-1"
  >
    <div class="flex shrink-0 justify-center pb-1 pt-2.5 sm:hidden">
      <span
        class="h-[5px] w-9 rounded-full transition-colors duration-200"
        class:bg-linie={!zieht}
        class:bg-gedaempft={zieht}
      ></span>
    </div>

    {@render children()}
  </div>
{/if}
