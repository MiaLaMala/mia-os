<script lang="ts">
  /**
   * Der Kalender. Ein normaler, schöner Kalender, Apple-Stil.
   *
   * FullCalendar liefert Monat, Woche, Tag. Die Kopfleiste ist unsere:
   * Monatsname, Blättern, Heute, Ansichtswahl, Kalenderfilter. Auf dem
   * Handy zeigt der Monat Punkte, darunter steht der gewählte Tag.
   */
  import { onMount } from "svelte";
  import { slide, fade } from "svelte/transition";
  import { Calendar } from "@fullcalendar/core";
  import deLocale from "@fullcalendar/core/locales/de";
  import dayGridPlugin from "@fullcalendar/daygrid";
  import timeGridPlugin from "@fullcalendar/timegrid";
  import interactionPlugin from "@fullcalendar/interaction";
  import { ausSpeicher, nachbarnVorladen, speicherLeeren, termineHolen } from "../lib/terminspeicher";
  import type { KalenderTermin, Eintrag } from "../lib/types";
  import { alsTag, langesDatum, uhrzeit, heute as heuteTag } from "../lib/datum";
  import { sammlung } from "../lib/sammlung.svelte";
  import Segment from "../komponenten/Segment.svelte";
  import Knopf from "../komponenten/Knopf.svelte";
  import Blatt from "../komponenten/Blatt.svelte";
  import Chip from "../komponenten/Chip.svelte";
  import Terminblatt, { type Termin } from "../komponenten/Terminblatt.svelte";
  import Eintragsblatt from "../komponenten/Eintragsblatt.svelte";
  import Symbol from "../komponenten/Symbol.svelte";

  const ANSICHTEN = [
    { key: "dayGridMonth", name: "Monat" },
    { key: "timeGridWeek", name: "Woche" },
    { key: "timeGridDay", name: "Tag" },
  ];

  let behaelter: HTMLElement | undefined = $state();
  let kalender: Calendar | undefined;
  let kalenderliste = $state<string[]>([]);
  let farben = $state<Record<string, string>>({});
  let gewaehlt = $state("");
  let laedt = $state(true);
  let fehler = $state("");
  let ansicht = $state("dayGridMonth");
  let titel = $state("");
  let filterOffen = $state(false);
  let schmal = $state(false);

  let gewaehlterTag = $state(heuteTag());
  let tagestermine = $state<KalenderTermin[]>([]);
  let offenerTermin = $state<Termin | null>(null);
  let aufgabenJeTag = $state<Record<string, number>>({});
  let offenerEintrag = $state<Eintrag | null>(null);

  const aktuellerEintrag = $derived(
    offenerEintrag
      ? (sammlung.eintraege.find((e) => e.id === offenerEintrag!.id) ?? offenerEintrag)
      : null,
  );
  const istHeuteSichtbar = $derived(gewaehlterTag === heuteTag());

  /** Marken für fällige Aufgaben. Nicht in dayCellDidMount: dort sind die
   *  Aufgaben noch nicht geladen. */
  function tagesmarkenZeichnen() {
    if (!behaelter) return;
    behaelter.querySelectorAll(".tag-aufgaben").forEach((x) => x.remove());
    for (const [tag, anzahl] of Object.entries(aufgabenJeTag)) {
      const kopf = behaelter.querySelector(`.fc-daygrid-day[data-date="${tag}"] .fc-daygrid-day-top`);
      if (!kopf) continue;
      const marke = document.createElement("span");
      marke.className = "tag-aufgaben";
      marke.textContent = String(anzahl);
      marke.title = `${anzahl} Aufgabe(n) fällig`;
      kopf.appendChild(marke);
    }
  }

  function gewaehltMarkieren() {
    if (!behaelter) return;
    behaelter.querySelectorAll(".fc-day-gewaehlt").forEach((e) => e.classList.remove("fc-day-gewaehlt"));
    behaelter.querySelector(`.fc-daygrid-day[data-date="${gewaehlterTag}"]`)?.classList.add("fc-day-gewaehlt");
  }

  $effect(() => {
    const tag = gewaehlterTag;
    if (!tag) return;
    termineHolen(tag, tag, gewaehlt)
      .then((d) => (tagestermine = d.termine))
      .catch(() => (tagestermine = []));
  });

  function wechseln(neu: string) {
    ansicht = neu;
    kalender?.changeView(neu, ansicht === "timeGridDay" ? gewaehlterTag : undefined);
  }

  function umwandeln(t: KalenderTermin) {
    return {
      id: t.id,
      title: t.title,
      start: t.start,
      end: t.end,
      allDay: t.allDay,
      backgroundColor: `color-mix(in srgb, ${t.farbe} 16%, transparent)`,
      borderColor: t.farbe,
      textColor: t.farbe,
      extendedProps: {
        kalender: t.kalender,
        hatNotiz: t.hat_notiz ?? false,
        offeneAufgaben: t.offene_aufgaben ?? 0,
        eintragId: t.eintrag_id ?? null,
        farbe: t.farbe,
      },
    };
  }

  function farbenMerken(termine: KalenderTermin[]) {
    const neu = { ...farben };
    for (const t of termine) if (t.kalender && !neu[t.kalender]) neu[t.kalender] = t.farbe;
    farben = neu;
  }

  onMount(() => {
    if (!behaelter) return;
    schmal = window.innerWidth < 640;

    // Aus der Suche kommt "#/termine?tag=2026-10-14": dann dorthin springen.
    const frage = window.location.hash.split("?")[1] ?? "";
    const zielTag = new URLSearchParams(frage).get("tag");
    if (zielTag && /^\d{4}-\d{2}-\d{2}$/.test(zielTag)) gewaehlterTag = zielTag;

    kalender = new Calendar(behaelter, {
      plugins: [dayGridPlugin, timeGridPlugin, interactionPlugin],
      locale: deLocale,
      initialView: "dayGridMonth",
      initialDate: zielTag && /^\d{4}-\d{2}-\d{2}$/.test(zielTag) ? zielTag : undefined,
      headerToolbar: false,
      fixedWeekCount: false,
      height: "auto",
      firstDay: 1,
      nowIndicator: true,
      dayMaxEvents: 3,
      eventDisplay: schmal ? "list-item" : "block",
      views: {
        timeGridDay: {
          slotMinTime: "06:00:00",
          slotMaxTime: "23:00:00",
          allDaySlot: true,
          allDayText: "ganztags",
          dayHeaders: false,
        },
        timeGridWeek: {
          slotMinTime: "06:00:00",
          slotMaxTime: "23:00:00",
          allDayText: "ganztags",
          dayHeaderFormat: { weekday: "short", day: "numeric" },
        },
        dayGridMonth: {
          dayMaxEvents: 3,
          displayEventTime: false,
          moreLinkContent: (arg) => `+${arg.num}`,
        },
      },
      scrollTime: "07:00:00",
      slotLabelFormat: { hour: "2-digit", minute: "2-digit", hour12: false },
      eventTimeFormat: { hour: "2-digit", minute: "2-digit", hour12: false },
      slotDuration: "00:30:00",
      slotLabelInterval: "01:00",

      dateClick: (info) => {
        const tag = info.dateStr.slice(0, 10);
        if (ansicht === "dayGridMonth" && gewaehlterTag === tag) {
          wechseln("timeGridDay");
          return;
        }
        gewaehlterTag = tag;
        gewaehltMarkieren();
      },

      eventDidMount: (info) => {
        const p = info.event.extendedProps;
        if (!p.hatNotiz && !p.offeneAufgaben) return;
        const marke = document.createElement("span");
        marke.className = "termin-marke";
        marke.textContent = p.offeneAufgaben ? String(p.offeneAufgaben) : "";
        marke.title = p.offeneAufgaben ? `${p.offeneAufgaben} offene Aufgabe(n)` : "Notiz vorhanden";
        const ziel =
          info.el.querySelector(".fc-event-title") ?? info.el.querySelector(".fc-event-main") ?? info.el;
        ziel.appendChild(marke);
      },

      eventClick: (info) => {
        info.jsEvent.preventDefault();
        const e = info.event;
        const eintragId = e.extendedProps.eintragId;
        if (eintragId) {
          sammlung.laden().then(() => {
            offenerEintrag = sammlung.eintraege.find((x) => x.id === eintragId) ?? null;
          });
          return;
        }
        const zeit = (d: Date | null) =>
          d ? d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" }) : "";
        offenerTermin = {
          uid: e.id,
          titel: e.title,
          datum: e.start ? langesDatum(alsTag(e.start)) : "",
          beginn: zeit(e.start),
          ende: zeit(e.end),
          ganztags: e.allDay,
          kalender: String(e.extendedProps.kalender ?? ""),
          farbe: String(e.extendedProps.farbe || "var(--color-akzent)"),
        };
      },

      datesSet: (info) => {
        ansicht = info.view.type;
        titel = info.view.title;
        queueMicrotask(() => {
          tagesmarkenZeichnen();
          gewaehltMarkieren();
        });
      },

      events: async (info, erfolg, misserfolg) => {
        const von = info.startStr.slice(0, 10);
        const bis = info.endStr.slice(0, 10);
        const da = ausSpeicher(von, bis, gewaehlt);
        if (da) {
          kalenderliste = da.kalender;
          farbenMerken(da.termine);
          erfolg(da.termine.map(umwandeln));
          aufgabenJeTag = da.aufgaben_je_tag ?? {};
          queueMicrotask(tagesmarkenZeichnen);
          laedt = false;
          nachbarnVorladen(info.start, gewaehlt);
          return;
        }
        try {
          laedt = true;
          const daten = await termineHolen(von, bis, gewaehlt);
          kalenderliste = daten.kalender;
          farbenMerken(daten.termine);
          erfolg(daten.termine.map(umwandeln));
          aufgabenJeTag = daten.aufgaben_je_tag ?? {};
          queueMicrotask(tagesmarkenZeichnen);
          fehler = "";
          nachbarnVorladen(info.start, gewaehlt);
        } catch (e) {
          fehler = e instanceof Error ? e.message : "Termine nicht erreichbar";
          misserfolg(e as Error);
        } finally {
          laedt = false;
        }
      },
    });

    kalender.render();

    // Wischen zum Blättern.
    let startX = 0, startY = 0, startZeit = 0;
    const anfang = (e: TouchEvent) => {
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      startZeit = Date.now();
    };
    const ende = (e: TouchEvent) => {
      const dx = e.changedTouches[0].clientX - startX;
      const dy = e.changedTouches[0].clientY - startY;
      if (Date.now() - startZeit > 600 || Math.abs(dx) < 60 || Math.abs(dy) > Math.abs(dx) * 0.6) return;
      dx < 0 ? kalender?.next() : kalender?.prev();
    };
    behaelter.addEventListener("touchstart", anfang, { passive: true });
    behaelter.addEventListener("touchend", ende, { passive: true });

    return () => {
      behaelter?.removeEventListener("touchstart", anfang);
      behaelter?.removeEventListener("touchend", ende);
      kalender?.destroy();
    };
  });

  function filtern(name: string) {
    gewaehlt = gewaehlt === name ? "" : name;
    kalender?.refetchEvents();
  }

  function zuHeute() {
    gewaehlterTag = heuteTag();
    kalender?.today();
    gewaehltMarkieren();
  }
</script>

<!-- Kopfleiste: Titel links, Werkzeuge rechts -->
<div class="mb-3 flex items-center gap-2">
  <h1 class="anzeige m-0 min-w-0 flex-1 truncate text-[1.5rem] leading-none lg:text-[1.75rem]">
    {titel}
  </h1>
  <button
    type="button"
    onclick={() => kalender?.prev()}
    aria-label="Zurück"
    class="grid size-9 place-items-center rounded-full text-gedaempft transition-colors hover:bg-erhoben hover:text-text active:scale-95"
  >
    <Symbol name="chevron-left" groesse={18} />
  </button>
  <button
    type="button"
    onclick={zuHeute}
    class="h-9 rounded-full px-3 text-[0.8125rem] font-medium transition-colors active:scale-95"
    class:bg-erhoben={istHeuteSichtbar}
    class:text-gedaempft={istHeuteSichtbar}
    class:bg-akzent={!istHeuteSichtbar}
    class:text-akzent-text={!istHeuteSichtbar}
  >
    Heute
  </button>
  <button
    type="button"
    onclick={() => kalender?.next()}
    aria-label="Weiter"
    class="grid size-9 place-items-center rounded-full text-gedaempft transition-colors hover:bg-erhoben hover:text-text active:scale-95"
  >
    <Symbol name="chevron-right" groesse={18} />
  </button>
</div>

<div class="mb-4 flex items-center gap-2">
  <Segment optionen={ANSICHTEN} wert={ansicht} waehlen={wechseln} />
  <span class="flex-1"></span>
  {#if kalenderliste.length}
    <Knopf
      symbol="filter"
      beschriftung="Kalender filtern"
      klick={() => (filterOffen = true)}
      aktiv={!!gewaehlt}
      text={gewaehlt || ""}
    />
  {/if}
</div>

{#if fehler}
  <p class="mb-3 rounded-element px-3.5 py-2.5 text-sm text-fehler" style="background: color-mix(in srgb, var(--color-fehler) 10%, transparent)">
    {fehler}
  </p>
{/if}

<div class="karte relative overflow-hidden px-2 py-2 sm:px-3 sm:py-3" class:opacity-60={laedt}>
  <div bind:this={behaelter} class="kalender" class:kalender-schmal={schmal}></div>
</div>

<!-- Der gewählte Tag unter dem Monat -->
{#if ansicht === "dayGridMonth"}
  <section class="mt-5" transition:slide={{ duration: 200 }}>
    <div class="mb-2 flex items-center justify-between px-1">
      <h2 class="m-0 text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-leise">
        {langesDatum(gewaehlterTag)}
      </h2>
      {#if tagestermine.length}
        <button type="button" onclick={() => wechseln("timeGridDay")} class="text-xs font-medium text-akzent">
          Tagesansicht
        </button>
      {/if}
    </div>
    {#if tagestermine.length}
      <ul class="karte m-0 list-none overflow-hidden p-0">
        {#each tagestermine as t, i (t.id)}
          <li class="auftauchen border-b border-linie-weich last:border-0" style="animation-delay: {Math.min(i, 8) * 30}ms">
            <button
              type="button"
              onclick={() => {
                if (t.eintrag_id) {
                  sammlung.laden().then(() => (offenerEintrag = sammlung.eintraege.find((x) => x.id === t.eintrag_id) ?? null));
                } else {
                  offenerTermin = {
                    uid: t.id,
                    titel: t.title,
                    datum: langesDatum(gewaehlterTag),
                    beginn: uhrzeit(t.start),
                    ende: t.end ? uhrzeit(t.end) : "",
                    ganztags: t.allDay,
                    kalender: t.kalender,
                    farbe: t.farbe,
                  };
                }
              }}
              class="flex w-full items-center gap-3 px-3.5 py-2.5 text-left transition-colors duration-150 hover:bg-erhoben"
            >
              <span class="ziffern w-12 shrink-0 text-[0.8125rem] text-gedaempft" class:text-[0.6875rem]={t.allDay}>
                {t.allDay ? "ganztags" : uhrzeit(t.start)}
              </span>
              <span class="h-5 w-[3px] shrink-0 rounded-full" style="background: {t.farbe}"></span>
              <span class="min-w-0 flex-1 truncate text-[0.9375rem]">{t.title}</span>
              {#if t.offene_aufgaben}
                <span class="ziffern rounded-full bg-akzent px-1.5 text-[0.625rem] font-semibold leading-4 text-akzent-text">{t.offene_aufgaben}</span>
              {:else if t.hat_notiz}
                <span class="text-leise"><Symbol name="note" groesse={14} /></span>
              {/if}
              {#if t.end && !t.allDay}
                <span class="ziffern shrink-0 text-xs text-leise">{uhrzeit(t.end)}</span>
              {/if}
            </button>
          </li>
        {/each}
      </ul>
    {:else}
      <p class="karte m-0 px-3.5 py-4 text-sm text-gedaempft">Nichts eingetragen.</p>
    {/if}
  </section>
{/if}

<!-- Filterblatt -->
<Blatt offen={filterOffen} schliessen={() => (filterOffen = false)} titel="Kalender">
  <div data-blatt-inhalt class="px-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-2 sm:pt-5">
    <h2 class="anzeige m-0 mb-3 text-[1.25rem]">Kalender</h2>
    <div class="flex flex-wrap gap-2">
      <Chip aktiv={!gewaehlt} klick={() => { filtern(""); filterOffen = false; }}>Alle</Chip>
      {#each kalenderliste as name (name)}
        <Chip aktiv={gewaehlt === name} farbe={farben[name] ?? ""} klick={() => { filtern(name); filterOffen = false; }}>
          {name}
        </Chip>
      {/each}
    </div>
  </div>
</Blatt>

<Eintragsblatt
  eintrag={aktuellerEintrag}
  schliessen={() => {
    offenerEintrag = null;
    speicherLeeren();
    kalender?.refetchEvents();
  }}
/>

<Terminblatt
  termin={offenerTermin}
  schliessen={() => (offenerTermin = null)}
  geaendert={() => {
    speicherLeeren();
    kalender?.refetchEvents();
  }}
/>

<style>
  /* FullCalendar auf die eigenen Tokens ziehen. */
  .kalender {
    --fc-border-color: var(--color-linie-weich);
    --fc-page-bg-color: transparent;
    --fc-neutral-bg-color: transparent;
    --fc-today-bg-color: transparent;
    --fc-now-indicator-color: var(--color-fehler);
    --fc-event-border-color: transparent;
    font-size: 0.8125rem;
    transition: opacity 200ms var(--ease-ruhig);
  }

  /* Kein Außenrahmen um das Raster: die Karte ist der Rahmen. */
  .kalender :global(.«redacted:fc-…»),
  .kalender :global(.fc-scrollgrid-section > *) {
    border: none !important;
  }
  .kalender :global(.fc-theme-standard th) {
    border: none;
  }
  .kalender :global(.fc-theme-standard td) {
    border-color: var(--color-linie-weich);
  }
  .kalender :global(.fc-daygrid-day:first-child),
  .kalender :global(.fc-timegrid-slot-label) {
    border-left: none !important;
  }
  .kalender :global(td:last-child) {
    border-right: none !important;
  }

  /* Wochentage */
  .kalender :global(.fc-col-header-cell-cushion) {
    padding: 0 0 8px;
    font-size: 0.6875rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--color-leise);
    text-decoration: none;
  }
  .kalender :global(.fc-day-today .fc-col-header-cell-cushion) {
    color: var(--color-akzent);
  }

  /* Tageszahl: runder Punkt bei heute, Ring beim gewählten Tag. */
  .kalender :global(.fc-daygrid-day-number) {
    display: inline-grid;
    place-items: center;
    width: 1.625rem;
    height: 1.625rem;
    margin: 3px;
    padding: 0;
    border-radius: 999px;
    font-size: 0.8125rem;
    color: var(--color-text);
    text-decoration: none;
    font-variant-numeric: tabular-nums;
  }
  .kalender :global(.fc-day-other .fc-daygrid-day-number) {
    color: var(--color-leise);
  }
  .kalender :global(.fc-day-today .fc-daygrid-day-number) {
    background: var(--color-akzent);
    color: var(--color-akzent-text) !important;
    font-weight: 600;
  }
  .kalender :global(.fc-day-gewaehlt:not(.fc-day-today) .fc-daygrid-day-number) {
    box-shadow: inset 0 0 0 1.5px var(--color-akzent);
    color: var(--color-akzent);
    font-weight: 600;
  }

  .kalender :global(.fc-daygrid-day-frame) {
    min-height: 5.25rem;
    cursor: pointer;
    transition: background 160ms var(--ease-ruhig);
  }
  .kalender :global(.fc-daygrid-day-frame:hover) {
    background: color-mix(in srgb, var(--color-akzent) 6%, transparent);
  }

  /* Termine im Monat: Balken mit Farbfläche */
  .kalender :global(.fc-event) {
    border-radius: 5px;
    padding: 1px 5px;
    font-weight: 500;
    font-size: 0.75rem;
    cursor: pointer;
    transition: filter 150ms var(--ease-ruhig), transform 150ms var(--ease-ruhig);
  }
  .kalender :global(.fc-event:hover) {
    filter: brightness(1.15);
  }
  .kalender :global(.fc-event:active) {
    transform: scale(0.97);
  }
  .kalender :global(.fc-daygrid-event) {
    margin: 1px 3px;
  }
  .kalender :global(.fc-daygrid-more-link) {
    font-size: 0.6875rem;
    color: var(--color-gedaempft);
    margin: 0 5px;
  }
  .kalender :global(.fc-popover) {
    background: var(--color-erhoben);
    border: none;
    border-radius: var(--radius-element);
    box-shadow: var(--shadow-menue);
  }
  .kalender :global(.fc-popover-header) {
    background: transparent;
    padding: 8px 10px 4px;
    font-size: 0.75rem;
    color: var(--color-gedaempft);
  }

  /* Zeitachse */
  .kalender :global(.fc-timegrid-slot) {
    height: 2.4rem;
    cursor: pointer;
  }
  .kalender :global(.fc-timegrid-slot-minor) {
    border-top-style: dotted !important;
  }
  .kalender :global(.fc-timegrid-slot-label-cushion),
  .kalender :global(.fc-timegrid-axis-cushion) {
    font-size: 0.6875rem;
    color: var(--color-leise);
    font-variant-numeric: tabular-nums;
  }
  .kalender :global(.fc-timegrid-event) {
    border-radius: 6px;
    box-shadow: inset 0 0 0 1px color-mix(in srgb, currentColor 35%, transparent);
    padding: 2px 5px;
  }
  .kalender :global(.fc-timegrid-event .fc-event-time) {
    font-size: 0.6875rem;
    opacity: 0.8;
  }
  .kalender :global(.fc-timegrid-now-indicator-line) {
    border-width: 1.5px 0 0;
  }
  .kalender :global(.fc-timegrid-now-indicator-arrow) {
    display: none;
  }
  .kalender :global(.fc-timegrid-axis) {
    border: none !important;
  }

  /* Marken */
  .kalender :global(.termin-marke) {
    display: inline-grid;
    place-items: center;
    min-width: 0.875rem;
    height: 0.875rem;
    margin-left: 0.25rem;
    padding: 0 0.1875rem;
    border-radius: 999px;
    background: currentColor;
    color: var(--color-flaeche);
    font-size: 0.5625rem;
    font-weight: 700;
    vertical-align: middle;
  }
  .kalender :global(.termin-marke:empty) {
    min-width: 0.375rem;
    height: 0.375rem;
    padding: 0;
  }
  .kalender :global(.tag-aufgaben) {
    display: inline-grid;
    place-items: center;
    min-width: 1rem;
    height: 1rem;
    margin: 3px 0 0 2px;
    padding: 0 0.25rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--color-akzent) 18%, transparent);
    color: var(--color-akzent);
    font-size: 0.625rem;
    font-weight: 700;
  }

  /* Handy-Monat: Punkte statt Balken, Zahl mittig über den Punkten. */
  .kalender-schmal :global(.fc-daygrid-day-frame) {
    min-height: 3.25rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-bottom: 5px;
  }
  .kalender-schmal :global(.fc-theme-standard td) {
    border: none !important;
  }
  .kalender-schmal :global(.fc-daygrid-body tr + tr td) {
    border-top: 1px solid var(--color-linie-weich) !important;
  }
  .kalender-schmal :global(.fc-daygrid-day-top) {
    justify-content: center;
  }
  .kalender-schmal :global(.fc-daygrid-day-number) {
    margin: 4px 0 0;
  }
  .kalender-schmal :global(.fc-daygrid-day-events) {
    display: flex;
    flex-wrap: nowrap;
    justify-content: center;
    gap: 3px;
    margin: 4px 0 0 !important;
    min-height: 0;
    overflow: hidden;
    padding: 0 2px;
  }
  .kalender-schmal :global(.fc-daygrid-day-bottom) {
    display: none;
  }
  .kalender-schmal :global(.fc-daygrid-event) {
    margin: 0;
    padding: 0;
    position: relative;
  }
  .kalender-schmal :global(.fc-daygrid-dot-event) {
    background: none !important;
  }
  .kalender-schmal :global(.fc-daygrid-event .fc-event-title),
  .kalender-schmal :global(.fc-daygrid-event .fc-event-time) {
    display: none;
  }
  .kalender-schmal :global(.fc-daygrid-event-dot) {
    margin: 0;
    border-width: 3.5px;
    border-radius: 999px;
  }
  .kalender-schmal :global(.fc-daygrid-block-event) {
    width: 7px;
    height: 7px;
    border-radius: 999px;
    background: currentColor;
    flex: none;
  }
  .kalender-schmal :global(.fc-daygrid-block-event .fc-event-main) {
    display: none;
  }
  .kalender-schmal :global(.fc-daygrid-event .termin-marke) {
    position: absolute;
    inset: -2.5px;
    min-width: 0;
    height: auto;
    margin: 0;
    padding: 0;
    border: 1.5px solid currentColor;
    background: none;
    font-size: 0;
    opacity: 0.6;
  }
  .kalender-schmal :global(.fc-daygrid-more-link) {
    font-size: 0.5625rem;
    margin: 0 0 0 1px;
    padding: 0;
  }
  .kalender-schmal :global(.tag-aufgaben) {
    min-width: 0.875rem;
    height: 0.875rem;
    font-size: 0.5625rem;
    margin: 4px 0 0 2px;
  }
  /* Zeitansichten auf dem Handy: alles sichtbar. */
  .kalender-schmal :global(.fc-timegrid-event .fc-event-title),
  .kalender-schmal :global(.fc-timegrid-event .fc-event-time),
  .kalender-schmal :global(.fc-timegrid-event .fc-event-main) {
    display: block;
  }
  .kalender-schmal :global(.fc-timegrid-slot) {
    height: 2.1rem;
  }
</style>


