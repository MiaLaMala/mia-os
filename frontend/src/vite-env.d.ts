/// <reference types="svelte" />
/// <reference types="vite/client" />

// Vite laedt CSS als Nebenwirkung. Ohne diese Zeile meldet svelte-check
// "Cannot find module or type declarations for side-effect import".
declare module "*.css";
