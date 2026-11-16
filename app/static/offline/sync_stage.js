"use strict";
// Manual first-stage sync: explicitly activated by the organizer.
// Uses globals from the existing app.js; does not change its offline engine.
(() => {
  // The button is part of index.html, so a failed JS load cannot hide it.
  const button = document.getElementById('stageSyncButton');
  const status = document.getElementById('stageSyncStatus');
  if (!button || !status) {
    console.error('Staging synchronizace: chybí #stageSyncButton / #stageSyncStatus v HTML.');
    return;
  }

  async function jsonFetch(url, options) {
    const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', redirect: 'error', ...options });
    const data = await response.json().catch(() => null);
    if (!response.ok || !data || data.status === 'ERROR') {
      throw new Error(data?.message || `Server vrátil HTTP ${response.status}. Přihlas se na testovacím Flask webu.`);
    }
    return data;
  }

  async function markSynced(requestIds) {
    const ids = new Set(requestIds);
    const idb = await openDB();
    try {
      await new Promise((resolve, reject) => {
        const tx = idb.transaction(OP_STORE, 'readwrite');
        const store = tx.objectStore(OP_STORE);
        for (const id of ids) {
          const req = store.get(id);
          req.onsuccess = () => {
            if (!req.result || req.result.status !== 'pending') {
              tx.abort();
              return;
            }
            store.put({ ...req.result, status: 'synced', synced_at: new Date().toISOString() });
          };
        }
        tx.oncomplete = resolve;
        tx.onerror = () => reject(tx.error || new Error('IndexedDB selhalo'));
        tx.onabort = () => reject(tx.error || new Error('Nelze potvrdit operace v telefonu'));
      });
    } finally {
      idb.close();
    }
  }

  function catalogFromSnapshot(snapshot, ops) {
    const matches = new Map(snapshot.matches.map(m => [m.id, m]));
    const brackets = new Map(snapshot.brackets.map(b => [b.id, b]));
    return ops.map(op => {
      const m = matches.get(op.match_id);
      if (!m || !Number.isInteger(m.player_a_id) || !Number.isInteger(m.player_b_id)) {
        throw new Error(`V SQLite chybí hráči zápasu ${op.match_id}.`);
      }
      if (m.group_id != null) {
        return { match_id: m.id, kind: 'group', group_id: m.group_id,
          player_a_id: m.player_a_id, player_b_id: m.player_b_id };
      }
      const b = brackets.get(m.bracket_id);
      if (!b) throw new Error(`V SQLite chybí pavouk zápasu ${op.match_id}.`);
      return { match_id: m.id, kind: 'playoff', player_a_id: m.player_a_id,
        player_b_id: m.player_b_id, is_consolation: Boolean(b.is_consolation),
        bracket_type: b.bracket_type };
    });
  }

  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const copy = await getCopy();
      if (!copy) throw new Error('Nejdřív načti offline turnaj.');
      if (copy.sourceKind === 'local') throw new Error('Nový offline turnaj zatím nemá serverové ID; synchronizaci vytvoření připravíme v další fázi.');
      const ops = (await getPendingOperations()).filter(o => o.tournament_id === copy.sourceId)
        .sort((a, b) => a.created_at.localeCompare(b.created_at));
      if (!ops.length) throw new Error('Fronta je prázdná. Není co synchronizovat.');
      if (!navigator.onLine) throw new Error('Zařízení hlásí, že je offline. Výsledky zůstávají uložené.');
      status.textContent = `Připravuji ${ops.length} operací…`;
      const base = `/api/offline/stage/${copy.sourceId}`;
      let handshake;
      try {
        handshake = await jsonFetch(`${base}/handshake`);
      } catch (err) {
        if (location.hostname === '127.0.0.1' && location.port === '8000') {
          throw new Error(`${err.message} Na localhostu spusť místo obyčejného http.server soubor dev_sync_proxy.py (proxy na Flask :5001).`);
        }
        throw err;
      }
      // A retry after a lost HTTP response may see revision > 0.
      // The server will accept only the EXACT already-committed batch; otherwise 409.
      if (!Number.isInteger(handshake.revision)) throw new Error('Server nevrátil platnou revizi.');
      const py = await getRuntime();
      py.FS.writeFile('/tmp/lab194b.sqlite', new Uint8Array(copy.bytes));
      const snapshot = JSON.parse(await py.runPythonAsync(PY));
      if (snapshot.source.source_tournament_id !== copy.sourceId) throw new Error('Nesouhlasí turnaj v SQLite.');
      const clean = ops.map(o => ({ request_id: o.request_id, tournament_id: o.tournament_id,
        action: o.action, match_id: o.match_id, sets: o.sets }));
      const payload = { format: 'spravaturnaje-offline-batch-v1', tournament_id: copy.sourceId,
        base_revision: 0, operations: clean, match_catalog: catalogFromSnapshot(snapshot, clean) };
      if (!window.confirm(`Odeslat ${clean.length} výsledků turnaje ${copy.sourceId} do TESTOVACÍ databáze?`)) {
        status.textContent = 'Odeslání zrušeno. Fronta zůstala uložená.';
        return;
      }
      status.textContent = 'Odesílám a čekám na potvrzení serveru…';
      const result = await jsonFetch(`${base}/sync`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Offline-Sync': '1' },
        body: JSON.stringify(payload),
      });
      if (!['COMMITTED', 'ALREADY_SYNCED'].includes(result.status) ||
          result.confirmed_request_ids?.length !== clean.length ||
          clean.some(o => !result.confirmed_request_ids.includes(o.request_id))) {
        throw new Error('Server neposlal úplné potvrzení. Frontu nemažu.');
      }
      await markSynced(result.confirmed_request_ids);
      await updateSavedLabel();
      status.textContent = `✅ ${clean.length} operací potvrzeno serverem, revize ${result.revision}.`;
    } catch (err) {
      status.textContent = `❌ ${err.message || err} Fronta v tomto prohlížeči zůstává zachovaná.`;
    } finally {
      button.disabled = false;
    }
  });

  // One-time bridge for the Android queue exported as a prevalidated staging batch.
  // Never merges a file with IndexedDB, and never marks browser operations as synced.
  const batchInput = document.getElementById('stageBatchFile');
  const batchButton = document.getElementById('stageBatchSend');
  const batchStatus = document.getElementById('stageBatchStatus');
  if (batchInput && batchButton && batchStatus) {
    batchButton.addEventListener('click', async () => {
      batchButton.disabled = true;
      try {
        const file = batchInput.files?.[0];
        if (!file) throw new Error('Vyber JSON dávku z Androidu.');
        if (file.size > 512 * 1024) throw new Error('Soubor je příliš velký.');
        const payload = JSON.parse(await file.text());
        if (payload?.format !== 'spravaturnaje-offline-batch-v1' || payload.tournament_id !== 76 ||
            payload.base_revision !== 0 || !Array.isArray(payload.operations) ||
            payload.operations.length !== 22 || !Array.isArray(payload.match_catalog) ||
            payload.match_catalog.length !== 22) {
          throw new Error('Očekávám připravenou staging dávku 22 operací turnaje 76.');
        }
        const ids = payload.operations.map(o => o.request_id);
        const mids = payload.operations.map(o => o.match_id);
        if (new Set(ids).size !== 22 || new Set(mids).size !== 22 ||
            payload.operations.some(o => o.tournament_id !== 76 || o.action !== 'submit_result')) {
          throw new Error('Neplatné nebo duplicitní operace.');
        }
        batchStatus.textContent = 'Ověřuji revizi na testovacím serveru…';
        const base = '/api/offline/stage/76';
        const handshake = await jsonFetch(`${base}/handshake`);
        if (handshake.tournament_id !== 76 || !Number.isInteger(handshake.revision)) {
          throw new Error('Handshake neodpovídá turnaji 76.');
        }
        if (handshake.revision !== 0 && handshake.revision !== 22) {
          throw new Error(`Server má revizi ${handshake.revision}; očekávám 0 nebo 22 pro bezpečné opakování.`);
        }
        if (!window.confirm('Opravdu odeslat 22 výsledků turnaje 76 do ODDĚLENÉ staging databáze?\nProdukční databáze se nemění.')) {
          batchStatus.textContent = 'Odeslání zrušeno.';
          return;
        }
        batchStatus.textContent = 'Odesílám 22 operací; čekám na potvrzení serveru…';
        const result = await jsonFetch(`${base}/sync`, {
          method: 'POST',
          headers: {'Content-Type':'application/json','X-Offline-Sync':'1'},
          body: JSON.stringify(payload),
        });
        if (!['COMMITTED','ALREADY_SYNCED'].includes(result.status) ||
            !Array.isArray(result.confirmed_request_ids) ||
            result.confirmed_request_ids.length !== 22 ||
            ids.some(id => !result.confirmed_request_ids.includes(id))) {
          throw new Error('Server nepotvrdil všechny operace; nic lokálně nemažu.');
        }
        batchStatus.textContent = `✅ ${result.status}: všech 22 operací potvrzeno, revize ${result.revision}.`;
      } catch (err) {
        batchStatus.textContent = `❌ ${err?.message || err} Soubor ani lokální fronta nebyly změněny.`;
      } finally {
        batchButton.disabled = false;
      }
    });
  }

})();
