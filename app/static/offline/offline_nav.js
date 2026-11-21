"use strict";
/* Offline navigation: presentation only. Never writes SQLite, IDB, or sync queue. */
(() => {
  const base = "/offline/";
  const pages = [["", "Nový turnaj"], ["groups", "Základní skupiny"],
    ["playoff", "Playoff"], ["consolation", "Útěcha"], ["results", "Výsledky"]];
  const known = new Set(pages.map(([slug]) => slug));
  const $ = id => document.getElementById(id);
  const style = document.createElement("style");
  style.textContent = `
    [hidden] { display:none !important; }
    .offline-nav { display:flex; justify-content:center; align-items:center; flex-wrap:wrap;
      gap:.4rem; padding:.65rem; margin:.8rem 0 1rem; background:rgba(10,20,34,.35);
      border-bottom:1px solid #31455e; }
    .offline-nav a { color:#cbd8e9; padding:.4rem .65rem; text-decoration:none; }
    .offline-nav a:hover, .offline-nav a:focus-visible { text-decoration:underline; }
    .offline-nav a[aria-current="page"] { font-weight:bold; text-decoration:underline; }
    .offline-nav-note { color:#9bacc4; text-align:center; font-size:.88rem; margin:.2rem 0 .8rem; }
    .offline-start-intro { display:none !important; }
    .offline-home-status { text-align:center; }
  `;
  document.head.append(style);
  const nav = document.createElement("nav");
  nav.className = "offline-nav";
  nav.hidden = true;
  nav.setAttribute("aria-label", "Navigace offline turnajem");
  for (const [slug, title] of pages) {
    const a = document.createElement("a");
    a.href = base + slug;
    a.textContent = title;
    a.dataset.offlinePage = slug;
    nav.append(a);
  }
  const h1 = document.querySelector("h1");
  if (h1) h1.insertAdjacentElement("afterend", nav);
  const notice = document.createElement("p");
  notice.className = "offline-nav-note";
  notice.hidden = true;
  nav.insertAdjacentElement("afterend", notice);
  // Hide verbose introductory text, but retain it in the DOM for accessibility/rollback.
  const longIntro = nav.nextElementSibling === notice ? notice.nextElementSibling : null;
  if (longIntro?.tagName === "P") longIntro.classList.add("offline-start-intro");

  const workspace = $("offlineWorkspace");
  const creator = $("newTournamentPanel");
  const staging = $("stageSyncSection");
  const matchForm = $("matchSelect")?.closest("section");
  const finish = $("finishLocalSection");
  const output = $("output");
  let hasTournament = false;
  let latestData = null;
  let activeUuid = null;
  let autoOpenedOnce = false;
  let finishOwnHidden = finish ? finish.hidden : true;
  let syncFinishVisibility = false;

  function page() {
    const slug = location.pathname.startsWith(base)
      ? location.pathname.slice(base.length).replace(/\/$/, "") : "";
    return known.has(slug) ? slug : "";
  }
  function route(slug, replace = false) {
    const method = replace ? "replaceState" : "pushState";
    history[method]({}, "", base + slug);
    update();
  }
  function classify(section) {
    const name = section.querySelector("h2")?.textContent?.trim() || "";
    if (name.startsWith("Turnaj ")) return "intro";
    if (name.startsWith("Postup ze skupin")) return "groups";
    if (name.startsWith("Skupina ")) return "groups";
    if (/útěcha|útěše/i.test(name)) return "consolation";
    if (/playoff|pavouk/i.test(name)) return "playoff";
    return "results";
  }
  function hasConsolation(data) {
    return Boolean(data?.brackets?.some(b => b.is_consolation) ||
      data?.groups?.some(g => g.is_consolation));
  }
  function nextPhase(data) {
    if (!data) return "groups";
    const matches = data.matches || [];
    const groups = (data.groups || []).filter(g => !g.is_consolation);
    if (matches.some(m => m.group_id != null && groups.some(g => g.id === m.group_id) && !m.is_finished)) return "groups";
    const brackets = data.brackets || [];
    const mainIds = new Set(brackets.filter(b => !b.is_consolation).map(b => b.id));
    const extraIds = new Set(brackets.filter(b => b.is_consolation).map(b => b.id));
    if (matches.some(m => mainIds.has(m.bracket_id) && !m.is_finished)) return "playoff";
    if (matches.some(m => extraIds.has(m.bracket_id) && !m.is_finished)) return "consolation";
    return "results";
  }
  function update() {
    const current = page();
    nav.hidden = !hasTournament;
    notice.hidden = !hasTournament;
    for (const link of nav.querySelectorAll("a")) {
      const slug = link.dataset.offlinePage;
      link.hidden = !hasTournament || (slug === "consolation" && !hasConsolation(latestData));
      if (slug === current) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    if (workspace) workspace.hidden = hasTournament && current !== "";
    if (creator) creator.hidden = hasTournament ? current !== "" : false;
    if (staging) staging.hidden = !hasTournament || current !== "results";
    if (matchForm) matchForm.hidden = !hasTournament || !["groups", "playoff", "consolation"].includes(current);
    if (finish) {
      syncFinishVisibility = true;
      finish.hidden = !(hasTournament && current === "results") || finishOwnHidden;
      syncFinishVisibility = false;
    }
    if (output) {
      // Keep the data in the DOM for other modules, but do not show debug/archive intro.
      output.hidden = !hasTournament || current === "";
      for (const section of output.querySelectorAll(":scope > section")) {
        const view = classify(section);
        section.hidden = !hasTournament || view === "intro" || view !== current;
      }
    }
    notice.textContent = "Výsledky se ukládají do tohoto zařízení. Na server se samy neodesílají.";
    // The current URL may point to a phase that does not exist for this event.
    if (hasTournament && current === "consolation" && latestData && !hasConsolation(latestData)) {
      route(nextPhase(latestData), true);
    }
  }
  nav.addEventListener("click", event => {
    const a = event.target.closest("a[data-offline-page]");
    if (!a || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    if (!hasTournament) return;
    route(a.dataset.offlinePage);
  });
  addEventListener("popstate", update);
  if (output) new MutationObserver(update).observe(output, { childList: true });
  if (finish) new MutationObserver(() => {
    if (syncFinishVisibility) return;
    if (hasTournament && page() === "results") finishOwnHidden = finish.hidden;
    else if (!finish.hidden) {
      finishOwnHidden = false;
      update();
    }
  }).observe(finish, { attributes: true, attributeFilter: ["hidden"] });

  async function onData(event) {
    const data = event.detail?.data;
    if (!data) return;
    latestData = data;
    // Only activate after the SQLite copy was committed. During creation a
    // temporary readAndDisplay() happens before IndexedDB is written.
    try {
      const copy = await getCopy();
      if (!copy) return;
      hasTournament = true;
      const newIdentity = `${copy.sourceKind}:${copy.sourceId}:${copy.localUuid || ""}`;
      if (!autoOpenedOnce || activeUuid !== newIdentity) {
        activeUuid = newIdentity;
        autoOpenedOnce = true;
        if (page() === "") route(nextPhase(data), true);
      }
      update();
    } catch (error) { console.warn("Navigace nemůže přečíst uložený turnaj:", error); }
  }
  addEventListener("offline:tournament-data", onData);
  addEventListener("offline:tournament-created", onData);
  addEventListener("offline:tournament-removed", () => {
    latestData = null;
    hasTournament = false;
    activeUuid = null;
    autoOpenedOnce = false;
    route("", true);
  });
  update();
})();
