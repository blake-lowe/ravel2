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
let TARGETING = null; // {label, filter, go} while picking one of your creatures

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

// Full change, every denomination shown: 1046 -> [10 gp][4 sp][6 cp]
function coinsHtml(cp) {
  const gp = Math.floor(cp / 100), sp = Math.floor((cp % 100) / 10), c = cp % 10;
  return `<span class="coin gp" title="gold">${gp}</span>
          <span class="coin sp" title="silver">${sp}</span>
          <span class="coin cp" title="copper">${c}</span>`;
}

function coinsFlat(cp) {
  const gp = Math.floor(cp / 100), sp = Math.floor((cp % 100) / 10), c = cp % 10;
  return [gp && `${gp} gp`, sp && `${sp} sp`, c && `${c} cp`].filter(Boolean).join(" ") || "0 cp";
}

function crStr(cr) {
  return cr === 0.125 ? "1/8" : cr === 0.25 ? "1/4" : cr === 0.5 ? "1/2" : String(cr);
}

// Token art: walk the candidate URLs on error, fall back to an initial.
function tokenImg(arts, name) {
  const letter = `<span class="mtoken letter">${esc(name[0] || "?")}</span>`;
  if (!arts || !arts.length) return letter;
  const chain = esc(JSON.stringify(arts.slice(1)));
  return `<img class="mtoken" src="${esc(arts[0])}" alt=""
    data-rest='${chain}' onerror="fwArtErr(this)">`;
}
window.fwArtErr = function (img) {
  const rest = JSON.parse(img.dataset.rest || "[]");
  if (rest.length) { img.dataset.rest = JSON.stringify(rest.slice(1)); img.src = rest[0]; }
  else {
    const sp = document.createElement("span");
    sp.className = "mtoken letter";
    sp.textContent = (img.closest("[data-name]")?.dataset.name || "?")[0];
    img.replaceWith(sp);
  }
};

function show(section) {
  for (const id of ["fw-lobby", "fw-shop", "fw-sands", "fw-over"])
    $("#" + id).hidden = id !== section;
  $("#fw-status").hidden = section === "fw-lobby";
  $("#fw-ages").hidden = section !== "fw-lobby";   // the Book of Aeons stays at the gate
  hideStatblock();                     // whatever was hovered just left the stage
}

// ---------------------- a name in the cant of the Cage -------------------------
// Planescape slang (theplanardm.com/planar-slang) plus the wider chant of the
// multiverse — dungeon vernacular, planar scars, and famous bad decisions.

const CANT_ADJ = ["Barmy", "Peery", "Clueless", "Leatherheaded", "Addle-Coved",
  "Jink-Flush", "Well-Lanned", "Cage-Born", "Gate-Touched", "Dustbound",
  "Bone-Boxed", "Bloodless",
  "Underdark-Lost", "Feywild-Touched", "Dragon-Hoarding", "Mind-Flayed",
  "Wild-Magicked", "Beholder-Eyed", "Styx-Dipped", "Tomb-Delving",
  "Owlbear-Bitten", "Kobold-Cunning", "Illithid-Addled", "Modron-Minded",
  "Abyss-Marked", "Vecna-Handed", "Tarrasque-Fleeing", "Mimic-Bitten",
  "Spellplagued", "Nine-Fingered"];
const CANT_NOUN = ["Berks", "Cutters", "Bloods", "Bashers", "Sods", "Bubbers",
  "Touts", "Knights of the Post", "Mimirs", "Primes", "Spivs", "Cagers",
  "Murderhobos", "Sellswords", "Torchbearers", "Meatshields", "Hirelings",
  "Planewalkers", "Dungeoneers", "Grave-Robbers", "Owlbears", "Mimics",
  "Kobolds", "Flumphs", "Harpers", "Zhents", "Red Wizards", "Githzerai"];
let NAME_PICK = { adj: null, noun: null };

function dealNames() {
  const deal = (pool) => {
    const bag = [...pool];
    const out = [];
    while (out.length < 3) out.push(bag.splice(Math.floor(Math.random() * bag.length), 1)[0]);
    return out;
  };
  const adjs = deal(CANT_ADJ), nouns = deal(CANT_NOUN);
  NAME_PICK = { adj: adjs[0], noun: nouns[0] };
  const col = (el, words, key) => {
    el.innerHTML = words.map((w) =>
      `<button type="button" class="pick ${NAME_PICK[key] === w ? "on" : ""}"
         data-word="${esc(w)}">${esc(w)}</button>`).join("");
    el.querySelectorAll(".pick").forEach((b) => b.onclick = () => {
      NAME_PICK[key] = b.dataset.word;
      el.querySelectorAll(".pick").forEach((x) => x.classList.toggle("on", x === b));
      $("#name-preview").textContent = `${NAME_PICK.adj} ${NAME_PICK.noun}`;
    });
  };
  col($("#pick-adj"), adjs, "adj");
  col($("#pick-noun"), nouns, "noun");
  $("#name-preview").textContent = `${NAME_PICK.adj} ${NAME_PICK.noun}`;
}

// ------------------------------- lobby ----------------------------------------

async function boot() {
  META = await api("/api/fortune/meta");
  const hasMM = META.books.some((b) => b.label === "MM");
  $("#lob-books").innerHTML = META.books.map((b) => `
    <label class="check"><input type="checkbox" value="${esc(b.label)}"
      ${!hasMM || b.label === "MM" ? "checked" : ""}>
      ${esc(b.label)} <span class="odds-note">(${b.monsters})</span></label>`).join("");
  dealNames();
  $("#btn-reshuffle").onclick = dealNames;
  $("#lob-enter").onclick = newRun;
  $("#btn-again").onclick = () => { localStorage.removeItem("fw-run"); RID = null; loadAges(); show("fw-lobby"); };
  const restart = $("#btn-restart");
  restart.onclick = () => {
    if (!restart.classList.contains("armed")) {
      restart.classList.add("armed");
      restart.textContent = "✕ abandon the run?";
      setTimeout(() => { restart.classList.remove("armed"); restart.textContent = "✕ restart"; }, 3000);
      return;
    }
    restart.classList.remove("armed");
    restart.textContent = "✕ restart";
    localStorage.removeItem("fw-run"); RID = null; S = null;
    dealNames(); loadAges(); show("fw-lobby");
  };
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
  const body = { books, handle: `${NAME_PICK.adj} ${NAME_PICK.noun}` };
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

// ------------------------------- status row ------------------------------------

function renderStatus() {
  $("#st-purse").innerHTML = coinsHtml(S.purse_cp);
  $("#st-lives").innerHTML = Array.from({ length: S.lives_max }, (_, i) =>
    `<span class="chip ${i < S.lives ? "" : "spent"}"></span>`).join("");
  $("#st-round").textContent = S.round;
  $("#st-cap").textContent = `CR ${S.cap}`;
  const losses = S.history.filter((h) => !h.won).length;
  $("#st-record").textContent = `${S.wins} – ${losses}`;
  $("#st-handle").textContent = S.handle;
}

// ------------------------------- the shop ---------------------------------------

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
  const el = $("#shop-error");
  el.innerHTML = `${esc(t.label)} — pick one of your creatures
    <button type="button" id="btn-cancel-target">cancel</button>
    ${t.note ? `<br><span class="odds-note">${esc(t.note)}</span>` : ""}`;
  $("#btn-cancel-target").onclick = () => {
    TARGETING = null;
    el.textContent = "";
    renderStable();
  };
  hideStatblock();                     // the stable re-renders under the pointer
  renderStable();
}

function renderShop() {
  hideStatblock();                     // cards are about to move or vanish
  renderStatus();
  renderStable();
  renderSetProgress();
  renderStock();
  renderBank();
  renderBattlePanel();
  $("#btn-reroll").textContent = "Reroll the offerings (5 sp)";
  $("#btn-sands").disabled = !S.stable.some((m) => !m.standby);
  if (S.phase === "over") { renderOver(); show("fw-over"); }
}

// One card shape for owned creatures — same skeleton as the for-sale cards.
function memberCard(m, i) {
  const stars = m.elite ? `<span class="stars">${"★".repeat(m.elite)}</span>` : "";
  const items = m.items.map((it) =>
    `<span class="tag" title="${esc(it.effect)} — ${esc(it.blurb)}">${esc(it.name)}</span>`).join("");
  const cap = S.train_cap || 3;
  const twin = S.stable.some((o, j) => j !== i && o.name === m.name
    && m.elite + o.elite + 1 <= cap);        // a merge may not pass 3 stars
  const fusable = S.stable.some((o, j) => j !== i && canFuse(m, o));
  const targetable = TARGETING && (!TARGETING.filter || TARGETING.filter(m, i));
  const fieldFull = S.stable.filter((x) => !x.standby).length >= S.team_cap;
  return `<div class="slot ${targetable ? "targetable" : ""}"
               data-name="${esc(m.name)}" ${targetable ? `data-pick="${i}"` : ""}>
    ${m.standby ? `<span class="slot-tag">standby</span>` : ""}
    ${tokenImg(m.art, m.name)}
    <div class="mname">${esc(m.name)} ${stars}</div>
    <div class="mmeta">CR ${crStr(m.cr)} · ${esc(m.size)}</div>
    <div class="mmeta">${esc(m.type)}${m.alignment ? " · " + esc(alignStr(m.alignment)) : ""}</div>
    <div class="mmeta">${m.hp} hp · AC ${m.ac} · ${speedStr(m)}</div>
    <div class="tags">${items}</div>
    ${targetable ? `<div class="btnrow bottom"><button>choose</button></div>` : `
      <div class="btnrow bottom">
        <a class="btnlink" href="/bestiary#${encodeURIComponent(m.name)}" target="_blank"
           title="the full chant, in the Bestiary">View in Bestiary</a>
      </div>
      <div class="btnrow">
        <button data-sell="${i}" title="half of all coin invested comes back: ${coinsFlat(Math.floor(m.invested_cp / 2))}">sell</button>
        ${m.standby
          ? `<button data-field="${i}" title="take the field">field</button>`
          : `<button data-bench="${i}" title="${fieldFull && S.stable.some((x) => x.standby)
              ? "trade places with the standby stall" : "wait out the battles"}">standby</button>`}
        ${twin ? `<button data-train="${i}" title="merge a twin into this one: +1 AC, +1 damage">train ★</button>` : ""}
        ${fusable ? `<button data-fuse="${i}"
            title="fuse with a creature of the same kind or creed into stronger stock">merge ◇</button>` : ""}
      </div>`}
  </div>`;
}

function renderStable() {
  const row = $("#stable-row");
  const active = [];
  let standbyCard = null;
  S.stable.forEach((m, i) => {
    if (m.standby) standbyCard = memberCard(m, i);
    else active.push(memberCard(m, i));
  });
  while (active.length < S.team_cap) active.push(`<div class="slot empty"></div>`);
  if (!standbyCard)
    standbyCard = `<div class="slot empty"><span class="slot-tag">standby</span></div>`;
  row.innerHTML = active.join("") + `<div class="standby-divider"></div>` + standbyCard;
  row.querySelectorAll("[data-sell]").forEach((b) =>
    b.onclick = (ev) => { ev.stopPropagation(); act({ action: "sell", target: +b.dataset.sell }); });
  row.querySelectorAll("[data-train]").forEach((b) =>
    b.onclick = (ev) => {
      ev.stopPropagation();
      const i = +b.dataset.train;
      beginTargeting({
        label: `Training ${S.stable[i].name}: pick the twin to merge in`,
        filter: (m, j) => j !== i && m.name === S.stable[i].name
          && S.stable[i].elite + m.elite + 1 <= (S.train_cap || 3),
        go: (j) => act({ action: "train", target: i, other: j }),
      });
    });
  row.querySelectorAll("[data-fuse]").forEach((b) =>
    b.onclick = (ev) => {
      ev.stopPropagation();
      const i = +b.dataset.fuse;
      const m = S.stable[i];
      beginTargeting({
        label: `Merging ${m.name}: pick its partner (same kind or creed)`,
        note: `two creatures sharing a creature type or an alignment fuse into one `
          + `of CR = 1 + the average of their CRs, capped at the stock tier `
          + `(CR ${S.cap}); items carry over, training does not`,
        filter: (o, j) => j !== i && canFuse(m, o),
        go: (j) => act({ action: "fuse", target: i, other: j }),
      });
    });
  row.querySelectorAll("[data-bench]").forEach((b) =>
    b.onclick = (ev) => { ev.stopPropagation();
      act({ action: "bench", target: +b.dataset.bench }); });
  row.querySelectorAll("[data-field]").forEach((b) =>
    b.onclick = (ev) => {
      ev.stopPropagation();
      const i = +b.dataset.field;
      const room = S.stable.filter((x) => !x.standby).length < S.team_cap;
      if (room) { act({ action: "bench", target: i }); return; }
      beginTargeting({
        label: `Fielding ${S.stable[i].name}: pick who steps down`,
        filter: (m, j) => !m.standby,
        go: (j) => act({ action: "bench", target: j }),   // benching j trades places
      });
    });
  row.querySelectorAll("[data-pick]").forEach((card) =>
    card.onclick = () => TARGETING.go(+card.dataset.pick));
}

// Collecting a set: 5 owned creatures of one type summon an overtier specimen.
// Show the closest set still unclaimed — "2/5 aberrations".
const TYPE_PLURAL = { undead: "undead", fey: "fey" };
function typePlural(t) {
  return TYPE_PLURAL[t] || (t.endsWith("y") ? t.slice(0, -1) + "ies" : t + "s");
}

function renderSetProgress() {
  const el = $("#set-progress");
  if (!el) return;
  const need = S.set_size || 5;
  const counts = {};
  for (const m of S.stable) {
    const t = (m.type || "").split("(")[0].trim().toLowerCase();
    if (!t || (S.sets_awarded || []).includes(t)) continue;
    counts[t] = (counts[t] || 0) + 1;
  }
  const best = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
  el.textContent = best ? `${Math.min(best[1], need)}/${need} ${typePlural(best[0])}` : "";
  el.hidden = !best;
}

// Fusion (SPEC 18.8.7): two creatures of one kind or one creed merge into a
// stronger one. Mirror the engine's grouping keys so the merge menu offers
// exactly the partners the house will accept.
function typeKeyOf(m) {
  return (m.type || "").split("(")[0].trim().toLowerCase() || "misc";
}
function alignKeyOf(m) {
  const a = (m.alignment || "").trim();
  if (!a) return "unaligned";
  if (/[a-z]/.test(a)) return a.toLowerCase();
  const W = { L: "lawful", N: "neutral", C: "chaotic", G: "good", E: "evil",
              U: "unaligned", A: "any" };
  return a.split(/\s+/).map((t) => W[t] || "").filter(Boolean).join(" ") || "unaligned";
}
function canFuse(a, b) {
  return typeKeyOf(a) === typeKeyOf(b) || alignKeyOf(a) === alignKeyOf(b);
}

// 5e.tools alignment codes ("L E", "U", "A") -> words; prose passes through
const ALIGN_WORD = { L: "lawful", N: "neutral", C: "chaotic", G: "good", E: "evil",
                     U: "unaligned", A: "any alignment", NX: "neutral", NY: "neutral" };
function alignStr(a) {
  if (!a) return "";
  if (/[a-z]/.test(a)) return a;
  return a.split(/\s+/).map((t) => ALIGN_WORD[t] || t.toLowerCase()).join(" ");
}

// A small inked wing (inline SVG so it renders the same on every platform).
const WING_SVG = `<svg class="wing" viewBox="0 0 20 12" width="13" height="8"
  aria-label="flies" role="img"><path fill="currentColor"
  d="M19,1 Q11,0 5,4 Q2,6 1,11 Q6,9 9,9 Q7,9 6,9.4 Q10,6.5 13,6 Q11,6 10,6.2
     Q14,3.5 19,1 Z"/></svg>`;

function speedStr(s) {
  const best = Math.max(s.speed || 0, s.fly || 0, s.swim || 0);
  const glyph = s.fly && s.fly >= (s.speed || 0) ? WING_SVG
    : s.swim && s.swim >= (s.speed || 0) ? "≈" : "";
  return `${best} ft${glyph ? " " + glyph : ""}`;
}

function renderStock() {
  const row = $("#stock-row");
  row.innerHTML = S.shop.monsters.map((s, i) => {
    if (!s) return `<div class="slot empty"></div>`;
    const owned = S.stable.findIndex((m) => m.name === s.name
      && m.elite < (S.train_cap || 3));
    const topTier = !s.overtier && s.cr === S.cap;  // book CR at the stock tier
    return `<div class="slot ${s.frozen ? "is-frozen" : ""} ${topTier ? "top-tier" : ""}
                 ${s.overtier ? "overtier" : ""}" data-name="${esc(s.name)}">
      ${s.overtier
        ? `<span class="slot-tag over" title="earned stock from beyond the tier — it waits until bought">overtier</span>`
        : `<button class="freeze ${s.frozen ? "on" : ""}" data-freeze="${i}"
             title="${s.frozen ? "unfreeze" : "freeze through the reroll"}">❄</button>`}
      ${tokenImg(s.art, s.name)}
      <div class="mname">${esc(s.name)}</div>
      <div class="mmeta">CR ${crStr(s.cr)} · ${esc(s.size)}</div>
      <div class="mmeta">${esc(s.type)}${s.alignment ? " · " + esc(alignStr(s.alignment)) : ""}</div>
      <div class="mmeta">${s.hp} hp · AC ${s.ac} · ${speedStr(s)}</div>
      <div class="price">${esc(s.price)}</div>
      <div class="btnrow bottom">
        <a class="btnlink" href="/bestiary#${encodeURIComponent(s.name)}" target="_blank"
           title="the full chant, in the Bestiary">View in Bestiary</a>
      </div>
      <div class="btnrow">
        <button data-buy="${i}">buy</button>
        ${owned >= 0 ? `<button data-buytrain="${i}" data-tgt="${owned}"
            title="feed this copy straight to yours: +1 AC, +1 damage (max ★★★)">train ★</button>` : ""}
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
    if (!s) return `<div class="slot equip empty"></div>`;
    return `<div class="slot equip ${s.frozen ? "is-frozen" : ""}">
      <span class="rib ${esc(s.rarity)}"></span>
      <button class="freeze ${s.frozen ? "on" : ""}" data-ifreeze="${i}"
        title="${s.frozen ? "unfreeze" : "freeze through the reroll"}">❄</button>
      <span class="mtoken letter equip-glyph ${esc(s.rarity)}">◈</span>
      <div class="mname">${esc(s.name)}</div>
      <div class="ieffect">${esc(s.effect)}</div>
      <div class="iflavor">${esc(s.blurb)}</div>
      <div class="mmeta">${esc(s.rarity)}</div>
      <div class="price">${esc(s.price)}</div>
      <div class="btnrow bottom"><button data-ibuy="${i}">buy</button></div>
    </div>`;
  }).join("");
  $("#item-shelf").querySelectorAll("[data-ibuy]").forEach((b) =>
    b.onclick = () => {
      const it = S.shop.items[+b.dataset.ibuy];
      beginTargeting({
        label: it.train
          ? `${it.name}: which creature does the exercises?`
          : `Buying ${it.name}: which creature carries it?`,
        filter: it.train ? (m) => m.elite < (S.train_cap || 3)
                         : (m) => m.items.length < 3,
        go: (j) => act({ action: "buy_item", slot: +b.dataset.ibuy, target: j }),
      });
    });
  $("#item-shelf").querySelectorAll("[data-ifreeze]").forEach((f) =>
    f.onclick = () => act({ action: "freeze", kind: "item", slot: +f.dataset.ifreeze }));
}

// Wheel winnings sit under the standby stall until claimed onto a creature.
function renderBank() {
  const el = $("#bank-row");
  if (!S.bank.length) { el.innerHTML = ""; return; }
  el.innerHTML = `<div class="won-head">Won on the wheel</div><div class="won-row">` +
    S.bank.map((it, i) => `
      <div class="slot equip won">
        <span class="rib ${esc(it.rarity)}"></span>
        <span class="mtoken letter equip-glyph ${esc(it.rarity)}">◈</span>
        <div class="mname">${esc(it.name)}</div>
        <div class="ieffect">${esc(it.effect)}</div>
        <div class="iflavor">${esc(it.blurb)}</div>
        <div class="price">free — the wheel's gift</div>
        <div class="btnrow bottom"><button data-bank="${i}">claim</button></div>
      </div>`).join("") + `</div>`;
  el.querySelectorAll("[data-bank]").forEach((b) =>
    b.onclick = () => {
      const it = S.bank[+b.dataset.bank];
      beginTargeting({
        label: it.train
          ? `${it.name}: which creature does the exercises?`
          : `Claiming ${it.name}: which creature carries it?`,
        filter: it.train ? (m) => m.elite < (S.train_cap || 3)
                         : (m) => m.items.length < 3,
        go: (j) => act({ action: "attach", slot: +b.dataset.bank, target: j }),
      });
    });
}

const WEATHER_GLYPH = { clear: "☀ clear", fog: "▒ fog", rain: "☂ rain", wind: "≋ wind" };
// what each sky actually does on the sands (engine truth, plainly stated)
const WEATHER_TIP = {
  clear: "clear skies — no effect on the fighting",
  fog: "fog: the whole field is heavily obscured — attacks against foes you can't see suffer disadvantage, unseen attackers strike with advantage; keen senses (blindsight, tremorsense) shine",
  rain: "rain: open flames are doused",
  wind: "strong wind: ranged attacks suffer disadvantage, nonmagical flyers are grounded, open flames are blown out",
};

function renderBattlePanel() {
  const rows = S.foresight.map((f, i) => `
    <tr class="${i === 0 ? "now" : "later"}">
      <td>${i === 0 ? "next" : "battle " + f.round}</td>
      <td>${esc(f.map || "the open floor")}
          ${f.boss ? `<span class="boss-mark" title="a single huge monster carries the house's whole purse">boss</span>` : ""}</td>
      <td title="${esc(WEATHER_TIP[f.weather] || "")}">${WEATHER_GLYPH[f.weather] || esc(f.weather)}</td>
    </tr>`).join("");
  $("#next-battle").innerHTML = `<table class="fore-table">${rows}</table>`;
  renderBill();
}

function renderBill() {
  const el = $("#the-bill");
  if (S.scouted && S.enemy.length) {
    el.innerHTML = `<div class="col-title">The Opposition</div>` +
      S.enemy.map((e) => `<span class="bill-chip" data-name="${esc(e.name)}">${e.count}× ${esc(e.name)}
        <span class="crtag">(CR ${crStr(e.cr)})</span></span>`).join("");
  } else {
    el.innerHTML = `<span class="odds-note">the chant of your opposition is shrouded.</span><br>
      <button id="btn-scout">Divine the future (5 sp)</button>`;
    const btn = $("#btn-scout");
    if (btn) btn.onclick = () => act({ action: "scout" });
  }
}

// ------------------------------- the sands ---------------------------------------

function wireSands() {
  $("#btn-back-shop").onclick = () => { renderShop(); show("fw-shop"); };
  $("#btn-gong").onclick = fight;
  $("#rp-done").onclick = afterBattle;
}

// The battle itself replays through the Blood Pit's own machinery (replay.js),
// gold corner vs the house's ink.
let REPLAY = null;
function ensureReplay() {
  if (REPLAY) return REPLAY;
  REPLAY = RavelReplay.create({
    els: {
      board: $("#board"), scrub: $("#scrub"), btnPlay: $("#btn-play"),
      btnPrev: $("#btn-prev"), btnNext: $("#btn-next"), btnStart: $("#btn-start"),
      btnEnd: $("#btn-end"), btnPrevRound: $("#btn-prev-round"),
      btnNextRound: $("#btn-next-round"), speed: $("#speed"),
      roundInd: $("#round-ind"), log: $("#fightlog"), initiative: $("#initiative"),
      legend: $("#legend"),
    },
    corners: { A: { name: "Gold", color: "#8a6d1f", prefix: "G" },
               B: { name: "House", color: "#211d18", prefix: "H" } },
    onPosition: (atEnd) => {
      if (!BATTLE) return;
      if (atEnd) {
        const won = BATTLE.outcome.won;
        const n = BATTLE.battle.rounds;
        $("#sands-verdict").innerHTML = `<div class="verdict ${won ? "won" : "lost"}">
          ${won ? "Won" : "Lost"} in ${n} round${n === 1 ? "" : "s"}</div>`;
        $("#rp-done").hidden = false;
        $("#rp-done").textContent = won ? "to the wheel ✦"
          : (S.phase === "over" ? "face the ledger" : "back to the offerings");
      } else {
        $("#sands-verdict").innerHTML = "";
        $("#rp-done").hidden = true;
      }
    },
  });
  return REPLAY;
}

async function openSands() {
  try { DEPLOY = await api(`/api/fortune/run/${RID}/deploy`); }
  catch (e) { $("#shop-error").textContent = e.message; return; }
  PLACEMENTS = S.stable.filter((m) => !m.standby).map(() => null);
  BATTLE = null;
  $("#sands-title").textContent = "Preparation";
  $("#deploy-wrap").hidden = false;
  $("#battle-wrap").hidden = true;
  $("#sands-verdict").innerHTML = "";
  renderSandsBrief();
  drawBoard(DEPLOY.grid, new Set(DEPLOY.zone.map((c) => c.join(","))));
  // deployment shows only YOUR creatures at their default cells
  for (const c of DEPLOY.combatants) placeToken(c, true);
  renderDeployRoster();
  show("fw-sands");
}

// Abbreviated cards for the creatures being deployed, badge matching the board.
function renderDeployRoster() {
  $("#deploy-roster").innerHTML = `<div class="col-title">Your side</div>` +
    DEPLOY.combatants.map((c) => `
      <div class="dr-card" data-name="${esc(c.name)}">
        <span class="dr-badge">${esc("G" + c.id.slice(1))}</span>
        ${tokenImg(c.token_art, c.name)}
        <span class="dr-meta"><b>${esc(c.name)}</b><br>
          AC ${c.ac} · ${c.max_hp} hp</span>
      </div>`).join("");
}

function renderSandsBrief() {
  const opp = DEPLOY.scouted && DEPLOY.enemy.length
    ? DEPLOY.enemy.map((e) => `<span class="bill-chip" data-name="${esc(e.name)}">${e.count}× ${esc(e.name)}</span>`).join(" ") + " await."
    : `the far corner keeps to the dark
       <button id="btn-scout2">divine the future (5 sp)</button>`;
  $("#sands-brief").innerHTML = `
    <b>Battle ${DEPLOY.round}</b> — ${esc(DEPLOY.map || "the open floor")},
    <span title="${esc(WEATHER_TIP[DEPLOY.weather] || "")}">${WEATHER_GLYPH[DEPLOY.weather] || esc(DEPLOY.weather)}</span><br>
    <span class="odds-note">drag your creatures anywhere in the gilded ground,
    then sound the gong.</span><br>${opp}`;
  const b2 = $("#btn-scout2");
  if (b2) b2.onclick = async () => {
    try { S = await api(`/api/fortune/run/${RID}/action`, { action: "scout" }, $("#sands-error")); }
    catch (e) { return; }
    DEPLOY.scouted = true;
    DEPLOY.enemy = S.enemy;
    renderStatus();
    renderSandsBrief();
  };
}

let BOARD = null;  // {svg, cell, w, h, zone, toks: {id: {g, foot, pos, max}}}

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
  const layer = (cls, cells) => {
    for (const [x, y] of cells) {
      const r = document.createElementNS(NS, "rect");
      r.setAttribute("x", x * cell); r.setAttribute("y", y * cell);
      r.setAttribute("width", cell); r.setAttribute("height", cell);
      r.setAttribute("class", `cell ${cls}`);
      svg.appendChild(r);
    }
  };
  const base = [];
  for (let y = 0; y < grid.h; y++) for (let x = 0; x < grid.w; x++) base.push([x, y]);
  layer("", base);
  if (zone) layer("zone", [...zone].map((s) => s.split(",").map(Number)));
  layer("wall", grid.walls || []);
  layer("water", grid.water || []);
  layer("difficult", grid.difficult || []);
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
    <text y="4" font-size="${r * 0.62}">${esc("G" + c.id.slice(1))}</text>
    <rect class="hpback" x="${-r + 2}" y="${r - 4}" width="${2 * r - 4}" height="3"></rect>
    <rect class="hpbar" x="${-r + 2}" y="${r - 4}" width="${2 * r - 4}" height="3"></rect>
    <title>${esc(c.name)} — AC ${c.ac}, ${c.hp}/${c.max_hp} hp</title>`;
  BOARD.svg.appendChild(g);
  const tok = { g, foot, hpw: 2 * r - 4, pos: c.pos.slice(), name: c.name, max: c.max_hp };
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

function setHp(id, hp, alive) {
  const t = BOARD.toks[id];
  if (!t) return;
  t.g.querySelector(".hpbar").setAttribute("width",
    Math.max(0, t.hpw * hp / Math.max(1, t.max || 1)));
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
      if (cell) moveToken(id, [cell[0] - Math.floor(tok.foot / 2),
                               cell[1] - Math.floor(tok.foot / 2)]);
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      tok.g.classList.remove("dragging");
      if (legalDrop(id, tok.pos, tok.foot)) {
        PLACEMENTS[idx] = tok.pos.slice();
        $("#sands-error").textContent = "";
      } else {
        $("#sands-error").textContent = "the pit hands wave you off — that ground is not yours";
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
  // no renderStatus() here: the chips would spoil the verdict — the status row
  // keeps its pre-battle face until we return to the offerings
  $("#sands-title").textContent = "The Field of Battle";
  $("#deploy-wrap").hidden = true;
  $("#battle-wrap").hidden = false;
  $("#rp-done").hidden = true;
  const rp = ensureReplay();
  rp.load(payload.battle);
  rp.play();               // an auto battler auto-plays; the scrubber is all yours
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

// Ring geometry only — the sector layouts come from /api/fortune/meta, so the
// picture is exactly what the engine rolls (no-prize sectors spread apart).
const RING_GEO = [
  { id: "outer", r0: 72, r1: 104 },
  { id: "middle", r0: 42, r1: 70 },
  { id: "center", r0: 12, r1: 40 },
];
let RINGS = [];
const SECTOR_FILL = { none: "#efe7d2", common: "rgba(184,145,46,.30)",
                      uncommon: "rgba(131,137,143,.38)", advance: "#b8912e",
                      rare: "rgba(184,145,46,.55)" };
const SECTOR_GLYPH = { none: "—", common: "◆", uncommon: "◈", advance: "★", rare: "✦" };

function wireWheel() {
  const layouts = (META && META.wheel) || {};
  RINGS = RING_GEO.map((g) => ({
    ...g, types: layouts[`${g.id}_ring`] || Array(10).fill("rare"),
  }));
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
    g.style.transform = `rotate(${-(turns * 360 + (stop - 0.5) * 36)}deg)`;
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
    $("#btn-wheel-done").textContent = res.spin.tier === "none"
      ? "return to the offerings" : "collect & return to the offerings";
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
  $("#over-line").innerHTML = `Three chips spent. <b>${esc(S.handle)}</b> leaves the arena
    with <b>${S.wins}</b> victor${S.wins === 1 ? "y" : "ies"} across ${S.history.length}
    battles. The Book of Aeons remembers.`;
  $("#inscribe-row").hidden = false;
  $("#inscribe-done").textContent = "";
  $("#over-initials").value = "";
  $("#btn-inscribe").onclick = async () => {
    try {
      const r = await api(`/api/fortune/run/${RID}/inscribe`,
        { initials: $("#over-initials").value });
      $("#inscribe-done").textContent = `${r.initials} — the Book remembers.`;
      $("#inscribe-row").hidden = true;
      loadAges();
    } catch (e) { $("#inscribe-done").textContent = e.message; }
  };
  loadAges();
}

// The full card, exactly as the shop shows it, for a creature at the gate.
function aeonCard(m) {
  const stars = m.elite ? ` <span class="stars">${"★".repeat(m.elite)}</span>` : "";
  const legacy = m.ac === undefined;      // rows carved before the card era
  const items = (m.items || []).map((it) => typeof it === "string"
    ? `<span class="tag">${esc(it)}</span>`
    : `<span class="tag" title="${esc(it.effect || "")} — ${esc(it.blurb || "")}">${esc(it.name)}</span>`
  ).join("");
  return `<div class="slot ${m.standby ? "aeon-standby" : ""}" data-name="${esc(m.name)}">
    ${m.standby ? `<span class="slot-tag">standby</span>` : ""}
    ${tokenImg(m.art, m.name)}
    <div class="mname">${esc(m.name)}${stars}</div>
    ${legacy ? "" : `
      <div class="mmeta">CR ${crStr(m.cr)} · ${esc(m.size)}</div>
      <div class="mmeta">${esc(m.type || "")}${m.alignment ? " · " + esc(alignStr(m.alignment)) : ""}</div>
      <div class="mmeta">${m.hp} hp · AC ${m.ac} · ${speedStr(m)}</div>`}
    <div class="tags">${items}</div>
  </div>`;
}

async function loadAges() {
  let rows;
  try { rows = await api("/api/fortune/leaderboard"); } catch (e) { return; }
  if (!rows.length) return;
  const podium = ["podium-gold", "podium-silver", "podium-bronze"];
  $("#ages-body").innerHTML = rows.map((r, i) => `
    <div class="aeon-entry ${i === 0 ? "first" : ""} ${podium[i] || ""}">
      <div class="aeon-id">
        <span class="aeon-mark">${esc(r.initials || "—")}</span>
        <div class="aeon-who"><b>${esc(r.handle)}</b><br>
          <span class="odds-note">${r.created ? new Date(r.created).toLocaleDateString() : ""}
            · seed ${r.seed}<br>${r.books.map(esc).join(" ")}</span></div>
      </div>
      <div class="aeon-stable">${[...(r.stable || [])]
        .sort((a, b) => (a.standby ? 1 : 0) - (b.standby ? 1 : 0))   // standby last
        .map(aeonCard).join("")
        || `<span class="odds-note">the stalls stood empty</span>`}</div>
      <div class="aeon-wins"><span class="lbl">wins</span><span class="val">${r.wins}</span></div>
    </div>`).join("");
}

// --------------------- hover: the full stat block, anywhere ---------------------
// Rest the pointer on any creature card — stable, offerings, deploy roster, the
// Book of Aeons — and the full chant appears beside it (the Bestiary's own
// renderer, statblock.js). Fetched once per creature, then cached.

const SB_CACHE = new Map();
let SB_TIMER = null;   // pending show (hover intent)
let SB_HIDE = null;    // pending hide (grace period to reach the popup)
let SB_CARD = null;    // the card the pointer is resting on

function wireStatblockHover() {
  const pop = document.createElement("div");
  pop.id = "fw-statblock";
  pop.hidden = true;
  document.body.appendChild(pop);
  document.addEventListener("mouseover", (ev) => {
    if (!ev.target.closest) return;
    if (pop.contains(ev.target)) { clearTimeout(SB_HIDE); return; }   // reading it
    const card = ev.target.closest(".fw [data-name]");
    if (card === SB_CARD) { clearTimeout(SB_HIDE); return; }          // back again
    if (!card) return;
    hideStatblock();                        // a different card: switch at once
    SB_CARD = card;
    SB_TIMER = setTimeout(() => showStatblock(card), 350);   // hover intent
  });
  document.addEventListener("mouseout", (ev) => {
    if (!SB_CARD) return;
    const to = ev.relatedTarget;
    if (to && (SB_CARD.contains(to) || pop.contains(to))) return;
    if (pop.hidden) { hideStatblock(); return; }   // not shown yet: just cancel
    // shown: linger long enough for the pointer to cross into the popup
    clearTimeout(SB_HIDE);
    SB_HIDE = setTimeout(hideStatblock, 300);
  });
  // page scroll dismisses the chant — but scrolling the chant itself must not
  window.addEventListener("scroll", (ev) => {
    if (ev.target instanceof Node && pop.contains(ev.target)) return;
    hideStatblock();
  }, true);
}

function hideStatblock() {
  clearTimeout(SB_TIMER);
  clearTimeout(SB_HIDE);
  SB_CARD = null;
  const pop = $("#fw-statblock");
  if (pop) pop.hidden = true;
}

async function showStatblock(card) {
  const name = (card.dataset.name || "").replace(/\s*★+\s*$/, "").trim();
  if (!name) return;
  let d = SB_CACHE.get(name);
  if (!d) {
    try { d = await api(`/api/monsters/${encodeURIComponent(name)}`); }
    catch (e) { return; }              // an unknown name shows nothing, quietly
    SB_CACHE.set(name, d);
  }
  if (SB_CARD !== card || !card.isConnected) return;  // moved on / re-rendered away
  const pop = $("#fw-statblock");
  pop.innerHTML = RavelStatblock.statblockHtml({ statblock: d.statblock, images: [] });
  pop.hidden = false;
  pop.scrollTop = 0;                   // each chant starts at its first line
  // beside the card: to the right when there's room, else the left, clamped
  const r = card.getBoundingClientRect();
  const pw = pop.offsetWidth, ph = pop.offsetHeight;
  let x = r.right + 12;
  if (x + pw > window.innerWidth - 8) x = r.left - pw - 12;
  if (x < 8) x = Math.max(8, Math.min(window.innerWidth - pw - 8, r.left));
  const y = Math.max(8, Math.min(r.top, window.innerHeight - ph - 8));
  pop.style.left = `${Math.round(x)}px`;
  pop.style.top = `${Math.round(y)}px`;
}

boot();
wireStatblockHover();
