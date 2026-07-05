/* Bestiary (Slice 12a): roster + classic stat-block render + the Pit Record panel.
   Single-ink figures: identity is carried by SHAPE (open circle = book CR, filled
   dot = playtested CR, bar = consensus) and polarity by DIRECTION + HATCHING,
   never by color. Values are direct-labeled; <title> supplies hover detail. */
"use strict";

const $ = (sel) => document.querySelector(sel);
const state = { all: [], filtered: [], selected: null };
let svgUid = 0; // unique pattern ids per inline SVG

// ---------------------------------------------------------------- utilities

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// 5etools alignment codes -> spelled-out prose (data is kept source-faithful)
const ALIGN_CODES = {
  U: "unaligned", A: "any alignment", N: "true neutral",
  "L NX C NY E": "any non-good alignment",   // Assassin, Cultist, Cult Fanatic, Thug
  "L NX C E": "any evil alignment",          // Lich, Cambion
  "NX C G NY E": "any non-lawful alignment", // Bandit Captain
  "C G NY E": "any chaotic alignment",       // Half-Ogre (Ogrillon)
};
const ALIGN_TOKEN = { L: "lawful", N: "neutral", C: "chaotic", G: "good", E: "evil" };

function alignText(a) {
  if (!a) return "";
  if (ALIGN_CODES[a]) return ALIGN_CODES[a];
  const parts = a.split(" ");
  if (parts.every((t) => ALIGN_TOKEN[t]))
    return parts.map((t) => ALIGN_TOKEN[t]).join(" ");
  return a;                                  // already prose ("chaotic evil", ...)
}

const FRACTIONS = { 0.125: "⅛", 0.25: "¼", 0.5: "½" };
const crText = (cr) => cr == null ? "?" : (FRACTIONS[cr] ?? String(cr));
const mod = (score) => Math.floor((score - 10) / 2);
const signed = (n) => (n >= 0 ? "+" : "") + n;
const ftList = (speeds) => Object.entries(speeds || {})
  .map(([m, ft]) => (m === "walk" ? `${ft} ft.` : `${m} ${ft} ft.`)).join(", ");
const num = (v, dp = 1) => v == null ? "—" : Number(v).toFixed(dp);

// ------------------------------------------------------------- booking slip
// Shared with the Blood Pit via localStorage: booking a creature here fills the
// slip; the Pit reads it into its corners on load (when no permalink names
// teams) and writes its corners back, so both pages see the same booking.

const BOOKING_KEY = "ravel.booking";
const MAX_TEAM = 12;                       // mirrors web/arena.py MAX_TEAM
const cornerName = (t) => (t === "A" ? "Red" : "Black");

function slipRead() {
  let b = null;
  try { b = JSON.parse(localStorage.getItem(BOOKING_KEY) || "null"); } catch { /* torn slip */ }
  const clean = (v) => (Array.isArray(v) ? v.filter((n) => typeof n === "string") : []);
  return { A: clean(b && b.A), B: clean(b && b.B) };
}

function slipBook(corner, name) {
  const slip = slipRead();
  if (slip[corner].length >= MAX_TEAM) return false;
  slip[corner].push(name);
  try { localStorage.setItem(BOOKING_KEY, JSON.stringify(slip)); } catch { return false; }
  renderSlip();
  return true;
}

function renderSlip() {
  const slip = slipRead();
  const el = $("#slip");
  if (!slip.A.length && !slip.B.length) { el.hidden = true; el.innerHTML = ""; return; }
  const bill = (names) => {
    const counts = {};
    names.forEach((n) => { counts[n] = (counts[n] || 0) + 1; });
    return Object.entries(counts)
      .map(([n, c]) => (c > 1 ? `${c} × ${esc(n)}` : esc(n))).join(", ") || "<i>empty</i>";
  };
  el.hidden = false;
  el.innerHTML = `<div class="slip-title hatch">Booking Slip</div>
    <p><b>Red</b> ${bill(slip.A)}</p>
    <p><b>Black</b> ${bill(slip.B)}</p>
    <p class="slip-actions"><a href="/pit">⚔ to the Blood Pit</a>
      <a href="#" id="slip-clear" title="clear both corners">tear it up</a></p>`;
  $("#slip-clear").addEventListener("click", (ev) => {
    ev.preventDefault();
    try { localStorage.removeItem(BOOKING_KEY); } catch { /* nothing to tear */ }
    renderSlip();
  });
}

// ---------------------------------------------------------------- roster

async function boot() {
  state.all = await (await fetch("/api/monsters")).json();
  const types = [...new Set(state.all.map((m) => m.type).filter(Boolean))].sort();
  $("#type").insertAdjacentHTML("beforeend",
    types.map((t) => `<option>${esc(t)}</option>`).join(""));
  const crs = [...new Set(state.all.map((m) => m.cr).filter((c) => c != null))]
    .sort((a, b) => a - b);
  $("#cr").insertAdjacentHTML("beforeend",
    crs.map((c) => `<option value="${c}">CR ${crText(c)}</option>`).join(""));
  const SOURCE_NAMES = { MM: "MM — Monster Manual", Ravel: "Ravel — house constructs" };
  const sources = [...new Set(state.all.map((m) => m.source).filter(Boolean))].sort();
  $("#source").insertAdjacentHTML("beforeend",
    sources.map((s) => `<option value="${esc(s)}">${esc(SOURCE_NAMES[s] || s)}</option>`).join(""));
  ["#q", "#type", "#cr", "#source"].forEach((sel) =>
    $(sel).addEventListener("input", renderList));
  renderList();
  renderSlip();
  const fromHash = decodeURIComponent(location.hash.slice(1));
  if (fromHash && state.all.some((m) => m.name === fromHash)) select(fromHash);
  else showLedger();
  // hash edits in an open tab navigate too (select() re-setting the same hash
  // fires this as well — the state.selected guard makes that a no-op)
  window.addEventListener("hashchange", () => {
    const name = decodeURIComponent(location.hash.slice(1));
    if (name === (state.selected || "")) return;
    if (name && state.all.some((m) => m.name === name)) select(name);
    else if (!name) showLedger();
  });
}

function renderList() {
  const q = $("#q").value.trim().toLowerCase();
  const type = $("#type").value;
  const cr = $("#cr").value;
  const source = $("#source").value;
  state.filtered = state.all.filter((m) =>
    (!q || m.name.toLowerCase().includes(q)) &&
    (!type || m.type === type) &&
    (cr === "" || String(m.cr) === cr) &&
    (!source || m.source === source));
  $("#count").textContent =
    `${state.filtered.length} of ${state.all.length} creatures on the bill`;
  let html = "", band = null;
  for (const m of state.filtered) {
    if (m.cr !== band) {
      band = m.cr;
      html += `<li class="cr-band hatch">Challenge ${crText(band)}</li>`;
    }
    const pit = m.best_cr != null ? `PR ${num(m.best_cr, 2)}` : "";
    html += `<li class="mon${m.name === state.selected ? " selected" : ""}"
      data-name="${esc(m.name)}"><span class="mon-name">${esc(m.name)}</span>
      <span class="delta">${pit}</span>
      <span class="book-btns">
        <a href="#" class="bk" data-corner="A" title="book for the Red corner">R+</a>
        <a href="#" class="bk" data-corner="B" title="book for the Black corner">B+</a>
      </span></li>`;
  }
  $("#list").innerHTML = html || `<li class="cr-band">nothing on the bill</li>`;
  $("#list").querySelectorAll("li.mon").forEach((li) =>
    li.addEventListener("click", () => select(li.dataset.name)));
  $("#list").querySelectorAll("a.bk").forEach((a) =>
    a.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();               // book without opening the entry
      slipBook(a.dataset.corner, a.closest("li").dataset.name);
    }));
}

async function select(name) {
  state.selected = name;
  location.hash = encodeURIComponent(name);
  renderList();
  const d = await (await fetch(`/api/monsters/${encodeURIComponent(name)}`)).json();
  $("#sheet").innerHTML =
    `<p class="backlink"><a href="#" id="back-ledger">← the Ledger (aggregate playtest figures)</a></p>`
    + bookRowHtml() + statblockHtml(d) + pitRecordHtml(d) + rawJsonHtml(d);
  $("#sheet").querySelectorAll(".bookrow button").forEach((btn) =>
    btn.addEventListener("click", () => {
      const ok = slipBook(btn.dataset.corner, name);
      const note = $("#book-note");
      note.textContent = ok
        ? `booked for the ${cornerName(btn.dataset.corner)} corner`
        : `that corner is full (${MAX_TEAM} at most)`;
      clearTimeout(note._t);
      note._t = setTimeout(() => { note.textContent = ""; }, 1800);
    }));
  const fig = $("#sheet .portrait");
  if (fig) {                       // walk the candidate art URLs; give up when exhausted
    const img = fig.querySelector("img");
    let i = 0;
    img.addEventListener("error", () => {
      i += 1;
      if (i < d.images.length) img.src = d.images[i];
      else fig.remove();
    });
  }
  $("#back-ledger").addEventListener("click", (ev) => { ev.preventDefault(); showLedger(); });
}

// ------------------------------------------------------- the Ledger (aggregates)

let ledgerRows = null;

async function showLedger() {
  state.selected = null;
  if (location.hash) history.replaceState(null, "", location.pathname);
  renderList();
  if (ledgerRows === null)
    ledgerRows = await (await fetch("/api/ratings")).json();
  if (!ledgerRows.length) {
    $("#sheet").innerHTML = `<p class="none">No playtest ratings in the book yet —
      run the <i>cr-rate</i> pipeline to fill the Ledger.</p>`;
    return;
  }
  const rated = ledgerRows.filter((r) => r.nominal_cr != null && r.best_cr != null);
  if (!rated.length) {
    $("#sheet").innerHTML = `<p class="none">No usable ratings in the book yet.</p>`;
    return;
  }
  // same quantity everywhere: correction = consensus playtest rating - book CR
  // (matches the scatter's y-axis and the roster's PR annotation)
  const byCorrection = rated
    .map((r) => ({ ...r, corr: r.best_cr - r.nominal_cr }))
    .sort((a, b) => b.corr - a.corr);
  const board = (byCorrection.length <= 20 ? byCorrection
    : [...byCorrection.slice(0, 10), ...byCorrection.slice(-10)])
    .map((r) => ({
      label: esc(r.name), name: r.name, value: r.corr,
      tip: `book CR ${crText(r.nominal_cr)}, playtest rating ${num(r.best_cr)}`,
    }));
  $("#sheet").innerHTML = `<section class="pitrecord ledger">
    <div class="panel-title hatch">The Ledger — every rating in the book</div>
    <div class="panel-body">
      ${figure(scatterSvg(rated),
        "each dot a creature: book CR across, playtest rating up — the hairline is where the book tells true; click a dot to read its entry")}
      ${figure(divergingBars(board, "Largest corrections to the book", 170),
        "largest corrections: underrated creatures pull right, overrated (hatched) pull left — click a name")}
    </div></section>`;
  $("#sheet").querySelectorAll("[data-name]").forEach((el) =>
    el.addEventListener("click", () => select(el.getAttribute("data-name"))));
}

function scatterSvg(rows) {
  const W = 460, H = 330, L = 46, R = 14, T = 12, B = 34;
  const max = Math.ceil(Math.max(...rows.map((r) => Math.max(r.nominal_cr, r.best_cr)))) + 1;
  const x = (cr) => L + cr / max * (W - L - R);
  const y = (cr) => H - B - cr / max * (H - T - B);
  let ticks = "";
  for (let t = 0; t <= max; t += 5) {
    ticks += `<line x1="${x(t)}" y1="${H - B}" x2="${x(t)}" y2="${H - B + 4}" stroke="#211d18"/>
      <text x="${x(t)}" y="${H - B + 16}" font-size="11" text-anchor="middle" class="faint">${t}</text>
      <line x1="${L - 4}" y1="${y(t)}" x2="${L}" y2="${y(t)}" stroke="#211d18"/>
      <text x="${L - 7}" y="${y(t) + 4}" font-size="11" text-anchor="end" class="faint">${t}</text>`;
  }
  const dots = rows.map((r) =>
    `<circle cx="${x(r.nominal_cr)}" cy="${y(r.best_cr)}" r="3.4" fill="#211d18"
       fill-opacity="0.45" data-name="${esc(r.name)}" style="cursor:pointer">
       <title>${esc(r.name)} — book CR ${crText(r.nominal_cr)}, playtest rating ${num(r.best_cr)}</title></circle>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img"
      aria-label="Book CR versus playtest rating, all creatures">
    <line x1="${L}" y1="${H - B}" x2="${W - R}" y2="${H - B}" stroke="#211d18" stroke-width="1.5"/>
    <line x1="${L}" y1="${T}" x2="${L}" y2="${H - B}" stroke="#211d18" stroke-width="1.5"/>
    ${ticks}
    <line x1="${x(0)}" y1="${y(0)}" x2="${x(max)}" y2="${y(max)}" stroke="#a99f8c"
      stroke-dasharray="5 4"><title>book tells true (PR = CR)</title></line>
    ${dots}
    <text x="${(L + W - R) / 2}" y="${H - 2}" font-size="12" text-anchor="middle">CR (book)</text>
    <text x="12" y="${(T + H - B) / 2}" font-size="12" text-anchor="middle"
      transform="rotate(-90 12 ${(T + H - B) / 2})">PR (playtest)</text>
  </svg>`;
}

const bookRowHtml = () => `<div class="bookrow">
  <span class="bookrow-label">book this creature:</span>
  <button type="button" data-corner="A">→ the Red Corner</button>
  <button type="button" data-corner="B">→ the Black Corner</button>
  <span class="book-note" id="book-note"></span></div>`;

// ---------------------------------------------------------------- stat block

function statblockHtml({ statblock: b, images }) {
  const image = (images || [])[0];
  const abil = b.abilities || {};
  const saves = (b.saving_throws || [])
    .map((a) => `${a} ${signed(mod(abil[a] ?? 10) + (b.proficiency_bonus || 0))}`)
    .join(", ");
  const skills = Object.entries(b.skills || {})
    .map(([k, v]) => `${k} ${signed(v)}`).join(", ");
  const senses = Object.entries(b.senses || {})
    .map(([k, v]) => k === "passive_perception"
      ? `passive Perception ${v}` : `${k.replace(/_/g, " ")} ${v} ft.`).join(", ");

  const line = (label, value) =>
    value ? `<p class="line"><b>${label}</b> ${esc(value)}</p>` : "";

  // Imported traits mark their engine-support gaps inline, e.g.
  // "[UNSUPPORTED] ..." / "[APPROXIMATED as a rider] ...". Strip the tag, show a
  // small badge (the bracket's detail becomes its tooltip), and drop a legend below.
  let suppSeen = false;
  const traits = (b.traits || []).map((t) => {
    // two shapes in the data: {name, text} objects and "Name: text" strings
    const [name, text] = typeof t === "string"
      ? (t.includes(": ") ? [t.slice(0, t.indexOf(": ")), t.slice(t.indexOf(": ") + 2)] : ["Trait", t])
      : [t.name || "Trait", t.text || ""];
    const m = /^\s*\[(UNSUPPORTED|APPROXIMATED)([^\]]*)\]\s*/.exec(text);
    let badge = "";
    let body = text;
    if (m) {
      suppSeen = true;
      const gap = m[1] === "UNSUPPORTED";
      const detail = m[2].trim();
      const tip = (gap ? "Not modelled by the engine" : "Approximated by the engine")
        + (detail ? ": " + detail : "") + ".";
      badge = `<sup class="supp supp-${gap ? "gap" : "approx"}" title="${esc(tip)}">${gap ? "!" : "~"}</sup> `;
      body = text.replace(m[0], "");
    }
    return `<p class="entry"><i class="aname">${esc(name)}.</i> ${badge}${esc(body)}</p>`;
  }).join("");
  const suppLegend = suppSeen
    ? `<p class="supp-legend">engine support: <sup class="supp supp-gap">!</sup> not modelled by the engine · <sup class="supp supp-approx">~</sup> approximated</p>`
    : "";

  const multi = (b.multiattack || []).length
    ? `<p class="entry"><i class="aname">Multiattack.</i> ${
        b.multiattack.map((m) => `${m.count} × ${esc(m.name)}`).join(", ")}.</p>`
    : "";

  const actions = (b.actions || []).map((a) => {
    const dmg = (a.damage || []).map((d) => `${d.dice} ${d.type}`).join(" plus ");
    const [rn, rl] = a.range || [];         // schema: "range": [normal, long]
    const range = a.kind === "melee"
      ? `reach ${a.reach || 5} ft.`
      : `range ${rn ?? "?"}${rl ? "/" + rl : ""} ft.`;
    const rider = a.rider
      ? ` DC ${a.rider.dc} ${esc(a.rider.ability)} save or ${esc(a.rider.on_fail_condition || "suffer its rider")}.`
      : "";
    return `<p class="entry"><i class="aname">${esc(a.name)}.</i> <i>${
      a.kind === "melee" ? "Melee" : "Ranged"} attack:</i> ${signed(a.attack_bonus ?? 0)} to hit, ${range} <i>Hit:</i> ${esc(dmg) || "—"}.${rider}</p>`;
  }).join("");

  const areas = (b.areas || []).map((ar) => {
    const dmg = (ar.damage || []).map((d) => `${d.dice} ${d.type}`).join(" plus ");
    const recharge = ar.recharge && ar.recharge !== "at-will"
      ? ` (Recharge ${esc(ar.recharge)})` : "";
    const save = ar.save ? `DC ${ar.dc} ${esc(ar.save)} save${ar.half_on_save ? ", half on save" : ""}` : "";
    return `<p class="entry"><i class="aname">${esc(ar.name)}${recharge}.</i> ${
      ar.size}-ft. ${esc(ar.shape)}; ${save}${dmg ? `; ${esc(dmg)}` : ""}.</p>`;
  }).join("");

  const leg = b.legendary ? `
    <h3>Legendary</h3>
    ${b.legendary.resistance ? `<p class="entry"><i class="aname">Legendary Resistance (${b.legendary.resistance}/day).</i></p>` : ""}
    ${b.legendary.actions ? `<p class="entry"><i class="aname">Legendary Actions (${b.legendary.actions}/round).</i> ${esc(b.legendary.attack || "")}${b.legendary.wing ? `; ${esc(b.legendary.wing.name)} (costs 2)` : ""}.</p>` : ""}` : "";

  const slots = Object.entries(b.spellcasting?.slots || {});
  const knownSpells = b.spellcasting?.spells || [];
  const innate = Object.entries(b.spellcasting?.innate || {});
  const sc = b.spellcasting ? `
    <h3>Spellcasting</h3>
    <p class="entry">(${esc(b.spellcasting.ability)}, save DC ${b.spellcasting.save_dc}${b.spellcasting.attack_bonus ? `, ${signed(b.spellcasting.attack_bonus)} to hit` : ""}, caster level ${b.spellcasting.caster_level}).
    ${slots.length ? "Slots: " + slots.map(([l, n]) => `${l}⁄${n}`).join(", ") + "." : ""}
    ${knownSpells.length ? "Spells: " + knownSpells.map(esc).join(", ") + "." : ""}
    ${innate.length ? "Innate: " + innate.map(([s, n]) => `${esc(s)} ${n}/day`).join(", ") + "." : ""}</p>` : "";

  const FLAG_KEYS = ["traits_flags", "pounce", "frightful_presence", "regeneration",
    "death_burst", "incorporeal", "swallow", "teleport", "reckless", "parry",
    "magic_resistance", "resist_nonmagical_physical", "eye_rays", "bonus_damage",
    "lair_action", "triggered_abilities", "strategy"];
  const flags = FLAG_KEYS.filter((k) => b[k] !== undefined &&
    (Array.isArray(b[k]) ? b[k].length : b[k]))
    .map((k) => Array.isArray(b[k]) && typeof b[k][0] === "string"
      ? b[k].join(", ") : k);               // string arrays (traits_flags) show members
  const notes = flags.length
    ? `<p class="engine-notes">Engine features: ${flags.map(esc).join(", ")} &mdash; full detail in the raw JSON below.</p>`
    : "";

  return `<article class="statblock">
    ${image ? `<figure class="portrait"><img src="${esc(image)}" alt="${esc(b.name)}"></figure>` : ""}
    <h2>${esc(b.name)}</h2>
    <p class="meta">${esc(b.size || "")} ${esc(b.type || "")}${alignText(b.alignment) ? ", " + esc(alignText(b.alignment)) : ""}</p>
    <hr class="rule">
    ${line("Armor Class", b.ac)}
    ${line("Hit Points", b.hp + (b.hit_dice ? ` (${b.hit_dice})` : ""))}
    ${line("Speed", ftList(b.speeds))}
    <table class="abilities"><tr>${Object.keys(abil).map((a) => `<th>${a}</th>`).join("")}</tr>
      <tr>${Object.values(abil).map((v) => `<td>${v} (${signed(mod(v))})</td>`).join("")}</tr></table>
    ${line("Saving Throws", saves)}
    ${line("Skills", skills)}
    ${line("Vulnerabilities", (b.damage_vulnerabilities || []).join(", "))}
    ${line("Resistances", (b.damage_resistances || []).join(", "))}
    ${line("Immunities", (b.damage_immunities || []).join(", "))}
    ${line("Condition Immunities", (b.condition_immunities || []).join(", "))}
    ${line("Senses", senses)}
    ${line("Languages", (b.languages || []).join(", "))}
    ${line("Challenge", crText(b.cr) + `  (proficiency ${signed(b.proficiency_bonus || 0)})`)}
    <hr class="rule">
    ${traits}
    ${(multi || actions || areas) ? "<h3>Actions</h3>" : ""}
    ${multi}${actions}${areas}
    ${leg}${sc}${notes}
    ${suppLegend}
  </article>`;
}

// ---------------------------------------------------------------- Pit Record

function pitRecordHtml({ statblock: b, rating: r, env }) {
  if (!r || r.adjusted_cr == null) {
    return `<section class="pitrecord"><div class="panel-title hatch">Pit Record</div>
      <div class="panel-body"><p class="none">This creature has not yet fought for its
      rating. Run the <i>cr-rate</i> pipeline to enter it in the book.</p></div></section>`;
  }
  const figures = [
    figure(crLineSvg(r), `○ CR ${crText(r.nominal_cr)} (book) · ● PR ${num(r.adjusted_cr, 2)} (playtest; 80% CI ${num(r.ci_lo)}–${num(r.ci_hi)})${r.refined_cr != null ? ` · ▏ consensus ${num(r.refined_cr, 2)} (mirror + round-robin agreement)` : ""}${flagNote(r.flag)}`),
    figure(signalBarsSvg(r), "advisory signals, in CR points — hover a bar or its label for how each is measured"),
  ];
  const comps = Object.entries(r.per_composition || {});
  if (comps.length > 1) figures.push(
    figure(compStripSvg(comps),
      "adjusted CR re-measured per enemy squad size: the y-value is the CR-equivalent of the"
      + " largest equal-XP enemy squad this creature fights to a coin flip when that squad is"
      + " fielded as 1, 3, or 6 bodies — a falling line means crowds (action economy) wear it down,"
      + " a rising line means it handles many weak foes better than one strong one"));
  const terrain = (env || []).filter((e) => e.environment !== "open");  // open = baseline
  figures.push(terrain.length
    ? figure(envBarsSvg(terrain), "playtest-rating shift by terrain, vs the open pit floor")
    : `<div class="figure"><p class="none">Terrain trials not yet run for this creature.</p></div>`);
  return `<section class="pitrecord"><div class="panel-title hatch">Pit Record</div>
    <div class="panel-body">${figures.join(`<hr class="hair">`)}</div></section>`;
}

// mirror-probe caveats: 'ok' is clean (hidden); 'left'/'right' mean the tie-point
// fell off the probe ladder, so the rating is only a bound
function flagNote(f) {
  if (!f || f === "ok") return "";
  if (f.includes("left"))
    return ` · ⚠ PR is an upper bound${f.includes("/") ? " in some compositions" : ""} (lost even against the smallest squads probed)`;
  if (f.includes("right"))
    return ` · ⚠ PR is a lower bound${f.includes("/") ? " in some compositions" : ""} (still winning at the top of the probe ladder)`;
  return ` · flag: ${esc(f)}`;
}

const figure = (svg, cap) =>
  `<div class="figure">${svg}<div class="cap">${cap}</div></div>`;

function hatchDef(id) {
  return `<defs><pattern id="${id}" width="5" height="5" patternUnits="userSpaceOnUse"
    patternTransform="rotate(45)"><rect width="5" height="5" fill="none"/>
    <line x1="0" y1="0" x2="0" y2="5" stroke="#211d18" stroke-width="1.4"/></pattern></defs>`;
}

// The CR number line: book (open circle) vs playtested (filled dot + CI whiskers),
// consensus as a short vertical bar. One shared scale; shape carries identity.
function crLineSvg(r) {
  const W = 460, H = 74, L = 40, R = 40, axisY = 50, markY = 30;
  const hi = Math.max(r.nominal_cr ?? 0, r.ci_hi ?? 0, r.adjusted_cr ?? 0, r.refined_cr ?? 0, 1);
  const max = Math.ceil(hi) + 1;
  const x = (cr) => L + (cr / max) * (W - L - R);
  const step = max > 24 ? 5 : max > 12 ? 2 : 1;
  let ticks = "";
  for (let t = 0; t <= max; t += step) {
    ticks += `<line x1="${x(t)}" y1="${axisY - 3}" x2="${x(t)}" y2="${axisY + 3}" stroke="#211d18"/>
      <text x="${x(t)}" y="${axisY + 16}" font-size="11" text-anchor="middle" class="faint">${crText(t) === "0" ? 0 : t % 1 ? "" : t}</text>`;
  }
  const bx = x(r.nominal_cr ?? 0), px = x(r.adjusted_cr);
  const stagger = Math.abs(bx - px) < 46;                 // dodge label collision
  const bookLabelY = stagger ? 10 : 16;
  const pitLabelY = stagger ? 23 : 16;
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img"
      aria-label="Book CR ${crText(r.nominal_cr)} versus playtest rating ${num(r.adjusted_cr)}">
    <line x1="${L}" y1="${axisY}" x2="${W - R}" y2="${axisY}" stroke="#211d18" stroke-width="1.5"/>
    ${ticks}
    <line x1="${Math.min(bx, px)}" y1="${markY}" x2="${Math.max(bx, px)}" y2="${markY}"
      stroke="#a99f8c" stroke-width="1.5"/>
    <line x1="${x(r.ci_lo ?? r.adjusted_cr)}" y1="${markY}" x2="${x(r.ci_hi ?? r.adjusted_cr)}" y2="${markY}"
      stroke="#211d18" stroke-width="2"><title>80% CI ${num(r.ci_lo)}–${num(r.ci_hi)}</title></line>
    <line x1="${x(r.ci_lo ?? r.adjusted_cr)}" y1="${markY - 5}" x2="${x(r.ci_lo ?? r.adjusted_cr)}" y2="${markY + 5}" stroke="#211d18" stroke-width="2"/>
    <line x1="${x(r.ci_hi ?? r.adjusted_cr)}" y1="${markY - 5}" x2="${x(r.ci_hi ?? r.adjusted_cr)}" y2="${markY + 5}" stroke="#211d18" stroke-width="2"/>
    ${r.refined_cr != null ? `<line x1="${x(r.refined_cr)}" y1="${markY - 9}" x2="${x(r.refined_cr)}" y2="${markY + 9}" stroke="#211d18" stroke-width="3"><title>consensus (mirror + Bradley-Terry round-robin) ${num(r.refined_cr, 2)}</title></line>` : ""}
    <circle cx="${bx}" cy="${markY}" r="6" fill="#f4efe2" stroke="#211d18" stroke-width="2">
      <title>book CR ${crText(r.nominal_cr)}</title></circle>
    <circle cx="${px}" cy="${markY}" r="5.5" fill="#211d18">
      <title>playtest rating ${num(r.adjusted_cr, 2)}</title></circle>
    <text x="${bx}" y="${bookLabelY}" font-size="12" text-anchor="middle">CR ${crText(r.nominal_cr)}</text>
    <text x="${px}" y="${pitLabelY}" font-size="12" text-anchor="middle"
      font-weight="bold">PR ${num(r.adjusted_cr, 2)}</text>
  </svg>`;
}

// Diverging single-ink bars: direction + hatching encode sign; value is labeled.
function divergingBars(rows, ariaLabel, labelW = 150) {
  const W = 460, rowH = 22, pad = 8;
  const shown = rows.filter((r) => r.value != null);
  const missing = rows.filter((r) => r.value == null);
  if (!shown.length) return `<p class="none">no signals measured</p>`;
  const H = shown.length * rowH + 12;
  const span = Math.max(1, ...shown.map((r) => Math.abs(r.value)));
  const zero = labelW + (W - labelW - pad) / 2;
  const halfW = (W - labelW - pad) / 2 - 44;   // reserve room for the value labels
  const pid = `hatch${++svgUid}`;
  let g = "";
  shown.forEach((r, i) => {
    const y = 8 + i * rowH, h = 11;
    const w = Math.max(1.5, Math.abs(r.value) / span * halfW);
    const neg = r.value < 0;
    const click = r.name
      ? ` data-name="${esc(r.name)}" style="cursor:pointer"`
      : ` style="cursor:help"`;                 // hover reveals how it's measured
    g += `<text x="${labelW - 6}" y="${y + h - 1}" font-size="12" text-anchor="end"${click}>${r.label}<title>${r.tip}</title></text>
      <rect x="${neg ? zero - w : zero}" y="${y}" width="${w}" height="${h}"
        fill="${neg ? `url(#${pid})` : "#211d18"}" stroke="#211d18" stroke-width="1"${click}>
        <title>${r.label}: ${signed(Number(r.value.toFixed(2)))} CR — ${r.tip}</title></rect>
      <text x="${neg ? zero - w - 5 : zero + w + 5}" y="${y + h - 1}" font-size="11"
        text-anchor="${neg ? "end" : "start"}" class="faint">${signed(Number(r.value.toFixed(2)))}</text>`;
  });
  const H2 = H + (missing.length ? 14 : 0);
  return `<svg viewBox="0 0 ${W} ${H2}" width="100%" role="img" aria-label="${ariaLabel}">
    ${hatchDef(pid)}
    <line x1="${zero}" y1="4" x2="${zero}" y2="${H - 4}" stroke="#a99f8c"/>
    ${g}
    ${missing.length ? `<text x="${labelW - 6}" y="${H2 - 4}" font-size="11" text-anchor="end" class="faint" font-style="italic">not measured: ${missing.map((m) => m.label).join(", ")}</text>` : ""}
  </svg>`;
}

function signalBarsSvg(r) {
  return divergingBars([
    { label: "CR correction", value: r.residual,
      tip: "playtest rating (PR) minus book CR — how far the book misses:"
        + " positive means the book undersells this creature" },
    { label: "ally synergy", value: r.group_synergy,
      tip: "per-creature rating when FOUR copies fight side by side, minus its rating alone"
        + " (the pack's tie budget is split per head before converting to CR) —"
        + " positive means it wants friends (pack tactics, auras, action-economy gains)" },
    { label: "composition sensitivity", value: r.composition_spread,
      tip: "rating measured against ONE strong foe minus the rating against SIX weaker foes"
        + " of the same total XP — positive means it prefers duels,"
        + " negative means it prefers crowds" },
    { label: "skill ceiling", value: r.skill_ceiling_delta,
      tip: "rating when the Oracle (LLM) picks its actions minus rating under the house"
        + " heuristic, on paired seeds — positive means the heuristic underplays it"
        + " (casters, nova and breath monsters)" },
    { label: "matchup variance", value: r.bt_disagreement,
      tip: "the mirror ladder's rating minus the Bradley-Terry rating fitted from a"
        + " round-robin against its CR-neighbors — a big gap either way means its"
        + " strength depends heavily on WHO it fights" },
  ], "Advisory rating signals");
}

function envBarsSvg(env) {
  return divergingBars(env.map((e) => ({
    label: esc(e.environment), value: e.delta,
    tip: `fights at CR ${num(e.env_cr)} here${e.flag ? ` (${esc(e.flag)})` : ""}`,
  })), "Per-environment CR shift");
}

// Dot strip: playtested CR against N-body opposing squads, direct-labeled.
function compStripSvg(comps) {
  const W = 460, H = 76, L = 46, R = 46, topY = 22, botY = 56;
  const pts = comps.map(([k, v]) => [Number(k), Number(v)]).sort((a, b) => a[0] - b[0]);
  const vals = pts.map((p) => p[1]);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const x = (i) => L + i * (W - L - R) / Math.max(1, pts.length - 1);
  const y = (v) => hi === lo ? (topY + botY) / 2 : botY - (v - lo) / (hi - lo) * (botY - topY);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p[1])}`).join(" ");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img"
      aria-label="Playtest rating by opposing squad size">
    <path d="${path}" fill="none" stroke="#a99f8c" stroke-width="1.5"/>
    ${pts.map((p, i) => `
      <circle cx="${x(i)}" cy="${y(p[1])}" r="5" fill="#211d18">
        <title>vs ${p[0]} ${p[0] === 1 ? "creature" : "creatures"}: PR ${num(p[1])}</title></circle>
      <text x="${x(i)}" y="${y(p[1]) - 9}" font-size="11" text-anchor="middle">${num(p[1])}</text>
      <text x="${x(i)}" y="${H - 4}" font-size="11" text-anchor="middle" class="faint">${p[0]} ${p[0] === 1 ? "creature" : "creatures"}</text>`).join("")}
  </svg>`;
}

// ---------------------------------------------------------------- raw JSON

function rawJsonHtml({ statblock }) {
  return `<details class="rawjson"><summary>Raw stat block (as read from data/monsters/)</summary>
    <pre>${esc(JSON.stringify(statblock, null, 2))}</pre></details>`;
}

if (typeof document !== "undefined") boot();      // browser entry
if (typeof module !== "undefined")                 // node render-smoke (tests/render_smoke.js)
  module.exports = { statblockHtml, pitRecordHtml, rawJsonHtml, crText };
