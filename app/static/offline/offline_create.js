"use strict";
(() => {
  const $local = (id) => document.getElementById(id);
  const create = $local('createOfflineTournament');
  if (!create) return;
  const log = $local('createOfflineStatus');
  create.addEventListener('click', async () => {
    create.disabled = true;
    try {
      // The existing single-copy prototype must never silently overwrite a tournament.
      const current = await getCopy();
      if (current) throw new Error(`V prohlížeči je stále turnaj ${current.sourceId}. Nejdřív ho zálohuj a bezpečně odstraň původním tlačítkem „Smazat uloženou kopii“.`);
      await ensureNoPendingOperations();
      if (!globalThis.crypto?.randomUUID) throw new Error('Je nutné HTTPS nebo localhost.');
      const name = $local('newTournamentName').value.trim();
      const date = $local('newTournamentDate').value;
      const groupCount = Number($local('newTournamentGroups').value);
      const advance = Number($local('newTournamentAdvance').value);
      const raw = $local('newTournamentPlayers').value.split(/[\n,;]+/).map(s => s.trim()).filter(Boolean);
      if (!name || !date) throw new Error('Vyplň název a datum.');
      if (!Number.isInteger(groupCount) || groupCount < 2 || groupCount > 8) throw new Error('Zadej 2–8 skupin.');
      if (raw.length < groupCount * 2) throw new Error(`Pro ${groupCount} skupin potřebujeme alespoň ${groupCount*2} hráčů.`);
      if (raw.length > groupCount * 8) throw new Error('Příliš mnoho hráčů pro zvolený počet skupin.');
      if (new Set(raw.map(s => s.toLocaleLowerCase('cs'))).size !== raw.length) throw new Error('Některá jména se opakují.');
      // Group preparation is a separate, editable step. No implicit draw on Create.
      if (!window.offlineGroupDraft) throw new Error('Příprava skupin není načtená. Obnov stránku a zkontroluj offline_group_draft.js.');
      const groups = window.offlineGroupDraft.getGroupsForCreation();
      if (Object.values(groups).some(g => g.length <= advance)) throw new Error('V každé skupině musí zůstat více hráčů než postupujících.');
      const config = {
        name,date,location:$local('newTournamentLocation').value.trim(),
        include_in_global_stats:false,
        group_match_format: Number($local('newGroupFormat').value),
        playoff_match_format: Number($local('newPlayoffFormat').value),
        advance_per_group:advance,
        group_elimination_action:$local('newConsolation').checked?'playoff_b':'KO',
        playoff_elimination_action:'consolation',groups
      };
      const localUuid = crypto.randomUUID();
      log.textContent = 'Vytvářím skupiny a pavouky původním Python enginem…';
      const py = await getRuntime();
      await py.loadPackage(['sqlalchemy','micropip']);
      await py.runPythonAsync("import micropip\nawait micropip.install(['flask','flask-sqlalchemy'])");
      await ensureEngineFiles(py);
      const code = await cachedPythonSource('real_tournament/offline_create.py');
      py.globals.set('_offline_config_json',JSON.stringify(config));
      py.globals.set('_offline_uuid',localUuid);
      let rawReport;
      try { rawReport = await py.runPythonAsync(code); }
      finally { py.globals.delete('_offline_config_json'); py.globals.delete('_offline_uuid'); }
      const report = JSON.parse(rawReport);
      if (report.status !== 'LOCAL_CREATED' || report.local_uuid !== localUuid) throw new Error('Python nepotvrdil vytvoření turnaje.');
      const sqliteBytes = py.FS.readFile('/tmp/new_offline.sqlite');
      if (sqliteBytes.length < 1000 || sqliteBytes.length > 25*1024*1024) throw new Error('Neplatná velikost SQLite.');
      const bytes = sqliteBytes.slice().buffer;
      // Validate BEFORE saving, then recheck existing copy before committing.
      const snapshot = await readAndDisplay(bytes);
      if (snapshot.source.source_kind !== 'local' || snapshot.tournaments.length !== 1 || snapshot.players.length !== raw.length) throw new Error('Nový turnaj neprošel ověřením.');
      if (await getCopy()) throw new Error('Mezitím byl načten jiný turnaj. Nic nepřepisuji.');
      await saveCopy({bytes,sourceId:1,sourceKind:'local',localUuid,byteLength:bytes.byteLength,savedAt:new Date().toISOString()});
      await updateSavedLabel();
      window.dispatchEvent(new CustomEvent("offline:tournament-created", {detail:{data:snapshot}}));
      log.textContent = `✅ Nový lokální turnaj uložen: ${raw.length} hráčů, ${groupCount} skupin, ${report.matches} zápasů. Po F5 lze použít „Načíst uložený turnaj“. Na server zatím nic neodesílej.`;
    } catch (err) {
      log.textContent = '❌ ' + (err?.message || String(err));
      console.error(err);
    } finally { create.disabled = false; }
  });
})();
