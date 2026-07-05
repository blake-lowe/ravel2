/* Shared battle-replay engine (extracted from pit.js so the Blood Pit and the
   Supertemporal Arena render bouts with the same infrastructure). The replay is
   a pure fold over the engine's event stream — every event carries absolute
   HP/pos snapshots plus round + log-index stamps, so any scrub position is
   reconstructed exactly, no simulation here.

   Browser use:  const replay = RavelReplay.create({ els, corners, onPosition })
                 replay.load(battlePayload)   // a /api/battle-shaped payload
   Node use:     module.exports = { foldEvents, initiativeOrder, roundStarts }
                 (tests/pit_replay_smoke.js proves the fold against the engine) */
"use strict";

// ======================= pure replay core (node-testable) ====================

// Fold events[0..upto] into {tokens, round, current}. Absolute snapshots make
// this exact at any prefix.
function foldEvents(events, upto) {
  const tokens = {};
  let round = 0, current = null;
  for (let i = 0; i <= upto && i < events.length; i++) {
    const e = events[i];
    round = Math.max(round, e.round);
    const t = tokens[e.actor];
    switch (e.kind) {
      case "spawn":
        tokens[e.actor] = { pos: e.pos, hp: e.hp, spawnHp: e.hp, alive: true,
                            alt: e.alt || 0, team: e.info || (e.actor && e.actor[0]) };
        break;
      case "move":   if (t) { t.pos = e.pos; t.alt = e.alt || 0; } break;
      // mirror ravel/reducer.py exactly: damage/heal/survive carry absolute HP
      // snapshots, and alive tracks hp > 0 (a downed death-saver renders downed)
      case "damage": case "heal": case "survive":
        if (t) { t.hp = e.hp; t.alive = e.hp > 0; } break;
      case "death":  if (t) { t.alive = false; t.hp = 0; } break;
      case "flee":   if (t) t.fled = true; break;   // escaped off the map edge
      case "conditions": if (t) t.conds = e.info; break;  // snapshot, last-write-wins
      case "turn_start": current = e.actor; break;
    }
  }
  return { tokens, round, current };
}

// Initiative order: the engine's canonical `initiative` events (one per
// combatant, in turn order — includes anyone slain before their first turn).
// Legacy payloads without them fall back to distinct round-1 turn_start actors.
function initiativeOrder(events) {
  const order = events.filter((e) => e.kind === "initiative").map((e) => e.actor);
  if (order.length) return order;
  const seen = new Set();
  for (const e of events) {
    if (e.kind !== "turn_start" || e.round > 1) continue;
    if (!seen.has(e.actor)) { seen.add(e.actor); order.push(e.actor); }
  }
  return order;
}

// Event indices where each round begins (first event of that round), for nav.
function roundStarts(events) {
  const starts = [];
  let r = 0;
  events.forEach((e, i) => { if (e.round > r) { r = e.round; starts.push(i); } });
  return starts;
}

if (typeof module !== "undefined")
  module.exports = { foldEvents, initiativeOrder, roundStarts };

// ============================ browser widget =================================

if (typeof document !== "undefined") (function () {

const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const INK = "#211d18", PAPER = "#f4efe2", FAINT = "#a99f8c", BLOOD = "#7c1a15";
const CELL = 30;
const SVG_NS = "http://www.w3.org/2000/svg";
const key = (x, y) => `${x},${y}`;

// Tiny and Small creatures get visibly smaller discs than Medium (same 1 cell).
const SIZE_SCALE = { Tiny: 0.55, Small: 0.78 };
const tokenRadius = (c) => (c.cells * CELL / 2 - 3) * (SIZE_SCALE[c.size] || 1);
const clipId = (r) => `tokclip-${String(r).replace(".", "_")}`;

// conditions implied by a parent (stunned implies incapacitated, ...) are noise
const IMPLIED_BY = { incapacitated: ["stunned", "paralyzed", "petrified", "unconscious"],
                     prone: ["unconscious"] };

/* opts:
     els: { board, scrub, btnPlay, btnPrev, btnNext, btnStart, btnEnd,
            btnPrevRound, btnNextRound, speed, roundInd, log, initiative,
            legend?, lightLegend?, lightingToggle? }   (null/absent = feature off)
     corners: { A: {name, color, prefix}, B: {name, color, prefix} }
     onPosition(atEnd, winner)?  — called on every position change
     keyboard: true              — arrow keys / space drive the replay          */
function create(opts) {
  const E = opts.els;
  const CORNERS = opts.corners || {
    A: { name: "Red", color: BLOOD, prefix: "R" },
    B: { name: "Black", color: INK, prefix: "B" },
  };
  const state = {
    battle: null, idx: 0, playTimer: null, rStarts: [], initOrder: [],
    lighting: !E.lightingToggle || E.lightingToggle.checked,
    speedOf: {}, deathInfo: {}, animBusyUntil: 0, animGen: 0,
  };

  const dispId = (id) => (id && CORNERS[id[0]] ? CORNERS[id[0]].prefix + id.slice(1) : id);
  const cornerName = (team) => (CORNERS[team] || {}).name || team;
  const cornerColor = (team) => (CORNERS[team] || {}).color || INK;
  const displayLog = (line) => line
    .replace(/\bA(\d+)\b/g, `${CORNERS.A.prefix}$1`)
    .replace(/\bB(\d+)\b/g, `${CORNERS.B.prefix}$1`)
    .replace("Winner: A", `Winner: ${CORNERS.A.name}`)
    .replace("Winner: B", `Winner: ${CORNERS.B.name}`);
  const nameOf = (id) => {
    const c = (state.battle.combatants || []).find((c) => c.id === id);
    return c ? c.name : id;
  };
  const tickMs = () => Number(E.speed.value);

  // ------------------------------ the board -----------------------------------

  function buildBoard(b) {
    const g = b.grid;
    const W = g.w * CELL, H = g.h * CELL;
    const hazardCells = {};
    g.hazards.forEach((z, zi) => z.cells.forEach(([x, y]) => { hazardCells[key(x, y)] = zi; }));
    const elev = g.elevation, chasm = g.chasm;

    let cells = "";
    for (let y = 0; y < g.h; y++) {
      for (let x = 0; x < g.w; x++) {
        const px = x * CELL, py = y * CELL, k = key(x, y);
        if (chasm[k] !== undefined) {
          cells += `<rect x="${px}" y="${py}" width="${CELL}" height="${CELL}" fill="${INK}" opacity="0.88"/>
            <rect x="${px + 2}" y="${py + 2}" width="${CELL - 4}" height="${CELL - 4}" fill="url(#px-hatch)" opacity="0.5"/>`;
          continue;
        }
        if (elev[k]) {
          cells += `<rect x="${px}" y="${py}" width="${CELL}" height="${CELL}"
            fill="${INK}" opacity="${Math.min(0.08 * elev[k] / 5, 0.4)}"/>
            <text x="${px + 2}" y="${py + 9}" font-size="7" fill="${FAINT}">${elev[k]}</text>`;
        }
        if (hazardCells[k] !== undefined) {
          const z = g.hazards[hazardCells[k]];
          const lava = z.name.includes("lava");
          cells += `<rect x="${px}" y="${py}" width="${CELL}" height="${CELL}"
            fill="${lava ? BLOOD : "none"}" opacity="${lava ? 0.5 : 1}" ${lava ? "" : `stroke="${INK}" stroke-dasharray="2 2"`}/>
            <text x="${px + CELL / 2}" y="${py + CELL / 2 + 4}" font-size="10" text-anchor="middle"
              fill="${lava ? PAPER : INK}">${hazardCells[k] + 1}</text>`;
        }
      }
    }
    const walls = g.walls.map(([x, y]) =>
      `<rect x="${x * CELL}" y="${y * CELL}" width="${CELL}" height="${CELL}"
         fill="url(#px-hatch)" stroke="${INK}" stroke-width="1.4"/>`).join("");
    const cover = g.cover.map(([x, y]) =>
      `<rect x="${x * CELL + 6}" y="${y * CELL + 6}" width="${CELL - 12}" height="${CELL - 12}"
         fill="${INK}" opacity="0.75"/>`).join("");
    const difficult = g.difficult.map(([x, y]) => {
      const px = x * CELL, py = y * CELL;
      return `<g fill="${INK}" opacity="0.55">
        <circle cx="${px + 9}" cy="${py + 11}" r="1.4"/><circle cx="${px + 20}" cy="${py + 8}" r="1.4"/>
        <circle cx="${px + 15}" cy="${py + 21}" r="1.4"/></g>`;
    }).join("");
    const water = g.water.map(([x, y]) => {
      const px = x * CELL, py = y * CELL;
      return `<g stroke="${INK}" opacity="0.5" fill="none">
        <path d="M${px + 5},${py + 12} q5,-4 10,0 t10,0"/>
        <path d="M${px + 5},${py + 21} q5,-4 10,0 t10,0"/></g>`;
    }).join("");

    let gridlines = "";
    for (let x = 0; x <= g.w; x++)
      gridlines += `<line x1="${x * CELL}" y1="0" x2="${x * CELL}" y2="${H}"/>`;
    for (let y = 0; y <= g.h; y++)
      gridlines += `<line x1="0" y1="${y * CELL}" x2="${W}" y2="${y * CELL}"/>`;

    const tokens = b.combatants.map((c) => tokenSvg(c)).join("");
    const lighting = lightingSvg(g);

    // one clipPath per distinct token radius (size-scaled), plus the summon default
    const radii = new Set(b.combatants.map(tokenRadius));
    radii.add(CELL / 2 - 3);
    const clips = [...radii].map((r) =>
      `<clipPath id="${clipId(r)}"><circle r="${r}"/></clipPath>`).join("");
    E.board.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%"
        style="max-height:70vh" aria-label="the pit floor">
      <defs>
        <pattern id="px-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" stroke="${INK}" stroke-width="1.6"/>
        </pattern>
        ${clips}
      </defs>
      <rect width="${W}" height="${H}" fill="${PAPER}"/>
      <g stroke="#b9c4c9" stroke-width="1">${gridlines}</g>
      ${cells}${water}${difficult}${walls}${cover}
      ${lighting}
      <g id="tokens">${tokens}</g>
      <g id="floats"></g>
      <rect width="${W}" height="${H}" fill="none" stroke="${INK}" stroke-width="3"/>
    </svg>`;
  }

  // Light/shadow overlay straight from the engine's light map (grid.light): dark and
  // dim cells get an ink veil, fixed sources (braziers) a warm glow. Drawn under the
  // tokens so combatants stay legible, and behind a group the toggle shows/hides.
  // Fully-lit maps send empty lists, so this renders nothing there.
  function lightingSvg(g) {
    const L = g.light || { dim: [], dark: [], sources: [] };
    const veil = (cells, op) => cells.map(([x, y]) =>
      `<rect x="${x * CELL}" y="${y * CELL}" width="${CELL}" height="${CELL}"
         fill="${INK}" opacity="${op}"/>`).join("");
    const sources = (L.sources || []).map((s) => {
      const cx = s.pos[0] * CELL + CELL / 2, cy = s.pos[1] * CELL + CELL / 2;
      return `<g class="brazier">
        <circle cx="${cx}" cy="${cy}" r="${CELL * 0.8}" fill="${BLOOD}" opacity="0.12"/>
        <circle cx="${cx}" cy="${cy}" r="${CELL * 0.42}" fill="${BLOOD}" opacity="0.2"/>
        <circle cx="${cx}" cy="${cy}" r="3.2" fill="${BLOOD}" stroke="${PAPER}" stroke-width="1"/></g>`;
    }).join("");
    const hidden = state.lighting ? "" : ' style="display:none"';
    return `<g id="lighting"${hidden}>${veil(L.dark, 0.66)}${veil(L.dim, 0.3)}${sources}</g>`;
  }

  // Legend swatches matching the veil opacities exactly (ink over paper).
  function renderLightLegend(g) {
    if (!E.lightLegend) return;
    const L = g.light || { dim: [], dark: [], sources: [] };
    const el = E.lightLegend;
    const any = L.dim.length || L.dark.length || (L.sources || []).length;
    if (!any) { el.hidden = true; el.innerHTML = ""; return; }
    const sw = (color) => `<span class="sw" style="background:${color}"></span>`;
    const parts = [`${sw(PAPER)} bright`];
    if (L.dim.length) parts.push(`${sw("#b5b0a5")} dim`);
    if (L.dark.length) parts.push(`${sw("#69645b")} dark`);
    if ((L.sources || []).length) parts.push(`<span class="sw glow"></span> brazier glow`);
    el.innerHTML = parts.join(" · ");
    el.hidden = !state.lighting;
  }

  function tokenSvg(c) {
    const r = tokenRadius(c);
    const color = cornerColor(c.team);
    const art = (c.token_art || [])[0];
    return `<g class="token" id="tok-${esc(c.id)}" data-cells="${c.cells}" data-arti="0">
      <circle class="tok-body" r="${r}" fill="${color}" stroke="${INK}" stroke-width="1.5"/>
      <text class="tok-label" text-anchor="middle" dy="4" font-size="${(11 + 2 * (c.cells - 1)) * (SIZE_SCALE[c.size] || 1)}"
        fill="${PAPER}" font-weight="bold">${esc(dispId(c.id))}</text>
      ${art ? `<image class="tok-art" href="${esc(art)}" x="${-r}" y="${-r}"
        width="${2 * r}" height="${2 * r}" clip-path="url(#${clipId(r)})"/>
      <circle class="tok-ring" r="${r - 0.5}" fill="none" stroke="${color}" stroke-width="3"/>
      <text class="tok-badge" y="${r - 1}" text-anchor="middle" font-size="9.5" font-weight="bold"
        fill="${color}" stroke="${PAPER}" stroke-width="2.5" paint-order="stroke">${esc(dispId(c.id))}</text>` : ""}
      <text class="tok-alt" y="${-r - 4}" text-anchor="middle" font-size="9.5" font-weight="bold"
        fill="${INK}" stroke="${PAPER}" stroke-width="2.5" paint-order="stroke"></text>
      <g class="tok-hp"><rect class="hp-back" x="${-r}" y="${r + 2}" width="${2 * r}" height="3.5"
        fill="none" stroke="${INK}" stroke-width="0.6"/>
      <rect class="hp-fill" x="${-r}" y="${r + 2}" width="${2 * r}" height="3.5" fill="${INK}"/></g>
      <title>${esc(c.name)} (${esc(dispId(c.id))}) — AC ${c.ac}, ${c.max_hp} HP</title>
    </g>`;
  }

  // The round token art loads from the 5etools mirror; on error walk the candidate
  // list, and if none load fall back to the plain letter disc (remove art + ring).
  function wireTokenArt() {
    E.board.querySelectorAll("#tokens .tok-art").forEach((img) => {
      img.addEventListener("error", () => {
        const g = img.closest(".token");
        const c = state.battle.combatants.find((x) => `tok-${x.id}` === g.id);
        const next = Number(g.dataset.arti) + 1;
        if (c && next < (c.token_art || []).length) {
          g.dataset.arti = String(next);
          img.setAttribute("href", c.token_art[next]);
        } else {
          img.remove();
          g.querySelector(".tok-ring")?.remove();
          g.querySelector(".tok-badge")?.remove();
        }
      });
    });
  }

  function tokEl(id) { return E.board.querySelector(`#tok-${CSS.escape(id)}`); }
  function boardGroup(id) { return E.board.querySelector(`#${id}`); }

  function ensureToken(id, tok) {         // mid-fight summon: build a token on the fly
    if (tokEl(id)) return;
    const c = { id, name: id, team: tok.team, cells: 1, ac: "?", max_hp: tok.spawnHp };
    boardGroup("tokens").insertAdjacentHTML("beforeend", tokenSvg(c));
  }

  function renderLegend(g) {
    if (!E.legend) return;
    const items = g.hazards.map((z, i) =>
      `<span><b>${i + 1}</b> ${esc(z.name)}${z.damage.length ? ` — ${esc(z.damage.join(" + "))}` : ""}${z.difficult ? " (difficult)" : ""}</span>`);
    if (g.difficult.length) items.push("<span>··· difficult ground</span>");
    if (g.water.length) items.push("<span>〰 water</span>");
    if (Object.keys(g.chasm).length) items.push("<span>■ chasm</span>");
    E.legend.innerHTML = items.join(" · ");
  }

  // --------------------------- applying a position ----------------------------

  function applyIndex(i, animate = false) {
    const b = state.battle;
    state.idx = Math.max(0, Math.min(i, b.events.length - 1));
    E.scrub.value = String(state.idx);
    const st = foldEvents(b.events, state.idx);
    const ev = b.events[state.idx];
    if (!animate) {                        // scrub/jump: drop any queued effects
      state.animGen++;
      state.animBusyUntil = 0;
    }
    const maxHp = {};
    b.combatants.forEach((c) => { maxHp[c.id] = c.max_hp; });

    for (const [id, tok] of Object.entries(st.tokens)) {
      ensureToken(id, tok);
      const el = tokEl(id);
      const cells = Number(el.dataset.cells);
      const cx = tok.pos[0] * CELL + cells * CELL / 2;
      const cy = tok.pos[1] * CELL + cells * CELL / 2;
      // the mover walks its actual route (ev.cells) at a rate scaled by its speed;
      // everyone else (and any scrub/jump) snaps instantly
      el.style.transition = "none";
      el.style.transform = `translate(${cx}px,${cy}px)`;
      if (animate && ev && ev.kind === "move" && ev.actor === id) {
        walkPath(el, id, ev.cells);
      } else if (!animate) {
        el.getAnimations().forEach((a) => a.cancel());   // scrubbing snaps clean
      }
      const frac = Math.max(0, tok.hp / (maxHp[id] || tok.spawnHp || 1));
      const fill = el.querySelector(".hp-fill");
      const back = el.querySelector(".hp-back");
      const w = Number(back.getAttribute("width"));
      fill.setAttribute("width", String(w * Math.min(1, frac)));
      fill.setAttribute("fill", frac < 0.5 ? BLOOD : INK);
      // airborne badge: altitude relative to the ground under the token
      const ground = b.grid.elevation[`${tok.pos[0]},${tok.pos[1]}`] || 0;
      const relAlt = Math.round((tok.alt || 0) - ground);
      const altEl = el.querySelector(".tok-alt");
      if (altEl) altEl.textContent = relAlt > 0 && tok.alive ? `↑${relAlt} ft` : "";
      el.classList.toggle("dead", !tok.alive);
      el.classList.toggle("current", st.current === id && tok.alive);
    }
    // hide tokens not yet spawned (scrubbing backward past a summon) or fled
    E.board.querySelectorAll("#tokens .token").forEach((el) => {
      const id = el.id.slice(4);
      const tok = st.tokens[id];
      el.style.display = tok && !tok.fled ? "" : "none";
    });

    if (animate && ev && (ev.kind === "damage" || ev.kind === "heal" || ev.kind === "survive")) {
      afterAnims(() => floatText(ev, st));
    }
    if (animate && ev && ev.kind === "attack") afterAnims(() => animateAttack(ev, st));
    if (animate && ev && ev.kind === "area") afterAnims(() => flashArea(ev));
    if (animate && ev && ev.kind === "conditions") {
      const prev = foldEvents(b.events, state.idx - 1).tokens[ev.actor];
      const before = new Set(((prev && prev.conds) || "").split(",").filter(Boolean));
      const gained = ev.info.split(",").filter((c) => c && !before.has(c));
      if (gained.length) afterAnims(() => floatConditions(ev.actor, gained, st));
    }
    E.roundInd.textContent = st.round ? `Round ${st.round} of ${b.rounds}` : "the combatants enter";
    renderLog(ev);
    renderInitiative(st);
    opts.onPosition?.(state.idx >= b.events.length - 1, b.winner);
  }

  function floatText(ev, st) {
    const tok = st.tokens[ev.actor];
    if (!tok) return;
    const x = tok.pos[0] * CELL + CELL / 2, y = tok.pos[1] * CELL;
    const txt = ev.kind === "damage" ? `−${ev.amount}` : ev.kind === "heal" ? `+${ev.amount}` : "✦";
    const color = ev.kind === "damage" ? BLOOD : INK;
    const id = `float-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    boardGroup("floats").insertAdjacentHTML("beforeend",
      `<text id="${id}" x="${x}" y="${y}" text-anchor="middle" font-size="13"
         font-weight="bold" fill="${color}" class="float-dmg">${txt}</text>`);
    setTimeout(() => document.getElementById(id)?.remove(), 900);
  }

  // ------------------------- combat animations (display only) -----------------
  // Everything here is a pure visual layer over the event stream: blood-red, brief,
  // and as simple as possible. Nothing feeds back into the replay fold.

  // Sequence the visuals: an effect that lands while the previous walk (or swing)
  // is still playing waits its turn; scrubbing bumps animGen and drops the queue.
  function afterAnims(fn) {
    const wait = state.animBusyUntil - performance.now();
    if (wait <= 10) { fn(); return; }
    const gen = state.animGen;
    setTimeout(() => { if (gen === state.animGen) fn(); }, wait);
  }

  // Walk the mover along its actual route (the engine's Dijkstra path, carried on
  // the move event) and chalk that route in light grey while it walks.
  function walkPath(el, id, cells) {
    const foot = Number(el.dataset.cells) || 1;
    const half = foot * CELL / 2;
    const pts = (cells || []).map(([x, y]) => [x * CELL + half, y * CELL + half]);
    if (pts.length < 2) return;                   // no route (teleport): snapping is correct
    const seg = [0];
    for (let i = 1; i < pts.length; i++)
      seg.push(seg[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0],
                                       pts[i][1] - pts[i - 1][1]));
    const totalPx = seg[seg.length - 1];
    if (!totalPx) return;
    const feet = totalPx / CELL * 5;
    const speed = state.speedOf[id] || 30;
    const tick = tickMs();
    // a full-speed move plays over ~2 playback ticks; faster creatures cover the
    // same ground in less time
    const dur = Math.max(80, Math.min(1200,
      Math.round(feet / Math.max(speed, 5) * tick * 2)));
    el.getAnimations().forEach((a) => a.cancel());
    el.animate(pts.map((p, i) => ({ transform: `translate(${p[0]}px,${p[1]}px)`,
                                    offset: seg[i] / totalPx })),
               { duration: dur, easing: "linear" });
    state.animBusyUntil = Math.max(state.animBusyUntil, performance.now() + dur);
    chalkPath(pts, dur);
  }

  function chalkPath(pts, walkMs) {
    const line = document.createElementNS(SVG_NS, "polyline");
    line.setAttribute("points", pts.map((p) => p.join(",")).join(" "));
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", FAINT);
    line.setAttribute("stroke-width", "2.5");
    line.setAttribute("stroke-linecap", "round");
    line.setAttribute("stroke-linejoin", "round");
    line.setAttribute("stroke-dasharray", "6 5");
    boardGroup("floats").appendChild(line);
    line.animate([{ opacity: 0.85 }, { opacity: 0.85, offset: 0.7 }, { opacity: 0 }],
                 { duration: walkMs + 700, easing: "linear" }).onfinish = () => line.remove();
  }

  function tokenCenter(id, st) {
    const tok = st.tokens[id];
    const el = tokEl(id);
    if (!tok || !el) return null;
    const cells = Number(el.dataset.cells) || 1;
    return [tok.pos[0] * CELL + cells * CELL / 2, tok.pos[1] * CELL + cells * CELL / 2];
  }

  // melee = a lunge toward the target; ranged = a tracer line. A hit lands an
  // impact ring; a miss reads fainter.
  function animateAttack(ev, st) {
    const from = tokenCenter(ev.actor, st), to = tokenCenter(ev.info, st);
    if (!from || !to) return;
    const hit = ev.amount > 0;
    // the damage float that follows waits for the blow to land
    state.animBusyUntil = Math.max(state.animBusyUntil,
                                   performance.now() + (ev.dtype === "melee" ? 240 : 320));
    if (ev.dtype === "melee") {
      const el = tokEl(ev.actor);
      const dx = (to[0] - from[0]) * 0.35, dy = (to[1] - from[1]) * 0.35;
      el.animate([
        { transform: `translate(${from[0]}px,${from[1]}px)` },
        { transform: `translate(${from[0] + dx}px,${from[1] + dy}px)`, offset: 0.45 },
        { transform: `translate(${from[0]}px,${from[1]}px)` },
      ], { duration: 260, easing: "ease-out" });
    } else {
      const line = document.createElementNS(SVG_NS, "line");
      line.setAttribute("x1", from[0]); line.setAttribute("y1", from[1]);
      line.setAttribute("x2", to[0]);   line.setAttribute("y2", to[1]);
      line.setAttribute("stroke", BLOOD);
      line.setAttribute("stroke-width", hit ? "2.5" : "1.5");
      line.setAttribute("stroke-linecap", "round");
      const len = Math.hypot(to[0] - from[0], to[1] - from[1]);
      line.setAttribute("stroke-dasharray", String(len));
      boardGroup("floats").appendChild(line);
      line.animate([
        { strokeDashoffset: len, opacity: hit ? 0.9 : 0.4 },
        { strokeDashoffset: 0, opacity: hit ? 0.9 : 0.4, offset: 0.4 },
        { strokeDashoffset: 0, opacity: 0 },
      ], { duration: 360, easing: "linear" }).onfinish = () => line.remove();
    }
    if (hit) impactRing(to);
  }

  function impactRing([x, y]) {
    const c = document.createElementNS(SVG_NS, "circle");
    c.setAttribute("cx", x); c.setAttribute("cy", y);
    c.setAttribute("fill", "none");
    c.setAttribute("stroke", BLOOD);
    c.setAttribute("stroke-width", "2");
    boardGroup("floats").appendChild(c);
    c.animate([{ r: 3, opacity: 0.9 }, { r: 11, opacity: 0 }],
              { duration: 300, easing: "ease-out" }).onfinish = () => c.remove();
  }

  // Shade an area ability's squares blood-red for a beat.
  function flashArea(ev) {
    if (!ev.cells || !ev.cells.length) return;
    const g = document.createElementNS(SVG_NS, "g");
    for (const [x, y] of ev.cells) {
      const r = document.createElementNS(SVG_NS, "rect");
      r.setAttribute("x", x * CELL); r.setAttribute("y", y * CELL);
      r.setAttribute("width", CELL); r.setAttribute("height", CELL);
      r.setAttribute("fill", BLOOD);
      g.appendChild(r);
    }
    boardGroup("floats").appendChild(g);
    g.animate([{ opacity: 0.4 }, { opacity: 0.4, offset: 0.55 }, { opacity: 0 }],
              { duration: 650, easing: "ease-out" }).onfinish = () => g.remove();
  }

  // Newly applied conditions rise off the token like damage numbers.
  function floatConditions(id, names, st) {
    const tok = st.tokens[id];
    if (!tok || !tok.alive) return;               // the dead-book covers the dead
    const x = tok.pos[0] * CELL + CELL / 2, y = tok.pos[1] * CELL;
    names.forEach((name, i) => {
      const el = document.createElementNS(SVG_NS, "text");
      el.setAttribute("x", x);
      el.setAttribute("y", y - 12 * i);
      el.setAttribute("text-anchor", "middle");
      el.setAttribute("font-size", "11");
      el.setAttribute("font-style", "italic");
      el.setAttribute("font-weight", "bold");
      el.setAttribute("fill", BLOOD);
      el.setAttribute("stroke", PAPER);
      el.setAttribute("stroke-width", "2.5");
      el.setAttribute("paint-order", "stroke");
      el.textContent = name + "!";
      el.setAttribute("class", "float-dmg");
      boardGroup("floats").appendChild(el);
      setTimeout(() => el.remove(), 1100);
    });
  }

  function condLine(tok) {
    const conds = ((tok && tok.conds) || "").split(",").filter(Boolean);
    const shown = conds.filter((c) =>
      !(IMPLIED_BY[c] || []).some((parent) => conds.includes(parent)));
    return shown.join(" · ");
  }

  function renderLog(ev) {
    const b = state.battle;
    const upto = ev ? Math.min(ev.log_index + 1, b.log.length) : 0;
    E.log.textContent = b.log.slice(0, upto).map(displayLog).join("\n");
    E.log.scrollTop = E.log.scrollHeight;
  }

  // -------------------- cause of death (the dead-book) ------------------------
  // Derived purely from the event stream: the nearest preceding hit (who) or area
  // (what) explains the killing blow; special death dtypes cover the environment.
  function deathCauses(events) {
    const SPECIAL = { fall: "fell to its death", suffocation: "suffocated",
                      expired: "faded away", drain: "drained dry" };
    const out = {};
    for (let i = 0; i < events.length; i++) {
      const e = events[i];
      if (e.kind !== "death" || out[e.actor]) continue;
      if (SPECIAL[e.dtype]) { out[e.actor] = SPECIAL[e.dtype]; continue; }
      let dtype = "", cause = "";
      for (let j = i - 1; j >= 0 && j > i - 60; j--) {
        const p = events[j];
        if (p.kind === "damage" && p.actor === e.actor && !dtype) dtype = p.dtype;
        if (p.kind === "attack" && p.info === e.actor && p.amount > 0) {
          cause = `slain by ${dispId(p.actor)}`;
          break;
        }
        if (p.kind === "area") {
          cause = `${p.info} (${dispId(p.actor)})`;
          break;
        }
        // don't attribute past the victim's own turn (hazards on its own move)
        if (p.kind === "turn_start" && p.actor === e.actor) break;
      }
      if (!cause) cause = (dtype && dtype !== "unavoidable")
        ? `killed by ${dtype}` : "struck down";
      out[e.actor] = cause;
    }
    return out;
  }

  function renderInitiative(st) {
    E.initiative.innerHTML =
      `<div class="panel-title hatch">Initiative</div><div class="init-chips">` +
      state.initOrder.map((id) => {
        const tok = st.tokens[id];
        const dead = tok && !tok.alive;
        const fled = tok && tok.fled;
        const cur = st.current === id;
        const cause = dead && (state.deathInfo || {})[id];
        const conds = !dead && !fled ? condLine(tok) : "";
        return `<span class="init-chip${cur ? " cur" : ""}${dead ? " dead" : ""}${fled ? " fled" : ""}"${
            cause ? ` title="${esc(nameOf(id))}: ${esc(cause)}"`
                  : conds ? ` title="${esc(nameOf(id))}: ${esc(conds)}"` : ""}>
          <span class="who"><b>${esc(dispId(id))}</b> ${esc(nameOf(id))}</span>${fled ? " (fled)" : ""}${
            cause ? `<i class="cause">✝ ${esc(cause)}</i>`
                  : conds ? `<i class="conds">${esc(conds)}</i>` : ""}</span>`;
      }).join("") + `</div>`;
  }

  // ------------------------------ playback ------------------------------------

  function wireControls() {
    E.scrub.addEventListener("input", () => { stopPlay(); applyIndex(Number(E.scrub.value)); });
    E.btnPrev.addEventListener("click", () => { stopPlay(); applyIndex(state.idx - 1); });
    E.btnNext.addEventListener("click", () => { stopPlay(); applyIndex(state.idx + 1, true); });
    E.btnStart.addEventListener("click", () => { stopPlay(); applyIndex(0); });
    E.btnEnd.addEventListener("click", () => { stopPlay(); applyIndex(state.battle.events.length - 1); });
    E.btnPrevRound.addEventListener("click", () => { stopPlay(); jumpRound(-1); });
    E.btnNextRound.addEventListener("click", () => { stopPlay(); jumpRound(1); });
    E.btnPlay.addEventListener("click", togglePlay);
    E.lightingToggle?.addEventListener("change", () => {
      state.lighting = E.lightingToggle.checked;
      const g = boardGroup("lighting");
      if (g) g.style.display = state.lighting ? "" : "none";
      if (state.battle) renderLightLegend(state.battle.grid);
    });
    if (opts.keyboard !== false) document.addEventListener("keydown", (ev) => {
      if (!state.battle || E.board.offsetParent === null
          || ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
      if (ev.key === "ArrowRight") { stopPlay(); applyIndex(state.idx + 1, true); }
      if (ev.key === "ArrowLeft") { stopPlay(); applyIndex(state.idx - 1); }
      if (ev.key === " ") { ev.preventDefault(); togglePlay(); }
    });
  }

  function jumpRound(dir) {
    const starts = state.rStarts;
    if (!starts.length) return;
    const cur = starts.filter((s) => s <= state.idx).length - 1;   // current round idx
    const target = cur + dir;
    applyIndex(target < 0 ? 0 : starts[Math.min(target, starts.length - 1)] ?? 0);
  }

  function togglePlay() {
    if (state.playTimer) { stopPlay(); return; }
    if (!state.battle) return;
    if (state.idx >= state.battle.events.length - 1) applyIndex(0);
    E.btnPlay.textContent = "❚❚";
    const tick = () => {
      if (state.idx >= state.battle.events.length - 1) { stopPlay(); return; }
      applyIndex(state.idx + 1, true);
      // hold the beat until any in-flight walk/swing finishes, so the next
      // event's effect lands after the movement, never during it
      const base = tickMs();
      const wait = Math.max(base, state.animBusyUntil - performance.now() + 40);
      state.playTimer = setTimeout(tick, wait);
    };
    state.playTimer = setTimeout(tick, tickMs());
  }

  function stopPlay() {
    if (state.playTimer) clearTimeout(state.playTimer);
    state.playTimer = null;
    E.btnPlay.textContent = "▶";
  }

  // ------------------------------ public API ----------------------------------

  function load(b) {
    stopPlay();
    state.battle = b;
    state.idx = 0;
    state.rStarts = roundStarts(b.events);
    state.initOrder = initiativeOrder(b.events);
    // ft/turn per combatant, for speed-scaled move animation (summons default to 30)
    state.speedOf = Object.fromEntries(
      b.combatants.map((c) => [c.id, Math.max(c.speed || 0, c.fly || 0) || 30]));
    state.deathInfo = deathCauses(b.events);
    E.scrub.max = String(b.events.length - 1);
    E.scrub.value = "0";
    buildBoard(b);
    wireTokenArt();
    renderLegend(b.grid);
    renderLightLegend(b.grid);
    // open on the end of pre-battle setup, so the whole bill is on the board
    let i0 = 0;
    while (i0 + 1 < b.events.length && b.events[i0 + 1].round === 0) i0++;
    applyIndex(i0);
  }

  wireControls();
  return { load, play: togglePlay, stop: stopPlay,
           toEnd: () => { stopPlay(); if (state.battle) applyIndex(state.battle.events.length - 1); } };
}

window.RavelReplay = { create };

})();
