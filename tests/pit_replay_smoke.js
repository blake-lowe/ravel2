/* Cross-language replay check: fold the full event stream with the browser's
   exact fold code and require the result to match the engine's survivors —
   identical HP, alive-ness, and monotonic round/log stamps.
   Usage: node pit_replay_smoke.js <battle.json>  (a /api/battle payload) */
"use strict";
const fs = require("fs");
const path = require("path");

const { foldEvents, initiativeOrder, roundStarts } =
  require(path.join(__dirname, "..", "web", "static", "pit.js"));

const battle = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const ev = battle.events;
if (!ev.length) throw new Error("no events");

// stamps sane
let lastR = 0, lastL = 0;
for (const e of ev) {
  if (e.round < lastR) throw new Error("round went backward");
  if (e.log_index < lastL) throw new Error("log_index went backward");
  lastR = e.round; lastL = e.log_index;
  if (e.log_index > battle.log.length) throw new Error("log_index out of range");
}

// final fold must agree with the engine's survivors exactly
const final = foldEvents(ev, ev.length - 1).tokens;
for (const [id, name, hp, max] of battle.survivors) {
  const t = final[id];
  if (!t) throw new Error(`survivor ${id} (${name}) missing from fold`);
  if (!t.alive) throw new Error(`survivor ${id} folded as dead`);
  if (t.hp !== hp) throw new Error(`survivor ${id}: fold hp ${t.hp} != engine ${hp}/${max}`);
}
for (const [id, t] of Object.entries(final)) {
  const isSurvivor = battle.survivors.some((s) => s[0] === id);
  if (!t.alive && isSurvivor) throw new Error(`fold killed survivor ${id}`);
  if (t.fled && isSurvivor) throw new Error(`fled ${id} listed as survivor`);
}

// prefix folds never crash and every spawn carries a team
for (let i = 0; i < ev.length; i += Math.max(1, Math.floor(ev.length / 25)))
  foldEvents(ev, i);
if (ev.filter((e) => e.kind === "spawn").some((e) => !e.info))
  throw new Error("spawn event without team info");

const order = initiativeOrder(ev);
if (!order.length) throw new Error("empty initiative order");
if (roundStarts(ev).length !== battle.rounds)
  throw new Error(`roundStarts ${roundStarts(ev).length} != rounds ${battle.rounds}`);

console.log(`replay fold OK: ${ev.length} events, ${order.length} in initiative, ` +
            `${battle.rounds} rounds, survivors exact`);
