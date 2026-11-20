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
        button.disabled = false;
        button.textContent = 'Vyčistit již synchronizovaný turnaj';
        status.textContent = `✅ Turnaj již byl převeden na TESTOVACÍ server jako #${copy.localImportedTournamentId}. Místní data lze nyní bezpečně odstranit.`;
      } else {
        button.textContent = 'Ukončit turnaj';
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

  // After a confirmed server import, remove the local tournament and its
  // queue in ONE IndexedDB transaction. Never delete on a network error.
  // Old "synced" entries are history from earlier tournaments and may reuse
  // the same local tournament/match IDs; they can safely be cleaned here.
  async function removeConfirmedLocalTournament(copy, confirmedOps, serverId, previouslyConfirmed = false) {
    if (!Number.isSafeInteger(Number(serverId)) || Number(serverId) <= 0 ||
        !copy || copy.sourceKind !== 'local') {
      throw new Error('Chybí platné potvrzení převzetí turnaje serverem.');
    }
    if (previouslyConfirmed && Number(copy.localImportedTournamentId) !== Number(serverId)) {
      throw new Error('ID dříve potvrzeného importu nesouhlasí.');
    }
    const confirmed = new Map(confirmedOps.map(op => [op.request_id, op]));
    if (confirmed.size !== confirmedOps.length) throw new Error('Duplicitní ID operace ve frontě.');
    const idb = await openDB();
    try {
      await new Promise((resolve, reject) => {
        const tx = idb.transaction([STORE, OP_STORE], 'readwrite');
        const copies = tx.objectStore(STORE);
        const operations = tx.objectStore(OP_STORE);
        const copyReq = copies.get(COPY_KEY);
        const opReq = operations.getAll();
        let currentReady = false, opsReady = false;
        let currentCopy, allOps;
        const abort = () => { try { tx.abort(); } catch (_) {} };
        const sameBytes = (a, b) => {
          if (!a || !b || a.byteLength !== b.byteLength) return false;
          const x = new Uint8Array(a), y = new Uint8Array(b);
          for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return false;
          return true;
        };
        const verifyAndDelete = () => {
          if (!currentReady || !opsReady) return;
          if (!currentCopy || currentCopy.sourceKind !== 'local' ||
              currentCopy.sourceId !== copy.sourceId ||
              currentCopy.localUuid !== copy.localUuid ||
              currentCopy.savedAt !== copy.savedAt ||
              currentCopy.byteLength !== copy.byteLength ||
              !sameBytes(currentCopy.bytes, copy.bytes) ||
              (currentCopy.localImportedTournamentId || null) !== (copy.localImportedTournamentId || null)) {
            abort(); return;
          }
          const pending = allOps.filter(op => op.status === 'pending');
          if (previouslyConfirmed) {
            if (pending.length !== 0) { abort(); return; }
          } else {
            if (currentCopy.localImportedTournamentId || pending.length !== confirmed.size ||
                pending.some(op => {
                  const sent = confirmed.get(op.request_id);
                  return !sent || op.tournament_id !== copy.sourceId ||
                    op.match_id !== sent.match_id || op.action !== sent.action ||
                    JSON.stringify(op.sets) !== JSON.stringify(sent.sets);
                })) { abort(); return; }
          }
          // Do not delete an unrecognized or still-active record.
          if (allOps.some(op => op.status !== 'pending' && op.status !== 'synced')) {
            abort(); return;
          }
          copies.delete(COPY_KEY);
          // The store is dedicated to the old local operation history.
          // Clear it atomically with the saved SQLite to avoid ID collisions.
          for (const op of allOps) operations.delete(op.request_id);
        };
        copyReq.onsuccess = () => {
          currentCopy = copyReq.result; currentReady = true; verifyAndDelete();
        };
        opReq.onsuccess = () => {
          allOps = opReq.result; opsReady = true; verifyAndDelete();
        };
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error || new Error('Chyba IndexedDB při úklidu turnaje.'));
        tx.onabort = () => reject(new Error('Lokální turnaj nebo fronta se změnily. Nic nebylo smazáno.'));
      });
    } finally { idb.close(); }
  }

  async function showCleanState(serverId) {
    await updateSavedLabel();
    document.getElementById('output')?.replaceChildren();
    window.dispatchEvent(new Event('offline:tournament-removed'));
    document.getElementById('status').textContent =
      `✅ Turnaj #${serverId} potvrzen serverem. Lokální SQLite i staré operace byly odstraněny; můžeš vytvořit nový turnaj.`;
    status.textContent = `✅ Turnaj #${serverId} synchronizován; místní data uklizena.`;
  }

  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const copy = await getCopy();
      if (!copy || copy.sourceKind !== 'local') throw new Error('Toto tlačítko je pouze pro turnaj založený přímo offline.');
      if (copy.localImportedTournamentId) {
        const serverId = Number(copy.localImportedTournamentId);
        if (!window.confirm(`Turnaj #${serverId} už server dříve potvrdil.\n\nOdstranit jeho místní SQLite a staré operace z tohoto zařízení?`)) return;
        await removeConfirmedLocalTournament(copy, [], serverId, true);
        await showCleanState(serverId);
        return;
      }
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
      if (!matches.length) throw new Error('Turnaj neobsahuje žádné zápasy.');

      // SQLite includes automatically completed playoff BYEs. They have no
      // entered sets and must not create submit_result operations.
      // A missing player ID alone is NOT sufficient: an unfinished slot may
      // still be waiting for an advancing player.
      const realMatches = [];
      for (const match of matches) {
        if (!match.is_finished) {
          throw new Error('Turnaj ještě není dohraný. Některé zápasy čekají na výsledek.');
        }
        const hasA = match.player_a_id != null;
        const hasB = match.player_b_id != null;
        if (hasA && hasB) {
          if (match.player_a_id === match.player_b_id ||
              ![match.player_a_id, match.player_b_id].includes(match.winner_id)) {
            throw new Error(`Zápas #${match.id} nemá platného vítěze.`);
          }
          realMatches.push(match);
        } else {
          if (match.bracket_id == null || match.group_id != null) {
            throw new Error(`Neplatný volný los v zápasu #${match.id}.`);
          }
          const expectedWinner = hasA ? match.player_a_id : hasB ? match.player_b_id : null;
          if (match.winner_id !== expectedWinner) {
            throw new Error(`Volný los v zápasu #${match.id} není správně vyhodnocen.`);
          }
        }
      }

      const realIds = new Set(realMatches.map(match => match.id));
      if (ops.length !== realMatches.length ||
          new Set(ops.map(op => op.match_id)).size !== ops.length ||
          ops.some(op => !realIds.has(op.match_id) || op.action !== 'submit_result')) {
        throw new Error(`SQLite má ${realMatches.length} skutečných zápasů z ${matches.length} celkem, ale fronta obsahuje ${ops.length} výsledků; nic neodesílám.`);
      }
      if (copy.bytes.byteLength > 2 * 1024 * 1024) throw new Error('SQLite překračuje staging limit 2 MB.');
      const preview = previewFromQueue(copy, ops);
      const queueJSON = JSON.stringify(preview);
      if (new Blob([queueJSON]).size > 256 * 1024) throw new Error('Fronta překračuje staging limit.');
      if (!window.confirm(`UKONČIT lokální turnaj a přenést jej na TESTOVACÍ server?\n\n${matches.length} dokončených pozic (z toho ${realMatches.length} skutečných zápasů), ${ops.length} výsledků.\nProdukční databáze se nemění.`)) {
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
        await removeConfirmedLocalTournament(copy, ops, Number(result.tournament_id));
      } catch (err) {
        throw new Error(`Server turnaj #${result.tournament_id} převzal, ale lokální úklid selhal: ${err.message}. Data zůstala uložená; opakování importu je bezpečné.`);
      }
      await showCleanState(result.tournament_id);
    } catch (error) {
      status.textContent = `❌ ${error?.message || error} Pokud úklid neproběhl, lokální data zůstala zachována.`;
      console.error('Offline finish:', error);
    } finally {
      // Already-imported copies may still be removed without re-sending data.
      const copy = await getCopy().catch(() => null);
      button.disabled = !copy || copy.sourceKind !== 'local';
    }
  });
})();
