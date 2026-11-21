"use strict";
/* Catalog data lives separately from the active tournament/operation queue. */
(() => {
  const $ = id => document.getElementById(id);
  const DB = "spravaturnaje-offline-player-catalog";
  const STORE = "catalog";
  const KEY = "recent-tournaments-v1";
  const URL_API = "/api/offline/player-catalog";
  const state = { tournaments: [], selectedId: null, updatedAt: null };
  const cleanName = value => String(value || "").trim().replace(/\s+/g, " ");
  const nameKey = value => cleanName(value).toLocaleLowerCase("cs-CZ");

  function dbOpen() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  async function readCache() {
    const db = await dbOpen();
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, "readonly");
        const req = tx.objectStore(STORE).get(KEY);
        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => reject(req.error);
      });
    } finally { db.close(); }
  }
  async function writeCache(data) {
    const db = await dbOpen();
    try {
      await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).put(data, KEY);
        tx.oncomplete = resolve;
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      });
    } finally { db.close(); }
  }
  function currentNames() {
    return ($("newTournamentPlayers")?.value || "").split(/[\n,]+/).map(cleanName).filter(Boolean);
  }
  function addPlayers(names) {
    const textarea = $("newTournamentPlayers");
    if (!textarea) return;
    const all = currentNames();
    const seen = new Set(all.map(nameKey));
    let count = 0;
    for (const value of names) {
      const name = cleanName(value);
      if (!name || seen.has(nameKey(name))) continue;
      seen.add(nameKey(name));
      all.push(name);
      count++;
    }
    if (count) {
      textarea.value = all.join("\n");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
      textarea.dispatchEvent(new Event("change", { bubbles: true }));
    }
    renderPlayers();
  }
  const status = message => { $("playerCatalogStatus").textContent = message; };
  function selected() {
    return state.tournaments.find(t => t.id === state.selectedId) || null;
  }
  function renderTournaments() {
    const root = $("playerCatalogTournaments");
    root.replaceChildren();
    const search = nameKey($("playerCatalogSearch").value);
    const items = state.tournaments.filter(t => nameKey(t.name).includes(search));
    if (!items.length) { root.textContent = state.tournaments.length ? "Žádná shoda." : "Žádné uložené turnaje."; return; }
    for (const t of items) {
      const row = document.createElement("div");
      row.className = "offline-catalog-tournament";
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("aria-pressed", String(t.id === state.selectedId));
      button.textContent = `${t.name} (${t.dateLabel})`;
      button.addEventListener("click", () => {
        state.selectedId = t.id;
        renderTournaments();
        renderPlayers();
      });
      row.append(button);
      root.append(row);
    }
  }
  function renderPlayers() {
    const root = $("playerCatalogPlayers");
    const addAll = $("playerCatalogAddAll");
    root.replaceChildren();
    const t = selected();
    addAll.hidden = !t;
    if (!t) { root.textContent = "Vyber turnaj vlevo."; return; }
    const current = new Set(currentNames().map(nameKey));
    const available = t.players.filter(p => !current.has(nameKey(p)));
    addAll.disabled = available.length === 0;
    if (!t.players.length) { root.textContent = "Turnaj nemá dostupné hráče."; return; }
    if (!available.length) { root.textContent = "Všichni hráči už byli přidáni."; return; }
    for (const player of available) {
      const row = document.createElement("div");
      row.className = "offline-catalog-player";
      const span = document.createElement("span");
      span.textContent = player;
      const button = document.createElement("button");
      button.type = "button";
      button.title = `Přidat hráče ${player}`;
      button.setAttribute("aria-label", `Přidat hráče ${player}`);
      button.textContent = "+";
      button.addEventListener("click", () => addPlayers([player]));
      row.append(span, button);
      root.append(row);
    }
  }
  function updateState(data) {
    if (!data || !Array.isArray(data.tournaments)) throw new Error("Neplatný katalog hráčů.");
    state.tournaments = data.tournaments;
    state.updatedAt = data.updated_at || null;
    if (!state.tournaments.some(t => t.id === state.selectedId)) {
      state.selectedId = state.tournaments[0]?.id ?? null;
    }
    renderTournaments();
    renderPlayers();
    status(`${state.tournaments.length} uložených turnajů${state.updatedAt ? " · aktualizováno " + new Date(state.updatedAt).toLocaleString("cs-CZ") : ""}`);
  }
  let syncing = false;
  async function refresh() {
    if (syncing) return;
    if (!navigator.onLine) { status("Bez internetu · používám poslední uložené turnaje."); return; }
    syncing = true;
    const btn = $("playerCatalogRefresh");
    btn.disabled = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const res = await fetch(URL_API, { credentials: "same-origin", cache: "no-store", signal: controller.signal, headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(res.status === 401 ? "Přihlas se na testovacím webu pro aktualizaci hráčů." : `Server vrátil HTTP ${res.status}.`);
      const data = await res.json();
      await writeCache(data); // replace only on fully successful response
      updateState(data);
    } catch (err) {
      status(`${state.tournaments.length ? "Používám uložené turnaje. " : "Katalog zatím není uložený. "}Aktualizace se nepovedla (${err.name === "AbortError" ? "server neodpovídá" : err.message}).`);
    } finally { clearTimeout(timeout); btn.disabled = false; syncing = false; }
  }
  async function initialize() {
    if (!$("playerCatalogPanel")) return;
    $("playerCatalogAddAll").addEventListener("click", () => addPlayers(selected()?.players || []));
    $("playerCatalogSearch").addEventListener("input", renderTournaments);
    $("newTournamentPlayers").addEventListener("input", renderPlayers);
    $("playerCatalogRefresh").addEventListener("click", refresh);
    try {
      const saved = await readCache();
      if (saved) updateState(saved);
      else { renderTournaments(); renderPlayers(); status("Zatím žádné uložené turnaje. Připoj se doma k internetu."); }
    } catch (err) { status(`Lokální katalog se nepodařilo načíst: ${err.message}`); }
    await refresh(); // cache-first, network optional; no tournament results are sent
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, {once:true});
  else initialize();
})();
