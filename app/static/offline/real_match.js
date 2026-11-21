"use strict";

let realMatchBusy = false;
const realMatchSelect = document.getElementById("matchSelect");
const realMatchButton = document.getElementById("submitRealMatch");
// Keep the existing new-result flow; editing is an explicit, opt-in mode.
const matchEditMode = document.createElement("select");
matchEditMode.id = "realMatchMode";
matchEditMode.setAttribute("aria-label", "Režim zápisu výsledku");
matchEditMode.append(new Option("Zapsat nový zápas", "new"), new Option("Opravit odehraný zápas", "edit"));
realMatchSelect.before(matchEditMode);
let lastRealMatchData = null;

function prefillEditedMatch(matchId) {
  if (!lastRealMatchData || matchEditMode.value !== "edit") return;
  const id = Number(matchId);
  const setRows = (lastRealMatchData.match_results || [])
    .filter(row => row.match_id === id)
    .sort((a, b) => a.set_number - b.set_number);
  for (let i = 1; i <= 5; i++) {
    document.getElementById(`setA${i}`).value = setRows[i - 1]?.score_a ?? "";
    document.getElementById(`setB${i}`).value = setRows[i - 1]?.score_b ?? "";
  }
}
matchEditMode.addEventListener("change", () => {
  if (lastRealMatchData) refreshRealMatchOptions(lastRealMatchData);
});
realMatchSelect.addEventListener("change", () => {
  if (matchEditMode.value === "edit") prefillEditedMatch(realMatchSelect.value);
});

function refreshRealMatchOptions(data) {
  lastRealMatchData = data;
  const old = realMatchSelect.value;
  const editing = matchEditMode.value === "edit";
  realMatchSelect.replaceChildren();
  const names = new Map(data.players.map((p) => [p.id, p.name]));
  const groups = new Map(data.groups.map((g) => [g.id, g.name]));
  const brackets = new Map(data.brackets.map((b) => [b.id, b]));
  const available = data.matches.filter((m) =>
    Boolean(m.is_finished) === editing && m.player_a_id && m.player_b_id &&
    (m.group_id !== null || m.bracket_id !== null));
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = available.length ? (editing ? "Vyber odehraný zápas" : "Vyber zápas") : (editing ? "Žádný odehraný zápas" : "Žádný neodehraný zápas");
  realMatchSelect.append(placeholder);
  for (const match of available) {
    const option = document.createElement("option");
    option.value = String(match.id);
    const bracket = brackets.get(match.bracket_id);
    const stage = match.bracket_id !== null
      ? (bracket?.bracket_type === "round_robin" ? "Útěcha – minitabulka" : (bracket?.is_consolation ? "Útěcha – playoff" : "Hlavní playoff"))
      : (groups.get(match.group_id) || "Skupina");
    option.textContent = `${stage} · #${match.id}: ${names.get(match.player_a_id)} × ${names.get(match.player_b_id)}`;
    realMatchSelect.append(option);
  }
  if (available.some((m) => String(m.id) === old)) realMatchSelect.value = old;
  else realMatchSelect.value = "";
  realMatchButton.textContent = editing ? "Opravit výsledek offline" : "Zapsat výsledek offline";
  if (editing) prefillEditedMatch(realMatchSelect.value);
  const groupsLeft = available.filter((m) => m.group_id !== null).length;
  const playoffsLeft = available.length - groupsLeft;
  document.getElementById("realMatchStatus").textContent = editing
    ? `K opravě ${groupsLeft} skupinových a ${playoffsLeft} zápasů playoff / útěchy. Opravu může engine odmítnout, pokud ovlivní odehraný navazující zápas.`
    : `K dispozici ${groupsLeft} skupinových a ${playoffsLeft} zápasů playoff / útěchy.`;
}

function collectRealSets() {
  const sets = [];
  let gap = false;
  for (let i = 1; i <= 5; i++) {
    const a = document.getElementById(`setA${i}`).value.trim();
    const b = document.getElementById(`setB${i}`).value.trim();
    if (!a && !b) { gap = true; continue; }
    if (!a || !b || gap) throw new Error("Vyplň oba hráče v každém setu bez vynechaných řádků.");
    const x = Number(a), y = Number(b);
    if (!Number.isInteger(x) || !Number.isInteger(y) || x < 0 || y < 0 || x > 99 || y > 99 || x === y) {
      throw new Error("Každý set musí obsahovat dvě různá celá skóre 0–99.");
    }
    sets.push([x, y]);
  }
  if (!sets.length) throw new Error("Vyplň alespoň jeden set.");
  return sets;
}

realMatchButton.addEventListener("click", async () => {
  if (realMatchBusy) return;
  realMatchBusy = true;
  realMatchButton.disabled = true;
  matchEditMode.disabled = true;
  realMatchSelect.disabled = true;
  const status = document.getElementById("realMatchStatus");
  const report = document.getElementById("realMatchReport");
  report.textContent = "";
  let stage = "zahájení";
  // Temporary profiling only. Timing starts when the Save button is clicked.
  // No tournament data or scores are logged.
  const profileStart = performance.now();
  let profileLast = profileStart;
  const profileSteps = [];
  function profileMark(label) {
    const now = performance.now();
    profileSteps.push({ krok: label, ms: Math.round((now - profileLast) * 10) / 10 });
    profileLast = now;
  }
  try {
    const editing = matchEditMode.value === "edit";
    const matchId = Number(realMatchSelect.value);
    if (!Number.isSafeInteger(matchId) || matchId <= 0) throw new Error("Nejdřív vyber zápas.");
    const sets = collectRealSets();
    stage = "načtení uloženého turnaje";
    const copy = await getCopy();
    profileMark("Načtení SQLite z IndexedDB");
    if (!copy || !Number.isInteger(copy.sourceId)) throw new Error("Nejdřív načti turnaj.");
    if (editing && (copy.sourceKind !== "local" || copy.localImportedTournamentId)) {
      throw new Error("Opravy nyní podporujeme pouze u nesynchronizovaného lokálního turnaje.");
    }
    status.textContent = editing ? "Opravuji zápas původním Python enginem…" : "Zpracovávám zápas původním Python enginem…";
    stage = "příprava Pyodide";
    const py = await getRuntime();
    profileMark("Inicializace/získání Pyodide");
    py.FS.writeFile("/tmp/lab202_work.sqlite", new Uint8Array(copy.bytes));
    profileMark("Zápis SQLite do Pyodide FS");
    stage = "načtení SQLAlchemy a micropip";
    await py.loadPackage(["sqlalchemy", "micropip"]);
    profileMark("Načtení SQLAlchemy a micropip");
    stage = "načtení Flask balíčků";
    try {
          py.runPython("import flask, flask_sqlalchemy");
    } catch (error) {
        await py.runPythonAsync(
            "import micropip\nawait micropip.install(['flask', 'flask-sqlalchemy'])"
        );
    }
    profileMark("Instalace/ověření Flask balíčků");
    stage = "načtení Python engine souborů";
    await ensureEngineFiles(py);
    profileMark("Příprava souborů enginu");
    stage = editing ? "načtení real_match_edit.py" : "načtení real_match.py";
    const sourcePath = editing ? "real_tournament/real_match_edit.py" : "real_tournament/real_match.py";
    const writerSource = await cachedPythonSource(sourcePath);
    profileMark("Načtení skriptu zápisu/opravy");
    py.globals.set("_lab202_code", writerSource);
    py.globals.set("_lab202_match_id", matchId);
    py.globals.set("_lab202_sets_json", JSON.stringify(sets));
    py.globals.set("_lab202_edit", editing);
    const wrapper = `
import json, traceback

def _lab202_run():
    try:
        globals().pop("report_json", None)
        exec(compile(_lab202_code, "real_match_edit.py" if _lab202_edit else "real_match.py", "exec"), globals())
        output = globals().get("report_json")
        if not isinstance(output, str) or not output:
            raise ValueError("Chybi report_json")
        return json.dumps({"ok": True, "data": output})
    except BaseException as exc:
        return json.dumps({"ok": False, "error_type": type(exc).__name__,
                           "message": str(exc), "traceback": traceback.format_exc()},
                          ensure_ascii=False)
_lab202_run()
`;
    const outcome = JSON.parse(await py.runPythonAsync(wrapper));
    profileMark("Výpočet výsledku v Pythonu");
    if (!outcome.ok) {
      // Full diagnostics stay in the developer console; the organizer sees a short reason.
      console.error("Python match processing failed:", outcome.traceback);
      const pythonMessage = String(outcome.message || "").trim();
      const knownBlockedReseed = /Nelze změnit nasazení|původní zápas už je odehraný|nasazení útěchy: zápas už je odehraný/i.test(pythonMessage);
      const knownDownstreamChange = /Oprava by změnila již odehraný navazující zápas/i.test(pythonMessage);
      if (editing && (knownBlockedReseed || knownDownstreamChange)) {
        throw new Error("Výsledek nelze takto opravit, protože by změna zasáhla již odehraný zápas v playoff nebo útěše. Samotný volný los (BYE) opravu neblokuje.");
      }
      if (outcome.error_type === "ValueError" && pythonMessage) {
        throw new Error(pythonMessage);
      }
      throw new Error("Při zpracování výsledku nastala interní chyba. Podrobnosti jsou v konzoli prohlížeče.");
    }
    const result = JSON.parse(outcome.data);
    if (result.status !== "OK" || !result.verified_on_disk || (!editing && !result.finished) || result.match_id !== matchId || JSON.stringify(result.sets) !== JSON.stringify(sets)) {
      throw new Error("Kontrola výsledku selhala; nic se neukládá.");
    }
    stage = "kontrola souběžné změny";
    const latest = await getCopy();
    profileMark("Kontrola aktuální SQLite");
    if (!latest || latest.savedAt !== copy.savedAt || latest.byteLength !== copy.byteLength) {
      throw new Error("Turnaj mezitím změnila jiná karta. Uložení zamítnuto.");
    }
    stage = "uložení do IndexedDB";
    const updated = py.FS.readFile("/tmp/lab202_work.sqlite");
    profileMark("Export SQLite z Pyodide FS");
    if (updated.length < 1000 || updated.length > 25 * 1024 * 1024) throw new Error("Neplatná velikost SQLite.");
    const bytes = updated.slice().buffer;
    const saveOperation = editing ? replaceQueuedMatchResult : saveCopyAndQueue;
    if (typeof saveOperation !== "function") throw new Error("Chybí podpora aktualizace synchronizační fronty.");
    const queued = await saveOperation(
      {...copy, bytes, byteLength:bytes.byteLength, savedAt:new Date().toISOString(),lastMatchId:matchId},
      copy,
      {action: "submit_result", match_id: matchId, sets}
    );
    profileMark("Uložení SQLite a operace do IndexedDB");
    await updateSavedLabel();
    profileMark("Aktualizace informace o uložení");
    await readAndDisplay(bytes);
    profileMark("Načtení a překreslení turnaje");
    report.textContent = JSON.stringify(result, null, 2);
    status.textContent = editing
      ? `✅ Zápas ${matchId} opraven. Původní operace ${queued.request_id.slice(0, 8)} byla aktualizována.`
      : `✅ Zápas ${matchId} uložen; operace ${queued.request_id.slice(0, 8)} je ve frontě. Zkus F5.`;
  } catch (err) {
    status.textContent = matchEditMode.value === "edit" ? "❌ Oprava se nepodařila." : "❌ Zápis se nepodařil.";
    report.textContent = `Krok: ${stage}\n\n${err?.message || String(err)}`;
    console.error(err);
  } finally {
    const totalMs = Math.round((performance.now() - profileStart) * 10) / 10;
    if (profileSteps.length) {
      console.groupCollapsed(`[Offline výkon] ${totalMs} ms celkem · ${stage}`);
      console.table(profileSteps);
      console.log("Celkem od kliknutí:", totalMs, "ms");
      console.groupEnd();
    }
    realMatchBusy = false;
    realMatchButton.disabled = false;
    matchEditMode.disabled = false;
    realMatchSelect.disabled = false;
  }
});
