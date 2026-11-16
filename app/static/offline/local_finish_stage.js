"use strict";
// STAGING ONLY. End a NEW tournament created fully offline.
// Never calls the existing /<tid>/sync for server-owned tournaments.
(() => {
  const button = document.getElementById('finishLocalTournament');
  const status = document.getElementById('finishLocalStatus');
  if (!button || !status) return;

  // Keep this feature visually separate from the old staging-result batch button.
  const section = document.getElementById('finishLocalSection');
  async function refreshVisibility() {
    try {
      const copy = await getCopy();
      if (section) section.hidden = copy?.sourceKind !== 'local';
      if (copy?.localImportedTournamentId) {
        button.disabled = true;
        status.textContent = `✅ Turnaj již byl převeden a ukončen na TESTOVACÍM serveru jako #${copy.localImportedTournamentId}.`;
      }
    } catch (error) {
      console.error('Lokální ukončení – nelze načíst stav:', error);
    }
  }
  // Called whenever the existing PWA updates the saved-tournament label
  // (load, new tournament creation, result entry); no changes to app.js needed.
  const saved = document.getElementById('saved');
  if (saved && typeof MutationObserver !== 'undefined') {
    new MutationObserver(() => { refreshVisibility(); }).observe(saved, { childList: true, characterData: true, subtree: true });
  }
  refreshVisibility();

  function previewFromQueue(copy, ops) {
    const records = ops.map(op => ({
      request_id: op.request_id,
      tournament_id: op.tournament_id,
      action: op.action,
      match_id: op.match_id,
      sets: op.sets,
      base_revision: op.base_revision ?? null,
      created_at: op.created_at,
    }));
    return {
      format: 'spravaturnaje-pending-operations-preview-v1',
      warning: 'LOCAL_PREVIEW_ONLY_DO_NOT_SUBMIT_TO_LIVE_API',
      tournament_id: copy.sourceId,
      count: records.length,
      operations: records,
    };
  }

  async function confirmLocally(copy, confirmedOps, serverId) {
    // Confirm SQLite and queue together only AFTER server acknowledgement.
    // Keep the SQLite bytes unchanged: an exact retry must have the same payload digest.
    const confirmed = new Set(confirmedOps.map(op => op.request_id));
    const db = await openDB();
    try {
      await new Promise((resolve, reject) => {
        const tx = db.transaction([STORE, OP_STORE], 'readwrite');
        const copies = tx.objectStore(STORE);
        const operations = tx.objectStore(OP_STORE);
        const copyReq = copies.get(COPY_KEY);
        const opReq = operations.getAll();
        let currentCopy, allOps;
        const abort = () => { try { tx.abort(); } catch (_) {} };
        const verify = () => {
          if (currentCopy === undefined || allOps === undefined) return;
          if (!currentCopy || currentCopy.sourceKind !== 'local' ||
              currentCopy.sourceId !== copy.sourceId ||
              currentCopy.savedAt !== copy.savedAt ||
              currentCopy.byteLength !== copy.byteLength ||
              allOps.filter(op => op.status === 'pending').length !== confirmed.size) {
            abort(); return;
          }
          const pending = allOps.filter(op => op.status === 'pending');
          if (pending.some(op => !confirmed.has(op.request_id) || op.tournament_id !== copy.sourceId)) {
            abort(); return;
          }
          // Do not change copy.bytes, sourceId or savedAt.
          copies.put({ ...currentCopy, localImportedTournamentId: serverId, localImportConfirmedAt: new Date().toISOString() }, COPY_KEY);
          for (const op of pending) operations.put({ ...op, status: 'synced', synced_at: new Date().toISOString() });
        };
        copyReq.onsuccess = () => { currentCopy = copyReq.result; verify(); };
        opReq.onsuccess = () => { allOps = opReq.result; verify(); };
        tx.oncomplete = resolve;
        tx.onerror = () => reject(tx.error || new Error('Chyba IndexedDB při potvrzení ukončení.'));
        tx.onabort = () => reject(new Error('Lokální stav se mezitím změnil. Data byla zachována; lze bezpečně opakovat potvrzení.'));
      });
    } finally { db.close(); }
  }

  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const copy = await getCopy();
      if (!copy || copy.sourceKind !== 'local') throw new Error('Toto tlačítko je pouze pro turnaj založený přímo offline.');
      if (copy.localImportedTournamentId) throw new Error(`Turnaj již byl importován jako #${copy.localImportedTournamentId}.`);
      const allPending = await getPendingOperations();
      if (allPending.some(op => op.tournament_id !== copy.sourceId)) throw new Error('Fronta obsahuje operace jiného turnaje.');
      const ops = allPending.slice().sort((a, b) => a.created_at.localeCompare(b.created_at));
      if (!ops.length) throw new Error('Fronta je prázdná; není co ukončovat.');
      if (!navigator.onLine) throw new Error('Zařízení je offline. Výsledky jsou bezpečně uložené; ukonči turnaj po návratu připojení.');
      status.textContent = 'Ověřuji dokončení turnaje…';
      const py = await getRuntime();
      py.FS.writeFile('/tmp/lab194b.sqlite', new Uint8Array(copy.bytes));
      const snapshot = JSON.parse(await py.runPythonAsync(PY));
      if (snapshot.source.source_kind !== 'local' || snapshot.source.source_tournament_id !== copy.sourceId ||
          snapshot.tournaments.length !== 1) throw new Error('SQLite neodpovídá lokálnímu turnaji.');
      const matches = snapshot.matches;
      if (!matches.length || matches.some(m => !m.is_finished || !m.player_a_id || !m.player_b_id)) {
        throw new Error('Turnaj ještě není dohraný. Všechny zápasy musí být dokončené.');
      }
      const ids = new Set(matches.map(m => m.id));
      if (ops.length !== matches.length || new Set(ops.map(op => op.match_id)).size !== ops.length ||
          ops.some(op => !ids.has(op.match_id) || op.action !== 'submit_result')) {
        throw new Error(`SQLite má ${matches.length} zápasů, ale fronta ${ops.length} neodpovídá; nic neodesílám.`);
      }
      if (copy.bytes.byteLength > 2 * 1024 * 1024) throw new Error('SQLite překračuje staging limit 2 MB.');
      const preview = previewFromQueue(copy, ops);
      const queueJSON = JSON.stringify(preview);
      if (new Blob([queueJSON]).size > 256 * 1024) throw new Error('Fronta překračuje staging limit.');
      if (!window.confirm(`UKONČIT lokální turnaj a přenést jej na TESTOVACÍ server?\n\n${matches.length} dokončených zápasů, ${ops.length} výsledků.\nProdukční databáze se nemění.`)) {
        status.textContent = 'Ukončení zrušeno. Lokální data zůstávají uložená.';
        return;
      }
      status.textContent = `Odesílám ${matches.length} zápasů do testovací databáze a čekám na potvrzení…`;
      const form = new FormData();
      form.append('sqlite', new Blob([copy.bytes], { type: 'application/vnd.sqlite3' }), 'offline_tournament.sqlite');
      form.append('operations', new Blob([queueJSON], { type: 'application/json' }), 'operations.json');
      const response = await fetch('/api/offline/stage/local/finish', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        redirect: 'error',
        headers: { 'X-Offline-Sync': '1' },
        body: form,
      });
      const result = await response.json().catch(() => null);
      if (!response.ok || !['COMMITTED', 'ALREADY_IMPORTED'].includes(result?.status) ||
          !result?.tournament_id || (result?.imported_matches != null && result.imported_matches !== matches.length) ||
          (result?.finished === false)) {
        throw new Error(result?.message || `Server vrátil HTTP ${response.status}. Zkontroluj testovací Flask na portu 5001 a odpověď importního endpointu.`);
      }
      try {
        await confirmLocally(copy, ops, result.tournament_id);
      } catch (err) {
        throw new Error(`Server turnaj #${result.tournament_id} převzal, ale lokální potvrzení selhalo: ${err.message}. Nic nemaž, zkus tlačítko znovu.`);
      }
      await updateSavedLabel();
      status.textContent = `✅ Turnaj ukončen na TESTOVACÍM webu jako #${result.tournament_id}. Potvrzeno ${matches.length} zápasů.`;
    } catch (error) {
      status.textContent = `❌ ${error?.message || error} Lokální SQLite a fronta nebyly odstraněny.`;
      console.error('Offline finish:', error);
    } finally {
      // If server import was confirmed, button remains locked.
      const copy = await getCopy().catch(() => null);
      button.disabled = Boolean(copy?.localImportedTournamentId);
    }
  });
})();
