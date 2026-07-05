/* Character Builder (Slice 12c): BG3-style flow in PHB order — race, background,
   name, point-buy abilities, class & advancement, equipment. The server enumerates
   every legal choice (engine registries + level_choices) and compiles the live
   sheet; this file only renders and selects. The roster lives in localStorage and
   round-trips through JSON download/import. */
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const signed = (n) => (n >= 0 ? "+" : "") + n;
const STORE = "ravel.characters";

// --- engine-support badges (meta.support, keyed by exact feature name) --------
const SUPP_GLYPH = { gap: "!", approx: "~", utility: "u", cosmetic: "*" };
let SUPP = {};          // name -> {status, note}
let SUBNAMES = null;    // subclass names, to strip a " (Subclass)" display suffix

function suppFor(name) {
  if (SUPP[name]) return SUPP[name];               // exact (base features may hold parens)
  const m = /^(.*) \(([^)]+)\)$/.exec(name);       // "Cutting Words (College of Lore)"
  if (m && SUBNAMES && SUBNAMES.has(m[2])) return SUPP[m[1]] || null;
  return null;
}
function suppBadge(name) {
  const s = suppFor(name);
  if (!s) return "";
  return `<sup class="supp supp-${s.status}" title="${esc(s.note)}">${SUPP_GLYPH[s.status]}</sup>`;
}
const annotate = (name) => esc(name) + suppBadge(name);   // escaped name + its badge

const state = {
  meta: null,
  ch: null,           // working character (character_to_dict shape)
  preview: null,      // last /api/builder/preview response
  levelupDraft: {},   // widget state for the pending level-up
};

function blankCharacter() {
  return { name: "", race: "", background: "",
           base_abilities: { STR: 8, DEX: 8, CON: 8, INT: 8, WIS: 8, CHA: 8 },
           levels: [], wild_shapes: [],
           equipment: { armor: "", shield: false, main_hand: "", off_hand: "",
                        two_handing: false, ammo: 20 } };
}

// ------------------------------- boot ----------------------------------------

async function init() {
  state.meta = await (await fetch("/api/builder/meta")).json();
  SUPP = state.meta.support || {};
  SUBNAMES = new Set(state.meta.classes.flatMap((c) => c.subclasses || []));
  state.ch = blankCharacter();
  renderRoster();
  renderRace();
  renderBackground();
  renderPointBuy();
  renderEquipment();
  $("#ch-name").addEventListener("input", () => { state.ch.name = $("#ch-name").value; refresh(); });
  $("#pb-budget").addEventListener("input", renderPointBuy);
  $("#ch-new").addEventListener("click", () => loadCharacter(blankCharacter()));
  $("#ch-save").addEventListener("click", saveCurrent);
  $("#ch-export").addEventListener("click", () => download(
    `${state.ch.name || "character"}.json`, JSON.stringify(state.ch, null, 2)));
  $("#ch-export-all").addEventListener("click", () => download(
    "ravel-roster.json", JSON.stringify(roster(), null, 2)));
  $("#ch-import").addEventListener("change", importFile);
  $("#ch-clear").addEventListener("click", () => {
    if (!confirm("strike EVERYONE from the roster? (downloaded JSON files are unaffected)")) return;
    setRoster({});
  });
  refresh();
}

// ------------------------------ the roster -----------------------------------

const roster = () => JSON.parse(localStorage.getItem(STORE) || "{}");
const setRoster = (r) => {
  try {
    localStorage.setItem(STORE, JSON.stringify(r));
  } catch (exc) {
    $("#b-error").textContent = "this browser won't keep the roster (storage blocked/full) — download your characters instead";
  }
  renderRoster();
};

function renderRoster() {
  const r = roster();
  const names = Object.keys(r).sort();
  $("#char-list").innerHTML = names.length ? names.map((n) => {
    const lv = (r[n].levels || []).length;
    const cls = [...new Set((r[n].levels || []).map((e) => e.cls))].join("/");
    return `<li><a href="#" class="char-load" data-name="${esc(n)}">${esc(n)}</a>
      <span class="char-meta">${esc(r[n].race || "?")}${cls ? " " + esc(cls) : ""} ${lv || ""}</span>
      <a href="#" class="char-del" data-name="${esc(n)}" title="strike from the roster">✕</a></li>`;
  }).join("") : `<li class="none">no one on the roster yet</li>`;
  document.querySelectorAll(".char-load").forEach((a) => a.addEventListener("click", (ev) => {
    ev.preventDefault();
    loadCharacter(roster()[a.dataset.name]);
  }));
  document.querySelectorAll(".char-del").forEach((a) => a.addEventListener("click", (ev) => {
    ev.preventDefault();
    if (!confirm(`strike ${a.dataset.name} from the roster?`)) return;
    const r2 = roster();
    delete r2[a.dataset.name];
    setRoster(r2);
  }));
}

function saveCurrent() {
  if (!state.ch.name) { $("#b-error").textContent = "name them first, berk"; return; }
  $("#b-error").textContent = "";
  const r = roster();
  r[state.ch.name] = state.ch;
  setRoster(r);
}

function loadCharacter(ch) {
  state.ch = JSON.parse(JSON.stringify(ch));
  state.levelupDraft = {};
  $("#ch-name").value = state.ch.name || "";
  renderRace();
  renderBackground();
  renderPointBuy();
  renderEquipment();
  refresh();
}

function download(filename, text) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function importFile(ev) {
  const files = [...ev.target.files];
  if (!files.length) return;
  const r = roster();
  let added = 0, last = null;
  for (const file of files) {                 // multiple files welcome
    let data;
    try { data = JSON.parse(await file.text()); }
    catch { $("#b-error").textContent = `${file.name} isn't JSON`; continue; }
    if (data.race !== undefined && data.levels !== undefined) {   // one character
      last = data;
      if (data.name) { r[data.name] = data; added += 1; }
    } else {                                                      // a whole roster
      for (const [name, ch] of Object.entries(data)) {
        if (ch && ch.levels !== undefined) { r[name] = ch; added += 1; last = ch; }
      }
    }
  }
  setRoster(r);
  if (last) loadCharacter(last);
  $("#b-error").textContent = added ? "" : "no characters found in those files";
  ev.target.value = "";
}

// ------------------------------ step 1: race ---------------------------------

function renderRace() {
  $("#race-cards").innerHTML = state.meta.races.map((r) => `
    <label class="race-card${state.ch.race === r.name ? " sel" : ""}">
      <input type="radio" name="race" value="${esc(r.name)}" ${state.ch.race === r.name ? "checked" : ""}>
      <b>${esc(r.name)}</b>
      <span class="race-bon">${Object.entries(r.bonuses).map(([a, n]) => `${a} ${signed(n)}`).join(", ")}</span>
      <span class="race-traits">${r.traits.map(annotate).join(" · ")}</span>
    </label>`).join("");
  document.querySelectorAll('input[name="race"]').forEach((el) =>
    el.addEventListener("change", () => { state.ch.race = el.value; renderRace(); renderPointBuy(); refresh(); }));
}

// --------------------------- step 2: background -------------------------------

function renderBackground() {
  $("#bg-chips").innerHTML = Object.entries(state.meta.backgrounds).map(([n, sk]) => `
    <label class="bg-chip${state.ch.background === n ? " sel" : ""}">
      <input type="radio" name="bg" value="${esc(n)}" ${state.ch.background === n ? "checked" : ""}>
      <b>${esc(n)}</b> <span>${sk.map(esc).join(", ")}</span>
    </label>`).join("");
  document.querySelectorAll('input[name="bg"]').forEach((el) =>
    el.addEventListener("change", () => { state.ch.background = el.value; renderBackground(); refresh(); }));
}

// --------------------------- step 4: point buy --------------------------------

const pbCost = (score) => state.meta.point_buy.costs[score] ?? 0;
const pbSpent = () => Object.values(state.ch.base_abilities).reduce((s, v) => s + pbCost(v), 0);

function renderPointBuy() {
  const pb = state.meta.point_buy;
  const budget = Number($("#pb-budget").value) || pb.default_budget;
  const race = state.meta.races.find((r) => r.name === state.ch.race);
  const remaining = budget - pbSpent();
  $("#pb-remaining").textContent = `${remaining} points left`;
  $("#pb-remaining").classList.toggle("over", remaining < 0);
  $("#pb-table").innerHTML =
    `<tr><th></th><th>score</th><th>cost</th><th>race</th><th>final</th></tr>` +
    state.meta.abilities.map((a) => {
      const v = state.ch.base_abilities[a];
      const bon = (race?.bonuses || {})[a] || 0;
      const canUp = v < pb.max && (pbCost(v + 1) - pbCost(v)) <= remaining;
      return `<tr>
        <th>${a}</th>
        <td class="pb-score"><button class="pb-btn" data-a="${a}" data-d="-1" ${v <= pb.min ? "disabled" : ""}>−</button>
          <b>${v}</b>
          <button class="pb-btn" data-a="${a}" data-d="1" ${canUp ? "" : "disabled"}>+</button></td>
        <td>${pbCost(v)}</td>
        <td>${bon ? signed(bon) : ""}</td>
        <td><b>${v + bon}</b> (${signed(Math.floor((v + bon - 10) / 2))})</td>
      </tr>`;
    }).join("");
  document.querySelectorAll(".pb-btn").forEach((b) => b.addEventListener("click", () => {
    state.ch.base_abilities[b.dataset.a] += Number(b.dataset.d);
    renderPointBuy();
    refresh();
  }));
}

// ----------------------- step 5: class & advancement ---------------------------

function levelSummary(e, i, clsLevel) {
  const bits = [];
  if (e.subclass) bits.push(esc(e.subclass));
  if (e.fighting_style) bits.push("style: " + esc(e.fighting_style));
  if (e.skills?.length) bits.push("skills: " + e.skills.map(esc).join(", "));
  if (Object.keys(e.asi || {}).length)
    bits.push("ASI " + Object.entries(e.asi).map(([a, n]) => `${esc(a)} ${signed(n)}`).join(", "));
  if (e.feat) bits.push("feat: " + esc(e.feat));
  if (e.spells?.length) bits.push("spells: " + e.spells.map(esc).join(", "));
  const grants = (state.preview?.level_grants || [])[i] || [];
  return `<li><b>${esc(e.cls)} ${clsLevel}</b>${bits.length ? " — " + bits.join(" · ") : ""}
    ${grants.length ? `<span class="grants">grants: ${grants.map(annotate).join(", ")}</span>` : ""}
    ${i === state.ch.levels.length - 1 ? '<a href="#" id="undo-level" title="undo this level">↶ undo</a>' : ""}</li>`;
}

function renderLevels() {
  const counts = {};   // per-class level within the multiclass ordering
  $("#level-list").innerHTML = state.ch.levels.map((e, i) => {
    counts[e.cls] = (counts[e.cls] || 0) + 1;
    return levelSummary(e, i, counts[e.cls]);
  }).join("");
  $("#undo-level")?.addEventListener("click", (ev) => {
    ev.preventDefault();
    state.ch.levels.pop();
    state.levelupDraft = {};
    refresh();
  });
}

function renderLevelUp() {
  const box = $("#levelup");
  if (!state.ch.race) { box.innerHTML = `<p class="none">pick a race first</p>`; return; }
  if (state.ch.levels.length >= 20) {
    box.innerHTML = `<hr class="hair"><p class="none">level 20 — the build is complete; the pit takes them no further</p>`;
    return;
  }
  const next = state.preview?.next || {};
  const d = state.levelupDraft;
  d.cls = d.cls || state.ch.levels[0]?.cls || state.meta.classes[0].name;
  const cd = state.meta.classes.find((c) => c.name === d.cls);
  const lc = next[d.cls] || {};
  let html = `<hr class="hair"><p class="lvl-head">Level ${state.ch.levels.length + 1}:
    <select id="lu-cls">${state.meta.classes.map((c) =>
      `<option ${c.name === d.cls ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>
    <span class="faint-note">d${cd.hit_die} hit die${lc.class_level ? ` · ${d.cls} ${lc.class_level}` : ""}</span></p>`;
  if (lc.grants?.length)
    html += `<p class="grants lu-grants">this level grants: ${lc.grants.map(annotate).join(", ")}</p>`;

  if (lc.skill_choices) {
    html += `<div class="lu-block"><b>skills</b> — choose ${lc.skill_choices}:
      ${cd.skill_list.map((s) => `<label class="pick"><input type="checkbox" class="lu-skill"
        value="${esc(s)}" ${d.skills?.includes(s) ? "checked" : ""}> ${esc(s)}</label>`).join("")}</div>`;
  }
  if (lc.fighting_style) {
    html += `<div class="lu-block"><b>fighting style</b>
      <select id="lu-style"><option value="">—</option>${state.meta.fighting_styles.map((s) =>
        `<option ${d.style === s ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></div>`;
  }
  if (lc.subclass) {
    html += `<div class="lu-block"><b>${d.cls === "Wizard" ? "arcane tradition" : "archetype"}</b>
      <select id="lu-sub"><option value="">—</option>${lc.subclass_options.map((s) =>
        `<option ${d.sub === s ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></div>`;
  }
  if (lc.asi_or_feat) {
    html += `<div class="lu-block"><b>ability score improvement</b> (two +1s, or a feat)
      <select id="lu-asi1"><option value="">—</option>${state.meta.abilities.map((a) =>
        `<option ${d.asi1 === a ? "selected" : ""}>${a}</option>`).join("")}</select>
      <select id="lu-asi2"><option value="">—</option>${state.meta.abilities.map((a) =>
        `<option ${d.asi2 === a ? "selected" : ""}>${a}</option>`).join("")}</select>
      or feat <select id="lu-feat"><option value="">—</option>${state.meta.feats.map((f) =>
        `<option ${d.feat === f ? "selected" : ""}>${esc(f)}</option>`).join("")}</select></div>`;
  }
  // spell picks: native caster class list, or a casting subclass's (Eldritch Knight)
  const subNow = d.sub || state.preview?.sheet?.subclasses?.[d.cls] || "";
  let entries = (state.meta.spell_lists || {})[d.cls];
  let maxLv = lc.max_spell_level ?? 0;
  if (!entries && (state.meta.spell_lists || {})[subNow]) {
    entries = state.meta.spell_lists[subNow];
    maxLv = lc.ek_max_spell_level ?? 0;
  }
  if (lc.wild_shapes) {
    const moon = (subNow || "").includes("Moon");
    const forms = (moon ? lc.wild_shape_options_moon : lc.wild_shape_options) || [];
    html += `<div class="lu-block"><b>wild shape forms</b>
      <span class="faint-note">(beasts within your circle's CR cap)</span><br>
      ${forms.map((f) => `<label class="pick"><input type="checkbox" class="lu-form"
        value="${esc(f)}" ${(state.ch.wild_shapes || []).includes(f) ? "checked" : ""}> ${esc(f)}</label>`).join("")}</div>`;
  }
  if (entries) {
    // only offer what the caster can actually cast at this level (cantrips always)
    const castable = entries.filter((s) => s.level === 0 || s.level <= maxLv);
    const lim = state.preview?.limits || {};
    const note = d.cls === "Wizard"
      ? `(knows ${lim.wizard_cantrips ?? "?"} cantrips, prepares ${lim.wizard_prepared ?? "?"} · up to level ${maxLv})`
      : `(up to spell level ${maxLv})`;
    html += `<div class="lu-block"><b>spells learned this level</b>
      <span class="faint-note">${note}</span><br>
      ${castable.map((s) => `<label class="pick"><input type="checkbox" class="lu-spell"
        value="${esc(s.name)}" ${d.spells?.includes(s.name) ? "checked" : ""}> ${esc(s.name)}
        <span class="splv">${s.level || "c"}</span></label>`).join("")}</div>`;
  }
  html += `<button id="lu-add">⚒ take the level</button>`;
  box.innerHTML = html;

  $("#lu-cls").addEventListener("change", () => { state.levelupDraft = { cls: $("#lu-cls").value }; renderLevelUp(); });
  box.querySelectorAll(".lu-skill").forEach((cb) => cb.addEventListener("change", () => {
    d.skills = [...box.querySelectorAll(".lu-skill:checked")].map((x) => x.value);
  }));
  box.querySelectorAll(".lu-spell").forEach((cb) => cb.addEventListener("change", () => {
    d.spells = [...box.querySelectorAll(".lu-spell:checked")].map((x) => x.value);
  }));
  box.querySelectorAll(".lu-form").forEach((cb) => cb.addEventListener("change", () => {
    state.ch.wild_shapes = [...box.querySelectorAll(".lu-form:checked")].map((x) => x.value);
  }));
  $("#lu-style")?.addEventListener("change", () => { d.style = $("#lu-style").value; });
  $("#lu-sub")?.addEventListener("change", () => {
    d.sub = $("#lu-sub").value;
    renderLevelUp();       // a casting subclass (Eldritch Knight) reveals spell picks
  });
  $("#lu-asi1")?.addEventListener("change", () => { d.asi1 = $("#lu-asi1").value; });
  $("#lu-asi2")?.addEventListener("change", () => { d.asi2 = $("#lu-asi2").value; });
  $("#lu-feat")?.addEventListener("change", () => { d.feat = $("#lu-feat").value; });
  $("#lu-add").addEventListener("click", takeLevel);
}

function takeLevel() {
  const d = state.levelupDraft;
  const lc = (state.preview?.next || {})[d.cls] || {};
  if (state.ch.levels.length >= 20) {
    $("#b-error").textContent = "the pit takes them at 20 levels, no more";
    return;
  }
  if (lc.skill_choices && (d.skills || []).length !== lc.skill_choices) {
    $("#b-error").textContent = `choose exactly ${lc.skill_choices} skills`;
    return;
  }
  $("#b-error").textContent = "";
  const asi = {};
  if (!d.feat) {
    for (const a of [d.asi1, d.asi2]) if (a) asi[a] = (asi[a] || 0) + 1;
  }
  state.ch.levels.push({
    cls: d.cls, hp_roll: null,
    asi, feat: d.feat || "",
    subclass: d.sub || "", fighting_style: d.style || "",
    skills: d.skills || [], spells: d.spells || [],
    at_will: [], signature: [],
  });
  state.levelupDraft = { cls: d.cls };
  refresh();
}

// ----------------------------- step 6: equipment -------------------------------

function renderEquipment() {
  const eq = state.ch.equipment;
  const opt = (list, sel) => `<option value="">—</option>` +
    list.map((n) => `<option ${n === sel ? "selected" : ""}>${esc(n)}</option>`).join("");
  $("#eq-grid").innerHTML = `
    <label>armor <select id="eq-armor">${opt(state.meta.equipment.armors, eq.armor)}</select></label>
    <label>main hand <select id="eq-main">${opt(state.meta.equipment.weapons, eq.main_hand)}</select></label>
    <label>off hand <select id="eq-off">${opt(state.meta.equipment.weapons, eq.off_hand)}</select></label>
    <label class="check"><input type="checkbox" id="eq-shield" ${eq.shield ? "checked" : ""}> shield</label>
    <label class="check"><input type="checkbox" id="eq-2h" ${eq.two_handing ? "checked" : ""}> wield two-handed</label>
    <label>ammo <input type="number" id="eq-ammo" value="${eq.ammo}" min="0" max="99"></label>`;
  const sync = () => {
    Object.assign(state.ch.equipment, {
      armor: $("#eq-armor").value, main_hand: $("#eq-main").value,
      off_hand: $("#eq-off").value, shield: $("#eq-shield").checked,
      two_handing: $("#eq-2h").checked, ammo: Number($("#eq-ammo").value) || 0,
    });
    refresh();
  };
  ["#eq-armor", "#eq-main", "#eq-off", "#eq-shield", "#eq-2h", "#eq-ammo"]
    .forEach((s) => $(s).addEventListener("change", sync));
}

// ------------------------------- the sheet ------------------------------------

function renderSheet() {
  const s = state.preview?.sheet;
  const body = $("#sheet-body");
  if (!s) { body.innerHTML = `<p class="none">choose a race to begin, berk</p>`; return; }
  const abil = Object.entries(s.abilities)
    .map(([a, v]) => `<td><b>${a}</b><br>${v.score} (${signed(v.mod)})</td>`).join("");
  let html = `<h2 class="sheet-name">${esc(s.name || "Nameless")}</h2>
    <p class="meta">${esc(s.race)}${s.background ? ", " + esc(s.background) : ""}
      ${Object.entries(s.classes || {}).map(([c, n]) =>
        `— ${esc((s.subclasses || {})[c] || "")} ${esc(c)} ${n}`).join(" / ")}</p>
    <table class="abilities sheet-abil"><tr>${abil}</tr></table>`;
  if (s.level) {
    html += `<p class="line"><b>AC</b> ${s.ac} · <b>HP</b> ${s.hp} · <b>speed</b> ${s.speed} ft. · <b>prof</b> ${signed(s.prof)}</p>
      <p class="line"><b>Saves</b> ${Object.entries(s.saves).map(([a, b]) =>
        `${a} ${signed(b)}${s.save_profs.includes(a) ? "•" : ""}`).join(", ")}</p>`;
    if (Object.keys(s.skills || {}).length)
      html += `<p class="line"><b>Skills</b> ${Object.entries(s.skills).map(([k, v]) => `${esc(k)} ${signed(v)}`).join(", ")}</p>`;
    if (s.attacks?.length)
      html += `<p class="line"><b>Attacks</b> ${s.attacks.map((a) =>
        `${esc(a.name)} ${signed(a.bonus)} (${esc(a.damage)})`).join(" · ")}</p>`;
    if (Object.keys(s.slots || {}).length)
      html += `<p class="line"><b>Slots</b> ${Object.entries(s.slots).map(([l, n]) => `${l}:${n}`).join(" ")}</p>`;
    if (Object.keys(s.resources || {}).length)
      html += `<p class="line"><b>Resources</b> ${Object.entries(s.resources).map(([k, v]) => `${esc(k)} ×${v}`).join(", ")}</p>`;
    if (s.spells?.length)
      html += `<p class="line"><b>Spellbook</b> ${s.spells.map(esc).join(", ")}</p>`;
    if (s.features?.length)
      html += `<hr class="hair"><p class="line features">${s.features.map(annotate).join(" · ")}</p>`;
  }
  body.innerHTML = html;
}

// ------------------------------ live preview ----------------------------------

let previewTimer = null;

function refresh() {
  renderLevels();
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    if (!state.ch.race) { state.preview = null; renderSheet(); renderLevelUp(); return; }
    const resp = await fetch("/api/builder/preview", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ character: state.ch }),
    });
    state.preview = await resp.json();
    $("#b-warnings").innerHTML = (state.preview.errors || [])
      .map((e) => `<p class="warn">⚠ ${esc(e)}</p>`).join("");
    renderSheet();
    renderLevelUp();
  }, 150);
}

init();
