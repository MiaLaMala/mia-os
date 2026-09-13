import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";

// Das Ergebnis landet dort, wo FastAPI seine statischen Dateien ausliefert.
// Kein CDN: auf einer Seite mit Ausweisen und Arztunterlagen wird nichts von
// fremden Servern nachgeladen.
export default defineConfig({
  plugins: [svelte(), tailwindcss()],
  // FastAPI liefert die Dateien unter /static/gebaut aus. Ohne diese Basis
  // zeigt das gebaute HTML auf /app.js und laeuft ins Leere.
  base: "/static/gebaut/",
  build: {
    outDir: "../backend/src/web/static/gebaut",
    emptyOutDir: true,
    // Namen mit Inhalts-Pruefsumme. Frueher hiess das Buendel immer "app.js":
    // Safari hat auf Mias iPhone die alte Fassung behalten und das neue
    // Berichtsheft tagelang nicht gezeigt, obwohl der Server es lieferte.
    // Bei jeder Aenderung entsteht jetzt ein neuer Dateiname, den kein
    // Zwischenspeicher kennen kann. Das erzeugte index.html verweist selbst
    // darauf, es gibt kein Jinja-Template mehr, das nachgezogen werden muss.
    rollupOptions: {
      output: {
        entryFileNames: "app-[hash].js",
        chunkFileNames: "[name]-[hash].js",
        assetFileNames: "[name]-[hash][extname]",
      },
    },
  },
  server: {
    // Im Entwicklungsmodus laufen die API-Aufrufe an das echte Backend.
    proxy: {
      "/api": { target: "http://127.0.0.1:8080", changeOrigin: true },
    },
  },
});
