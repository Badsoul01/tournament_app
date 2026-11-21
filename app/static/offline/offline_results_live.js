"use strict";
/* Read-only results based on exactly the same WebManager.get_results_data()
   as the online results route. No sync, local data mutation or new ranking rules. */
(() => {
  const out = document.getElementById("output");
  if (!out) return;
  const presenter = String.raw`
import json, sqlite3, sys, types
from flask import Flask
SOURCE = '/tmp/lab194b.sqlite'
TARGET = '/tmp/st_results_view.sqlite'
with sqlite3.connect(SOURCE) as origin, sqlite3.connect(TARGET) as dest:
    origin.backup(dest)
    if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('Dočasná SQLite kopie je poškozená')
    row = dest.execute('SELECT source_tournament_id FROM offline_source').fetchone()
    if not row or not isinstance(row[0], int):
        raise ValueError('Chybí ID turnaje')
    tournament_id = row[0]
for name in ('app','app.models','app.services','app.services.utils','app.services.tournament','app.web'):
    if name not in sys.modules:
        mod = types.ModuleType(name)
        mod.__path__ = ['/home/pyodide/' + name.replace('.', '/')]
        sys.modules[name] = mod
from app.models.models import db
from app.web.webmanager import WebManager
app = Flask('offline_results_presenter')
app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:////tmp/st_results_view.sqlite',
                  SQLALCHEMY_TRACK_MODIFICATIONS=False)
db.init_app(app)
with app.app_context():
    try:
        wm = WebManager(tournament_id)
        # The exact online results order and final_rank logic.
        result = [{'name': player.name, 'rank': rank}
                  for player, rank in wm.get_results_data()]
        st_results_json = json.dumps({'results': result}, ensure_ascii=False)
    finally:
        db.session.remove()
        db.engine.dispose()
st_results_json
`;
  let latest = null, results = null, revision = 0, running = false, errorText = "";
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = String(text);
    if (cls) node.className = cls;
    return node;
  };
  function draw() {
    out.querySelectorAll(":scope > section.offline-live-results").forEach(node => node.remove());
    if (!latest) return;
    const section = el("section", null, "offline-live-results");
    section.append(el("h2", "VÝSLEDKY", "tournament-section-title"));
    if (errorText) section.append(el("p", "⚠️ " + errorText, "results-info"));
    else if (!results?.length) {
      const empty = el("div", null, "results-empty-box");
      empty.append(el("p", "Turnaj se stále hraje."));
      section.append(empty);
    } else {
      const table = el("table", null, "results-table");
      const head = el("thead"), headerRow = el("tr", null, "results-header-row");
      headerRow.append(el("th", "Pořadí"), el("th", "Hráč"));
      head.append(headerRow);
      const body = el("tbody");
      for (const {name, rank} of results) {
        const tr = el("tr", null, "results-row");
        const place = el("td", `${rank === 1 ? '🥇 ' : rank === 2 ? '🥈 ' : rank === 3 ? '🥉 ' : ''}${rank}.`, rank === 1 ? "offline-first-place" : "");
        const player = el("td", name);
        tr.append(place, player);
        body.append(tr);
      }
      table.append(head, body);
      section.append(table);
    }
    out.append(section);
  }
  async function refresh() {
    if (running) return;
    running = true;
    try {
      do {
        const expected = revision;
        try {
          const py = await getRuntime();
          await py.loadPackage(["sqlalchemy", "micropip"]);
          try {
              py.runPython("import flask, flask_sqlalchemy");
          } catch (error) {
              await py.runPythonAsync(
                    "import micropip\nawait micropip.install(['flask', 'flask-sqlalchemy'])"
              );
          }
          await ensureEngineFiles(py);
          const json = await py.runPythonAsync(presenter);
          if (revision === expected) {
            results = JSON.parse(json).results;
            errorText = "";
            draw();
          }
        } catch (error) {
          if (revision === expected) {
            console.error("Offline results presenter:", error);
            errorText = String(error.message || error);
            draw();
          }
        }
        if (revision === expected || !latest) break;
      } while (true);
    } finally { running = false; }
  }
  // Match commits broadcast data; wait for the groups and playoff presenters
  // to release their shared Pyodide runtime before calculating results.
  window.addEventListener("offline:tournament-data", event => {
    latest = event.detail?.data || null;
    revision++;
    results = null;
    errorText = "";
  });
  window.addEventListener("offline:playoff-presented", () => {
    if (latest) refresh();
  });
  window.addEventListener("offline:tournament-removed", () => {
    latest = null; results = null; errorText = ""; revision++;
    out.querySelectorAll(":scope > section.offline-live-results").forEach(node => node.remove());
  });
})();
