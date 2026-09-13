/**
 * Der Symbolsatz. 24px-Raster, 1.5px Strich, runde Enden.
 *
 * Inline statt Bilddatei, damit sie currentColor erben und keinen
 * Netzabruf kosten. Keine Emojis: die brechen die Strichstärke und tragen
 * Fremdfarbe in die Palette.
 */

export const SYMBOLE: Record<string, string> = {
  "arrow-down": '<path d="M12 5v14M12 19l-5.5-5.5M12 19l5.5-5.5"/>',
  "arrow-up": '<path d="M12 19V5M12 5l-5.5 5.5M12 5l5.5 5.5"/>',
  "arrow-right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
  back: '<path d="M15 5.5 8.5 12l6.5 6.5"/>',
  book: '<path d="M12 6.5c-1.8-1.5-4.2-2.25-7.25-2.25v13.5C7.8 17.75 10.2 18.5 12 20c1.8-1.5 4.2-2.25 7.25-2.25V4.25C15.8 4.25 13.8 5 12 6.5Z"/><path d="M12 6.5V20"/>',
  calendar:
    '<rect x="3.25" y="5.25" width="17.5" height="15.5" rx="2.5"/><path d="M3.25 10.25h17.5M8 3.25v4M16 3.25v4"/>',
  camera:
    '<path d="M3.75 8.75a2 2 0 0 1 2-2h1.9l1.35-2h6l1.35 2h1.9a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2H5.75a2 2 0 0 1-2-2Z"/><circle cx="12" cy="13" r="3.5"/>',
  check: '<path d="M5 12.5 9.5 17 19 7.5"/>',
  chevron: '<path d="M8.5 10.5 12 14l3.5-3.5"/>',
  "chevron-down": '<path d="M7.5 10 12 14.5 16.5 10"/>',
  "chevron-left": '<path d="M14 7.5 9.5 12 14 16.5"/>',
  "chevron-right": '<path d="M10 7.5 14.5 12 10 16.5"/>',
  "chevron-up": '<path d="M7.5 14 12 9.5 16.5 14"/>',
  clock: '<circle cx="12" cy="12" r="8.25"/><path d="M12 7.5V12l3 2"/>',
  close: '<path d="M6.5 6.5 17.5 17.5M17.5 6.5 6.5 17.5"/>',
  document:
    '<path d="M6.25 3.75h7l4.5 4.5v12a1.5 1.5 0 0 1-1.5 1.5h-10a1.5 1.5 0 0 1-1.5-1.5V5.25a1.5 1.5 0 0 1 1.5-1.5Z"/><path d="M13.25 3.75v4.5h4.5"/><path d="M8.75 13h6.5M8.75 16.5h4.5"/>',
  external:
    '<path d="M13.75 4.25h6v6"/><path d="M19.75 4.25 11 13"/><path d="M18 14v5.25a1.5 1.5 0 0 1-1.5 1.5h-11a1.5 1.5 0 0 1-1.5-1.5v-11a1.5 1.5 0 0 1 1.5-1.5H10"/>',
  filter: '<path d="M4 6h16M7 12h10M10 18h4"/>',
  folder:
    '<path d="M3.25 7.25a2 2 0 0 1 2-2h3.4a2 2 0 0 1 1.5.7l1.1 1.3h7.5a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2H5.25a2 2 0 0 1-2-2Z"/>',
  grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/>',
  heart:
    '<path d="M12 20.25s-7.5-4.4-7.5-9.6a4.35 4.35 0 0 1 7.5-3 4.35 4.35 0 0 1 7.5 3c0 5.2-7.5 9.6-7.5 9.6Z"/>',
  info: '<circle cx="12" cy="12" r="8.25"/><path d="M12 11v5.5"/><path d="M12 7.75h.01" stroke-width="2.2"/>',
  home: '<path d="M4 11.25 12 4.5l8 6.75"/><path d="M6.25 9.75V19a1 1 0 0 0 1 1h3.25v-5.5h3v5.5h3.25a1 1 0 0 0 1-1V9.75"/>',
  kanban:
    '<rect x="3.5" y="4" width="5" height="16" rx="1.5"/><rect x="9.5" y="4" width="5" height="10" rx="1.5"/><rect x="15.5" y="4" width="5" height="13" rx="1.5"/>',
  layers: '<path d="m12 4 8.5 4.5L12 13 3.5 8.5Z"/><path d="m3.5 12.5 8.5 4.5 8.5-4.5"/><path d="m3.5 16.5 8.5 4.5 8.5-4.5"/>',
  list: '<path d="M8.5 6.5H20M8.5 12H20M8.5 17.5H20"/><path d="M4 6.5h.01M4 12h.01M4 17.5h.01" stroke-width="2.2"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  more: '<circle cx="6" cy="12" r="1.15" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.15" fill="currentColor" stroke="none"/><circle cx="18" cy="12" r="1.15" fill="currentColor" stroke="none"/>',
  note: '<path d="M5.25 4.75h13.5v14.5H5.25Z"/><path d="M8.5 9h7M8.5 12.5h7M8.5 16h4"/>',
  paperclip:
    '<path d="M18.5 11.5 12 18a4.25 4.25 0 0 1-6-6l7-7a2.85 2.85 0 0 1 4 4l-7 7a1.45 1.45 0 0 1-2-2l6.5-6.5"/>',
  pin: '<path d="M12 21v-5"/><path d="M8 16h8l-1-4V7h1V4H8v3h1v5Z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  refresh: '<path d="M20 12a8 8 0 1 1-2.35-5.65"/><path d="M20 4.5V10h-5.5"/>',
  search: '<circle cx="11" cy="11" r="6.25"/><path d="M15.5 15.5 20 20"/>',
  laptop:
    '<path d="M5.25 5.75a1.5 1.5 0 0 1 1.5-1.5h10.5a1.5 1.5 0 0 1 1.5 1.5v9.5H5.25Z"/><path d="M2.75 15.25h18.5l-1.5 3.25a1.5 1.5 0 0 1-1.35.85H5.6a1.5 1.5 0 0 1-1.35-.85Z"/>',
  phone:
    '<rect x="7" y="2.75" width="10" height="18.5" rx="2.5"/><path d="M10.75 18.75h2.5"/>',
  server:
    '<rect x="3.25" y="4.25" width="17.5" height="6" rx="2"/><rect x="3.25" y="13.75" width="17.5" height="6" rx="2"/><path d="M7 7.25h.01M7 16.75h.01"/>',
  settings:
    '<path d="M4.5 7.5h9M17 7.5h2.5"/><circle cx="15" cy="7.5" r="2"/><path d="M4.5 16.5h2.5M11 16.5h8.5"/><circle cx="9" cy="16.5" r="2"/>',
  sidebar:
    '<rect x="3.25" y="4.75" width="17.5" height="14.5" rx="2.5"/><path d="M9.25 4.75v14.5"/>',
  sparkles: '<path d="m12 4 1.8 4.7L18.5 10.5l-4.7 1.8L12 17l-1.8-4.7L5.5 10.5l4.7-1.8Z"/><path d="M18.5 16.5v3M17 18h3"/>',
  table: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 9.5h17M3.5 14.5h17M9.5 9.5v10"/>',
  trash: '<path d="M4.5 7h15"/><path d="M9.5 7V4.75h5V7"/><path d="M6.5 7l.75 12a1 1 0 0 0 1 .95h7.5a1 1 0 0 0 1-.95L17.5 7"/><path d="M10 11v5M14 11v5"/>',
  trending: '<path d="M3.5 16.5 9 11l3.5 3.5 7-7"/><path d="M15 7.5h4.5V12"/>',
};
