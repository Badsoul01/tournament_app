"use strict";

const ENGINE_FILES = [
  "app/models/models.py",
  "app/services/utils/transaction.py",
  "app/services/utils/player.py",
  "app/services/utils/match.py",
  "app/services/tournament/groupmanager.py",
  "app/services/tournament/playoff.py",
  "app/services/tournament/seedingengine.py",
  "app/services/tournament/tournament.py",
  "app/web/webmanager.py",
  "real_tournament/engine_dry_run.py"
];

// Keep a separate, explicit copy of engine sources in Cache Storage.
// This avoids relying on browser HTTP cache or on a network fetch while offline.
const ENGINE_SOURCE_CACHE = "st-offline-flask-engine-v2";

async function cachedPythonSource(file) {
 const path = file.startsWith("real_tournament/")
    ? "./" + file.slice("real_tournament/".length)
    : "./engine/" + file;
  const url = new URL(path, location.href).href;
  const cache = await caches.open(ENGINE_SOURCE_CACHE);
  let response = await cache.match(url);
  if (!response) {
    try {
      response = await fetch(url, { cache: "no-cache" });
    } catch (err) {
      throw new Error(`${file}: není v offline cache a síť je nedostupná (${err?.message || err})`);
    }
    if (!response.ok) throw new Error(`${file}: HTTP ${response.status}`);
    await cache.put(url, response.clone());
  }
  if (!response.ok) throw new Error(`${file}: HTTP ${response.status}`);
  return await response.text();
}

async function ensureEngineFiles(py) {
  for (const file of ENGINE_FILES) {
    const code = await cachedPythonSource(file);
    const target = "/home/pyodide/" + file;
    py.FS.mkdirTree(target.substring(0, target.lastIndexOf("/")));
    py.FS.writeFile(target, code);
  }
}
