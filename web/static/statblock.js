/* The classic 5e stat-block renderer, extracted from the Bestiary so any page
   can show the full chant: the Bestiary's entry pane and the Supertemporal
   Arena's hover cards both draw from here. Pure string-in string-out — no DOM,
   no fetch — wrapped in an IIFE so its helpers never collide with a page's own.
   Browser: window.RavelStatblock.statblockHtml. Node (render smoke test):
   require("./statblock.js").statblockHtml. */
"use strict";

(function (root) {

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

  const API = { statblockHtml, alignText, crText };
  if (typeof module !== "undefined") module.exports = API;   // node smoke test
  else root.RavelStatblock = API;                            // browser pages
})(typeof window !== "undefined" ? window : globalThis);
