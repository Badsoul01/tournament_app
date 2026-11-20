"use strict";
const SHELL = "st-offline-flask-shell-pwa-v7";
const RUNTIME = "st-offline-flask-runtime-v1";
const CORE = ["./", "./index.html", "./app.js", "./style.css", "./live_style.css", "./live_perchanment.css", "./live_nav.css", "./live_tournament.css", "./offline_live_adapter.css", "./sw.js",
  "./engine_dry_run.js", "./engine_dry_run.py", "./real_match.js", "./real_match.py", './real_match_edit.py',
  "./sync_stage.js", "./offline_nav.js", "./offline_player_catalog.js", "./offline_player_catalog.css",
  "./offline_group_draft.js", "./offline_group_draft.css", "./offline_create.js", "./offline_create.py", "./local_finish_stage.js",
  "./offline_groups_live.js", "./offline_groups_live.css", "./offline_playoff_live.js", "./offline_playoff_live.css", "./offline_results_live.js", "./offline_results_live.css", "./manifest.webmanifest",
  "./icon-192.png", "./icon-512.png", "./apple-touch-icon.png"];
const EXTERNAL = new Set(["cdn.jsdelivr.net", "cdn.pyodide.org", "files.pythonhosted.org", "pypi.org"]);

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL);
    await cache.addAll(CORE);
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    // Clean only caches owned by this new Flask offline integration.
    for (const name of await caches.keys()) {
      if (name.startsWith("st-offline-flask-") &&
          ![SHELL, RUNTIME, "st-offline-flask-engine-v1"].includes(name)) {
        await caches.delete(name);
      }
    }
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  const local = url.origin === self.location.origin;
  const scopePath = new URL(self.registration.scope).pathname;
  // Never touch regular tournament pages or the Flask API.
  if (local && (!url.pathname.startsWith(scopePath) || url.pathname.startsWith("/api/"))) return;
  if (!local && !EXTERNAL.has(url.hostname)) return;

  event.respondWith((async () => {
    const cache = await caches.open(local ? SHELL : RUNTIME);
    if (local && event.request.mode === "navigate") {
      try {
        const response = await fetch(event.request);
        if (response.ok) await cache.put(event.request, response.clone());
        return response;
      } catch (error) {
        const hit = await cache.match(event.request) || await cache.match("./index.html");
        if (hit) return hit;
        throw error;
      }
    }
    const hit = await cache.match(event.request);
    if (hit) return hit;
    const response = await fetch(event.request);
    if (response.ok) {
      try { await cache.put(event.request, response.clone()); }
      catch (err) { console.warn("Cache storage failed", err); }
    }
    return response;
  })());
});
