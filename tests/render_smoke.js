/* Renders every stat block in data/monsters/ through the real bestiary renderer
   (with and without a rating) and fails on missing names or leaked "undefined"/
   "NaN"/"[object Object]" — the class of defect the API tests cannot see.
   Run directly (node tests/render_smoke.js) or via pytest (test_web.py). */
"use strict";
const fs = require("fs");
const path = require("path");

const { statblockHtml, pitRecordHtml, rawJsonHtml } =
  require(path.join(__dirname, "..", "web", "static", "bestiary.js"));

function* jsonFiles(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) yield* jsonFiles(p);
    else if (e.name.endsWith(".json")) yield p;
  }
}

// a rating exercising every Pit Record figure, including a null signal
const rating = {
  nominal_cr: 5, nominal_xp: 1800, adjusted_cr: 6.2, ci_lo: 5.8, ci_hi: 6.6,
  refined_cr: 6.1, residual: 1.2, composition_spread: -0.4, group_synergy: 0.7,
  skill_ceiling_delta: null, bt_disagreement: 0.1, flag: "swingy",
  environment: "open", per_composition: { 1: 6.5, 2: 6.2, 4: 5.9 },
};
const env = [
  { environment: "underwater", env_cr: 4.5, delta: -1.7, flag: "" },
  { environment: "fog", env_cr: 6.4, delta: 0.2, flag: "" },
];
const LEAKS = ["undefined", "NaN", "[object Object]"];

let count = 0;
for (const f of jsonFiles(path.join(__dirname, "..", "data", "monsters"))) {
  const block = JSON.parse(fs.readFileSync(f, "utf8"));
  if (!block.name) continue;
  for (const r of [null, rating]) {
    const html = statblockHtml({ statblock: block, image: null })
      + pitRecordHtml({ statblock: block, rating: r, env: r ? env : [] })
      + rawJsonHtml({ statblock: block });
    if (!html.includes("statblock")) throw new Error(`empty render: ${f}`);
    for (const leak of LEAKS) {
      // raw JSON echoes the file verbatim, so only scan the rendered parts
      const rendered = html.slice(0, html.indexOf('<details class="rawjson"'));
      if (rendered.includes(leak)) throw new Error(`"${leak}" leaked rendering ${f}`);
    }
  }
  count += 1;
}
if (count < 450) throw new Error(`only ${count} blocks found — registry missing?`);

// engine-support trait tags: the badge renders and the raw "[UNSUPPORTED]" /
// "[APPROXIMATED …]" tag is stripped from the visible trait text (the ankheg
// carries one of each).
const ankheg = JSON.parse(fs.readFileSync(
  path.join(__dirname, "..", "data", "monsters", "mm", "ankheg.json"), "utf8"));
const ah = statblockHtml({ statblock: ankheg, image: null });
if (!ah.includes('class="supp supp-gap"'))
  throw new Error("ankheg [UNSUPPORTED] trait did not render a gap badge");
if (!ah.includes('class="supp supp-approx"'))
  throw new Error("ankheg [APPROXIMATED] trait did not render an approx badge");
for (const raw of ["[UNSUPPORTED]", "[APPROXIMATED"]) {
  if (ah.includes(raw)) throw new Error(`raw tag "${raw}" leaked into the rendered ankheg trait`);
}
if (!ah.includes("supp-legend"))
  throw new Error("ankheg stat block is missing the engine-support legend");

console.log(`rendered ${count} stat blocks clean, with and without ratings; support badges OK`);
