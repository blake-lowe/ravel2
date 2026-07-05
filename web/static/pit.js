/* The Blood Pit (Slice 12b): book a match, replay it blow by blow, or run the
   gauntlet across many seeds. The replay itself (board, event fold, scrubber,
   initiative, animations) lives in replay.js — shared with the Supertemporal
   Arena; this file is the page: booking form, fight card, gauntlet, permalinks.
   Blood red is THIS page's accent: damage, the gong, team B's corner. */
"use strict";

// Under node, re-export the pure fold from replay.js so
// tests/pit_replay_smoke.js keeps proving the fold against the engine.
if (typeof document === "undefined") {
  module.exports = require("./replay.js");
} else {
  boot();
}

// ============================== page wiring ==================================

function boot() {

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const INK = "#211d18", BLOOD = "#7c1a15";

// Corners are Red (engine team "A") and Black (engine team "B"). The engine's
// combatant ids are A1/B2…; the replay shows R1/B2 instead (corners config).
const cornerName = (team) => (team === "A" ? "Red" : "Black");

const state = {
  meta: null,
  teams: { A: [], B: [] },
  lairs: new Set(),      // creature names fighting in THEIR lair (lair actions on)
  es: null,              // gauntlet EventSource
};

const replay = RavelReplay.create({
  els: {
    board: $("#board"), scrub: $("#scrub"), btnPlay: $("#btn-play"),
    btnPrev: $("#btn-prev"), btnNext: $("#btn-next"), btnStart: $("#btn-start"),
    btnEnd: $("#btn-end"), btnPrevRound: $("#btn-prev-round"),
    btnNextRound: $("#btn-next-round"), speed: $("#speed"),
    roundInd: $("#round-ind"), log: $("#fightlog"), initiative: $("#initiative"),
    legend: $("#legend"), lightLegend: $("#light-legend"),
    lightingToggle: $("#cfg-lighting"),
  },
  corners: { A: { name: "Red", color: BLOOD, prefix: "R" },
             B: { name: "Black", color: INK, prefix: "B" } },
  onPosition: (atEnd, winner) => {
    const verdict = $("#fc-verdict");
    if (!verdict) return;
    if (atEnd) {
      verdict.innerHTML = winner
        ? `⚑ the ${cornerName(winner)} corner stands — the rest go in the dead-book`
        : "⚑ a draw — the crowd spits";
      verdict.classList.add("shown");
    } else {
      verdict.textContent = "";
      verdict.classList.remove("shown");
    }
  },
});

// ----------------------------- booking form ---------------------------------

async function init() {
  state.meta = await (await fetch("/api/arena-meta")).json();
  $("#roster-list").innerHTML = state.meta.roster
    .map((r) => `<option value="${esc(r.name)}">`).join("");
  $("#cfg-map").insertAdjacentHTML("beforeend", state.meta.maps
    .map((m) => `<option value="${esc(m)}">${esc(m.replace(/_/g, " "))}</option>`).join(""));
  $("#cfg-weather").innerHTML = state.meta.weathers
    .map((w) => `<option>${esc(w)}</option>`).join("");
  $("#cfg-ai").innerHTML = state.meta.ais.map((k) => `<option value="${esc(k)}">${
    { heuristic: "house heuristics", random: "drunken chance",
      greedy: "the bookmaker (greedy EV) both corners",
      greedy_vs_heuristic: "bookmaker (Red) vs house (Black)",
      llm: "the Oracle (LLM) both corners", llm_vs_heuristic: "Oracle (A) vs house (B)" }[k] || esc(k)
  }</option>`).join("");

  for (const team of ["A", "B"]) {
    const box = document.getElementById(`team-${team}`);
    const input = box.querySelector(".team-input");
    const add = () => {
      const name = input.value.trim();
      if (!name || !state.meta.roster.some((r) => r.name === name)) return;
      if (state.teams[team].length >= state.meta.max_team) return;
      state.teams[team].push(name);
      input.value = "";
      renderTeams();
    };
    box.querySelector(".team-add-btn").addEventListener("click", add);
    input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") add(); });
  }
  $("#gong").addEventListener("click", () => fight());
  $("#copy-link").addEventListener("click", copyPermalink);
  $("#g-run").addEventListener("click", runGauntlet);
  readPermalink();
}

const rosterOf = (name) => state.meta.roster.find((r) => r.name === name) || {};
const xpOf = (name) => rosterOf(name).xp || 0;
const teamXp = (t) => state.teams[t].reduce((s, n) => s + xpOf(n), 0);
const hasLair = (name) => !!rosterOf(name).has_lair;
const FRACTIONS = { 0.125: "⅛", 0.25: "¼", 0.5: "½" };
const crText = (cr) => cr == null ? "—" : (FRACTIONS[cr] ?? String(cr));

// The booking slip is shared with the Bestiary via localStorage: its "book for
// the Red/Black corner" buttons fill the slip, the Pit reads it into the corners
// when no permalink names teams, and writes the corners back on every change.
const BOOKING_KEY = "ravel.booking";

function readBookingSlip() {
  let b = null;
  try { b = JSON.parse(localStorage.getItem(BOOKING_KEY) || "null"); } catch { /* torn slip */ }
  if (!b) return null;
  const known = new Set(state.meta.roster.map((r) => r.name));
  const clean = (v) => (Array.isArray(v) ? v.filter((n) => known.has(n)).slice(0, state.meta.max_team) : []);
  const slip = { A: clean(b.A), B: clean(b.B) };
  return slip.A.length || slip.B.length ? slip : null;
}

function writeBookingSlip() {
  try { localStorage.setItem(BOOKING_KEY, JSON.stringify({ A: state.teams.A, B: state.teams.B })); }
  catch { /* private mode etc. — the slip is only a convenience */ }
}

function renderTeams() {
  // lair toggles only make sense for creatures actually booked
  const inPlay = new Set([...state.teams.A, ...state.teams.B]);
  for (const name of [...state.lairs]) if (!inPlay.has(name)) state.lairs.delete(name);

  for (const team of ["A", "B"]) {
    const box = document.getElementById(`team-${team}`);
    const names = state.teams[team];
    const rows = names.map((n, i) => {
      const r = rosterOf(n);
      // the lair toggle applies per creature name — show it once, on the first copy
      const lair = hasLair(n) && names.indexOf(n) === i
        ? ` <label class="chip-lair" title="a monster only takes lair actions at home — tick to fight in ITS lair">
            <input type="checkbox" class="chip-lair-box" data-name="${esc(n)}"
              ${state.lairs.has(n) ? "checked" : ""}> in its lair</label>` : "";
      return `<tr>
        <td class="tt-name">${esc(n)}${lair}</td>
        <td class="tt-num">${crText(r.cr)}</td>
        <td class="tt-num">${r.best_cr != null ? Number(r.best_cr).toFixed(2) : "—"}</td>
        <td class="tt-num">${r.xp ? Math.round(r.xp).toLocaleString() : "—"}</td>
        <td class="tt-btns"><span class="chip-btns">
          <a href="#" class="chip-plus" data-team="${team}" data-idx="${i}" title="one more">+</a>
          <a href="#" class="chip-minus" data-team="${team}" data-idx="${i}" title="strike from the bill">−</a>
        </span></td></tr>`;
    }).join("");
    box.querySelector(".team-roster").innerHTML = names.length
      ? `<table class="team-table">
          <thead><tr><th>combatant</th><th class="tt-num">CR</th>
            <th class="tt-num" title="playtest rating — how it actually fights in the pit">PR</th>
            <th class="tt-num">XP</th><th></th></tr></thead>
          <tbody>${rows}</tbody></table>`
      : "";
    const xp = teamXp(team);
    box.querySelector(".team-xp").textContent = names.length
      ? `worth ${Math.round(xp).toLocaleString()} XP by the touts' book` : "";
  }
  document.querySelectorAll(".chip-minus, .chip-plus").forEach((btn) =>
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      const { team, idx } = ev.currentTarget.dataset;
      const i = Number(idx);
      if (ev.currentTarget.classList.contains("chip-plus")) {
        if (state.teams[team].length < state.meta.max_team)
          state.teams[team].splice(i + 1, 0, state.teams[team][i]);
      } else {
        state.teams[team].splice(i, 1);
      }
      renderTeams();
    }));
  document.querySelectorAll(".chip-lair-box").forEach((cb) =>
    cb.addEventListener("change", () => {
      if (cb.checked) state.lairs.add(cb.dataset.name);
      else state.lairs.delete(cb.dataset.name);
    }));
  writeBookingSlip();
  const xa = teamXp("A"), xb = teamXp("B");
  $("#odds-line").textContent = (xa && xb)
    ? (Math.abs(xa - xb) < 1 ? "the touts call it even money"
       : `the touts favor the ${xa > xb ? "Red" : "Black"} corner (${Math.round(Math.max(xa, xb) / Math.min(xa, xb) * 10) / 10}:1 by XP)`)
    : "";
}

function configQuery(extra = {}) {
  const q = new URLSearchParams({
    a: state.teams.A.join(","), b: state.teams.B.join(","),
    seed: $("#cfg-seed").value || "1",
    ai: $("#cfg-ai").value, map: $("#cfg-map").value,
    weather: $("#cfg-weather").value, surprised: $("#cfg-surprised").value,
  });
  if ($("#cfg-underwater").checked) q.set("underwater", "true");
  if ($("#cfg-flanking").checked) q.set("flanking", "true");
  if ($("#cfg-avg-hp").checked) q.set("avg_hp", "true");
  if (state.lairs.size) q.set("lair", [...state.lairs].join(","));
  for (const [k, v] of Object.entries(extra)) q.set(k, v);
  return q;
}

function readPermalink() {
  const q = new URLSearchParams(location.search);
  if (q.get("a")) state.teams.A = q.get("a").split(",").filter(Boolean);
  if (q.get("b")) state.teams.B = q.get("b").split(",").filter(Boolean);
  if (!q.get("a") && !q.get("b")) {
    // no corners in the URL — pick up the Bestiary's booking slip instead
    const slip = readBookingSlip();
    if (slip) state.teams = { A: slip.A, B: slip.B };
  }
  if (q.get("seed")) $("#cfg-seed").value = q.get("seed");
  if (q.get("map")) $("#cfg-map").value = q.get("map");
  if (q.get("weather")) $("#cfg-weather").value = q.get("weather");
  if (q.get("ai")) $("#cfg-ai").value = q.get("ai");
  if (q.get("surprised")) $("#cfg-surprised").value = q.get("surprised");
  $("#cfg-underwater").checked = q.get("underwater") === "true";
  $("#cfg-flanking").checked = q.get("flanking") === "true";
  $("#cfg-avg-hp").checked = q.get("avg_hp") === "true";
  state.lairs = new Set((q.get("lair") || "").split(",").filter(Boolean));
  renderTeams();
  if (q.get("a") && q.get("b")) fight(false);
}

function copyPermalink() {
  const url = `${location.origin}/pit?${configQuery()}`;
  navigator.clipboard?.writeText(url);
  $("#copy-link").textContent = "copied!";
  setTimeout(() => { $("#copy-link").textContent = "copy permalink"; }, 1200);
}

// ------------------------------- the bout -----------------------------------

async function fight(push = true) {
  $("#error").textContent = "";
  if (!state.teams.A.length || !state.teams.B.length) {
    $("#error").textContent = "both corners need at least one combatant, berk";
    return;
  }
  if (push) history.pushState(null, "", `/pit?${configQuery()}`);
  if ($("#cfg-ai").value.includes("llm")) { fightStreamed(); return; }
  $("#gong").disabled = true;
  $("#gong").textContent = "⚔ the crowd roars… ⚔";
  try {
    const resp = await fetch(`/api/battle?${configQuery()}`);
    if (!resp.ok) {
      const detail = (await resp.json()).detail || resp.statusText;
      $("#error").textContent = detail;
      return;
    }
    loadBattle(await resp.json());
  } finally {
    $("#gong").disabled = false;
    $("#gong").textContent = "⚔ Fight ⚔";
  }
}

// LLM bouts are slow (one model call per decision) — stream them, showing the
// live round + decision count beside the button while the crowd roars.
function fightStreamed() {
  $("#gong").disabled = true;
  $("#gong").textContent = "⚔ the crowd roars… ⚔";
  const status = $("#llm-status");
  status.hidden = false;
  status.textContent = "the Oracle takes its corner…";
  const es = new EventSource(`/api/battle-stream?${configQuery()}`);
  const finish = () => {
    es.close();
    status.hidden = true;
    $("#gong").disabled = false;
    $("#gong").textContent = "⚔ Fight ⚔";
  };
  es.onmessage = (m) => {
    const d = JSON.parse(m.data);
    status.textContent = d.round
      ? `round ${d.round} · decision ${d.decisions}`
      : "the combatants enter…";
  };
  es.addEventListener("done", (m) => {
    const payload = JSON.parse(m.data);
    finish();
    loadBattle(payload);
  });
  es.addEventListener("error", (m) => {
    $("#error").textContent = m.data
      ? JSON.parse(m.data).error
      : "the stream broke — check the booking and the server";
    finish();
  });
}

function loadBattle(b) {
  $("#arena-wrap").hidden = false;
  renderFightCard(b);          // before replay.load: the verdict slot must exist
  replay.load(b);
  $("#arena-wrap").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderFightCard(b) {
  const bill = (t) => {
    const counts = {};
    b.config[t.toLowerCase()].split(",").forEach((n) => { counts[n] = (counts[n] || 0) + 1; });
    return Object.entries(counts).map(([n, c]) => (c > 1 ? `${c} × ${esc(n)}` : esc(n))).join(", ");
  };
  const ground = b.config.map ? b.config.map.replace(/_/g, " ") : "the open pit floor";
  const mods = [b.config.weather !== "clear" ? b.config.weather : "",
                b.config.underwater ? "underwater" : "",
                b.config.flanking ? "flanking" : "",
                b.config.surprised ? `${b.config.surprised === "B" ? "Red" : "Black"} ambushes` : "",
                b.config.lair ? `in the lair of: ${esc(b.config.lair)}` : ""]
    .filter(Boolean).join(" · ");
  $("#fightcard").innerHTML = `
    <div class="fc-team fc-a">${bill("A")}</div>
    <div class="fc-mid">
      <div class="fc-vs">VS</div>
      <div class="fc-ground">${esc(ground)}${mods ? " · " + esc(mods) : ""} · seed ${b.config.seed}</div>
      <div class="fc-odds">${esc(b.odds.line)}</div>
      <div class="fc-verdict" id="fc-verdict"></div>
    </div>
    <div class="fc-team fc-b">${bill("B")}</div>`;
}

// ------------------------------ the gauntlet --------------------------------

function runGauntlet() {
  if (!state.teams.A.length || !state.teams.B.length) {
    $("#error").textContent = "book both corners first, berk";
    return;
  }
  const ai = $("#cfg-ai").value;
  const n = Number($("#g-n").value) || 50;
  if (ai.includes("llm") &&
      !confirm(`${n} Oracle bouts will take a LONG while. The pit stays open all night. Proceed?`))
    return;
  state.es?.close();
  const rows = [];
  $("#g-results").innerHTML = "";
  $("#g-progress").textContent = "the gate lifts…";
  const q = configQuery({ n: String(n), seed0: $("#g-seed0").value || "1" });
  const es = state.es = new EventSource(`/api/gauntlet?${q}`);
  es.onmessage = (m) => {
    const d = JSON.parse(m.data);
    rows.push(d);
    $("#g-progress").textContent = `bout ${d.i} of ${d.n}…`;
  };
  // LLM bouts stream mid-bout ticks so the pit is never silent for minutes
  es.addEventListener("tick", (m) => {
    const d = JSON.parse(m.data);
    $("#g-progress").textContent = d.round
      ? `bout ${d.i} of ${d.n} — round ${d.round} · decision ${d.decisions}…`
      : `bout ${d.i} of ${d.n} — the combatants enter…`;
  });
  es.addEventListener("error", (m) => {
    $("#g-progress").textContent = m.data
      ? "the gauntlet halted: " + JSON.parse(m.data).error
      : "the gate jammed — check the booking (unknown name? corner too crowded?)";
    es.close();
  });
  es.addEventListener("done", (m) => {
    es.close();
    $("#g-progress").textContent = "";
    renderGauntlet(JSON.parse(m.data), rows);
  });
}

function renderGauntlet(sum, rows) {
  const pct = (x) => Math.round(x * 100);
  const hist = {};
  sum.rounds.forEach((r) => { hist[r] = (hist[r] || 0) + 1; });
  const hMax = Math.max(...Object.values(hist));
  const bars = Object.keys(hist).map(Number).sort((a, b) => a - b).map((r) =>
    `<div class="hist-col" title="${hist[r]} bouts ended in round ${r}">
       <div class="hist-bar" style="height:${Math.round(hist[r] / hMax * 60)}px"></div>
       <div class="hist-x">${r}</div></div>`).join("");
  const seedRows = rows.map((d) => `
    <tr class="seed-row" data-seed="${d.seed}">
      <td>${d.seed}</td><td class="w-${(d.winner || "draw").toLowerCase()}">${d.winner ? cornerName(d.winner) : "draw"}</td>
      <td>${d.rounds}</td><td>${pct(d.hp_frac)}% left</td><td class="replay-link">⟲ replay</td>
    </tr>`).join("");
  $("#g-results").innerHTML = `
    <p class="g-verdict">Across ${sum.n} bouts: <b>the Red corner took ${sum.wins_a}</b>
      (${pct(sum.win_rate_a)}%, CI ${pct(sum.ci_a[0])}–${pct(sum.ci_a[1])}%),
      the Black corner ${sum.wins_b}${sum.draws ? `, ${sum.draws} draws` : ""} ·
      bouts last ${sum.avg_rounds} rounds on average</p>
    <div class="hist">${bars}</div>
    <p class="faint-note">every seed replays identically — click one to watch that exact bout</p>
    <table class="seed-table"><tr><th>seed</th><th>victor</th><th>rounds</th><th>victors' life</th><th></th></tr>
      ${seedRows}</table>`;
  document.querySelectorAll(".seed-row").forEach((tr) => tr.addEventListener("click", () => {
    $("#cfg-seed").value = tr.dataset.seed;
    fight();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }));
}

init();

}
