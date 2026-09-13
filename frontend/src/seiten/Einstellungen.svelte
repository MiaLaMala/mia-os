<script lang="ts">
  /**
   * Einstellungen im Stil der iOS-Einstellungen: Gruppen als Karten,
   * jede Zeile ein Posten, rechts das Bedienelement. Kein Speichern-Knopf.
   */
  import { einstellungen } from "../lib/stores.svelte";
  import Seitenkopf from "../komponenten/Seitenkopf.svelte";
  import Abschnitt from "../komponenten/Abschnitt.svelte";
  import Ladezustand from "../komponenten/Ladezustand.svelte";
  import Segment from "../komponenten/Segment.svelte";
  import Symbol from "../komponenten/Symbol.svelte";
  import Kopplung from "../komponenten/Kopplung.svelte";

  let hinweis = $state("");
  let hinweisFehler = $state(false);
  let timer: ReturnType<typeof setTimeout>;

  const gruppen = $derived.by(() => {
    const raus = new Map<string, typeof einstellungen.posten>();
    for (const p of einstellungen.posten) {
      if (!raus.has(p.gruppe)) raus.set(p.gruppe, []);
      raus.get(p.gruppe)!.push(p);
    }
    return [...raus.entries()];
  });

  async function setzen(key: string, wert: string) {
    const ok = await einstellungen.setzen(key, wert);
    melden(ok ? "Gespeichert" : "Wert nicht möglich", !ok);
  }

  function melden(text: string, istFehler: boolean) {
    hinweis = text;
    hinweisFehler = istFehler;
    clearTimeout(timer);
    timer = setTimeout(() => (hinweis = ""), istFehler ? 3000 : 1600);
  }

  function schritt(key: string, min: number | undefined, max: number | undefined, delta: number) {
    const alt = Number(einstellungen.werte[key] ?? 0);
    const neu = Math.min(max ?? Infinity, Math.max(min ?? -Infinity, alt + delta));
    if (neu !== alt) setzen(key, String(neu));
  }
</script>

<Seitenkopf titel="Einstellungen" untertitel="Änderungen gelten sofort. Zugangsdaten stehen bewusst nicht hier." />

{#if !einstellungen.geladen}
  <Ladezustand />
{:else}
  {#each gruppen as [name, posten] (name)}
    <Abschnitt titel={name}>
      {#each posten as e (e.key)}
        {@const wert = einstellungen.werte[e.key]}
        <div class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-linie-weich px-3.5 py-3 last:border-0">
          <div class="min-w-0 flex-1 basis-40">
            <label id="l-{e.key}" for="f-{e.key}" class="block text-[0.9375rem] font-medium">
              {e.titel}
            </label>
            <p class="m-0 mt-0.5 text-xs leading-snug text-gedaempft">{e.hilfe}</p>
          </div>

          <div class="ml-auto shrink-0">
            {#if e.art === "schalter"}
              <button
                id="f-{e.key}"
                type="button"
                role="switch"
                aria-checked={wert === "1"}
                aria-labelledby="l-{e.key}"
                onclick={() => setzen(e.key, wert === "1" ? "0" : "1")}
                class="relative h-[31px] w-[51px] rounded-full transition-colors duration-200 ease-ruhig"
                class:bg-gut={wert === "1"}
                class:bg-linie={wert !== "1"}
              >
                <span
                  class="absolute top-[2px] size-[27px] rounded-full bg-white shadow-md
                         transition-[left] duration-200 ease-ruhig"
                  style="left: {wert === '1' ? '22px' : '2px'}"
                ></span>
              </button>
            {:else if e.art === "zahl"}
              <div class="flex items-center rounded-full bg-erhoben">
                <button
                  type="button"
                  onclick={() => schritt(e.key, e.minimum, e.maximum, -(e.maximum && e.maximum > 100 ? 5 : 1))}
                  aria-label="Weniger"
                  class="grid size-8 place-items-center rounded-full text-gedaempft hover:text-text"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14" /></svg>
                </button>
                <input
                  id="f-{e.key}"
                  type="number"
                  inputmode="numeric"
                  min={e.minimum}
                  max={e.maximum}
                  value={wert}
                  onchange={(ev) => setzen(e.key, ev.currentTarget.value)}
                  class="ziffern w-12 border-0 bg-transparent text-center text-[0.9375rem] font-medium
                         outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
                />
                <button
                  type="button"
                  onclick={() => schritt(e.key, e.minimum, e.maximum, e.maximum && e.maximum > 100 ? 5 : 1)}
                  aria-label="Mehr"
                  class="grid size-8 place-items-center rounded-full text-gedaempft hover:text-text"
                >
                  <Symbol name="plus" groesse={12} />
                </button>
              </div>
            {:else if e.art === "auswahl"}
              <Segment
                optionen={(e.optionen ?? []).map(([key, name]) => ({ key, name }))}
                wert={wert}
                waehlen={(k) => setzen(e.key, k)}
              />
            {/if}
          </div>
        </div>
      {/each}
    </Abschnitt>
  {/each}

  <Kopplung />
{/if}

<p
  class="mt-2 min-h-5 text-center text-xs transition-opacity duration-200"
  class:opacity-0={!hinweis}
  class:text-schlecht={hinweisFehler}
  class:text-gut={!hinweisFehler}
  role="status"
  aria-live="polite"
>
  {hinweis}
</p>
