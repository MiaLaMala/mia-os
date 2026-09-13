<script lang="ts">
  /** 404 innerhalb der App. Ein Satz, ein Weg zurück. */
  import { link } from "svelte-spa-router";
  import Leerzustand from "../komponenten/Leerzustand.svelte";
</script>

<Leerzustand text="Diese Seite gibt es nicht." symbol="search" />
<p class="text-center">
  <a href="/" use:link class="rounded-full bg-erhoben px-4 py-2 text-sm font-medium text-text">
    Zurück zu Heute
  </a>
</p>
