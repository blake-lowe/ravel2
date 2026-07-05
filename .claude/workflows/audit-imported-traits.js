export const meta = {
  name: 'audit-imported-traits',
  description: 'Audit auto-imported monster traits for engine-support gaps, in batches of 10',
  phases: [
    { title: 'Analyze', detail: 'batches of 10 monsters classify each ability vs the engine spec' },
    { title: 'Synthesize', detail: 'rank the engine updates by coverage-per-effort' },
  ],
}

// args: { dir: "data/monsters/<book>", slugs: [ "<slug>", ... ] }
// (robust to args arriving as a JSON string rather than an object)
const input = (typeof args === 'string') ? JSON.parse(args) : args
const dir = input.dir || 'data/monsters/mm'
const slugs = Array.isArray(input.slugs) ? input.slugs : JSON.parse(input.slugs)

const ENGINE_SPEC = `The Ravel engine is a deterministic 5e combat engine. Classify each meaningful trait/action as:
- "supported": maps cleanly to a mechanized capability below, OR is pure flavor with no combat effect.
- "partial": partly works but loses fidelity (e.g. only the on-hit damage of a grapple lands, not the grapple).
- "unsupported": has a real combat effect that is NOT mechanized (lives only as descriptive text).

MECHANIZED: weapon attacks (to-hit, multi-damage, reach/range, on-hit save RIDERS: extra damage and/or a condition);
multiattack; AREA actions in the "areas" field (cone/line/sphere/cube + save + damage + recharge + condition) — an
ability described ONLY in "traits" text is NOT mechanized; saves + all standard conditions (+ multi-stage escalation,
save-ends, disease/curse); damage resist/immune/vuln + nonmagical-physical + condition immunities; movement
walk/fly/swim/climb/burrow/hover/teleport + incorporeal phasing + difficult terrain + falling; trait FLAGS
(pack_tactics, magic_resistance, flyby, reckless, regeneration, legendary_resistance, legendary_actions); reactions via
a registry (Shield, Parry, Counterspell, Hellish Rebuke, Death Burst — others NOT supported); conditional bonus damage
(sneak-attack, charge/pounce, bonus-vs-condition); containment (swallow: acid + escape DC); spellcasting mapped to a
~40-spell built-in LIBRARY — a spell NOT in the library is DROPPED (treat as unsupported, name it); auras/zones
(damaging/difficult/silence/antimagic + Frightful Presence -> frightened); summons.

KNOWN-UNSUPPORTED to flag: Shapechanger/Change Shape/multi-form; Swarm mechanics; False Appearance/ambush; save-abilities
living only in trait text (breath/gaze/burst NOT parsed into "areas"); damage transfer/redirection; ally-buff auras
(leader bonuses, Magic Weapons); Rejuvenation; Incorporeal-Movement object damage; Blood Frenzy (adv vs wounded);
grapple-drag beyond a one-shot condition; reactions beyond the 5 registered; Lair actions.

FLAVOR-ONLY (classify "supported"): Amphibious, Water/Hold Breath, Keen senses, Spider Climb/Web Walker (= climb speed),
Limited Telepathy, Illumination, Devil's Sight. Report only "partial"/"unsupported" findings; be concrete about engine_work.`

const FINDINGS = { type:'object', additionalProperties:false, properties:{
  findings:{ type:'array', items:{ type:'object', additionalProperties:false, properties:{
    monster:{type:'string'}, ability:{type:'string'},
    support:{type:'string', enum:['partial','unsupported']},
    reason:{type:'string'}, engine_work:{type:'string'} },
    required:['monster','ability','support','reason','engine_work'] } } },
  required:['findings'] }

const PLAN = { type:'object', additionalProperties:false, properties:{
  recommendations:{ type:'array', items:{ type:'object', additionalProperties:false, properties:{
    title:{type:'string'}, affected_monster_count:{type:'integer'},
    examples:{type:'array', items:{type:'string'}},
    engine_change:{type:'string'}, effort:{type:'string', enum:['small','medium','large']},
    priority:{type:'integer'} },
    required:['title','affected_monster_count','examples','engine_change','effort','priority'] } } },
  required:['recommendations'] }

const batches = []
for (let i = 0; i < slugs.length; i += 10) batches.push(slugs.slice(i, i + 10))
log(`auditing ${slugs.length} monsters from ${dir} in ${batches.length} batches of 10`)

phase('Analyze')
const results = await parallel(batches.map((batch, bi) => () =>
  agent(
    `You are auditing auto-imported D&D 5e monster stat blocks for engine-support gaps.\n` +
    `Read each of these files under ${dir}/ : ${batch.map(s => s + '.json').join(', ')}.\n` +
    `For EACH monster, inspect "traits" (verbatim ability text), "actions", "areas", "spellcasting", and flags. ` +
    `Classify every ability with a real combat effect that is NOT fully mechanized. Return only "partial"/"unsupported".\n\n` +
    ENGINE_SPEC,
    { label: `batch ${bi + 1}/${batches.length}`, phase: 'Analyze', schema: FINDINGS, effort: 'low' }
  )
))

const all = results.filter(Boolean).flatMap(r => r.findings || [])
const groups = {}
for (const f of all) {
  const key = f.ability.split('(')[0].trim().toLowerCase()
  if (!groups[key]) groups[key] = { ability: f.ability.split('(')[0].trim(), monsters: new Set(), support: {}, samples: [] }
  groups[key].monsters.add(f.monster)
  groups[key].support[f.support] = (groups[key].support[f.support] || 0) + 1
  if (groups[key].samples.length < 3) groups[key].samples.push(`${f.monster}: ${f.reason} -> ${f.engine_work}`)
}
const ranked = Object.values(groups)
  .map(g => ({ ability: g.ability, count: g.monsters.size, support: g.support, samples: g.samples }))
  .sort((a, b) => b.count - a.count)
log(`collected ${all.length} findings across ${ranked.length} distinct abilities`)

phase('Synthesize')
const plan = await agent(
  `You are the lead engineer of a deterministic 5e combat engine. Below is an aggregated audit of imported ` +
  `monster abilities that are partially or not supported, grouped by ability and ranked by monster count. Produce a ` +
  `PRIORITIZED list of concrete ENGINE UPDATES that close the biggest gaps. Group related abilities where one change ` +
  `covers many. Prefer importer fixes that populate ALREADY-EXISTING engine features (areas, frightful_presence, ` +
  `death_burst, pounce, bonus_damage, swallow, condition riders) over new subsystems. For each: title, #monsters, ` +
  `2-4 example monsters, the concrete engine/importer change, an effort estimate, and a priority (1=highest). Favor ` +
  `coverage-per-effort.\n\nEngine capabilities:\n${ENGINE_SPEC}\n\nAGGREGATED GAPS:\n` +
  ranked.map(g => `- ${g.ability} — ${g.count} monsters — ${JSON.stringify(g.support)} — e.g. ${g.samples[0] || ''}`).join('\n'),
  { label: 'synthesize engine-update plan', phase: 'Synthesize', schema: PLAN, effort: 'high' }
)

return { total_findings: all.length, distinct_abilities: ranked.length,
  top_gaps: ranked.slice(0, 30).map(g => ({ ability: g.ability, count: g.count, support: g.support })),
  recommendations: (plan && plan.recommendations) || [] }
