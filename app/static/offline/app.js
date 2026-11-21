"use strict";

const PYODIDE_BASE = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";
const RUNTIME_CACHE = "st-offline-flask-runtime-v1";
const DB_NAME = "spravaturnaje-lab194c"; // Zachovano kvuli kompatibilite ulozenych dat na stejnem originu
const STORE = "copies";
const OP_STORE = "pending_operations";
const COPY_KEY = "live_76";  // Historicky klic - zatim nemenit bez migrace IndexedDB.
let runtimePromise = null;
const $ = (id) => document.getElementById(id);

const PY = String.raw`
import sqlite3, json
con=sqlite3.connect('/tmp/lab194b.sqlite')
con.row_factory=sqlite3.Row
try:
    good=con.execute('PRAGMA integrity_check').fetchone()[0]
    if good!='ok': raise ValueError('Kontrola SQLite neprošla: '+str(good))
    tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required={'tournaments','groups','players','brackets','matches','match_results','offline_source'}
    if not required.issubset(tables): raise ValueError('Toto není databáze experimentu 19.4A; chybí: '+', '.join(sorted(required-tables)))
    source=[dict(r) for r in con.execute('SELECT * FROM offline_source')]
    if len(source)!=1 or source[0]['source_kind'] not in ('live','local'): raise ValueError('Chybí jednoznačný původ turnaje')
    data={'source': source[0], 'integrity_check':good}
    for table in ['tournaments','groups','players','brackets','matches','match_results','group_stats','playoff_stats','consolation_stats']:
        data[table]=[dict(r) for r in con.execute('SELECT * FROM '+table)]
    for b in data['brackets']:
        if b['tree_data']:
            b['tree_data']=json.loads(b['tree_data']) if isinstance(b['tree_data'],str) else b['tree_data']
    result_json=json.dumps(data, ensure_ascii=False)
finally:
    con.close()
result_json
`;

function element(tag, value, className) {
  const node = document.createElement(tag);
  if (value !== undefined) node.textContent = String(value);
  if (className) node.className = className;
  return node;
}

function errorMessage(err) {
  $("error").textContent = String(err?.message || err);
  console.error(err);
}

function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 2);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) {
        request.result.createObjectStore(STORE);
      }
      if (!request.result.objectStoreNames.contains(OP_STORE)) {
        const ops = request.result.createObjectStore(OP_STORE, { keyPath: "request_id" });
        ops.createIndex("by_tournament", "tournament_id", { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function transact(mode, operation) {
  const db = await openDB();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const request = operation(tx.objectStore(STORE));
      let result;
      request.onsuccess = () => { result = request.result; };
      request.onerror = () => reject(request.error);
      tx.oncomplete = () => resolve(result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error("IndexedDB transakce byla přerušena"));
    });
  } finally {
    db.close();
  }
}

const getCopy = () => transact("readonly", (store) => store.get(COPY_KEY));
const saveCopy = (value) => transact("readwrite", (store) => store.put(value, COPY_KEY));
// 22.9D: locally durable operation queue; no network calls here.
// The IndexedDB transaction commits BOTH the SQLite blob and the operation, or neither.
async function saveCopyAndQueue(nextCopy, previousCopy, operation) {
  if (!operation || operation.action !== "submit_result" || !Array.isArray(operation.sets) || !operation.sets.length) {
    throw new Error("Neplatná synchronizační operace.");
  }
  if (!globalThis.crypto?.randomUUID) throw new Error("Pro frontu operací je nutné HTTPS nebo localhost.");
  const queued = {
    request_id: crypto.randomUUID(),
    tournament_id: nextCopy.sourceId,
    action: "submit_result",
    match_id: operation.match_id,
    sets: operation.sets.map(([a, b]) => [a, b]),
    status: "pending",
    // Revisions are not known until we implement the server handshake.
    base_revision: null,
    created_at: new Date().toISOString(),
  };
  const idb = await openDB();
  try {
    await new Promise((resolve, reject) => {
      const tx = idb.transaction([STORE, OP_STORE], "readwrite");
      const copyStore = tx.objectStore(STORE);
      const operationStore = tx.objectStore(OP_STORE);
      const get = copyStore.get(COPY_KEY);
      get.onsuccess = () => {
        const current = get.result;
        // Validate inside the write transaction to avoid other tabs overwriting us.
        if (!current || current.sourceId !== previousCopy.sourceId ||
            current.savedAt !== previousCopy.savedAt ||
            current.byteLength !== previousCopy.byteLength) {
          tx.abort();
          return;
        }
        copyStore.put(nextCopy, COPY_KEY);
        operationStore.add(queued);
      };
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error || new Error("Chyba IndexedDB"));
      tx.onabort = () => reject(tx.error || new Error("Souběžná změna SQLite nebo chyba při ukládání fronty"));
    });
    return queued;
  } finally {
    idb.close();
  }
}

// Offline edit support: replace the existing submit_result in-place.
// SQLite + queue are committed in ONE IndexedDB transaction.
// This is intentionally NOT a new operation: the completed-local-tournament
// importer expects exactly one submit_result per match.
async function replaceQueuedMatchResult(nextCopy, previousCopy, operation) {
  if (!operation || operation.action !== "submit_result" ||
      !Number.isSafeInteger(operation.match_id) || operation.match_id <= 0 ||
      !Array.isArray(operation.sets) || !operation.sets.length ||
      operation.sets.some(row => !Array.isArray(row) || row.length !== 2 ||
        row.some(v => !Number.isInteger(v) || v < 0 || v > 99) || row[0] === row[1])) {
    throw new Error("Neplatný opravovaný výsledek.");
  }
  if (!nextCopy || !previousCopy || nextCopy.sourceKind !== "local" ||
      nextCopy.localImportedTournamentId || previousCopy.localImportedTournamentId ||
      nextCopy.sourceId !== previousCopy.sourceId) {
    throw new Error("Opravu fronty podporujeme zatím jen před odesláním lokálního turnaje.");
  }
  const idb = await openDB();
  try {
    let replaced;
    await new Promise((resolve, reject) => {
      const tx = idb.transaction([STORE, OP_STORE], "readwrite");
      const copies = tx.objectStore(STORE);
      const operations = tx.objectStore(OP_STORE);
      const currentRequest = copies.get(COPY_KEY);
      const operationsRequest = operations.getAll();
      let currentReady = false, operationsReady = false;
      let current, all;
      const abort = () => { try { tx.abort(); } catch (_) {} };
      const verifyAndWrite = () => {
        if (!currentReady || !operationsReady) return;
        if (!current || current.sourceId !== previousCopy.sourceId ||
            current.sourceKind !== "local" || current.localImportedTournamentId ||
            current.savedAt !== previousCopy.savedAt ||
            current.byteLength !== previousCopy.byteLength) {
          abort(); return;
        }
        const matches = all.filter(item => item.status === "pending" &&
          item.tournament_id === previousCopy.sourceId &&
          item.match_id === operation.match_id && item.action === "submit_result");
        if (matches.length !== 1 ||
            all.some(item => item.tournament_id === previousCopy.sourceId &&
              item.match_id === operation.match_id && item.status !== "pending")) {
          abort(); return;
        }
        // Keep request_id, created_at and queue ordering stable.
        replaced = { ...matches[0], sets: operation.sets.map(row => [...row]) };
        copies.put(nextCopy, COPY_KEY);
        operations.put(replaced);
      };
      currentRequest.onsuccess = () => {
        current = currentRequest.result; currentReady = true; verifyAndWrite();
      };
      operationsRequest.onsuccess = () => {
        all = operationsRequest.result; operationsReady = true; verifyAndWrite();
      };
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error || new Error("Chyba IndexedDB při opravě zápasu."));
      tx.onabort = () => reject(new Error("Oprava nebyla uložena: změnila se SQLite nebo chybí jednoznačná původní operace."));
    });
    return replaced;
  } finally {
    idb.close();
  }
}

async function getPendingOperations() {
  const idb = await openDB();
  try {
    return await new Promise((resolve, reject) => {
      const tx = idb.transaction(OP_STORE, "readonly");
      const req = tx.objectStore(OP_STORE).getAll();
      req.onsuccess = () => resolve(req.result.filter(item => item.status === "pending"));
      req.onerror = () => reject(req.error);
    });
  } finally {
    idb.close();
  }
}

async function ensureNoPendingOperations() {
  const pending = await getPendingOperations();
  if (pending.length) throw new Error(`Nejdřív vyřeš ${pending.length} neodeslaných změn. Přepsání SQLite by je odpojilo od výsledků.`);
}

// Test-only reset. A downloaded preview file must match every currently pending
// operation before the SQLite copy and its queue are removed atomically.
function queueRecord(op) {
  return {
    request_id: op.request_id,
    tournament_id: op.tournament_id,
    action: op.action,
    match_id: op.match_id,
    sets: op.sets,
    base_revision: op.base_revision,
    created_at: op.created_at,
  };
}

function sameQueue(backupOps, currentOps) {
  const canonical = (op) => JSON.stringify(queueRecord(op));
  const a = backupOps.map(canonical).sort();
  const b = currentOps.map(canonical).sort();
  return a.length === b.length && a.every((entry, i) => entry === b[i]);
}

async function deleteCopyWithVerifiedBackup(backup) {
  const idb = await openDB();
  try {
    await new Promise((resolve, reject) => {
      const tx = idb.transaction([STORE, OP_STORE], "readwrite");
      const copies = tx.objectStore(STORE);
      const operations = tx.objectStore(OP_STORE);
      const copyReq = copies.get(COPY_KEY);
      const opsReq = operations.getAll();
      let copy, ops;
      const fail = () => { try { tx.abort(); } catch (_) {} };
      copyReq.onsuccess = () => { copy = copyReq.result; };
      opsReq.onsuccess = () => { ops = opsReq.result; };
      // All checks and deletes happen in the same transaction: no other tab
      // can append an operation between verification and deletion.
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error || new Error("Chyba IndexedDB"));
      tx.onabort = () => reject(new Error("Lokální data se změnila nebo ověření zálohy selhalo. Nic nebylo smazáno."));
      // Runs after both reads without yielding outside the transaction.
      const validate = () => {
        if (copy === undefined || ops === undefined) return;
        if (!copy || backup.tournament_id !== copy.sourceId ||
            !Array.isArray(backup.operations) ||
            backup.format !== "spravaturnaje-pending-operations-preview-v1" ||
            backup.warning !== "LOCAL_PREVIEW_ONLY_DO_NOT_SUBMIT_TO_LIVE_API") {
          fail(); return;
        }
        const pending = ops.filter((op) => op.status === "pending");
        if (!pending.length || pending.some((op) => op.tournament_id !== copy.sourceId) ||
            backup.count !== pending.length || !sameQueue(backup.operations, pending)) {
          fail(); return;
        }
        copies.delete(COPY_KEY);
        for (const op of pending) operations.delete(op.request_id);
      };
      const copySuccess = copyReq.onsuccess;
      copyReq.onsuccess = () => { copySuccess(); validate(); };
      const opsSuccess = opsReq.onsuccess;
      opsReq.onsuccess = () => { opsSuccess(); validate(); };
    });
  } finally {
    idb.close();
  }
}

const deleteCopy = async () => {
  await ensureNoPendingOperations();
  return transact("readwrite", (store) => store.delete(COPY_KEY));
};

async function updateSavedLabel() {
  const copy = await getCopy();
  const pending = await getPendingOperations();
  $("saved").textContent = (copy
    ? `Uloženo: ${copy.sourceKind === 'local' ? 'lokální turnaj' : 'turnaj'} ${copy.sourceId} | ${copy.byteLength} B | ${copy.savedAt}`
    : "Žádná uložená kopie") + ` | Neodeslané operace: ${pending.length}`;
}
async function getRuntime() {
  if (!runtimePromise) {
    runtimePromise = (async () => {
      if (!globalThis.loadPyodide) {
        await new Promise((resolve, reject) => {
          const script = document.createElement("script");
          script.src = PYODIDE_BASE + "pyodide.js";
          script.onload = resolve;
          script.onerror = () => reject(new Error("Nelze načíst Pyodide (poprvé je nutný internet)."));
          document.head.appendChild(script);
        });
      }
      const start = performance.now();
      const py = await globalThis.loadPyodide({ indexURL: PYODIDE_BASE });

      console.log(
        "[PWA] Pyodide:",
        Math.round(performance.now() - start),
        "ms"
      );

      await py.loadPackage("sqlite3");
      console.log(
        "[PWA] Pyodide + SQLite:",
        Math.round(performance.now() - start),
         "ms"
      );
      return py;
    })().catch((err) => { runtimePromise = null; throw err; });
  }
  return runtimePromise;
}

function addSection(title) {
  const section = element("section");
  section.append(element("h2", title));
  $("output").append(section);
  return section;
}

function addTable(parent, headers, rows) {
  const table = element("table");
  const header = element("tr");
  for (const title of headers) header.append(element("th", title));
  table.append(header);
  for (const fields of rows) {
    const tr = element("tr");
    for (const field of fields) tr.append(element("td", field ?? "—"));
    table.append(tr);
  }
  parent.append(table);
}

function display(data) {
  $("output").replaceChildren();
  const tournament = data.tournaments[0];
  if (!tournament) throw new Error("Databáze neobsahuje turnaj");
  if (tournament.id !== data.source.source_tournament_id) {
    throw new Error("Nesouhlasí ID zdrojového turnaje");
  }

  const players = new Map(data.players.map((p) => [p.id, p.name]));
  const setsByMatch = new Map();
  for (const set of data.match_results) {
    if (!setsByMatch.has(set.match_id)) setsByMatch.set(set.match_id, []);
    setsByMatch.get(set.match_id).push(set);
  }

  const intro = addSection(`Turnaj ${tournament.id} – ${tournament.name}`);
  intro.append(element("p", `Zdroj: ${data.source.source_kind === "local" ? "lokální turnaj" : "live"} ${data.source.source_tournament_id} | ${data.players.length} hráčů | ${data.groups.length} skupiny | ${data.matches.length} zápasů | ${data.brackets.length} pavouky`));
  intro.append(element("p", `SQLite: ${data.integrity_check} | dokončené zápasy: ${data.matches.filter((m) => m.is_finished).length} | záznamy setů: ${data.match_results.length}`));

  const mainGroups = data.groups.filter((g) => !g.is_consolation);
  const mainMatches = data.matches.filter((m) => m.group_id !== null && mainGroups.some((g) => g.id === m.group_id));
  const finishedGroupMatches = mainMatches.filter((m) => m.is_finished).length;
  const progress = addSection("Postup ze skupin do playoff / útěchy");
  progress.append(element("p", `Skupinové zápasy: ${finishedGroupMatches}/${mainMatches.length} · dokončené skupiny: ${mainGroups.filter((g) => g.is_finished).length}/${mainGroups.length}`));
  const bracketById = new Map(data.brackets.map((b) => [b.id, b]));
  const seeded = data.players.filter((p) => p.group_seed).sort((a,b) =>
    a.group_seed.localeCompare(b.group_seed, "cs", {numeric: true}));
  const advanceCount = Number(tournament.advance_per_group) || 0;
  const placementRows = seeded.map((p) => {
    const rank = Number.parseInt(p.group_seed, 10);
    const destination = rank <= advanceCount ? "Hlavní playoff" : "Útěcha / další pořadí";
    const assigned = data.matches.filter((m) => m.bracket_id !== null &&
      (m.player_a_id === p.id || m.player_b_id === p.id));
    const places = [...new Set(assigned.map((m) => bracketById.get(m.bracket_id)?.name || "Pavouk"))].join(", ");
    return [p.group_seed, p.name, destination, places || "Čeká na soupeře / slot"];
  });
  if (placementRows.length) addTable(progress, ["Seed", "Hráč", "Cíl", "Aktuální zápasy"], placementRows);
  else progress.append(element("p", "Postupující zatím nejsou určení."));
  if (mainGroups.length && mainGroups.every((g) => g.is_finished)) {
    progress.append(element("p", "✅ Všechny skupiny dokončeny. Hráči byli zpracováni původním turnajovým enginem."));
  }

  for (const group of data.groups) {
    const section = addSection(group.name + (group.is_finished ? " ✅" : " (rozehraná)"));
    const members = data.players.filter((p) => p.group_id === group.id);
    addTable(section, ["Hráč ID", "Jméno", "Seed", "Body"], members.map((p) => [
      p.id, p.name, p.group_seed,
      data.group_stats.find((stat) => stat.player_id === p.id)?.points ?? "—",
    ]));
    const groupMatches = data.matches.filter((m) => m.group_id === group.id);
    addTable(section, ["Zápas ID", "Hráč A", "Hráč B", "Sety (míčky)", "Stav"], groupMatches.map((match) => [
      match.id,
      players.get(match.player_a_id) || "—",
      players.get(match.player_b_id) || "—",
      (setsByMatch.get(match.id) || []).sort((a, b) => a.set_number - b.set_number)
        .map((set) => `${set.score_a}:${set.score_b}`).join(", ") || "—",
      match.is_finished ? "Hotovo" : "Čeká",
    ]));
  }

  for (const bracket of data.brackets) {
    const section = addSection(bracket.name + (bracket.is_consolation ? " (útěcha)" : ""));
    const matches = data.matches.filter((m) => m.bracket_id === bracket.id);
    section.append(element("p", `Uložený strom playoff – zachován beze změn. Zápasy v databázi: ${matches.length}`));
    if (matches.length) addTable(section, ["Zápas", "Hráči", "Stav"], matches.map((match) => [
      match.id,
      `${players.get(match.player_a_id) || "BYE/čeká"} × ${players.get(match.player_b_id) || "BYE/čeká"}`,
      match.is_finished ? "Hotovo" : "Čeká",
    ]));
    const details = element("details");
    details.append(element("summary", "Zobrazit původní tree_data (bez přegenerování)"));
    details.append(element("pre", JSON.stringify(bracket.tree_data, null, 2)));
    section.append(details);
  }
  addSection("Ukládání").append(element("p", "Zápisy se ukládají pouze do místní SQLite v IndexedDB a do fronty neodeslaných operací. Na server se nic neposílá."));
}

async function readAndDisplay(bytes) {
  const py = await getRuntime();
  py.FS.writeFile("/tmp/lab194b.sqlite", new Uint8Array(bytes));
  const raw = await py.runPythonAsync(PY);
  const data = JSON.parse(raw);
  if (!Number.isInteger(data.source.source_tournament_id) || data.source.source_tournament_id <= 0) {
    throw new Error("SQLite neobsahuje platné ID zdrojového turnaje.");
  }
  display(data);
  if (typeof refreshRealMatchOptions === "function") refreshRealMatchOptions(data);
  window.dispatchEvent(new CustomEvent("offline:tournament-data", {detail: {data}}));
  return data;
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) throw new Error("Service Worker není podporován");
  if (!isSecureContext) throw new Error("Použij HTTPS nebo localhost/127.0.0.1");
  const registration = await navigator.serviceWorker.register("./sw.js", { updateViaCache: "none" });
  await navigator.serviceWorker.ready;
  return registration;
}

$("dbfile").addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  $("error").textContent = "";
  try {
    if (file.size > 25 * 1024 * 1024) throw new Error("Databáze překračuje limit 25 MB");
    $("status").textContent = "Načítám a ověřuji SQLite…";
    const bytes = await file.arrayBuffer();
    await ensureNoPendingOperations();
    const data = await readAndDisplay(bytes);
    await saveCopy({ bytes, sourceId: data.source.source_tournament_id, sourceKind: data.source.source_kind,
      byteLength: bytes.byteLength, savedAt: new Date().toLocaleString("cs-CZ") });
    await updateSavedLabel();
    $("status").textContent = "✅ Zobrazeno a uloženo do IndexedDB";
  } catch (err) { $("status").textContent = "Načtení selhalo"; errorMessage(err); }
});

async function loadSavedTournament({ quietIfMissing = false } = {}) {
  $("error").textContent = "";
  try {
    $("status").textContent = "Načítám uložený turnaj…";
    const copy = await getCopy();
    if (!copy) {
      if (quietIfMissing) {
        $("status").textContent = "Připraveno k vytvoření nového turnaje.";
        return false;
      }
      throw new Error("Žádná uložená SQLite kopie");
    }
    await readAndDisplay(copy.bytes);
    await updateSavedLabel();
    $("status").textContent = "✅ Uložený turnaj je připravený";
    return true;
  } catch (err) {
    $("status").textContent = "Načtení turnaje selhalo";
    errorMessage(err);
    return false;
  }
}
$("loadSaved").addEventListener("click", () => loadSavedTournament());

$("prepare").addEventListener("click", async () => {
  $("error").textContent = "";
  try {
    $("status").textContent = "Registruji Service Worker…";
    await registerServiceWorker();
    // The first registration may not control this already-open page.
    // Loading packages before SW control would bypass its offline cache.
    const controller = navigator.serviceWorker.controller;
    if (!controller || new URL(controller.scriptURL).pathname !== new URL("./sw.js", location.href).pathname) {
      $("status").textContent = "Service Worker připraven. Obnov stránku (F5) a klikni na Připravit offline znovu.";
      return;
    }
    $("status").textContent = "Stahuji Pyodide a Python závislosti (nutný internet)…";
    const py = await getRuntime();
    // The result writer loads these packages through micropip. Download them
    // while online and under the controlling SW, including metadata/wheels.
    await py.loadPackage(["sqlalchemy", "micropip"]);
    await py.runPythonAsync("import micropip\nawait micropip.install(['flask', 'flask-sqlalchemy'])");
    // The writer also uses the local Python engine sources. Preload them now.
    if (typeof ensureEngineFiles !== "function") {
      throw new Error("Chybí ensureEngineFiles() – zkontroluj načtení engine_dry_run.js.");
    }
    await ensureEngineFiles(py);
    await cachedPythonSource("real_tournament/real_match.py");
    await cachedPythonSource("real_tournament/real_match_edit.py");
    await cachedPythonSource("real_tournament/offline_create.py");
    const sourceCache = await caches.open(ENGINE_SOURCE_CACHE);
    const sourceCount = (await sourceCache.keys()).length;
    if (sourceCount < ENGINE_FILES.length + 3) {
      throw new Error(`Offline cache Python enginu není kompletní (${sourceCount}/${ENGINE_FILES.length + 3}).`);
    }
    const cache = await caches.open(RUNTIME_CACHE);
    const resources = await cache.keys();
    if (!resources.length) {
      throw new Error(`Cache ${RUNTIME_CACHE} je prázdná. Stránku ještě neovládá aktuální Service Worker; obnov F5 a spusť přípravu znovu.`);
    }
    $("status").textContent = `✅ Online příprava dokončena; v ${RUNTIME_CACHE} je ${resources.length} požadavků; Python zdroje ${sourceCount}/${ENGINE_FILES.length + 3}. Nyní zkus offline zápis.`;
    await updateSavedLabel();
  } catch (err) { $("status").textContent = "Offline příprava selhala"; errorMessage(err); }
});

// The reset control is intentionally separate from normal deletion.
// Selecting a file alone never deletes anything.
const resetBackupLabel = element("label", "Záloha 2 neodeslaných operací (JSON):");
const resetBackupInput = document.createElement("input");
resetBackupInput.type = "file";
resetBackupInput.accept = ".json,application/json";
resetBackupLabel.style.display = "block";
resetBackupLabel.style.marginTop = "0.75rem";
resetBackupLabel.append(" ", resetBackupInput);
$("remove").insertAdjacentElement("afterend", resetBackupLabel);

$("remove").addEventListener("click", async () => {
  $("error").textContent = "";
  try {
    const pending = await getPendingOperations();
    if (!pending.length) {
      const copy = await getCopy();
      if (!copy) throw new Error("Žádná uložená kopie.");
      if (!confirm(`Smazat místní kopii turnaje ${copy.sourceId}?`)) return;
      await deleteCopy();
    } else {
      const file = resetBackupInput.files?.[0];
      if (!file) throw new Error("Nejdřív vyber stažený JSON zálohy fronty. Pouhé stažení nestačí.");
      if (file.size > 1024 * 1024) throw new Error("Záloha fronty je příliš velká.");
      let backup;
      try { backup = JSON.parse(await file.text()); }
      catch (_) { throw new Error("Vybraný soubor není platný JSON."); }
      const copy = await getCopy();
      if (!copy) throw new Error("Uložená kopie neexistuje.");
      if (!confirm(`SMAZAT lokální SQLite turnaje ${copy.sourceId} a ${pending.length} neodeslané operace?\n\nZáloha byla vybrána, ale toto NENÍ synchronizace. Po odstranění už nebudou výsledky v tomto prohlížeči.`)) return;
      await deleteCopyWithVerifiedBackup(backup);
    }
    resetBackupInput.value = "";
    $("output").replaceChildren();
    await updateSavedLabel();
    $("status").textContent = "✅ Lokální kopie a případná ověřená fronta byly smazány. Původní soubor a server se nezměnily.";
    window.dispatchEvent(new Event("offline:tournament-removed"));
  } catch (err) { errorMessage(err); }
});

// Staging preparation: inspect or export pending operations locally.
// This does not call the server and never marks operations as synchronized.
function installQueueInspector() {
  const saved = document.getElementById("saved");
  if (!saved) return;
  const wrapper = document.createElement("section");
  wrapper.style.marginTop = "0.75rem";
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Zobrazit / exportovat frontu";
  const info = document.createElement("p");
  const detail = document.createElement("pre");
  detail.style.whiteSpace = "pre-wrap";
  detail.style.overflowWrap = "anywhere";
  const downloadButton = document.createElement("button");
  downloadButton.type = "button";
  downloadButton.textContent = "Stáhnout JSON fronty";
  downloadButton.hidden = true;
  let exportContent = "";
  button.addEventListener("click", async () => {
    try {
      const copy = await getCopy();
      const pending = (await getPendingOperations())
        .filter((op) => op.tournament_id === copy?.sourceId)
        .sort((a, b) => a.created_at.localeCompare(b.created_at));
      const records = pending.map((op) => ({
        request_id: op.request_id,
        tournament_id: op.tournament_id,
        action: op.action,
        match_id: op.match_id,
        sets: op.sets,
        base_revision: op.base_revision,
        created_at: op.created_at,
      }));
      exportContent = JSON.stringify({
        format: "spravaturnaje-pending-operations-preview-v1",
        warning: "LOCAL_PREVIEW_ONLY_DO_NOT_SUBMIT_TO_LIVE_API",
        tournament_id: copy?.sourceId ?? null,
        count: records.length,
        operations: records,
      }, null, 2);
      detail.textContent = exportContent;
      const missingRevision = records.filter((op) => !Number.isInteger(op.base_revision)).length;
      info.textContent = `${records.length} čekajících operací · ${missingRevision} bez výchozí serverové revize. Tento export není synchronizace.`;
      downloadButton.hidden = records.length === 0;
      await updateSavedLabel();
    } catch (err) {
      info.textContent = `Chyba při čtení fronty: ${err.message || err}`;
      downloadButton.hidden = true;
      detail.textContent = "";
    }
  });
  downloadButton.addEventListener("click", () => {
    if (!exportContent) return;
    const blob = new Blob([exportContent], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "offline_pending_operations_preview.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  wrapper.append(button, downloadButton, info, detail);
  const target = document.getElementById("advancedQueueTools");
  if (target) target.append(wrapper);
  else saved.insertAdjacentElement("afterend", wrapper);
}

installQueueInspector();

// Download a snapshot of the *current* SQLite bytes from IndexedDB.
// Read-only: never changes the copy, pending operations or their statuses.
function installSqliteBackupButton() {
  const saved = document.getElementById("saved");
  if (!saved) return;
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Stáhnout zálohu SQLite turnaje";
  button.style.marginTop = "0.5rem";
  const status = document.createElement("p");
  status.className = "small";
  status.setAttribute("role", "status");
  button.addEventListener("click", async () => {
    button.disabled = true;
    status.textContent = "Připravuji kopii SQLite z IndexedDB…";
    try {
      const copy = await getCopy();
      if (!copy || !copy.bytes) throw new Error("V IndexedDB není uložená SQLite databáze.");
      const bytes = copy.bytes;
      const byteLength = bytes.byteLength;
      if (!Number.isInteger(byteLength) || byteLength < 100) {
        throw new Error("Uložená SQLite není platný datový buffer.");
      }
      const bytesView = bytes instanceof ArrayBuffer
        ? new Uint8Array(bytes)
        : ArrayBuffer.isView(bytes)
          ? new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength)
          : null;
      if (!bytesView || new TextDecoder().decode(bytesView.subarray(0, 16)) !== "SQLite format 3\u0000") {
        throw new Error("Uložený soubor nemá hlavičku SQLite.");
      }
      const blob = new Blob([bytesView], { type: "application/vnd.sqlite3" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const kind = copy.sourceKind === "local" ? "local" : "import";
      const id = String(copy.sourceId ?? "unknown").replace(/[^a-zA-Z0-9_-]/g, "_");
      link.href = url;
      link.download = `offline_tournament_${kind}_${id}_backup.sqlite`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.textContent = `✅ SQLite připravena ke stažení (${byteLength} B). Fronta operací zůstává beze změny.`;
    } catch (err) {
      status.textContent = `Chyba zálohy: ${err.message || err}`;
    } finally {
      button.disabled = false;
    }
  });
  const target = document.getElementById("advancedQueueTools");
  if (target) target.append(button, status);
  else { saved.insertAdjacentElement("afterend", button); button.insertAdjacentElement("afterend", status); }
}
installSqliteBackupButton();

// Startup without buttons: resume local SQLite, never upload pending operations.
// Cache warming is allowed ONLY when the browser reports online and does not
// replace or remove a tournament. A failed probe never blocks offline play.
let automaticPreparationStarted = false;
async function prepareOfflineIfNeeded() {
  if (automaticPreparationStarted || !navigator.onLine) return;
  automaticPreparationStarted = true;
  try {
    const runtime = await caches.open(RUNTIME_CACHE);
    const sourceName = typeof ENGINE_SOURCE_CACHE === "string" ? ENGINE_SOURCE_CACHE : null;
    const source = sourceName ? await caches.open(sourceName) : null;
    const requiredSources = typeof ENGINE_FILES !== "undefined" ? ENGINE_FILES.length + 3 : null;
    const runtimeReady = (await runtime.keys()).length > 0;
    const engineReady = source && requiredSources && (await source.keys()).length >= requiredSources;
    // Aktualizaci Service Workeru kontrolujeme vždy při online spuštění.
    await registerServiceWorker();

    if (runtimeReady && engineReady) return;
    // Let the existing, tested preparation handler own the download logic.
    // The SW may be installed but not yet control the very first page load.
    if (navigator.serviceWorker.controller &&
        new URL(navigator.serviceWorker.controller.scriptURL).pathname === new URL("./sw.js", location.href).pathname) {
      $("prepare").click();
    } else {
      const onControl = () => {
        navigator.serviceWorker.removeEventListener("controllerchange", onControl);
        if (navigator.onLine) $("prepare").click();
      };
      navigator.serviceWorker.addEventListener("controllerchange", onControl, { once: true });
      $("status").textContent = "Offline soubory se připraví po převzetí stránky Service Workerem.";
    }
  } catch (err) {
    console.warn("Automatická příprava offline souborů se nepovedla:", err);
    // The manual prepare button stays available in Správa dat.
  }
}

window.addEventListener("DOMContentLoaded", async () => {
  try {
    const resumed = await loadSavedTournament({ quietIfMissing: true });
    if (resumed) {
      // Keep current URL and navigation; the organizer may be on any tab.
      // readAndDisplay() already makes all match lists available.
    }
  } catch (err) { errorMessage(err); }
  const dateInput = document.getElementById("newTournamentDate");
  if (dateInput && !dateInput.value) {
    const now = new Date();
    const localDate = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
    dateInput.value = localDate.toISOString().slice(0, 10);
  }
  await updateSavedLabel().catch(errorMessage);
  await prepareOfflineIfNeeded();
});
