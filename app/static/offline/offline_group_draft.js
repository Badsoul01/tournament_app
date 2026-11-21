"use strict";
/* Offline preparation only. Doesn't touch SQLite, the match engine or results sync.
 * Random seeding mirrors SetupWizard.auto_seed_players(seed_mode="reset_existing",
 * seed_criterion="random"): one player into each empty group, shuffle the rest,
 * then always fill the least-populated group, in A..H tie order.
 */
(() => {
  const $ = id => document.getElementById(id);
  const source = $("newTournamentPlayers");
  if (!source || !$("offlineGroupDraft")) return;
  const clean = s => String(s || "").trim().replace(/\s+/g," ");
  const key = s => clean(s).toLocaleLowerCase("cs-CZ");
  const names = () => source.value.split(/[\n,;]+/).map(clean).filter(Boolean);
  const letters = () => Array.from({length:Number($("newTournamentGroups").value)},(_,i)=>String.fromCharCode(65+i));
  let groups = {}, selected = null;
  let groupCount = 0;
  const current = () => names();
  const allAssigned = () => Object.values(groups).flat();
  const unassigned = () => current().filter(n=>!new Set(allAssigned().map(key)).has(key(n)));
  const message = text => { $("draftStatus").textContent=text; };
  // Keep assignments if catalog adds players; removing a name never creates a phantom assignment.
  function reconcile() {
    const valid = new Map(current().map(n=>[key(n),n]));
    const ls = letters();
    const next = Object.fromEntries(ls.map(l=>[l,[]]));
    const seen = new Set();
    for (const l of ls) for (const old of groups[l] || []) {
      const k = key(old);
      if (valid.has(k) && !seen.has(k)) { next[l].push(valid.get(k)); seen.add(k); }
    }
    if (selected && !valid.has(key(selected))) selected=null;
    if (selected) selected=valid.get(key(selected));
    if (groupCount !== ls.length) {
      groupCount=ls.length;
      message(`Počet skupin: ${groupCount}. Hráči z odebraných skupin jsou nyní nezařazení.`);
    }
    groups=next;
  }
  function playerButton(name) {
    const b=document.createElement("button");
    b.type="button";
    b.className="offline-draft-player";
    b.textContent=name;
    b.setAttribute("aria-pressed",String(selected!==null && key(selected)===key(name)));
    b.addEventListener("click",()=>{selected=(selected && key(selected)===key(name))?null:name;render();});
    return b;
  }
  function move(target) {
    if (!selected) { message("Nejprve označ hráče."); return; }
    const val=selected;
    if (target && groups[target].length>=8 && !groups[target].some(n=>key(n)===key(val))) {
      message(`Skupina ${target} už má 8 hráčů.`);render();return;
    }
    for (const l of Object.keys(groups)) groups[l]=groups[l].filter(n=>key(n)!==key(val));
    if (target) groups[target].push(val);
    selected=null;
    render();
    message(`${val} → ${target ? "skupina " + target : "nezařazení hráči"}.`);
  }
  function render() {
    reconcile();
    const pool=$("draftUnassigned");pool.replaceChildren();
    const free=unassigned();
    for (const name of free)pool.append(playerButton(name));
    if (!free.length) { const label=document.createElement("span");label.textContent="Žádní nezařazení hráči.";pool.append(label); }
    $("draftUnassignedCount").textContent=`(${free.length})`;
    const dest=$("draftGroups");dest.replaceChildren();
    for (const l of letters()) {
      const card=document.createElement("section");card.className="offline-draft-group";
      const title=document.createElement("button");title.type="button";title.className="offline-draft-group-target";
      title.textContent=`Skupina ${l} (${groups[l].length})`;
      title.title=`Přesunout označeného hráče do skupiny ${l}`;
      title.addEventListener("click",()=>move(l));
      const members=document.createElement("div");members.className="offline-draft-player-list";
      for (const p of groups[l])members.append(playerButton(p));
      if (!groups[l].length) {const label=document.createElement("span");label.textContent="Prázdná skupina";members.append(label);}
      card.append(title,members);dest.append(card);
    }
    $("draftSelection").textContent=selected?`Označený hráč: ${selected}. Klepni na skupinu, „Nezařazení“, nebo na koš.`:"Klepni na jméno hráče, potom na cílovou skupinu.";
    $("draftRemovePlayer").disabled=!selected;
    $("draftReturnPlayer").disabled=!selected;
  }
  function randomOrder(arr) {
    const copy=arr.slice();
    // Secure Fisher-Yates; source wizard uses Python random.shuffle.
    for(let i=copy.length-1;i>0;i--){
      const n=4294967296,limit=n-(n%(i+1));let r;
      do {const bytes=new Uint32Array(1);crypto.getRandomValues(bytes);r=bytes[0];}while(r>=limit);
      const j=r%(i+1);[copy[i],copy[j]]=[copy[j],copy[i]];
    }
    return copy;
  }
  function autoSeed(){
    reconcile();const people=current(),ls=letters();
    if(new Set(people.map(key)).size!==people.length){message("V seznamu jsou duplicitní hráči.");return;}
    if(people.length<ls.length*2 || people.length>ls.length*8){message(`Pro ${ls.length} skupin je potřeba ${ls.length*2} až ${ls.length*8} hráčů.`);return;}
    const shuffled=randomOrder(people);
    groups=Object.fromEntries(ls.map(l=>[l,[]]));
    // The first player of each freshly empty group (SetupWizard step 4).
    ls.forEach((l,i)=>groups[l].push(shuffled[i]));
    // SetupWizard step 5 shuffles remaining players a second time.
    for(const p of randomOrder(shuffled.slice(ls.length))){
      const target=ls.filter(l=>groups[l].length<8).sort((a,b)=>groups[a].length-groups[b].length)[0];
      if(!target){message("Skupiny jsou plné.");return;}
      groups[target].push(p);
    }
    selected=null;render();message("Skupiny rozlosovány. Nyní je můžeš ručně upravit; turnaj zatím nebyl vytvořen.");
  }
  function removeSelected(){
    if(!selected)return;
    const val=selected;
    if(!confirm(`Opravdu odstranit hráče „${val}“ z připravovaného turnaje?`))return;
    source.value=current().filter(n=>key(n)!==key(val)).join("\n");
    selected=null;
    source.dispatchEvent(new Event("input",{bubbles:true}));
    render();message(`Hráč ${val} byl odstraněn. Z katalogu minulých turnajů se nemaže.`);
  }
  function getGroupsForCreation(){
    reconcile();
    const people=current(), ls=letters(), advance=Number($("newTournamentAdvance").value);
    if(new Set(people.map(key)).size!==people.length)throw new Error("Duplicitní jména hráčů.");
    if(unassigned().length)throw new Error(`Nejdřív zařaď všechny hráče do skupin (${unassigned().length} nezařazených).`);
    if(!people.length)throw new Error("Přidej hráče a rozděl je do skupin.");
    if(ls.some(l=>groups[l].length<2 || groups[l].length>8))throw new Error("Každá skupina musí mít 2 až 8 hráčů.");
    if(ls.some(l=>groups[l].length<=advance))throw new Error("V každé skupině musí být více hráčů než postupujících.");
    const final=Object.fromEntries(ls.map(l=>[l,groups[l].slice()]));
    if(Object.values(final).flat().length!==people.length)throw new Error("Počet zařazených hráčů nesouhlasí se seznamem.");
    return final;
  }
  const toolbar=$("draftRemovePlayer");
  const back=document.createElement("button");back.type="button";back.id="draftReturnPlayer";back.textContent="↩ Nezařazení";back.disabled=true;
  back.addEventListener("click",()=>move(null));toolbar.before(back);
  $("draftAutoSeed").addEventListener("click",autoSeed);
  $("draftClearGroups").addEventListener("click",()=>{reconcile();groups=Object.fromEntries(letters().map(l=>[l,[]]));selected=null;render();message("Všichni hráči vráceni mezi nezařazené.");});
  $("draftRemovePlayer").addEventListener("click",removeSelected);
  source.addEventListener("input",render);
  $("newTournamentGroups").addEventListener("change",render);
  $("newTournamentAdvance").addEventListener("change",render);
  // The create handler reads this only when the user explicitly clicks Create.
  window.offlineGroupDraft={getGroupsForCreation};
  render();
})();
