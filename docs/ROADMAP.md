# ROADMAP — Slices

> ## Current build status (2026-07-02) — engine + full PC layer complete
> A pragmatic, stdlib-only implementation in `ravel/` delivers **AI-vs-AI multi-combatant battles**
> at high fidelity, driven by a deterministic heuristic AI or the local LLM (`gemma4:12b` via Ollama).
> **493 tests pass.** The **entire Monster Manual (450 stat blocks)** is imported and file-driven under
> `data/monsters/mm/`. The combat engine (Slices 0–5, 8, 10, 11-monsters, 16) is deeply built, plus the
> **battlefield environment** — lighting/vision, ground hazards, aquatic combat, weather — and now
> **equipment & inventory (Slice 7):** weapons/armor/magic-items/consumables deriving AC + attacks.
> **The player-character half is now built:** **Slice 6 is COMPLETE** (2026-07-02) — all 12 classes +
> 32 subclasses 1-20, races/backgrounds/feats/languages, the skills layer, multiclassing + ASIs, and
> Inspiration; a PC compiles into a `MonsterDef` and fights through the engine's exact path. Slice 9's
> rests + death saves are done. **What remains:** Slice 9 leftovers (§14.4-14.5 revival/regen/recharge +
> minute/hour timers), Slice 12's finish (12c arena integration of built PCs + 12d human play & LLM
> narration), and the completeness passes on Slices 8/10/11 (movement/cover math, legendary/encounter
> features, SRD import/license tagging) plus the deferred pure event-sourced core (§2.2 strong form).
> NB: the per-item `- [ ]` checkboxes below were not maintained during the milestone push and understate
> what's done; the per-slice status notes and this banner are the accurate ledger.
>
> **Content is fully file-driven (2026-06-30):** one JSON stat block per file under `data/monsters/` (24 files,
> CR 1/8-10), parsed by `ravel/statblock.py` into `MonsterDef`. Add a monster by dropping a JSON file there — no code change.
> Round-trip (load→serialize→load) is test-verified for every block. The JSON schema is faithful to a 5e block
> (type, alignment, hit dice, speeds-by-mode, saves, skills, senses, languages, damage/condition modifiers, traits, actions, multiattack, areas).
>
> **What it covers (partial, against the SPEC):** dice/RNG (§1), state+event-log (§2 simplified, no full reducer),
> grid + distance + **cost-aware pathing (Dijkstra) with difficult terrain** + **line of sight + cover** + full **AoE geometry (sphere/cube/cone/line)** (§3.1-3.7), creature stats (§4), attack/save/check core (§5.1-5.3),
> damage + resist/vuln/immunity (§6.1-6.3), action economy + movement + melee/ranged/multiattack (focus-fire redirect) + **opportunity attacks** (§7),
> **all 15 conditions + 6 exhaustion levels with exact effects, immunities, save-ends and implications** via `ravel/conditions.py` (§8), **true save-for-half riders** (§6/§9),
> save-for-half **area abilities with recharge** (breath weapons, part of §10/§15), regeneration & multiattack (§15 partial),
> **spellcasting (§10): file-driven spells (`data/spells/`, 16 spells), spell attack / save / auto / heal / passive-modifier effects, AoE templates, upcast + cantrip scaling, full concentration (set/swap/break-on-damage CON save/break-on-incapacitation/duration), and caster stat blocks (Mage, Priest)** — see `docs/SPELLCASTING.md`,
> the **LLM controller** with constrained selection + fallback (§16), and a batch-stats simulator + the `monster-arena` skill (§18 partial).
>
> **Reactions, auras, summons, legendary (2026-06-30):** full reaction system (one/round): opportunity attacks, **Shield**,
> **Counterspell**, **Hellish Rebuke**, and **readied actions** (§7.5 done). Concentration **auras** — caster-anchored
> (Spirit Guardians) and **movable point-anchored** (Moonbeam). **Summons** (Conjure Animals, Spiritual Weapon; untargetable
> summons + difficult-terrain auras). **Legendary monster features** (§15): legendary resistance, legendary actions, lair actions
> (+ Adult Red Dragon CR 17).
>
> **Encounter & positioning completeness (2026-06-30):** **surprise** rounds (skip first turn, no reactions until it ends, §15.6),
> **flanking** (DMG optional rule behind `RulesConfig.flanking`, §3.8), and **three-quarters cover** (low-wall/pillar obstacles +5;
> grid cover tiers wall=total / obstacle=+5 / creature=+2 / clear=0, §3.6). A `RulesConfig` carries optional-rule toggles (§19).
>
> **True distance, verticality & trait completeness (2026-06-30):** distances are now **actual Euclidean** (diagonal = 5√2 ≈ 7.07 ft;
> movement budget in feet; the 5-10-5 variant is dropped, §3.3). **3D verticality for flyers** (`Combatant.alt`): flyers climb to
> attack at range and kite, descend to melee; grounded melee can't reach airborne foes; **Flyby** (no OAs). Common **monster traits**:
> Pack Tactics, Magic Resistance, resistance to nonmagical physical (§15). Plus the remaining minor features: multi-cost legendary
> **Wing Attack**, **Flaming Sphere**, **aura on-enter trigger**, and **squeezing** (§3.9). New monsters: Adult Red Dragon, Giant Eagle.
>
> **Monster ability completeness (2026-06-30):** **Frightful Presence** (mass frighten), **Death Burst** (on-death AoE, chains),
> **Pounce/Charge** (move ≥X → prone + bonus attack), **Life Drain** (necrotic that lowers max HP), **Parry** (martial AC reaction),
> and **senses vs invisibility** (blindsight/tremorsense/truesight ignore unseen). New monsters: Wraith, Magmin, Gladiator (32 total).
> Encounters now start ~35 ft apart so chargers can pounce. Review fixes: footprint-aware distance in the movement/enumeration layer
> (Large creatures no longer self-squeeze), flyer climb capped to keep targets in range, squeezing refreshed each turn.
>
> **Action economy & catalog completeness (2026-06-30):** real action + **bonus-action** economy (bonus-cast spells,
> two-weapon off-hand, the bonus-action spell rule); full **minor action catalog** — Dash, Disengage, **Grapple** (+ Escape, with
> release when the grappler dies/moves), **Shove**, **Help**, **Hide** (vs passive Perception; blindsight sees through); **temporary HP**
> (§6.4). Dice: reroll / minimum-die / exploding / keep-N, expanded **crit range**, **Elven Accuracy** (§1). **Innate (X/day) spellcasting**
> (§15.5), **swim** terrain (§4.6), **cylinder** AoE (§3.7), and an LLM **decision-quality eval harness** (`sim.run_eval`, §16.5).
>
> **Battlefield complexity & named maps (2026-06-30):** terrain is now multi-layered and tactically live.
> The grid carries **elevation** (ground height per cell) and **chasms** (pits with a depth). **Cliffs** (an elevation
> jump > 5 ft) block walkers in the Dijkstra pather and need a climb/fly speed (and cost double); **chasms** are impassable
> to non-flyers and **lethal-or-painful when shoved into** — `Encounter.apply_fall` follows the standard fall rules
> (1d6 bludgeoning per 10 ft, **capped at 20d6**; **no damage/prone under 10 ft**) + prone, or "lost" for a bottomless
> gap (`grid.BOTTOMLESS` sentinel); forced movement (`cast._push`) stops a creature at a chasm lip and drops it in. Grounded creatures
> inherit terrain height on spawn and every move; a `RulesConfig.high_ground` toggle grants **advantage attacking a foe
> ≥5 ft below** (auto-enabled on any elevated map). New **ASCII map** module (`ravel/maps.py`): a one-char-per-square legend
> (`# o : ~ x v 1-9 A B`) → `(Grid, spawns)`, three example arenas (**chasm_bridge**, **hilltop**, **ruins**), wired into
> `build_encounter(map_name=…)` and `ravel fight --map <name>`. (§3.3 verticality, §3.6 cover, §3.10 elevation/falling.)
>
> **Spellcasting interactions, 3D AoE, burrow/hover (2026-06-30):** **§10.10** built — **Dispel Magic** (`cast._dispel_magic`,
> auto-dispels spells of level ≤ slot, else a spellcasting-ability check vs DC 10+level; ends concentration, spell ActiveEffects, and
> spell-applied conditions — tracked via new `Concentration.level` / `ActiveEffect.slot_level` / `Condition.spell_level`),
> **Antimagic Field** (self-anchored zone: no casting inside, spells fizzle vs creatures inside, aura damage suppressed), and
> **Absorb Elements** (reaction: halves one acid/cold/fire/lightning/thunder instance + `Combatant.absorb_rider` for the next melee hit).
> **§10.4** — **Silence** zone blocks verbal-component casting (`cast.requires_verbal`, `enc.is_silenced`; also bars Shield/Counterspell/
> Hellish Rebuke reactions in-zone); action/bonus/reaction casting modes formalized (ritual/longer casts recognized but not surfaced in
> the combat loop). **§3.7** — true 3D AoE: spheres are real balls that respect altitude (a high flyer escapes a ground Fireball), and
> **cylinders** reach any altitude in their column (`cast.area_targets`, `grid.cylinder_cells`; Moonbeam is now a cylinder). **§4.6** —
> **burrow** (tunnels under chasms / through difficult terrain, grounded; `reachable(can_burrow=...)`) and **hover** (a non-hovering flyer
> falls when incapacitated/prone via `enc.enforce_flight`). New spells: Dispel Magic, Antimagic Field, Silence, Absorb Elements. 142 tests pass.
> **Won't-do (per product decision):** §10.3 component/material tracking (kept flavor-only); §10.1 Pact Magic (deferred to the PC slice).
>
> **Monster Manual import + support audit (2026-06-30):** added **14 MM 2014 stat blocks** (CR ¼–9, 8 creature types) → roster of
> **46**; full write-up in `docs/MONSTER_AUDIT.md`. New: Zombie, Gnoll, Orc, Ghoul, Giant Spider, Berserker, Ankheg, Veteran,
> Basilisk, Mummy, Air Elemental, Vampire Spawn, Mind Flayer, Young Blue Dragon (the last two + Ankheg exercise the new burrow/hover).
> Each ability either maps to an engine primitive or is preserved verbatim in `traits` with an `[UNSUPPORTED]`/`[APPROXIMATED]` tag.
> The audit surfaced and **fixed two engine gaps**: (1) area abilities were gated on `reachable_within(origin_range)`, so
> self-emanations (gaze/whirlwind, `origin_range 0`) were never offered and breath weapons only fired near-melee — now gated on
> `origin_range + size` (Mind Flayer 0%→91% vs a Stone Giant once it could Mind Blast at range; dragons breathe from proper distance);
> (2) the heuristic ignored no-damage control areas — added a hard-control (restrain/paralyze/stun/petrify) step so a basilisk uses its
> gaze. Playtested across **all three controllers** (Heuristic/Random matrix, 0 errors; small LLM pass). 142 tests pass.
>
> **Event/trigger system — STARTED (2026-06-30):** the keystone enabler is underway (`ravel/events.py` typed `Event` stream on
> `Encounter.events`, emitted alongside the prose log; `ravel/triggers.py` trigger registry). First triggered abilities live:
> **Undead Fortitude** (`would_drop_to_0`) and **Rampage** (`on_kill`), opted into via `MonsterDef.triggered_abilities`. Also fixed
> a flying-movement bug (a non-hovering flyer now falls when restrained/grappled/speed-0, per PHB, not only when incapacitated/prone).
> See "Path to full monster-ability coverage" below. 149 tests pass.
>
> **Event/trigger system — CLOSED OUT (2026-06-30):** the reducer/replay landed. `ravel/reducer.py` folds the canonical event stream
> (`spawn/turn_start/move/damage/heal/death/survive/condition`, carrying absolute HP/pos snapshots) into per-combatant state; `state_at(n)`
> reconstructs any prefix (replay/undo) with no re-run. A consistency test proves `reduce(enc.events)` reproduces the engine's final HP +
> alive exactly, and the event stream is byte-identical per seed (the golden master). Also: a hit is now **one damage event** (a multi-type
> hit gets a single Undead Fortitude save at DC 5 + total, via `resolve_attack`'s `finalize=False` bundle + `rules.handle_drop`), and
> `on_turn_start`/`on_turn_end` trigger points were added (Orc **Aggressive** implemented on `on_turn_start`). 178 tests pass.
>
> **Still genuinely unbuilt:**
> - **Full event-sourced core (§2.2, the strong form)** — the engine remains imperative (state mutated in place) with the event stream
>   emitted alongside; a pure "state in → events out → reduce" rewrite is deferred (high-churn, low marginal value now that reduce/replay
>   work off the emitted stream). The reducer currently reconstructs HP/alive (complete) + position (best-effort), not every condition.
> - **PC-facing (deferred):** classes/feats (§11-12), equipment (§13), rests/death-saves (§14), skills layer (§5.4-5.5).
> - **Excluded:** content importers (§17), the interactive app (§18 — now the web UI, Slice 12a-12d).
> - **Documented N/A:** regional effects (§15.4, non-combat flavor), climb/burrow speeds (need climbable/earthen terrain),
>   encumbrance (§19, an equipment concern).
>
> The slice plan below stays authoritative for finishing the engine properly; the milestone code should be folded into it
> (e.g. migrate models to Pydantic, add the missing mechanics) rather than treated as the final architecture.

## Path to full monster-ability coverage (enabler plan)

Implementing *every* unsupported MM ability is **not** ~50 features ground out one by one; it is **~6 architectural enablers**, each
unlocking a whole class, plus a large-but-mechanical data buildout and an irreducible bespoke tail. The catalogue of currently-unsupported
abilities lives in `docs/MONSTER_AUDIT.md`. Ranked by leverage:

1. **Event / trigger system** *(= the §2.2 event-sourced core; **CORE DONE** 2026-06-30)* — typed events + a trigger registry so reactive
   abilities subscribe instead of being hard-coded. Unlocks the entire reactive class: Undead Fortitude, Rampage, **Aggressive**
   (on_turn_start) — all done; Relentless, Redirect Attack, ooze Split, create-spawn are now just handler-writing. **All five hard-coded
   reactions migrated onto the registry.** `on_turn_start`/`on_turn_end` trigger points added; "a hit is one damage event" done; the
   **reducer/replay (§2.4)** landed (`ravel/reducer.py` fold + `state_at` fold-prefix, consistency-tested vs the engine). Remaining: a pure
   event-sourced rewrite (§2.2 strong form) is deferred; add `on_missed`/`on_condition` points as abilities need them. *Effort: Large — core done.*
2. **Declarative ability schema** *(**core started** 2026-06-30)* — abilities as data (trigger + targeting + effects + predicates), on the
   Foundry *Activities* model. **Built:** a **conditional-modifier** layer (`ravel/modifiers.py` predicate registry, mirroring the trigger
   registry; `MonsterDef.bonus_damage` = declarative on-hit riders gated by a named predicate; `MonsterDef.reckless`). Live abilities:
   **Reckless** (self-advantage on melee + attackers gain advantage back), **Martial Advantage** (`ally_adjacent_to_target`), **Sneak
   Attack** (`sneak_attack`: advantage or a flanking ally, not at disadvantage), **Charge** (`charged`: moved ≥ threshold ft). New monsters
   Scout + Centaur exercise Sneak Attack / Charge. Remaining: fold attacks/spells/actions into one Activity schema, grapple-on-hit,
   conditional-advantage generalisation. *Effort: Large — conditional-modifier core done.* Slots into Slices 5/10.
3. **Condition framework v2** *(**started/core done** 2026-06-30)* — multi-stage / escalating-save conditions + disease/curse. **Built:**
   `Condition.escalates_to` (a save-ends condition worsens on a repeat fail — Basilisk gaze now restrains→**petrifies**), and lasting
   **curse** conditions via `SaveRider.condition_save_ends=False` + `conditions.BLOCKS_HEALING`/`can_heal()` (Mummy Rot now blocks all HP
   recovery, permanently). Unlocks the petrification family (Medusa/Gorgon/Cockatrice) and diseases. Remaining: per-type immunity
   exceptions (Ghoul-vs-elf), richer disease progressions. *Effort: Medium — core done.* Slice 4 extension.
4. **Movement / space modes v2** *(**core done** 2026-06-30)* — **Built:** **phasing/incorporeal** (`grid.reachable(can_phase=...)` +
   `MonsterDef.incorporeal` — passes through walls, creatures, chasms, cliffs), **teleport** (`MonsterDef.teleport` ft — ignores terrain,
   provokes no OA, counts as movement), and **containment/swallow** (`MonsterDef.swallow`/`SwallowDef`, `Combatant.swallowed_by`: a
   grappled foe is swallowed → blinded+restrained+total-cover, takes acid each turn, escapes by dealing `escape_threshold` damage from
   inside → regurgitation, or is freed prone when the swallower dies). New monsters: **Specter** (incorporeal), **Blink Dog** (teleport),
   **Giant Toad** (swallow) — roster 50. Remaining: engulf as a swallow variant (Gelatinous Cube), true incorporeal end-in-wall force
   damage. *Effort: Medium — core done.* Slice 8.
5. **Spell-library buildout** (§10) *(**core done** 2026-06-30)* — **Architecture built:** the **caster interface** is live (`Combatant`
   `spell_dc`/`spell_attack`/`spell_ability`/`spell_mod`/`caster_level`/`prof_bonus` properties delegating to `md`; `cast.py` reads through
   them, so a future PC-backed combatant supplies the same fields without re-authoring spells). New effect kinds: **`banish`**
   (remove-from-combat, concentration-linked, `Combatant.banished` excluded from the fight, returns on concentration break) and
   **`terrain`** (`models.Zone` + `Encounter.zones`: spell-created difficult/damaging patches — Wall of Fire, Spike Growth — consulted by
   `dynamic_difficult` + start-of-turn damage, expiring each round). Plus `attackers_have_disadvantage` (Blur / Mirror Image). **Data
   buildout:** Banishment, Wall of Fire, Spike Growth, Blur, + Cone of Cold, Ice Storm, Fear, Hold Monster, Blindness, Cloudkill, Slow,
   Mirror Image. New casters: Archmage, Drow Mage. Remaining: `dominate` (controller-hijack) + Wall-of-Force (blocking terrain) effect
   kinds; the rest of the SRD is pure data. *Effort: Large but parallelizable — core done.*
6. **Defender-side trait modifiers** — Damage Threshold, Limited Magic Immunity, Antimagic Susceptibility, Turn Immunity. A few lines each
   in `rules.py`. *Effort: Low/incremental.* Slice 10.

**Irreducible bespoke tail** — even with all six, ~10–20 marquee monsters need custom code: Beholder (random eye-ray menu + directional
antimagic cone), shapechangers (runtime `md` swap), splitters, create-spawn lifecycle. A "ray menu" and "shapechange" primitive each cover
a small family; the rest is per-monster.

**Honest bottom line:** ~60–70% of unsupported abilities fall out of enablers 1/2/3/6 + the spell data — i.e. *one core refactor + a data
effort*, not bespoke code per monster. "100% of the MM" has a long, low-value tail (non-combat utilities, single-use mechanics); the
pragmatic target is **every combat-relevant ability**. Recommended order: (1) finish the event/trigger refactor → (5/6) spell data +
defender traits in parallel → (2/3) ability schema + conditions v2 → (4) movement/containment → bespoke pass last. These map onto existing
Slices (§2 events, §9 effects, §10 spells, §15 monsters), not new scope.



Every SPEC capability is assigned to exactly one slice below. Slices are **ordering, not scope cuts** — the full SPEC is committed. Build slices strictly in order. **Do not start slice N+1 until slice N's Definition of Done (DoD) is fully green.** Do not pull later-slice work forward; do not leak current work into a later slice. Each slice lists its exact boundary ("Not here → Slice X") so nothing is vaguely "deferred."

Legend: `[ ]` not started · `[~]` in progress · `[x]` done. Check boxes in the same change that completes the work.

---

## Slice 0 — Harness & engine skeleton `(SPEC 1, 2, 3.1-3.3, 19)`
**Goal:** the deterministic machine exists and is provably reproducible, with zero game rules beyond passing turns.
**Build:** uv/pyproject scaffold, Ruff + mypy(strict) + pytest + syrupy + hypothesis + coverage, CI. Seeded RNG, dice roller (§1), state/event/reducer core (§2), 2D grid + size footprints + distance (§3.1-3.3), `RulesConfig` shell (§19), `Controller` protocol + `RandomController` + `ScriptedController`, interruptible turn-loop skeleton, the replay/golden-master harness, `ravel sim`.
**DoD:** a scenario of two inert creatures runs to a fixed end condition; the same seed yields a byte-identical event stream (golden master via syrupy); a property test asserts round/turn counters and the RNG stream are reproducible; `uv run ravel sim` works; CI green (lint, types, tests, coverage gate).
**Not here:** any attack/damage/movement-cost rules → Slice 1; difficult terrain/LoS/cover → Slice 8.

- [ ] Scaffold + tooling + CI
- [ ] Seeded RNG + dice (§1)
- [ ] State / events / reducer (§2)
- [ ] Grid coords + footprints + distance (§3.1-3.3)
- [ ] Controller protocol + Random + Scripted
- [ ] Interruptible turn-loop skeleton
- [ ] Golden-master + property harness, `ravel sim`

## Slice 1 — Minimal vertical combat `(SPEC 4, 5.1-5.3, 6.1-6.2, 6.4 base, 7.1-7.2 basic, 7.3 melee Attack)`
**Goal:** two creatures fight to the death with melee attacks, fully deterministic.
**Build:** creature stats (§4), d20 attack/save/check core (§5.1-5.3), damage types + rolls (§6.1-6.2), 0 HP → unconscious/dead + massive-damage instant death (§6.4 base), action-economy tracking for all categories (§7.1), basic movement on the grid (§7.2 basic), the melee **Attack** action with Extra Attack hook (§7.3).
**DoD:** `RandomController` arena fight runs to a winner deterministically (golden master); property tests: HP never invalid, action economy never negative, exactly one action/turn. Acceptance scenario "two-monster melee arena" green.
**Not here:** ranged/unarmed/multiattack, Dash/Disengage/etc., reactions, OA → Slice 3; resistance/vuln → Slice 4; spells → Slice 5.

- [ ] Creature core stats (§4)
- [ ] Attack/save/check d20 core (§5.1-5.3)
- [ ] Damage types + rolls + 0-HP/instant-death (§6.1-6.2, 6.4 base)
- [ ] Action-economy tracking (§7.1) + basic movement (§7.2)
- [ ] Melee Attack action (§7.3)

## Slice 2 — LLM controller `(SPEC 16)`
**Goal:** an LLM drives a monster through the Slice-1 fight, always legally.
**Build:** serialized legal options + valid targets (§16.1), `LLMController` with Pydantic→JSON-schema constrained selection + validation (§16.2), decision-context serialization (§16.3), framing A/B (§16.4), mocked-LLM fixtures for CI (§16.6), decision-quality eval harness (§16.5).
**DoD:** LLM-controlled monster completes the arena fight; across N seeds it selects only legal options 100% of the time (LLM mocked in CI); a live eval run demonstrates sane targeting (focus-fire wounded foe). **This is the seed's MVP: two monsters battling, one LLM-controlled.**
**Not here:** richer tactics depend on later mechanics; evals expand as slices land.

- [ ] Option/target serialization (§16.1)
- [ ] LLMController + constrained selection + validation (§16.2-16.4)
- [ ] Mocked fixtures (§16.6) + eval harness (§16.5)

## Slice 3 — Full action catalog & reactions `(SPEC 5.6, 5.8, 7.3 remainder, 7.4, 7.5, 7.6)`
**Goal:** every non-spell action type exists, plus the reaction system.
**Build:** ranged + unarmed + multiattack (§7.3), Dash, Disengage, Dodge, Help (§5.8), Hide, Search, Ready, Use an Object (§7.3), Grapple/Shove + contested checks (§5.6, §7.3), two-weapon fighting (§7.4), improvised action; bonus-action framework (§7.4); reactions + windows: Opportunity Attack, readied triggers, reaction hooks (§7.5); ranged-in-melee/long-range penalties (§7.6, cover stub until S8).
**DoD:** each action type has a passing test; OA fires correctly when a creature leaves reach on the grid; readied action triggers and consumes the reaction; golden-master scenarios exercising each.
**Not here:** cover math → Slice 8; spell-granted bonus actions/reactions wired in Slice 5.

- [ ] Ranged/unarmed/multiattack (§7.3)
- [ ] Dash/Disengage/Dodge/Help/Hide/Search/Ready/Use Object (§7.3, 5.8)
- [ ] Grapple/Shove + contested checks (§5.6)
- [ ] Two-weapon fighting + bonus-action framework (§7.4)
- [ ] Reactions + OA + readied triggers (§7.5, 7.6)

## Slice 4 — Conditions & effects engine `(SPEC 6.3, 8, 9)`
**Goal:** all conditions and a general timed-effect pipeline.
**Build:** all 15 conditions + exhaustion (§8), durations / save-ends / immunities (§8.2-8.3), condition interactions (§8.4), resistance/vulnerability/immunity (§6.3), effect application/expiry pipeline + buffs/debuffs + ongoing/triggered effects (§9), concentration linkage hook (§9.5, the CON-save itself lands with spells in S5).
**DoD:** each condition's mechanical effect verified by test (e.g. prone, restrained, paralyzed-crit, unconscious auto-fail); resistance halves and stacks correctly; an ongoing damage effect ticks and expires on schedule.
**Not here:** spells that apply these → Slice 5 (this slice provides the machinery + tests via synthetic effects).

- [ ] All 15 conditions + exhaustion (§8)
- [ ] Durations / save-ends / immunities / interactions (§8.2-8.4)
- [ ] Resist/vuln/immunity (§6.3)
- [ ] Effect pipeline: buffs, ongoing, triggered (§9)

## Slice 5 — Spellcasting `(SPEC 10, 3.7 for AoE)`
**Goal:** the full spell system; the option/effect schema is proven on all archetypes.
**Build:** slots/pact/cantrips (§10.1), known/prepared + DC/attack (§10.2), components (§10.3), casting times incl. reaction/ritual (§10.4), ranges/durations (§10.5), concentration + CON save (§10.6), upcasting + cantrip scaling (§10.7), AoE on grid (§10.8 consuming §3.7), attack/save/auto spells (§10.9), interaction spells: Counterspell/Dispel/Shield/Hellish Rebuke (§10.10).
**DoD:** the schema proof set (§10.11) all resolve correctly by test — attack-roll spell, Fireball (save-for-half AoE), Bless (concentration buff), Hold Person (condition + save-ends), Cure Wounds (heal), Shield (reaction). Concentration drops on failed save and on new concentration. **Gate: no bulk content import (Slice 11) before this DoD is green.**
**Not here:** the full spell corpus → imported in Slice 11; this slice hand-builds the proof set.

- [ ] Slots/pact/cantrips + DC/attack/known/prepared (§10.1-10.2)
- [ ] Components, casting times, ranges, durations (§10.3-10.5)
- [ ] Concentration + CON save (§10.6)
- [ ] Upcasting + scaling (§10.7)
- [ ] AoE templates on grid (§10.8, §3.7)
- [ ] Interaction spells (§10.10)
- [ ] Schema proof set green (§10.11)

## Slice 6 — Character building: classes, races, backgrounds, feats `(SPEC 5.4-5.5, 5.7, 11, 12)`
**Goal:** construct any PC; all derived stats correct; class options feed the engine.
**Build:** all 18 skills + expertise/JoAT/passive (§5.4-5.5), inspiration (§5.7), classes/subclasses 1-20 + features (§11.1), all caster types (§11.2), class resources + recovery (§11.3), fighting styles (§11.4), multiclassing (§11.5), ASIs (§11.6), races/subraces (§12.1), backgrounds (§12.2), feats (§12.3), languages + proficiency aggregation (§12.4-12.5). Features supply granted actions/bonus-actions/reactions into the §7 framework.
**DoD:** build one valid character per class from data; derived numbers (AC, saves, skills, slots, resources) match known reference characters by test; multiclass slot table correct.

- [x] Skills layer + expertise/JoAT/passive (§5.4-5.5) — `ravel/skills.py`: 18-skill→ability map, `skill_modifier`/`skill_check`/`passive_score`, prof/expertise/JoAT; fixed a passive-Perception double-count. **Inspiration (§5.7) done** (Slice 6 WP0): `Character.inspiration` → a one-use resource the engine spends for advantage on the holder's first own-turn attack lacking it (`rules.resolve_attack`, deterministic), serialized + round-trip tested.
- [x] Classes/subclasses/features/resources 1-20 (§11.1-11.4) — **Fighter and Wizard complete as BASE classes** (every non-subclass feature L1-20). **Subclass system established** (`Subclass`/`SUBCLASSES` registry, applied in `compile_character`): **Champion** (Improved/Superior Critical via `crit_range`), **School of Evocation** (Potent Cantrip + Empowered Evocation), and **Battle Master** (Superiority Dice 4/5/6 + d8→d12; Trip/Menacing maneuvers spending a die on a hit, one per turn, recharge on a short rest). **Arcane Recovery** implemented (rest-powered slot recovery). **All Fighter archetypes and all 8 Wizard Arcane Traditions now have their headline combat feature implemented:** Champion (crit range), Battle Master (maneuvers), **Eldritch Knight** (third-caster + War Magic); Evocation, **Abjuration** (Arcane Ward + Spell Resistance), **Conjuration** (Focused Conjuration), **Divination** (Portent), **Enchantment** (Hypnotic Gaze), **Illusion** (Illusory Self), **Necromancy** (Grim Harvest + Inured to Undeath), **Transmutation** (Transmuter's Stone). `test_subclasses.py` (9). Each subclass's minor/out-of-combat features (savant, ritual utilities, Transmuter's Stone alt-modes, etc.) are noted as follow-ons. Fighter: all 6 Fighting Styles (Defense/Archery/Dueling/GWF/Two-Weapon/Protection), Second Wind, Action Surge (1/2 uses), Extra Attack (2/3/4), **Indomitable** (save reroll, 9/13/17). Wizard: full-caster spellcasting + slot table 1-20, **Spell Mastery** (L18, at-will) + **Signature Spells** (L20, free 1/day) via the innate machinery. `CLASS_FEATURES` progression table + `class_features()` for inspection/tests. **Slice 6 WP0 scaffolded the remaining ten classes** (Barbarian, Bard, Cleric, Druid, Monk, Paladin, Ranger, Rogue, Sorcerer, Warlock): `ClassDef` rows (hit die, saves, skills, armor/weapon profs, subclass levels, caster type/ability), `CLASS_FEATURES` base-feature name tables L1-20, and numeric `class_resources` (Rage/Ki/Sorcery Points/Bardic Inspiration/Channel Divinity/Lay on Hands) with short/long-rest recovery incl. Warlock pact slots — **their in-combat mechanics are WP1-3.** **Slice 6 WP1 completes the martial pack (Barbarian / Monk / Rogue):** Barbarian (Rage toggle + damage/resist, Reckless, Unarmored Defense, Fast Movement, Brutal Critical, Danger Sense, Relentless Rage, Primal Champion; Berserker Frenzy + Totem-Bear resistance), Monk (Martial Arts + DEX unarmed die, Unarmored Defense/Movement, Ki: Flurry/Patient Defense/Stunning Strike, Evasion, Diamond Soul; Open Hand prone rider + Way of Shadow teleport), Rogue (Sneak Attack, Cunning Action, Uncanny Dodge, Evasion, Reliable Talent, Expertise wired through `level_choices`/serialization/`validate`, Stroke of Luck; Assassin auto-crit + Arcane Trickster third caster). `test_class_barbarian.py`/`test_class_monk.py`/`test_class_rogue.py` (30). **Slice 6 WP2 completes the divine pack (Cleric / Paladin / Ranger):** Cleric (full WIS prepared caster, Channel Divinity: Turn/Destroy Undead, Life Preserve Life + War War Priest/Guided Strike, Divine Strike), Paladin (half CHA caster, Lay on Hands, Divine Smite, Aura of Protection, Improved Divine Smite; Devotion Sacred Weapon + Vengeance Vow of Enmity), Ranger (half WIS caster, Hunter's Mark via a new `mark` spell-effect, Extra Attack; Hunter Colossus Slayer + Beast Master companion). `test_class_cleric.py`/`test_class_paladin.py`/`test_class_ranger.py` (23). **Slice 6 WP3 completes the arcane pack (Bard / Sorcerer / Warlock / Druid):** Bard (Bardic Inspiration die spent on an attack, Jack of All Trades, Expertise 3/10, Song of Rest, Font of Inspiration; Lore Cutting Words + Valor Extra Attack/profs), Sorcerer (Sorcery Points, Metamagic Quickened + Empowered; Draconic Resilience/Elemental Affinity + Wild Magic Tides of Chaos), Warlock (Eldritch Blast beams + Agonizing Blast, Hex, Mystic Arcanum; Fiend Dark One's Blessing + Great Old One Entropic Ward), Druid (Wild Shape md-swap with revert-at-0, prepared WIS caster; Circle of the Moon Combat Wild Shape/heal + Circle of the Land Natural Recovery). `test_class_bard.py`/`test_class_sorcerer.py`/`test_class_warlock.py`/`test_class_druid.py` (30). **All 12 classes now have their base features + ≥2 subclasses' headline combat features implemented.** Approximations noted in `docs/SLICE6_PLAN.md`. *(Rest-dependent recovery — Arcane Recovery, Second Wind/Action Surge refresh — in Slice 9 rests.)*
- [x] Multiclassing + ASIs (§11.5-11.6) — ASI stat bumps supported (`Character.asi`); **multiclass slot table done** (Slice 6 WP0): `multiclass_slots(full_half, third)` = combined caster level (full + half//2 + third//3) → full-caster row; `caster_slots("pact", …)` for Warlock; `compile_character` uses the combined table when 2+ casting sources are present (single-class unchanged). `ASI_LEVELS` per class (Rogue +10). `test_slice6_scaffold.py`.
- [x] Races, backgrounds, feats, proficiencies (§12) — Human/Hill Dwarf/High Elf/Half-Orc + **Slice 6 WP0: Mountain Dwarf, Wood Elf, Lightfoot/Stout Halfling, Dragonborn (Red) w/ breath weapon, Rock Gnome, Half-Elf, Tiefling w/ innate Hellish Rebuke** (approximations noted in `character.py`) + 12 backgrounds + skill/save/armor proficiencies + **Inspiration (§5.7)** (advantage in play, serialized). **Languages (§12.4) now modelled** (WP4): each race carries concrete languages (Common + racial), backgrounds a bonus-language count, `character_languages` surfaces them on the compiled stat block + builder sheet ("of your choice" grants shown as an `Any (N)` placeholder — the language *picker* is a build-time follow-on). **Proficiency aggregation (§12.5)**: armor/weapons unioned across race + classes; saves granted by the starting class only (multiclass-RAW-correct); skills aggregated; **tools not modelled** (follow-on). *(Feats §12.3 beyond the existing set: follow-on.)*

> **DONE (2026-07-01) — the PC framework's first vertical.** `ravel/character.py`. Two decisions:
> (1) **A PC compiles into a `MonsterDef`** (`compile_character`) — so a PC runs the engine's exact
> same enumeration/resolution path as a monster (near-zero engine changes). (2) **Advancement is the
> source of truth:** a `Character` is an ordered list of `LevelUp` entries (one per character level,
> each recording the class advanced + the choices made *at* it — ASI/feat, subclass, fighting style,
> skills, HP roll, spells). Every flat number (level, class levels, final abilities, HP, features) is
> *derived*; `level_up(ch, cls, **choices)` appends one entry (the atomic op a character builder
> drives) and `level_choices()` reports what the next level requires. This makes multiclass order,
> per-level choices, and rolled HP first-class — HP correctly takes the max hit die only at character
> level 1. Verified reference **L5 Fighter**: AC 19, HP 44, saves +6/+5, skills, Longsword +6
> Extra-Attack×2, Second Wind + Action Surge; beats an Ogre ~28/30. `test_pc.py` (9) + `test_skills.py`
> (6). 259 tests pass, roster smoke 0 crashes, PC determinism holds. **Next:** a caster class
> (Wizard/Cleric — slot table + prepared spells over the existing spell engine), then more
> classes/subclasses/races/feats, multiclassing, and eventually a character-builder UI + a scenario/CLI
> way to field a PC (ties into Slice 12).

> **SLICE 6 COMPLETE (2026-07-02) — WP4 DoD closure.** All twelve classes (Barbarian, Bard, Cleric,
> Druid, Fighter, Monk, Paladin, Ranger, Rogue, Sorcerer, Warlock, Wizard) are built L1-20 from data
> with their combat-relevant base features implemented, **32 subclasses** (Fighter 3 + Wizard 8 + two
> each for the ten others, Rogue 3) with headline combat features, ten new races + 12 backgrounds,
> Inspiration, multiclass + pact slot tables, ASIs, all six fighting styles (incl. Protection's
> reaction, working for Paladin/Ranger), and the skills layer w/ expertise/JoAT/passive. **DoD test**
> `tests/test_slice6_dod.py` (15): each class builds a leveled reference character (subclass +
> equipment/spells), compiles, asserts 2-3 PHB-checkable numbers (AC/HP/saves/slots/resources), and
> runs a deterministic Ogre bout that is byte-identical twice; plus a Paladin 2/Wizard 3 multiclass
> slot-table case and a prereq-warning case. **Full suite 493 green**; the web builder auto-follows
> (meta = 12 classes / 32 subclasses, `/api/builder/preview` compiles a Barbarian L3 with Rage). WP4
> also closed two genuine §12 gaps cheaply: **languages (§12.4)** (race+background, surfaced on the
> sheet) and **multiclass prerequisites (§11.5)** (min-13 ability-score checks as build warnings,
> never blocking). **Named follow-ons** (recorded, not "deferred"): the language/skill/ability *pickers*
> for choice-granting races & backgrounds; **feats §12.3** beyond the current set (effects of Sentinel/
> Polearm Master/Lucky reroll etc. are flags/noted, full mechanics later); **tool proficiencies §12.5**;
> the multiclass *reduced* proficiency grant (currently unions full class lists); and the per-subclass
> and per-race approximations catalogued in `docs/SLICE6_PLAN.md` (Halfling Lucky reroll, Wild Magic
> surge table, Beast Master real companion, Divine Intervention, Mystic Arcanum/Invocation pickers,
> Wild Shape self-feature re-derivation, bonus-action-after-action turn ordering). None are combat
> blockers; each is tied to a future slice or a builder-UI pass.

## Slice 7 — Equipment & inventory `(SPEC 7.7, 13)`
**Goal:** items affect options and derived stats.
**Build:** weapons + all properties + attack generation (§13.1, §7.7 ammo/loading/two-handed), armor + AC formulas + don/doff (§13.2), magic items + attunement + charges (§13.3), consumables incl. scrolls + ammunition tracking (§13.4), currency + encumbrance variant (§13.5), equip/unequip recompute (§13.6).
**DoD:** equipping armor/weapon/shield changes AC and available attack options correctly by test; ammunition depletes and blocks attacks at zero; attunement cap enforced.

- [x] Weapons + properties + attack generation (§13.1, 7.7) — `equipment.py` WEAPONS + `weapon_attack` (finesse/versatile/thrown/ranged/reach/magic); ammo depletes & blocks at 0
- [x] Armor + AC formulas + don/doff (§13.2) — ARMORS + `armor_ac` (light/medium-cap/heavy/shield/magic); `Combatant.ac` derives from the loadout
- [x] Magic items + attunement + charges (§13.3) — ITEMS (+1/+2 weapon, +1 armor, rings/cloaks); `Loadout.attune` enforces the 3-item cap; magic +hit/+dmg/+AC
- [x] Consumables, ammo (§13.4) — Potion of Healing (quaff action + heuristic drinks when wounded); ammunition tracking/recovery. *(Scrolls, currency & encumbrance variant: follow-on.)*

> **DONE (2026-07-01):** `ravel/equipment.py` (Weapon/Armor/Item/Loadout) + `Combatant.ac`/`.attacks`
> properties that derive from equipped gear (falling back to the base stat block, so monsters are
> unchanged). Wired into `resolve_attack`/enumeration/ammo; `test_equipment.py` (7) covers the DoD.
> A Commoner in plate+shield+longsword goes AC 10→20 and beats a bare Commoner 20/20. **Follow-on for
> the PC slice (S6):** off-hand/two-weapon bonus attack is generated but not yet auto-used by the AI;
> scrolls, currency, and the encumbrance variant; unarmed-strike fallback when a bow runs dry.

## Slice 8 — Movement & positioning completeness `(SPEC 3.4-3.9, 7.2 remainder)`
**Goal:** the grid is fully realized.
**Build:** difficult terrain, forced movement, teleport, special movement modes, jump/climb/swim/crawl, stand-from-prone cost (§7.2 remainder), LoS/line of effect (§3.5), cover half/three-quarters/total (§3.6), full AoE template geometry (§3.7), flanking (§3.8), squeezing & size-vs-space (§3.9).
**DoD:** cover and LoS computed deterministically and feed attack rolls; movement costs correct over difficult terrain; AoE template square-selection verified for sphere/cube/cone/line/cylinder.

- [ ] Movement completeness (§7.2 remainder)
- [ ] LoS + line of effect (§3.5)
- [ ] Cover (§3.6)
- [ ] Full AoE geometry (§3.7)
- [ ] Flanking + squeezing (§3.8-3.9)

## Slice 9 — Rest, recovery, time, death `(SPEC 14)`
**Goal:** the time/recovery/death lifecycle.
**Build:** short rest + Hit Dice (§14.1), long rest recovery (§14.2), death saves full rules (§14.3), revival/regeneration/recharge (§14.4), round/turn + minute/hour timers (§14.5).
**DoD:** rests restore the correct resources by test; the death-save sequence (incl. nat 1/20, damage-while-dying, instant death, stabilization) verified; a regenerating creature heals on schedule.

- [x] Short/long rest + Hit Dice (§14.1-14.2) — `ravel/rest.py`: `short_rest` (spend Hit Dice to heal + recover short-rest resources: Second Wind/Action Surge/Superiority Dice) and `long_rest` (full HP, half Hit Dice back, all spell slots + innate uses + daily resources, −1 exhaustion). `SHORT_REST_RESOURCES` metadata. `test_rest.py` (5).
- [x] Death saves (§14.3) — `rules.handle_drop`/`_damage_while_dying`/`_die` + `engine.roll_death_save`: a PC falls unconscious at 0 and rolls raw-d20 death saves (nat 20 → 1 HP, nat 1 → 2 failures, 3 successes stabilize, 3 fail die); damage at 0 = a failure (2 on crit); overkill ≥ HP max = instant death; healing wakes a downed ally (`_wounded_ally` targets the dying). Monsters still die at 0 (opt-in via `uses_death_saves`). `test_deathsaves.py` (7).
- [ ] Revival/regen/recharge + timers (§14.4-14.5) — regen/recharge already exist for monsters; revival + minute/hour timers pending

> **Rests DONE (2026-07-01):** the recovery lifecycle for PCs. Resource maxima are recomputed from
> the `Character` (`all_resources`) since class resources depend on class+level; Hit-Dice pool is
> tracked in `Combatant.resources["Hit Dice"]`. This unblocks every rest-recharged class feature
> (Second Wind, Action Surge, Indomitable, spell slots, Signature Spells, and future Ki/Rage/Channel
> Divinity/Warlock slots). Death saving throws are the remaining S9 combat piece.

## Slice 10 — Monsters & encounter features `(SPEC 15)`
**Goal:** full monster expressiveness and encounter-scope mechanics.
**Build:** full stat block model (§15.1), multiattack (§15.2), legendary actions + resistance (§15.3), lair actions + regional effects (§15.4), recharge + innate/X-per-day (§15.5), surprise + initiative ties + start/end-of-turn triggers + multi-combatant (§15.6).
**DoD:** a legendary monster (dragon: multiattack, breath recharge 5-6, 3 legendary actions, legendary resistance, lair action on init 20) runs a full multi-combatant encounter by test, all features firing correctly.

- [ ] Full stat block + multiattack (§15.1-15.2)
- [ ] Legendary actions/resistance + lair actions (§15.3-15.4)
- [ ] Recharge/innate + encounter triggers/surprise (§15.5-15.6)

## Slice 11 — Content importers `(SPEC 17)`
**Goal:** bulk SRD content compiled into the proven schema.
**Build:** importers for monsters/spells/items/classes/races/backgrounds/feats (§17.1), idempotent + validated + license-tagged (§17.2), raw source in-repo + reproducible build (§17.3), full SRD corpus (§17.4).
**DoD:** the full SRD imports with zero schema-validation errors; 20 randomly chosen imported monsters run valid fights end-to-end; re-running the importer is a no-op (idempotent).
**Gate:** requires Slices 4, 5, 6, 7, 10 schemas green (the importer targets the proven models).

> **Monster importer built (2026-06-30):** `tools/import_5etools.py` parses the 5e.tools bestiary JSON directly into our
> schema (no hallucination) — core stats, defenses, senses, attacks (incl. flat/multi-type + save riders), multiattack,
> recharge/save areas (breath weapons), spellcasting (mapped to spells we own), legendary actions + resistance, and trait-flag
> detection; every other ability is preserved verbatim in `traits`. Ran over the **full MM 2014 (450 stat blocks)**: **all 450
> imported** (52 hand-curated kept + 398 auto; the 5 that can't attack — Frog/Sea Horse/Shrieker/Pixie/Demilich — import as
> move/dodge-only). Stat blocks live under **`data/monsters/mm/`** (loader recurses); registry holds 451 (+ Spiritual Weapon summon).
> **All files load and every combat monster fights a goblin pack with 0 crashes; determinism holds.** Auto-imported blocks
> carry `"imported": "5etools-mm"` (idempotent: re-running skips curated + regenerates auto). Full checklist by CR in
> `docs/MONSTER_TODO.md`. **HP is rolled from hit dice by default** (`Encounter(roll_hp=True)`; CLI `--avg-hp` opts out;
> `hit_dice` backfilled into curated blocks so it's universal). Remaining for this slice: spells/items/classes importers (§17.1),
> license tagging (§17.2), the SRD corpus proper (§17.4 — this used the owned MM), and "support fully" = mechanizing abilities.

- [~] Importers per content type (§17.1) — **monster importer done**; spells/items/classes pending
- [ ] Idempotent + validated + sourced (§17.2-17.3) — idempotent + validated done; license tags pending
- [~] Full MM imported & smoke-fought (§17.4) — **all 450 MM monsters imported (under `data/monsters/mm/`), 0-crash smoke**; SRD-tagging pending

## Slice 12 — Player experience: web app `(SPEC 18)`

> **Product decision (2026-07-01):** the player-facing app is a **web UI**, replacing the previously
> planned terminal TUI (SPEC §18 amended in the same change). Split into four sub-slices, built in
> order. The web layer is an *outer* layer: `web/` imports `ravel`, never the reverse (invariant 3).

### Slice 12a — Web foundation & Bestiary `(SPEC 18.1, 18.2)`
**Goal:** the site exists, styled, serving the read-only Bestiary.
**Build:** engine prep (round-stamped events + event↔prose-log linkage — small, pure, tested); FastAPI app in `web/` (first third-party dep, per the sanctioned stack) with thin JSON endpoints (`/api/monsters`, `/api/monsters/{name}`, `/api/ratings`); static frontend, no build step; the "dungeon module" design-system CSS (ink-on-paper, double-rule stat-block frames, cross-hatch/grid SVG patterns); monster art from the 5etools-img GitHub mirror (name→URL candidates, client-side fallback); Bestiary page: filterable list (name/CR/type), classic stat-block render, art, "Pit Record" panel from `ratings.db` (nominal→adjusted CR line + CI, advisory bars, per-composition strip, env deltas).
**DoD:** `uvicorn web.app:app` serves the Bestiary; every stat block in `data/monsters/` renders without error; art resolves for MM monsters (graceful placeholder otherwise); Pit Record renders for every rated monster and hides cleanly for unrated ones; API endpoints + event round-stamping/log-linkage covered by tests; README documents how to run the site.
**Not here:** running fights from the browser → 12b; builder → 12c.

- [x] Engine prep: round on events + log linkage — `Event.round`/`Event.log_index` stamped in `Encounter.emit`; `BattleResult.events` exposes the stream; `tests/test_event_linkage.py` (5)
- [x] FastAPI skeleton + monster/ratings endpoints — `web/app.py`: `/api/monsters`, `/api/monsters/{name}` (raw stat block + rating + env deltas + ordered art-URL candidates), art from the 5etools-img GitHub mirror (`RAVEL_IMG_BASE`; MM→XMM→token + dragon-age fallbacks walked client-side), graceful no-DB/offline degradation; `tests/test_web.py` (self-skipping without FastAPI)
- [x] Design-system CSS + base page shell — `web/static/style.css`: ink-on-paper, double-rule frames, cross-hatch + graph-paper patterns, period bevels; blood-red reserved for the Pit page; shared masthead/nav (+ `construction.html` for 12b/12c routes)
- [x] Bestiary page (list, stat block, art, Pit Record) — `bestiary.html`/`bestiary.js`: CR-banded filterable roster, classic stat-block render from raw JSON (+ raw-JSON view), dithered art (MM→XMM→token fallback chain), Pit Record panel (CR-vs-PR line + CI, single-ink diverging signal bars, composition strip, terrain shifts); deep-linkable via URL hash
- [x] Aggregate figures ("the Ledger", default sheet view; pulled forward from 12b 2026-07-02) — CR-vs-PR scatter with identity hairline + largest-corrections leaderboard, both click-through to entries, fed by `/api/ratings`
- [x] Engine-support badges (bestiary + builder) — `ravel/support.py` `FEATURE_SUPPORT` (hand-curated from the PC audits: 130 entries, statuses gap/approx/utility/cosmetic) shipped in `/api/builder/meta`; the builder badges features/grants/race traits by name and the bestiary strips imported `[UNSUPPORTED]`/`[APPROXIMATED]` trait tags into small ink superscripts with a legend; `tests/test_support_registry.py` pins every key to a real feature name, `render_smoke.js` asserts the tag→badge render

### Slice 12b — The Blood Pit (arena) `(SPEC 18.3, 18.4)`
**Goal:** fights are configured, run, replayed, and batch-analyzed in the browser.
**Build:** fight-card config UI (teams, map, environment, controllers, seed) ↔ scenario format (§18.4) ↔ permalink query string; `/api/battle` returning the full event stream + linked prose log; client-side replay (SVG dungeon-map grid, tokens, HP ticks, synced combat log, initiative strip; step by event/turn/round, play/pause); gauntlet mode over SSE (win rates + CIs, round histogram, per-seed replay links); pre-fight odds from `encounter_view`. *(Aggregate bestiary figures moved to 12a by product decision 2026-07-02.)*
**DoD:** a fight configured in the browser replays deterministically from its permalink (same seed → identical replay); scrubbing keeps grid, log, and initiative in sync; a 50-seed heuristic gauntlet streams progress and every listed seed opens its exact replay; LLM-controller bouts work with visible progress.

- [x] Config UI ↔ scenario format ↔ permalinks — `pit.html`/`pit.js` booking form (team builders with XP tallies, map/weather/controllers/seed/surprise/underwater/flanking/avg-HP); the query string is the scenario serialization v1 (§18.4), read on load (auto-fights) and written on gong (pushState + copy-permalink button)
- [x] `/api/battle` + client-side replay — `web/arena.py` returns events + log + grid layers + combatant metadata + odds; engine stamps team on spawn events (summons tokenize client-side) and emits `flee` when a routed creature escapes off the map edge (token removed, initiative marked); replay is a pure fold over absolute HP/pos snapshots (scrub/step by event/round, play/pause at 3 speeds, keyboard arrows), SVG dungeon-map board (hatched walls, stippled difficult ground, lava in blood-red, elevation shading, chasms, hazard legend), synced log reveal via `log_index`, initiative strip, damage floats; `tests/pit_replay_smoke.js` proves the JS fold reproduces the engine's survivors exactly
- [x] Gauntlet (SSE) + odds — `/api/gauntlet` streams per-seed outcomes + Wilson-CI summary; UI shows live progress, round histogram, and a per-seed table where every row replays that exact bout; pre-fight odds from adjusted XP ("the touts lay 3:1…"); LLM bouts run over `/api/battle-stream` (SSE) with a live progress bar counting the Oracle's decisions, final payload identical to `/api/battle`; per-side lair-action toggles (`lair=` param → `Encounter.lair_teams`). `tests/test_arena.py` (13)

### Slice 12c — Character builder `(SPEC 18.5)`
**Goal:** PCs are built level-by-level in the browser and fielded in the arena.
**Build:** schema-driven builder over `character.py`'s `level_up`/`level_choices` — the server enumerates legal choices per level, the UI only selects (mirror of the `Controller.decide` principle); sheet preview (derived AC/HP/saves/attacks); character roster persisted **in the browser** (localStorage + JSON download/import; product decision 2026-07-02, replacing the planned `data/characters/*.json`) — the JSON form is `character_to_dict`, round-trip tested; arena integration (characters selectable as combatants).
**DoD:** a legal character of every implemented class builds in the browser with no way to produce an engine-invalid character; the saved JSON round-trips and fights in the Blood Pit; builder options grow automatically when a new class/feature lands in `character.py` (no UI rework, verified by test).

- [x] Schema-driven builder over `level_choices` — `web/builder.py` (`/api/builder/meta` mirrors the engine registries exactly — races/backgrounds/classes/subclasses/styles/feats/skills/equipment/spell-lists — pinned by test, so new engine content reaches the UI with zero builder changes; `/api/builder/preview` compiles via `compile_character`/`to_combatant` + `validate_character` warnings + per-class `level_choices`); `builder.html`/`builder.js` in PHB order — race cards, background, name, point-buy abilities (configurable budget, PHB costs), class & advancement level-by-level (skills/style/subclass/ASI-or-feat/spells, undoable), equipment
- [x] Sheet preview + JSON persistence — live sheet panel (abilities/AC/HP/saves/skills/attacks/slots/resources/features) recompiled on every change; roster in localStorage with per-character and whole-roster JSON download + import; serialization = `character_to_dict`/`character_from_dict` in `ravel/character.py`, round-trip + illegal-input rejection tested (`tests/test_builder_api.py`, 7)
- [ ] Arena integration
- Known builder gaps (engine `level_choices` follow-ons, with Slice 6's remaining classes): Champion's L10 Additional Fighting Style and Eldritch Knight spell picks aren't yet surfaced as level-up choices; attuned magic items aren't in the equipment step or the JSON form.

### Slice 12e — The Supertemporal Arena (auto battler) `(SPEC 18.8)`

> **Product decision (2026-07-04):** commissioned ahead of 12c's last item and 12d — the mode
> needs neither (battles run heuristic-vs-heuristic until §18.6 lands; PCs stay out of the stable
> for now). Themed on the Fortune's Wheel casino (Sigil, *Turn of Fortune's Wheel*); Shemeshka
> presides. Silver/gold accents over the house style; the wheel is gold with red accents.

**Goal:** a full roguelite auto-battler run — shop, deploy, battle, spin — playable in the browser at `/supertemporal`, deterministic per seed, with a persistent leaderboard.
**Build:** pure seeded run-state machine `ravel/fortune.py` (economy in cp, adjusted-CR pricing, CR-cap ladder, owned-downweighted shop rolls, item kit boons via `apply_kit`, duplicate-merge training, three-ring wheel with the exact 18.8.8 odds, XP-budget enemy generation, foresight queue, serializable state); `ravel/sim.py` seams (team entries as `MonsterDef`, team-A placements override + deployment zone); `web/fortune.py` router (run lifecycle, battle replay payload shaped like `/api/battle`, wheel spins, leaderboard) + sqlite store `data/fortune/runs.db`; `web/static/supertemporal.html/.js` (shop with stable + sale slots, drag-drop deployment grid, replay, three-ring wheel animation, foresight queue, Book of Aeons).
**DoD:** a scripted run (fixed seed + action list) reproduces the identical end state twice (golden test); shop/wheel/enemy-gen properties hold across a seed sweep (prices in band, CR ≤ cap, book filter respected, wheel frequencies within tolerance); a browser run plays shop → deploy (drag-drop, zone-validated) → replayed battle → wheel spin → next round, through to 3 losses; the finished run appears on the leaderboard with its final stable; all new engine/web behavior covered by tests.

- [x] `ravel/fortune.py` run-state machine + tests — economy in cp (`coins` change renderer), adjusted-CR pricing (`price_cp`, flat 3 gp ± the playtested residual), CR-cap ladder + enemy XP-budget generation (pure in seed+round), owned-downweighted shop rolls with freeze, items as `apply_kit` stat-block transforms, duplicate-merge training (+1 AC/+1 HP per ★), the three-ring wheel at the exact 18.8.8 odds, counter-derived RNG so `to_dict`/`from_dict` round-trips exactly; `tests/test_fortune.py` (30: golden script replay, wheel frequency sweep, price bands, run-arc bookkeeping)
- [x] `ravel/sim.py`: `placements_a` override on `build_encounter`/`run_battle` (validated vs `deployment_zone`, footprints, overlaps; default path byte-identical), team entries accept ready `MonsterDef` objects (kitted/elite variants)
- [x] `web/fortune.py` API + `data/fortune/runs.db` store — run lifecycle (`/api/fortune/new`, single `/action` verb endpoint, `/deploy`, `/battle` shaped like `/api/battle`, `/spin`, `/leaderboard`), in-memory sessions + sqlite Book of Aeons; `tests/test_fortune_api.py` (10)
- [x] `/supertemporal` page — lobby (books, seed, a name dealt from the planar cant), Shemeshka's Offerings (5 creature slots + 2 equipment on one row, stable with a standby stall, freeze/reroll, train/sell/give/swap with targeting), foresight table + the opposition as a paid secret ("Divine the future", 5 sp), pointer-drag deployment on the SVG board (gilt zone, client pre-check + server validation) with a badge-matched roster column, battles replayed through the Pit's own machinery — extracted to `web/static/replay.js` (board, fold, scrubber, initiative, animations; parameterized corners/elements; `pit.js` re-exports it for the node smoke test) — plus a Cinematic speed, three-ring gold wheel drawn from the engine's own ring layouts (no-prize sectors spread apart) and animated to the server's stops, Book of Aeons on the landing view only; gilt/silver page accents, lacquer red reserved for the wheel

### Slice 12d — Human play & narration `(SPEC 18.6, 18.7)`
**Goal:** a human plays a PC in the Blood Pit; the fight is narrated.
**Build:** `HumanController` bridged over the web (the enumerated legal options render as the action menu; a click is the `decide`); narration LLM over the event log only (§18.7), strictly isolated from mechanics.
**DoD:** a human plays a full PC-vs-monsters encounter in the browser; the narrator LLM produces prose from the event log without ever touching mechanics.

- [ ] HumanController over the web
- [ ] Narration LLM over event log

---

## Coverage matrix (every SPEC section → a slice)

| SPEC | Section | Slice |
|---|---|---|
| 1 | Dice & RNG | 0 |
| 2 | State/events/reducer | 0 |
| 3.1-3.3 | Grid base | 0 |
| 3.4-3.9 | Grid completeness | 8 |
| 4 | Creature core stats | 1 |
| 5.1-5.3 | d20 core | 1 |
| 5.4-5.5,5.7 | Skills/expertise/inspiration | 6 |
| 5.6,5.8 | Contested/help | 3 |
| 6.1-6.2,6.4 | Damage base | 1 |
| 6.3 | Resist/vuln/immunity | 4 |
| 7.1-7.2 | Action economy + basic move | 1 (+8 move completeness) |
| 7.3 | Action catalog | 1 (melee) +3 (rest) |
| 7.4-7.6 | Bonus/reactions/ranged pen. | 3 |
| 7.7 | Ammo/loading | 7 |
| 8 | Conditions | 4 |
| 9 | Effects engine | 4 |
| 10 | Spellcasting | 5 |
| 11 | Classes/progression | 6 |
| 12 | Race/background/feats | 6 |
| 13 | Equipment | 7 |
| 14 | Rest/death/time | 9 |
| 15 | Monsters/encounter | 10 |
| 16 | LLM control | 2 |
| 17 | Importers | 11 |
| 18 | App/presentation | 12a (web+bestiary), 12b (arena), 12c (builder), 12d (human play+narration), 12e (Supertemporal Arena auto battler) |
| 19 | Rules config | 0 (+ per-feature flags) |

No SPEC section is unassigned. If a new capability is discovered, add it to SPEC **and** assign it a slice here in the same change — never leave it floating.
