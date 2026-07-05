/* The Supertemporal Arena (Slice 12e): a roguelite auto-battler over the pure
   run-state machine in ravel/fortune.py. The server owns every rule and every
   die; this file only renders state, drags tokens, and animates the wheel to
   the stops the house already rolled. Gilt is this page's accent; the wheel
   alone gets lacquer red. */
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let META = null;      // /api/fortune/meta
let S = null;         // latest run state
let RID = localStorage.getItem("fw-run") || null;
let DEPLOY = null;    // current /deploy payload
let PLACEMENTS = [];  // stable-index -> [x,y] | null
let BATTLE = null;    // last battle payload
let TARGETING = null; // {verb, label, filter} while picking a stable member

// ------------------------------- plumbing ------------------------------------

async function api(path, body, errEl) {
  if (errEl) errEl.textContent = "";
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (e) { /* keep */ }
    if (errEl) errEl.textContent = msg;
    throw new Error(msg);
  }
  return res.json();
}

function coinsHtml(cp) {
  const gp = Math.floor(cp / 100), sp = Math.floor((cp % 100) / 10), c = cp % 10;
  const bits = [];
  if (gp) bits.push(`<span class="coin gp" title="gold">${gp}</span>`);
  if (sp) bits.push(`<span class="coin sp" title="silver">${sp}</span>`);
  if (c || !bits.length) bits.push(`<span class="coin cp" title="copper">${c}</span>`);
  return bits.join(" ");
}

// Token art: walk the candidate URLs on error, fall back to an initial.
function tokenImg(arts, name, cls) {
  const letter = `<span class="mtoken letter ${cls || ""}">${esc(name[0] || "?")}</span>`;
  if (!arts || !arts.length) return letter;
  const chain = esc(JSON.stringify(arts.slice(1)));
  return `<img class="mtoken ${cls || ""}" src="${esc(arts[0])}" alt=""
    data-rest='${chain}' onerror="fwArtErr(this)">`;
}
window.fwArtErr = function (img) {
  const rest = JSON.parse(img.dataset.rest || "[]");
  if (rest.length) { img.dataset.rest = JSON.stringify(rest.slice(1)); img.src = rest[0]; }
  else {
    const sp = document.createElement("span");
    sp.className = img.className + " letter";
    sp.textContent = (img.closest("[data-name]")?.dataset.name || "?")[0];
    img.replaceWith(sp);
  }
};

function show(section) {
  for (const id of ["fw-lobby", "fw-shop", "fw-sands", "fw-over"])
    $("#" + id).hidden = id !== section;
  $("#fw-status").hidden = section === "fw-lobby";
}

// ------------------------------- lobby ----------------------------------------

async function boot() {
  META = await api("/api/fortune/meta");
  $("#lob-books").innerHTML = META.books.map((b) => `
    <label class="check"><input type="checkbox" value="${esc(b.label)}" checked>
      ${esc(b.label)} <span class="odds-note">(${b.monsters})</span></label>`).join("");
  $("#lob-enter").onclick = newRun;
  $("#btn-again").onclick = () => { localStorage.removeItem("fw-run"); RID = null; show("fw-lobby"); };
  wireShop();
  wireSands();
  wireWheel();
  loadAges();
  if (RID) {
    try { S = await api(`/api/fortune/run/${RID}`); resume(); }
    catch (e) { localStorage.removeItem("fw-run"); RID = null; }
  }
}

async function newRun() {
  const books = [...document.querySelectorAll("#lob-books input:checked")].map((i) => i.value);
  const seedRaw = $("#lob-seed").value;
  const body = { books, handle: $("#lob-handle").value || "Anonymous Berk" };
  if (seedRaw !== "") body.seed = Number(seedRaw);
  S = await api("/api/fortune/new", body, $("#lob-error"));
  RID = S.run_id;
  localStorage.setItem("fw-run", RID);
  renderShop();
  show("fw-shop");
}

function resume() {
  if (S.phase === "over") { renderOver(); show("fw-over"); }
  else if (S.phase === "wheel") { renderShop(); show("fw-shop"); openWheel(); }
  else { renderShop(); show("fw-shop"); }
}

// ------------------------------- status strip ----------------------------------

function renderStatus() {
  $("#st-purse").innerHTML = coinsHtml(S.purse_cp);
  $("#st-lives").innerHTML = Array.from({ length: S.lives_max }, (_, i) =>
    `<span class="chip ${i < S.lives ? "" : "spent"}"></span>`).join("");
  $("#st-round").textContent = S.round;
  $("#st-cap").textContent = `CR ${S.cap}`;
  const losses = S.history.filter((h) => !h.won).length;
  $("#st-record").textContent = `${S.wins}–${losses}`;
  $("#st-years").textContent = `${S.years.toLocaleString()} years witnessed`;
  $("#st-handle").textContent = S.handle;
}

// ------------------------------- shop -------------------------------------------

function wireShop() {
  $("#btn-reroll").onclick = () => act({ action: "reroll" });
  $("#btn-sands").onclick = openSands;
}

async function act(body) {
  try { S = await api(`/api/fortune/run/${RID}/action`, body, $("#shop-error")); }
  catch (e) { return; }
  TARGETING = null;
  renderShop();
}

function beginTargeting(t) {
  TARGETING = t;
  $("#shop-error").textContent = t.label + " — pick a beast in your stable (or reroll to cancel)";
  renderStable();
}

function renderShop() {
  renderStatus();
  renderStable();
  renderStock();
  renderBank();
  renderForesight();
  renderBill();
  $("#btn-reroll").textContent = "Reroll the stock (5 sp)";
  $("#btn-sands").disabled = !S.stable.length;
  if (S.phase === "over") { renderOver(); show("fw-over"); }
}

function renderStable() {
  const row = $("#stable-row");
  const cards = S.stable.map((m, i) => {
    const stars = m.elite ? `<span class="stars">${"★".repeat(m.elite)}</span>` : "";
    const items = m.items.map((it) =>
      `<span class="tag" title="${esc(it.blurb)}">${esc(it.name)}</span>`).join("");
    const twin = S.stable.some((o, j) => j !== i && o.name === m.name);
    const targetable = TARGETING && (!TARGETING.filter || TARGETING.filter(m, i));
    return `<div class="mcard ${targetable ? "is-frozen" : ""}" data-name="${esc(m.name)}" data-idx="${i}">
      ${tokenImg(m.art, m.name)}
      <div class="mname">${esc(m.name)} ${stars}</div>
      <div class="mmeta">AC ${m.ac} · ${m.hp} hp · CR ${crStr(m.cr)}</div>
      <div class="stable-items">${items}</div>
      <div class="cardbtns">
        ${targetable ? `<button data-pick="${i}">choose</button>` : `
          <button data-sell="${i}" title="half of all coin invested comes back">sell (${coinsFlat(Math.floor(m.invested_cp / 2))})</button>
          ${twin ? `<button data-train="${i}" title="merge a twin into this one: +1 AC, +1 HP">train ★</button>` : ""}`}
      </div>
    </div>`;
  });
  while (cards.length < S.team_cap) cards.push(`<div class="mcard empty">an empty stall</div>`);
  row.innerHTML = cards.join("");
  row.querySelectorAll("[data-sell]").forEach((b) =>
    b.onclick = () => act({ action: "sell", target: +b.dataset.sell }));
  row.querySelectorAll("[data-train]").forEach((b) =>
    b.onclick = () => {
      const i = +b.dataset.train;
      beginTargeting({
        label: `Training ${S.stable[i].name}: pick the twin to merge in`,
        filter: (m, j) => j !== i && m.name === S.stable[i].name,
        go: (j) => act({ action: "train", target: i, other: j }),
      });
    });
  row.querySelectorAll("[data-pick]").forEach((b) =>
    b.onclick = () => TARGETING.go(+b.dataset.pick));
}

function crStr(cr) {
  return cr === 0.125 ? "1/8" : cr === 0.25 ? "1/4" : cr === 0.5 ? "1/2" : String(cr);
}

function coinsFlat(cp) {
  const gp = Math.floor(cp / 100), sp = Math.floor((cp % 100) / 10), c = cp % 10;
  return [gp && `${gp} gp`, sp && `${sp} sp`, c && `${c} cp`].filter(Boolean).join(" ") || "0 cp";
}

function renderStock() {
  const row = $("#stock-row");
  row.innerHTML = S.shop.monsters.map((s, i) => {
    if (!s) return `<div class="mcard empty">sold</div>`;
    const owned = S.stable.findIndex((m) => m.name === s.name);
    const pr = s.best_cr != null && s.best_cr !== s.cr
      ? `<span title="the pit's own ledger disagrees with the book">PR ${s.best_cr}</span>` : "";
    return `<div class="mcard ${s.frozen ? "is-frozen" : ""}" data-name="${esc(s.name)}">
      <span class="frozen-flag ${s.frozen ? "on" : ""}" data-freeze="${i}" title="freeze through the reroll">❄</span>
      ${tokenImg(s.art, s.name)}
      <div class="mname">${esc(s.name)}</div>
      <div class="mmeta">CR ${crStr(s.cr)} ${pr} · ${esc(s.source)}</div>
      <div class="price">${esc(s.price)}</div>
      <div class="cardbtns">
        <button data-buy="${i}">buy</button>
        ${owned >= 0 ? `<button data-buytrain="${i}" data-tgt="${owned}"
            title="feed this copy straight to yours: +1 AC, +1 HP">train ★</button>` : ""}
      </div>
    </div>`;
  }).join("");
  row.querySelectorAll("[data-buy]").forEach((b) =>
    b.onclick = () => act({ action: "buy", slot: +b.dataset.buy }));
  row.querySelectorAll("[data-buytrain]").forEach((b) =>
    b.onclick = () => act({ action: "buy", slot: +b.dataset.buytrain, target: +b.dataset.tgt }));
  row.querySelectorAll("[data-freeze]").forEach((f) =>
    f.onclick = () => act({ action: "freeze", kind: "monster", slot: +f.dataset.freeze }));

  $("#item-shelf").innerHTML = S.shop.items.map((s, i) => {
    if (!s) return `<div class="icard"><span class="blurb">sold</span></div>`;
    return `<div class="icard ${s.frozen ? "is-frozen" : ""}">
      <span class="frozen-flag ${s.frozen ? "on" : ""}" data-ifreeze="${i}">❄</span>
      <span class="iname">${esc(s.name)}</span>
      <span class="rarity ${esc(s.rarity)}">${esc(s.rarity)}</span> · <span class="price">${esc(s.price)}</span>
      <div class="blurb">${esc(s.blurb)}</div>
      <button data-ibuy="${i}">buy for a beast…</button>
    </div>`;
  }).join("");
  $("#item-shelf").querySelectorAll("[data-ibuy]").forEach((b) =>
    b.onclick = () => beginTargeting({
      label: `Buying ${S.shop.items[+b.dataset.ibuy].name}: who carries it?`,
      filter: (m) => m.items.length < 3,
      go: (j) => act({ action: "buy_item", slot: +b.dataset.ibuy, target: j }),
    }));
  $("#item-shelf").querySelectorAll("[data-ifreeze]").forEach((f) =>
    f.onclick = () => act({ action: "freeze", kind: "item", slot: +f.dataset.ifreeze }));
}

function renderBank() {
  const el = $("#bank-row");
  if (!S.bank.length) { el.innerHTML = ""; return; }
  el.innerHTML = `<span class="odds-note">won on the wheel, unclaimed:</span> ` +
    S.bank.map((it, i) =>
      `<button data-bank="${i}" title="${esc(it.blurb)}">${esc(it.name)} → give</button>`).join(" ");
  el.querySelectorAll("[data-bank]").forEach((b) =>
    b.onclick = () => beginTargeting({
      label: `Handing over ${S.bank[+b.dataset.bank].name}: who carries it?`,
      filter: (m) => m.items.length < 3,
      go: (j) => act({ action: "attach", slot: +b.dataset.bank, target: j }),
    }));
}

const WEATHER_GLYPH = { clear: "☀ clear", fog: "▒ fog", rain: "☂ rain", wind: "≋ wind" };

function renderForesight() {
  $("#fore-strip").innerHTML = S.foresight.map((f, i) => `
    <div class="fore-card">
      <div class="fr">${i === 0 ? "next" : "battle " + f.round}</div>
      <div class="fmap">${esc(f.map || "the open floor")}</div>
      <div>${WEATHER_GLYPH[f.weather] || esc(f.weather)}</div>
    </div>`).join("");
}

function renderBill() {
  $("#the-bill").innerHTML = S.enemy.length
    ? S.enemy.map((e) => `<span class="bill-line">${e.count}× <b>${esc(e.name)}</b>
        <span class="odds-note">CR ${crStr(e.cr)}</span></span>`).join("")
    : `<span class="odds-note">the bill is being printed…</span>`;
}

// ------------------------------- the sands ---------------------------------------

function wireSands() {
  $("#btn-back-shop").onclick = () => show("fw-shop");
  $("#btn-gong").onclick = fight;
  $("#rp-play").onclick = togglePlay;
  $("#rp-skip").onclick = skipToEnd;
  $("#rp-done").onclick = afterBattle;
}

async function openSands() {
  try { DEPLOY = await api(`/api/fortune/run/${RID}/deploy`); }
  catch (e) { $("#shop-error").textContent = e.message; return; }
  PLACEMENTS = S.stable.map(() => null);
  BATTLE = null;
  $("#sands-verdict").innerHTML = "";
  $("#fw-log").hidden = true; $("#fw-log").textContent = "";
  $("#deploy-controls").hidden = false;
  $("#replay-controls").hidden = true;
  $("#sands-brief").innerHTML = `
    <b>Battle ${DEPLOY.round}</b> — ${esc(DEPLOY.map || "the open floor")},
    ${WEATHER_GLYPH[DEPLOY.weather] || esc(DEPLOY.weather)}<br>
    <span class="odds-note">drag your beasts anywhere in the gilded ground, then sound the gong.
    The other corner's placement is the house's secret.</span><br>
    ${DEPLOY.enemy.map((e) => `${e.count}× ${esc(e.name)}`).join(", ")} await.`;
  drawBoard(DEPLOY.grid, new Set(DEPLOY.zone.map((c) => c.join(","))));
  // deployment shows only YOUR tokens at their default cells; the foe is a rumor
  for (const c of DEPLOY.combatants.filter((c) => c.team === "A")) placeToken(c, true);
  show("fw-sands");
}

let BOARD = null;  // {svg, cell, w, h, zone, toks: {id: {g, foot}}}

function drawBoard(grid, zone) {
  const cell = Math.max(18, Math.min(30, Math.floor(720 / grid.w)));
  const W = grid.w * cell, H = grid.h * cell;
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", W); svg.setAttribute("height", H);
  svg.innerHTML = `<defs><pattern id="fw-hatch" width="5" height="5"
      patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <rect width="5" height="5" fill="#f4efe2"/>
      <line x1="0" y1="0" x2="0" y2="5" stroke="#211d18" stroke-width="1.6"/>
    </pattern></defs>`;
  const kinds = [["walls", "wall"], ["water", "water"], ["difficult", "difficult"]];
  const layer = (cls, cells) => {
    for (const [x, y] of cells) {
      const r = document.createElementNS(NS, "rect");
      r.setAttribute("x", x * cell); r.setAttribute("y", y * cell);
      r.setAttribute("width", cell); r.setAttribute("height", cell);
      r.setAttribute("class", `cell ${cls}`);
      r.dataset.cell = `${x},${y}`;
      svg.appendChild(r);
    }
  };
  // base grid + zone wash
  const base = [];
  for (let y = 0; y < grid.h; y++) for (let x = 0; x < grid.w; x++) base.push([x, y]);
  layer("", base);
  if (zone) layer("zone", [...zone].map((s) => s.split(",").map(Number)));
  for (const [key, cls] of kinds) layer(cls, grid[key] || []);
  layer("chasm", Object.keys(grid.chasm || {}).map((s) => s.split(",").map(Number)));
  $("#fw-board").innerHTML = "";
  $("#fw-board").appendChild(svg);
  BOARD = { svg, cell, w: grid.w, h: grid.h, zone: zone || new Set(), toks: {} };
}

function footOf(sizeName) {
  return { Tiny: 1, Small: 1, Medium: 1, Large: 2, Huge: 3, Gargantuan: 4 }[sizeName] || 1;
}

function placeToken(c, draggable) {
  const NS = "http://www.w3.org/2000/svg";
  const foot = footOf(c.size);
  const g = document.createElementNS(NS, "g");
  g.setAttribute("class", `tok team-${c.team.toLowerCase()} ${draggable ? "mine" : ""}`);
  const r = (foot * BOARD.cell) / 2;
  g.innerHTML = `
    <circle class="body" r="${r - 2}"></circle>
    <text y="4" font-size="${r * 0.9}">${esc(c.name[0])}</text>
    <rect class="hpback" x="${-r + 2}" y="${r - 4}" width="${2 * r - 4}" height="3"></rect>
    <rect class="hpbar" x="${-r + 2}" y="${r - 4}" width="${2 * r - 4}" height="3"></rect>
    <title>${esc(c.name)} — AC ${c.ac}, ${c.hp}/${c.max_hp} hp</title>`;
  BOARD.svg.appendChild(g);
  const tok = { g, foot, hpw: 2 * r - 4, pos: c.pos.slice(), name: c.name };
  BOARD.toks[c.id] = tok;
  moveToken(c.id, c.pos);
  if (draggable) wireDrag(c.id, tok);
}

function moveToken(id, pos) {
  const t = BOARD.toks[id];
  if (!t) return;
  t.pos = pos.slice();
  const cx = (pos[0] + t.foot / 2) * BOARD.cell, cy = (pos[1] + t.foot / 2) * BOARD.cell;
  t.g.setAttribute("transform", `translate(${cx},${cy})`);
}

function setHp(id, hp, max, alive) {
  const t = BOARD.toks[id];
  if (!t) return;
  t.g.querySelector(".hpbar").setAttribute("width", Math.max(0, t.hpw * hp / Math.max(1, max)));
  t.g.classList.toggle("dead", !alive);
}

// deployment drag: pointer events on the SVG, snap to the gilded ground
function wireDrag(id, tok) {
  const idx = Number(id.slice(1)) - 1;   // A1 -> stable index 0
  tok.g.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    tok.g.classList.add("dragging");
    const move = (e) => {
      const cell = cellAt(e);
      if (cell) moveToken(id, [cell[0] - Math.floor(tok.foot / 2), cell[1] - Math.floor(tok.foot / 2)]);
    };
    const up = (e) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      tok.g.classList.remove("dragging");
      const origin = tok.pos;
      if (legalDrop(id, origin, tok.foot)) {
        PLACEMENTS[idx] = origin.slice();
        $("#sands-error").textContent = "";
      } else {
        $("#sands-error").textContent = "the pit hands wave you off — that ground is not yours";
        // revert to default spawn
        const dflt = DEPLOY.combatants.find((c) => c.id === id);
        moveToken(id, dflt.pos);
        PLACEMENTS[idx] = null;
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });
}

function cellAt(ev) {
  const pt = BOARD.svg.createSVGPoint();
  pt.x = ev.clientX; pt.y = ev.clientY;
  const p = pt.matrixTransform(BOARD.svg.getScreenCTM().inverse());
  const x = Math.floor(p.x / BOARD.cell), y = Math.floor(p.y / BOARD.cell);
  if (x < 0 || y < 0 || x >= BOARD.w || y >= BOARD.h) return null;
  return [x, y];
}

function legalDrop(id, origin, foot) {
  const cells = [];
  for (let dx = 0; dx < foot; dx++) for (let dy = 0; dy < foot; dy++)
    cells.push([origin[0] + dx, origin[1] + dy]);
  if (!cells.every((c) => BOARD.zone.has(c.join(",")))) return false;
  for (const [oid, t] of Object.entries(BOARD.toks)) {
    if (oid === id) continue;
    for (let dx = 0; dx < t.foot; dx++) for (let dy = 0; dy < t.foot; dy++)
      if (cells.some((c) => c[0] === t.pos[0] + dx && c[1] === t.pos[1] + dy)) return false;
  }
  return true;
}

// ------------------------------- battle & replay -----------------------------------

async function fight() {
  let payload;
  try {
    payload = await api(`/api/fortune/run/${RID}/battle`,
      { placements: PLACEMENTS }, $("#sands-error"));
  } catch (e) { return; }
  BATTLE = payload;
  S = payload.state;
  renderStatus();
  $("#deploy-controls").hidden = true;
  $("#replay-controls").hidden = false;
  $("#rp-done").hidden = true;
  $("#fw-log").hidden = false;
  startReplay(payload.battle);
}

// The same pure fold the Pit uses: absolute snapshots make any prefix exact.
function foldStep(e) {
  const t = BOARD.toks[e.actor];
  switch (e.kind) {
    case "spawn":
      if (!t) placeToken({ id: e.actor, name: e.actor, team: (e.info || e.actor[0]),
                           pos: e.pos, size: "Medium", hp: e.hp, max_hp: e.hp, ac: "?" }, false);
      else moveToken(e.actor, e.pos);
      (BOARD.toks[e.actor] || {}).max = e.hp;
      break;
    case "move": if (t) moveToken(e.actor, e.pos); break;
    case "damage": case "heal": case "survive":
      if (t) setHp(e.actor, e.hp, t.max || 1, e.hp > 0); break;
    case "death": if (t) setHp(e.actor, 0, t.max || 1, false); break;
  }
}

let RP = null;   // {events, log, i, timer, logShown}

function startReplay(b) {
  drawBoard(b.grid, null);
  for (const c of b.combatants) {
    placeToken(c, false);
    BOARD.toks[c.id].max = c.max_hp;
  }
  RP = { events: b.events, log: b.log, i: 0, timer: null, logShown: 0, winner: b.winner };
  $("#fw-log").textContent = "";
  $("#rp-round").textContent = "";
  togglePlay();
}

function togglePlay() {
  if (!RP) return;
  if (RP.timer) { clearInterval(RP.timer); RP.timer = null; $("#rp-play").textContent = "▶"; return; }
  $("#rp-play").textContent = "❚❚";
  RP.timer = setInterval(step, Number($("#rp-speed").value));
}

function step() {
  if (!RP) return;
  if (RP.i >= RP.events.length) { finishReplay(); return; }
  const e = RP.events[RP.i++];
  foldStep(e);
  if (e.round) $("#rp-round").textContent =
    `round ${e.round} — the crowd ages ${e.round * 10} years`;
  const upto = (e.log_index == null ? RP.logShown : e.log_index + 1);
  if (upto > RP.logShown) {
    $("#fw-log").textContent = RP.log.slice(0, upto).join("\n");
    $("#fw-log").scrollTop = $("#fw-log").scrollHeight;
    RP.logShown = upto;
  }
}

function skipToEnd() {
  if (!RP) return;
  while (RP.i < RP.events.length) { foldStep(RP.events[RP.i++]); }
  $("#fw-log").textContent = RP.log.join("\n");
  $("#fw-log").scrollTop = $("#fw-log").scrollHeight;
  finishReplay();
}

function finishReplay() {
  if (RP && RP.timer) { clearInterval(RP.timer); RP.timer = null; }
  $("#rp-play").textContent = "▶";
  const won = BATTLE.outcome.won;
  $("#sands-verdict").innerHTML = `<div class="verdict ${won ? "won" : "lost"}">
    ${won ? "Your corner stands — the touts weep." : "The sands take yours — a chip is spent."}
    <span class="odds-note">(${BATTLE.outcome.years} years passed outside)</span></div>`;
  $("#rp-done").hidden = false;
  $("#rp-done").textContent = won ? "to the wheel ✦" : (S.phase === "over" ? "face the ledger" : "back to the shop");
}

function afterBattle() {
  if (BATTLE.outcome.spin_owed) { openWheel(); return; }
  if (S.phase === "over") { renderOver(); show("fw-over"); loadAges(); return; }
  renderShop();
  show("fw-shop");
}

// ------------------------------- the wheel -----------------------------------------

const TAU = Math.PI / 180;
function sectorPath(r0, r1, a0, a1) {
  const p = (r, a) => [r * Math.sin(a * TAU), -r * Math.cos(a * TAU)];
  const [x0, y0] = p(r1, a0), [x1, y1] = p(r1, a1);
  const [x2, y2] = p(r0, a1), [x3, y3] = p(r0, a0);
  const large = a1 - a0 > 180 ? 1 : 0;
  return `M${x0},${y0} A${r1},${r1} 0 ${large} 1 ${x1},${y1}
          L${x2},${y2} A${r0},${r0} 0 ${large} 0 ${x3},${y3} Z`;
}

// ring sector types, 1-indexed by the server's d10 stops
const RINGS = [
  { id: "outer", r0: 72, r1: 104, types: ["none", "none", "none", "common", "common",
      "common", "common", "common", "common", "advance"] },
  { id: "middle", r0: 42, r1: 70, types: ["none", "uncommon", "uncommon", "uncommon",
      "uncommon", "uncommon", "uncommon", "uncommon", "uncommon", "advance"] },
  { id: "center", r0: 12, r1: 40, types: ["rare", "rare", "rare", "rare", "rare",
      "rare", "rare", "rare", "rare", "rare"] },
];
const SECTOR_FILL = { none: "#efe7d2", common: "rgba(184,145,46,.30)",
                      uncommon: "rgba(131,137,143,.38)", advance: "#b8912e",
                      rare: "rgba(184,145,46,.55)" };
const SECTOR_GLYPH = { none: "—", common: "◆", uncommon: "◈", advance: "★", rare: "✦" };

function wireWheel() {
  const svg = $("#fw-wheel");
  let parts = `<polygon points="-7,-114 7,-114 0,-100" fill="#8f1f1a"></polygon>`;
  for (const ring of RINGS) {
    let s = `<g class="ring" id="ring-${ring.id}">`;
    for (let i = 0; i < 10; i++) {
      const a0 = i * 36, a1 = (i + 1) * 36, ty = ring.types[i];
      const mid = (a0 + a1) / 2, rm = (ring.r0 + ring.r1) / 2;
      const gx = rm * Math.sin(mid * TAU), gy = -rm * Math.cos(mid * TAU);
      s += `<path d="${sectorPath(ring.r0, ring.r1, a0, a1)}" fill="${SECTOR_FILL[ty]}"
              stroke="#8a6d1f" stroke-width="1.2"></path>
            <text x="${gx}" y="${gy + 4}" text-anchor="middle" font-size="11"
              fill="${ty === "none" ? "#8f1f1a" : "#211d18"}">${SECTOR_GLYPH[ty]}</text>`;
    }
    s += `</g>`;
    parts += s;
  }
  parts += `<circle r="11" fill="#b8912e" stroke="#8a6d1f" stroke-width="2"></circle>`;
  svg.innerHTML = parts;
  $("#btn-spin").onclick = doSpin;
  $("#btn-wheel-done").onclick = closeWheel;
}

function openWheel() {
  for (const ring of RINGS) {
    const g = $(`#ring-${ring.id}`);
    g.style.transition = "none"; g.style.transform = "rotate(0deg)";
    void g.getBoundingClientRect();       // flush so the next spin animates
    g.style.transition = "";
  }
  $("#wheel-prize").innerHTML = "";
  $("#btn-spin").hidden = false;
  $("#btn-wheel-done").hidden = true;
  $("#fw-veil").hidden = false;
}

async function doSpin() {
  $("#btn-spin").hidden = true;
  let res;
  try { res = await api(`/api/fortune/run/${RID}/spin`, {}); }
  catch (e) { $("#wheel-prize").textContent = e.message; return; }
  S = res.state;
  const spinRing = (idx, stop, turns) => {
    const g = $(`#ring-${RINGS[idx].id}`);
    const target = -(turns * 360 + (stop - 0.5) * 36);
    g.style.transform = `rotate(${target}deg)`;
  };
  spinRing(0, res.spin.outer, 4);
  const seq = [];
  if (res.spin.middle != null) seq.push(() => spinRing(1, res.spin.middle, 5));
  if (res.spin.center != null) seq.push(() => spinRing(2, res.spin.center, 6));
  let delay = 2300;
  for (const fn of seq) { setTimeout(fn, delay); delay += 2300; }
  setTimeout(() => {
    const p = res.spin.prize;
    const lines = {
      none: "The wheel keeps your luck. The crowd sighs across a century.",
      common: `The outer ring pays: <strong>${esc(p.label)}</strong>.`,
      uncommon: `The middle ring turns for you: <strong>${esc(p.label)}</strong>.`,
      rare: `<strong>The center!</strong> Shemeshka's own ring yields <strong>${esc(p.label)}</strong>.`,
    };
    $("#wheel-prize").innerHTML = lines[res.spin.tier] || esc(p.label);
    $("#btn-wheel-done").hidden = false;
    renderStatus();
  }, delay + 300);
}

function closeWheel() {
  $("#fw-veil").hidden = true;
  renderShop();
  show("fw-shop");
}

// ------------------------------- game over & the Book of Ages ------------------------

function renderOver() {
  renderStatus();
  const years = S.years.toLocaleString();
  $("#over-line").innerHTML = `Three chips spent. <b>${esc(S.handle)}</b> leaves the arena
    with <b>${S.wins}</b> victor${S.wins === 1 ? "y" : "ies"} across ${S.history.length}
    battles — <b>${years} years</b> witnessed from the glass sphere. The Book of Ages
    remembers; Sigil, outside, has moved on without you.`;
  loadAges();
}

async function loadAges() {
  let rows;
  try { rows = await api("/api/fortune/leaderboard"); } catch (e) { return; }
  if (!rows.length) return;
  $("#ages-body").innerHTML = `<table><thead><tr>
      <th>stable master</th><th>wins</th><th>battles</th><th>years witnessed</th>
      <th>final stable</th><th>books</th><th>seed</th></tr></thead><tbody>` +
    rows.map((r, i) => `<tr class="${i === 0 ? "gold-row" : ""}">
      <td>${esc(r.handle)}</td><td>${r.wins}</td><td>${r.rounds}</td>
      <td>${r.years.toLocaleString()}</td>
      <td>${r.stable.map((m) => esc(m.name) + (m.elite ? " " + "★".repeat(m.elite) : ""))
            .join(", ") || "—"}</td>
      <td>${r.books.map(esc).join(" ")}</td><td>${r.seed}</td>
    </tr>`).join("") + `</tbody></table>`;
}

boot();
