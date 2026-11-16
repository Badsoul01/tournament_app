"use strict";
/* Read-only presenter using the original WebManager inside the existing Pyodide.
   Writes results ONLY through the existing real_match.js button and IDB queue. */
(() => {
  const $ = id => document.getElementById(id);
  const out = $("output");
  if (!out) return;
  const originalMatchSection = $("matchSelect")?.closest("section");
  if (originalMatchSection) originalMatchSection.classList.add("offline-lab-match-hidden");
  function syncPageClass() {
    document.body.classList.toggle("offline-live-groups-page", location.pathname.replace(/\/$/, "").endsWith("/groups"));
  }
  document.addEventListener("click", event => {
    if (event.target.closest(".offline-nav")) setTimeout(syncPageClass, 0);
  });
  window.addEventListener("popstate", syncPageClass);
  syncPageClass();

  const pythonPresenter = String.raw`
import json, sqlite3, sys, types, traceback
from flask import Flask

# The original readAndDisplay() already validated this SQLite file.
# Work on a separate temporary copy to ensure presenting cannot alter the saved bytes.
SOURCE = '/tmp/lab194b.sqlite'
TARGET = '/tmp/st_groups_view.sqlite'
with sqlite3.connect(SOURCE) as original, sqlite3.connect(TARGET) as isolated:
    original.backup(isolated)
    if isolated.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('Dočasná SQLite kopie je poškozená')
    row = isolated.execute('SELECT source_tournament_id FROM offline_source').fetchone()
    if not row or not isinstance(row[0], int):
        raise ValueError('Chybí ID zdrojového turnaje')
    tournament_id = row[0]
for name in ('app','app.models','app.services','app.services.utils','app.services.tournament','app.web'):
    if name not in sys.modules:
        mod = types.ModuleType(name)
        mod.__path__ = ['/home/pyodide/' + name.replace('.', '/')]
        sys.modules[name] = mod
from app.models.models import db
from app.web.webmanager import WebManager
app = Flask('offline_groups_presenter')
app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:////tmp/st_groups_view.sqlite', SQLALCHEMY_TRACK_MODIFICATIONS=False)
db.init_app(app)
with app.app_context():
    try:
        manager = WebManager(tournament_id)
        result = {'groups': manager.get_groups_page_data(),
                  'advance_per_group': manager.tournament.advance_per_group}
        st_groups_json = json.dumps(result, ensure_ascii=False)
    finally:
        db.session.remove()
        db.engine.dispose()
st_groups_json
`;

  let lastData = null;
  let groupsData = null;
  let expandedMatch = null;
  let requestedVersion = 0;
  let running = false;
  let lastActionText = "";

  function elt(tag, content, className) {
    const node = document.createElement(tag);
    if (content != null) node.textContent = String(content);
    if (className) node.className = className;
    return node;
  }
  function cell(row, tag, value, className) {
    const n = elt(tag, value, className);
    row.append(n);
    return n;
  }
  function currentPage() {
    return location.pathname.replace(/\/$/, "").endsWith("/groups");
  }
  function hideOldGroupSections() {
    for (const section of out.querySelectorAll(":scope > section:not(.offline-live-groups)")) {
      const heading = section.querySelector("h2")?.textContent?.trim() || "";
      if (heading.startsWith("Skupina ") || heading.startsWith("Postup ze skupin")) {
        section.classList.add("offline-legacy-group-hidden");
      }
    }
  }
  function activeMatch(card, match) {
    if (expandedMatch === match.match_id) {
      expandedMatch = null;
    } else {
      expandedMatch = match.match_id;
    }
    draw();
  }
  function fmtScore(match) {
    const sets = match.played_sets || [];
    return sets.map(([a, b]) => `${a}:${b}`).join(", ");
  }
  function draw() {
    hideOldGroupSections();
    out.querySelector(":scope > section.offline-live-groups")?.remove();
    if (!groupsData || !lastData) return;
    const section = elt("section", null, "offline-live-groups");
    section.append(elt("h2", "Skupina – základní skupiny", "tournament-section-title"));
    if (lastActionText) section.append(elt("p", lastActionText, "offline-groups-feedback"));
    for (const [groupName, group] of Object.entries(groupsData.groups)) {
      const details = elt("details", null, "group-details-box");
      details.open = true;
      details.append(elt("summary", `Skupina ${groupName}`, "group-summary-title"));
      const container = elt("div", null, "group-container-mt");
      const layout = elt("table", null, "group-layout-table");
      const layoutRow = elt("tr");
      const left = elt("td", null, "group-left-col");
      const right = elt("td", null, "group-right-col");
      layoutRow.append(left, right);
      layout.append(layoutRow);
      container.append(layout);

      // Same statistics and rank order as the live group's _group_content.html.
      const rankings = elt("table", null, "group-table");
      const thead = elt("thead"), head = elt("tr");
      for (const name of ["Hráč", "Sety", "Míčky +/-", "Body"]) cell(head, "th", name);
      thead.append(head);
      rankings.append(thead);
      const tbody = elt("tbody");
      (group.players || []).forEach((p, index) => {
        const tr = elt("tr", null, index < groupsData.advance_per_group ? "qualifying-row" : "");
        cell(tr, "td", p.name, "fw-bold");
        cell(tr, "td", `${p.games_win}-${p.games_lost}`);
        cell(tr, "td", p.balls_diff);
        cell(tr, "td", p.points, "fw-bold");
        tbody.append(tr);
      });
      rankings.append(tbody);
      left.append(rankings, elt("p", "V případě shody pořadí určuje: Vzájemný zápas, Sety, Míčky.", "group-hint-text"));
      left.append(elt("h4", "Odehrané zápasy", "text-accent"));
      const finishedTable = elt("table", null, "matches-table");
      for (const match of group.matches || []) {
        if (!match.is_finished) continue;
        const row = elt("tr"), players = elt("td", null, "matches-table-player-col");
        const a = elt("span", match.player_a_name, match.winner_name === match.player_a_name ? "text-winner" : "text-main");
        const b = elt("span", match.player_b_name, match.winner_name === match.player_b_name ? "text-winner" : "text-main");
        players.append(a, elt("span", " – ", "text-muted"), b);
        row.append(players, elt("td", fmtScore(match), "matches-table-score-col"));
        finishedTable.append(row);
      }
      if (!finishedTable.children.length) {
        const r = elt("tr"); cell(r, "td", "Zatím žádné odehrané zápasy."); finishedTable.append(r);
      }
      left.append(finishedTable);

      for (const match of group.matches || []) {
        if (match.is_finished || match.player_a_name === "TBD" || match.player_b_name === "TBD") continue;
        const card = elt("div", null, "match-card offline-groups-card" + (expandedMatch === match.match_id ? " active-match" : ""));
        const label = `${match.player_a_name} vs ${match.player_b_name}`;
        const toggle = elt("button", `${label}   ${expandedMatch === match.match_id ? "✕" : "📜"}`, "offline-groups-toggle");
        toggle.type = "button";
        toggle.setAttribute("aria-expanded", String(expandedMatch === match.match_id));
        toggle.addEventListener("click", () => activeMatch(card, match));
        card.append(toggle);
        if (expandedMatch === match.match_id) card.append(makeForm(match));
        right.append(card);
      }
      if (!(group.matches || []).some(m => !m.is_finished)) right.append(elt("p", "Všechny zápasy skupiny jsou odehrané.", "group-hint-text"));
      details.append(container);
      section.append(details);
    }
    out.prepend(section);
    // The existing navigation MutationObserver selects sections by heading.
  }
  function makeForm(match) {
    const form = elt("form", null, "match-form-column offline-group-match-form");
    const lineCount = Math.min(5, Math.max(1, Number(match.match_format || lastData?.tournaments?.[0]?.group_match_format || 3) + 1));
    for (let i = 1; i <= lineCount; i++) {
      const row = elt("label", null, "offline-set-row");
      row.append(elt("span", `${i}. set:`));
      const a = elt("input"), b = elt("input");
      for (const input of [a, b]) {
        input.type = "number";
        input.min = "0";
        input.max = "99";
        input.inputMode = "numeric";
        input.autocomplete = "off";
      }
      a.dataset.side = "a"; b.dataset.side = "b";
      row.append(a, elt("span", ":"), b);
      form.append(row);
    }
    const button = elt("button", "Uložit výsledek", "offline-save-group-match");
    button.type = "submit";
    form.append(button);
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (running) return;
      const values = [...form.querySelectorAll(".offline-set-row")].map(row => [row.querySelector('[data-side="a"]').value.trim(), row.querySelector('[data-side="b"]').value.trim()]);
      let gap = false, count = 0;
      for (const [a, b] of values) {
        if (!a && !b) {gap = true; continue;}
        if (!a || !b || gap || !/^\d+$/.test(a) || !/^\d+$/.test(b) || Number(a) > 99 || Number(b) > 99 || Number(a) === Number(b)) {
          lastActionText = "❌ Sety musí mít dvě různá skóre 0–99 a nesmí se vynechávat řádky.";
          draw(); return;
        }
        count++;
      }
      if (!count) { lastActionText = "❌ Vyplň alespoň jeden set."; draw(); return; }
      const select = $("matchSelect"), originalButton = $("submitRealMatch");
      if (!select || !originalButton || ![...select.options].some(o => Number(o.value) === match.match_id)) {
        lastActionText = "❌ Zápas není ve výběru offline enginu."; draw(); return;
      }
      select.value = String(match.match_id);
      for (let i = 1; i <= 5; i++) {
        $("setA" + i).value = values[i - 1]?.[0] || "";
        $("setB" + i).value = values[i - 1]?.[1] || "";
      }
      running = true; button.disabled = true;
      lastActionText = "Zapisování výsledku do lokální SQLite…";
      try {
        originalButton.click();
        // real_match.js emits offline:tournament-data after the SQLite and queue commit.
        // Watch status as well, because a rejected operation emits no data event.
        const status = $("realMatchStatus");
        const report = $("realMatchReport");
        await new Promise((resolve, reject) => {
          let done = false;
          const onData = () => finish(null);
          const observer = new MutationObserver(() => {
            if (status?.textContent?.startsWith("❌")) finish(new Error(report?.textContent || status.textContent));
          });
          function finish(error) {
            if (done) return;
            done = true;
            window.removeEventListener("offline:tournament-data", onData);
            observer.disconnect();
            error ? reject(error) : resolve();
          }
          window.addEventListener("offline:tournament-data", onData, {once: true});
          if (status) observer.observe(status, {childList: true, characterData: true, subtree: true});
          // No timeout needed for correctness; button remains disabled while the writer works.
        });
        expandedMatch = null;
        lastActionText = "✅ Výsledek uložen do zařízení.";
      } catch (error) {
        lastActionText = "❌ " + String(error.message || error);
      } finally {
        running = false;
        draw();
      }
    });
    return form;
  }
  async function rebuildVersion(version) {
    try {
      const py = await getRuntime();
      await py.loadPackage(["sqlalchemy", "micropip"]);
      await py.runPythonAsync("import micropip\nawait micropip.install(['flask', 'flask-sqlalchemy'])");
      await ensureEngineFiles(py);
      const raw = await py.runPythonAsync(pythonPresenter);
      if (version !== requestedVersion) return;
      groupsData = JSON.parse(raw);
      draw();
    } catch (error) {
      if (version !== requestedVersion) return;
      console.error("Offline zobrazení skupin:", error);
      lastActionText = "⚠️ Nepodařilo se připravit tabulky z původního WebManageru: " + String(error.message || error);
      groupsData = null;
      // Preserve the original lab view as an emergency fallback.
      for (const section of out.querySelectorAll(".offline-legacy-group-hidden")) section.classList.remove("offline-legacy-group-hidden");
      const section = elt("section", null, "offline-live-groups");
      section.append(elt("h2", "Skupina – chyba zobrazení", "tournament-section-title"), elt("p", lastActionText));
      out.prepend(section);
    } finally {
      // Allow the playoff presenter to use the same Pyodide runtime afterwards.
      // Even an unsuccessful group presentation must release its turn.
      if (version === requestedVersion) {
        window.dispatchEvent(new CustomEvent("offline:groups-presented", { detail: { version } }));
      }
    }
  }
  window.addEventListener("offline:tournament-data", event => {
    lastData = event.detail?.data;
    syncPageClass();
    expandedMatch = null;
    requestedVersion++;
    rebuildVersion(requestedVersion);
  });
  window.addEventListener("offline:tournament-removed", () => {
    lastData = null; groupsData = null;
    requestedVersion++;
    out.querySelector(".offline-live-groups")?.remove();
  });
})();
