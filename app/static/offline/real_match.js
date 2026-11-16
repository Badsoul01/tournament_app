"use strict";

let realMatchBusy = false;
const realMatchSelect = document.getElementById("matchSelect");
const realMatchButton = document.getElementById("submitRealMatch");

function refreshRealMatchOptions(data) {
  const old = realMatchSelect.value;
  realMatchSelect.replaceChildren();
  const names = new Map(data.players.map((p) => [p.id, p.name]));
  const groups = new Map(data.groups.map((g) => [g.id, g.name]));
  const brackets = new Map(data.brackets.map((b) => [b.id, b]));
  const available = data.matches.filter((m) => !m.is_finished && m.player_a_id && m.player_b_id && (m.group_id !== null || m.bracket_id !== null));
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = available.length ? "Vyber zápas" : "Žádný neodehraný zápas";
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
  const groupsLeft = available.filter((m) => m.group_id !== null).length;
  const playoffsLeft = available.length - groupsLeft;
  document.getElementById("realMatchStatus").textContent = `K dispozici ${groupsLeft} skupinových a ${playoffsLeft} zápasů playoff / útěchy.`;
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
  const status = document.getElementById("realMatchStatus");
  const report = document.getElementById("realMatchReport");
  report.textContent = "";
  let stage = "zahájení";
  try {
    const matchId = Number(realMatchSelect.value);
    if (!Number.isSafeInteger(matchId) || matchId <= 0) throw new Error("Nejdřív vyber zápas.");
    const sets = collectRealSets();
    stage = "načtení uloženého turnaje";
    const copy = await getCopy();
    if (!copy || !Number.isInteger(copy.sourceId)) throw new Error("Nejdřív načti turnaj.");
    status.textContent = "Zpracovávám zápas původním Python enginem…";
    stage = "příprava Pyodide";
    const py = await getRuntime();
    py.FS.writeFile("/tmp/lab202_work.sqlite", new Uint8Array(copy.bytes));
    stage = "načtení SQLAlchemy a micropip";
    await py.loadPackage(["sqlalchemy", "micropip"]);
    stage = "načtení Flask balíčků";
    await py.runPythonAsync("import micropip\nawait micropip.install(['flask', 'flask-sqlalchemy'])");
    stage = "načtení Python engine souborů";
    await ensureEngineFiles(py);
    stage = "načtení real_match.py";
    const writerSource = await cachedPythonSource("real_tournament/real_match.py");
    py.globals.set("_lab202_code", writerSource);
    py.globals.set("_lab202_match_id", matchId);
    py.globals.set("_lab202_sets_json", JSON.stringify(sets));
    const wrapper = `
import json, traceback

def _lab202_run():
    try:
        exec(compile(_lab202_code, "real_match.py", "exec"), globals())
        output = globals().get("report_json")
        if not isinstance(output, str) or not output:
            raise ValueError("Chybi report_json")
        return json.dumps({"ok": True, "data": output})
    except BaseException:
        return json.dumps({"ok": False, "traceback": traceback.format_exc()})
_lab202_run()
`;
    const outcome = JSON.parse(await py.runPythonAsync(wrapper));
    if (!outcome.ok) throw new Error(outcome.traceback);
    const result = JSON.parse(outcome.data);
    if (result.status !== "OK" || !result.verified_on_disk || !result.finished || result.match_id !== matchId || JSON.stringify(result.sets) !== JSON.stringify(sets)) {
      throw new Error("Kontrola výsledku selhala; nic se neukládá.");
    }
    stage = "kontrola souběžné změny";
    const latest = await getCopy();
    if (!latest || latest.savedAt !== copy.savedAt || latest.byteLength !== copy.byteLength) {
      throw new Error("Turnaj mezitím změnila jiná karta. Uložení zamítnuto.");
    }
    stage = "uložení do IndexedDB";
    const updated = py.FS.readFile("/tmp/lab202_work.sqlite");
    if (updated.length < 1000 || updated.length > 25 * 1024 * 1024) throw new Error("Neplatná velikost SQLite.");
    const bytes = updated.slice().buffer;
    const queued = await saveCopyAndQueue(
      {...copy, bytes, byteLength:bytes.byteLength, savedAt:new Date().toISOString(),lastMatchId:matchId},
      copy,
      {action: "submit_result", match_id: matchId, sets}
    );
    await updateSavedLabel();
    await readAndDisplay(bytes);
    report.textContent = JSON.stringify(result, null, 2);
    status.textContent = `✅ Zápas ${matchId} uložen; operace ${queued.request_id.slice(0, 8)} je ve frontě. Zkus F5.`;
  } catch (err) {
    status.textContent = "❌ Zápis se nepodařil.";
    report.textContent = `Krok: ${stage}\n\n${err?.message || String(err)}`;
    console.error(err);
  } finally {
    realMatchBusy = false;
    realMatchButton.disabled = false;
  }
});
