# Monster mechanization — status

How faithfully the imported Monster Manual roster (451 blocks; see `MONSTER_TODO.md`) is
mechanized. The 2026-06-30 audit that produced this list is **fully resolved** — every item below
is implemented, applied to the roster, and tested. What remains is a small, named tail.

## Resolved (implemented + tested)

Abilities the importer left as text are now routed into engine fields by `tools/trait_routing.py`
(`route_all`), wired into `import_5etools.py` and available as an in-place migration
(`tools/upgrade_traits.py`).

- **Breath / gaze / self-emanation → `areas`**, **Frightful Presence → `frightful_presence`**,
  **Death Burst → `death_burst`** (incl. restrained→petrified escalation). ~88 areas + 21 frightful.
- **Grapple/restrain on-hit riders** — `parse_attack` reads `…grappled/restrained (escape DC N)`
  (32 grapplers).
- **Charge/Pounce/Trample → `pounce`/`bonus_damage`**, **Swallow/Engulf → `swallow`** (24 + 3).
- **Blood Frenzy** (advantage vs. wounded), **Magic Weapons** (bypass nonmagical-physical resist;
  also fixed 18 monsters mis-imported as immune to *all* physical), **Leadership** (+1d4 to nearby
  allies' attacks).
- **Spell library** grown to 51 (Disintegrate, Chain Lightning, Confusion, Flame Strike, …); casters
  keep more of their lists on re-import (Lich → 11 spells).
- **Swarm** — half damage when bloodied **and** true space-sharing (a swarm neither blocks nor is
  blocked; `_blocked` excludes swarms). Fixed reach-0 ("in the swarm's space") + "or Xd6 if bloodied"
  double-parse.
- **False Appearance** — ambush (hidden at encounter start).
- **Eye Rays** — `RayDef` menu + `fire_eye_rays` (N distinct rays/turn, seeded); Beholder/Spectator/
  Death Tyrant fire charm/paralyze/fear/petrify/sleep + enervation/disintegration/death.
- **Incorporeal Movement** — phasing flag from the trait (5 ghosts) + 1d10-if-it-ends-in-an-object.
- **Vampire Misty Escape** — at 0 HP it becomes mist and flees instead of dying (once per fight);
  vampires are now unkillable in a stand-up fight.

Combat-inert by nature (recognized, trait text preserved, no mechanic needed):
- **Rejuvenation** — returns to life hours/days after the fight (between-sessions).
- **Change Shape / most shapeshifting** — shapechangers already fight in their combat form; disguise
  and alternate forms have no tactical effect here.

## Remaining tail (small, optional)

- **`dominate` effect kind** (Dominate Person/Monster) — a controller-hijack; deferred from Enabler 5.
- **Wall of Force** — a blocking-terrain effect kind; deferred.
- **More SRD spells** — ~20 casters still keep partial lists (utility/illusion spells outside the
  combat library are dropped). Incremental data work.
- **Minor approximations:** Vampire Misty Escape ignores the sunlight/running-water exception (no light
  model — see battlefield notes); the Beholder's Slowing/Telekinetic rays are saves with no lasting
  effect; swarm resistance is modeled as B/P/S resistance rather than "resistance to single-target
  effects."

189 → **215 tests pass**; full-roster smoke (450 monsters × Heuristic + Random) **0 crashes**;
determinism holds.

---

# MPMM audit — 2026-07-02

Imported **Mordenkainen's Monsters of the Multiverse** (261 blocks → `data/monsters/mpmm/`,
0 failed). Registry loads 712 total; 261 × {Heuristic, Random} = **0 crashes**; determinism holds;
5 complex legendaries under LLM = 100% legal-choice, 0 fallbacks. Importer bug fixed en route: the
Adult Oblex `skill` field carries a 5e.tools `oneOf` list (mimicked-creature skills) that crashed
the skills parser — now guarded (`isinstance(v, str)` in `import_5etools.py`).

The `audit-imported-traits` workflow (27 batches + synthesis) produced **326 findings across 226
abilities**. Ranked engine updates below — **coverage-per-effort, highest first**.

## Resolved 2026-07-02 (implemented + tested; MPMM re-imported)

Six gaps closed this session. Full suite **425 tests pass** (+8 new); 261 × {Heuristic, Random}
= **0 crashes**; determinism holds; teleporters/rampagers under LLM = 100% legal-choice.

- **Gap 1 — `regeneration.stopped_by`** (importer). Parse the "if it takes X damage this trait
  doesn't function" clause. **16/16** regenerators now populated (Bael cold/radiant, trolls
  acid/fire, Zariel radiant, …). Engine's `rules.py:apply_damage` already suppresses regen on a
  matching hit. `test_importer.py::test_convert_regeneration_stopped_by_from_trait`.
- **Gap 5 — area condition riders** (importer). `parse_area` now runs the shared `_condition_rider`,
  so an action-area's on-fail condition is kept. **84 areas** carry riders (Howler→frightened,
  Steel Predator→stunned, …). `test_importer.py::test_parse_area_populates_condition_rider`.
- **Gap 8 — charge/buff damage double-count** (importer). `parse_attack` splits the "extra … if it
  moved 20 ft" charge dice into a `charged` `bonus_damage` rider (fires only on a charge) and drops
  the "or … while <enlarged/raging>" buff alternative. **6 monsters** (Aurochs Gore 2d8+5 base +
  2d8-on-charge; Soulblade no longer sums the Enlarge form). `test_parse_attack_charge_damage_*`.
- **Gap 2 — `save_advantages`** (importer + engine). Parse "advantage on saves against being
  <conditions>" (**26 monsters**: Fey Ancestry, Duergar Resilience, Mental Fortitude, Two/Six/Extra
  Heads). Round-tripped in `statblock.py`; the previously-dead `rules.py:218` `vs` branch is now
  **live** — wired `vs=` at the frightful-presence, area-rider, and eye-ray save sites.
  End-to-end test proves advantage reduces frightened frequency.
- **Gap 7 — on-kill triggers** (importer + engine). Route "Rampage" → `triggered_abilities`
  (**5 monsters**; existing `triggers.py` handler makes the bonus Bite) and a new
  `temp_hp_on_kill` field + `on_kill` handler for fixed temp-HP blessings (**3 monsters**: Imix 5,
  Raxivort 4, Sseth 9). Soul Thirst's *derived* amount stays as text (noted). Handler + routing tests.
- **Gap 3 — bonus-action self-teleport** (importer + engine). New `teleport_bonus` field parsed
  from bonus-action teleports (**14 monsters**: Astral/Fey/Cloud Step, Blue Abishai). New
  `teleport` bonus Option + `_teleport_destination` (phases past terrain/creatures, no OA) +
  heuristic rule to close gaps. Action-economy caveat: fires in the bonus phase, so it repositions
  for next turn rather than teleport-then-attack. Behavioral + routing tests.

## Resolved 2026-07-03 (second pass; MPMM re-imported)

Three more gaps closed. Suite **520 tests pass** (+6 new).

- **Gap 6 — cube save-AoEs** (importer). The engine already resolves `cube` areas — `parse_area`
  just didn't recognize them. Added cube shape + a flat "takes 45 radiant damage" (no-dice → `Nd1`)
  fallback + refined `half_on_save` ("save or take" → half rewards the save; automatic-damage bursts
  like Blazing Edict → full even on a success). **10 cube AoEs recovered** (Marut Blazing Edict→stun,
  Moloch Breath of Despair→frighten, Sonic Scream→prone, Zaratan Spew Debris, …). Verified end-to-end:
  a survivor of Blazing Edict is stunned. Parse tests + mirrored `cube` in `trait_routing`.
- **Gap 9 — missing multiattack / dropped attacks** (importer). Four sub-fixes: (a) **choice-type
  damage** ("9 (2d6+2) of a type … choice: acid, cold, …") now keeps the attack with the first
  listed type — recovers Chromatic Bolt, Nature's Wrath; (b) **single "range N feet"** → `[N, N]`;
  (c) **"makes N attacks, using X, Y"** multiattack (Blackguard → Glaive×3); (d) **Parry** reaction
  routed to `md.parry` (Drow House Captain 3, Githyanki/Eladrin 3–5) — no parry handling existed
  before. ~7 monsters. Parse + routing tests.
- **Gap 4 — damage-less grapple/restrain attacks** (importer + engine). `parse_attack` now keeps a
  0-damage attack that carries a grapple rider (was dropped as "no damage"); `grapple_rider` extended
  to the webbing "DC N Strength check" escape (no "escape" keyword). **4 recovered**: Sticky Leg
  (Female/Male Steeder, grappled), Web (Choldrith, Drow Arachnomancer, restrained). Added a heuristic
  rule to open with a **restrained** attack (Web) on an uncontrolled foe — verified Choldrith restrains
  under Heuristic. *(Grapple-only Sticky Leg is recovered as data and used by Random/LLM: the heuristic
  keeps its damage focus for it — grappled is lower-value than restrained.)*

---

# Mis-rating audit — 2026-07-04

Investigated every monster whose consensus playtest rating misses its book CR by **4+ CR**
(36 gross outliers). Root causes fell into four buckets: **import-fidelity bugs** (fixed),
**engine/controller gaps** (some fixed, the rest below), **rating-methodology artifacts**, and
**honest book-vs-arena context** (no action needed). All fixes are in the importer/engine, so
re-imports keep them; **97 affected monsters re-rated** (mirror + synergy + env + BT with the
stale pair-cache evicted). Suite **534 tests pass** (+8: area fidelity + parse rules).

## Fixed (importer `trait_routing.py`/`import_5etools.py` + engine + schema)

- **Bare `{@recharge}` = Recharge 6** — was parsed as at-will (Allip Howling Babble: an at-will
  30-ft stun AoE, book says Recharge 6).
- **"targets/chooses (up to) N creatures" → `AreaDef.max_targets`** (new field; engine takes the
  nearest N, deterministic). **~35 abilities** were hitting *everyone* in range — Demilich Life
  Drain (3), Allip Whispers (3), Merrshaulk's Slumber (5), and a whole family of single-target
  gazes/rays imported as full spheres: Enslave, Chilling/Rotting/Dreadful/Vengeful/Terrifying/Fear/
  Hypnotic Gaze, Devour Intellect, Death Ray, Eat Memories, Forgetfulness, Warp Creature, …
  Sculpt-Spells-style protection clauses ("up to three creatures … to ignore the spell") are
  correctly NOT caps.
- **"or drop to 0 hit points" → `SaveRider.zero_hp_on_fail`** (new field; typeless, bypasses
  resistances, routed through `apply_damage` so death processing and the event stream stay
  canonical). Demilich **Howl** (was fear-only!), Banshee **Wail** (was an at-will 3d6 — now 1/day
  + drop), Sea Hag **Death Glare**. Death-burst triggers ("when it drops to 0…") are excluded.
  The heuristic learned to value these (≈ half the target's HP) and to fire them as hard control.
- **"regains hit points equal to damage dealt" → `AreaDef.heal_owner`** — Demilich Life Drain,
  Nabassu Soul-Stealing Gaze.
- **`AreaDef.requires_condition`** (new field) — Sea Hag's Death Glare only works on a
  **frightened** target; the engine now gates both the option and the application.
- **"Nd8 damage of the chosen type"** — recovered (first listed type). The Evoker's signature
  Sculpted Explosion previously dealt **zero damage**.
- **Beholder Zombie fires 1 random ray**, not 3 ("uses a random eye ray" vs the Beholder's
  "shoots three").
- **No-damage death bursts keep their rider** — dust/smoke mephit blind-bursts were falling
  through to `areas` as at-will actions (usable while alive) with `death_burst` left null.

Rating shifts confirm the fixes (mirror CR, before → after): Demilich 5.4 → **14.6** (book 18),
Beholder Zombie 8.7 → **4.4** (book 5), Allip 8.5 → **5.7** (book 5), Evoker 5.0 → **8.0**
(book 9), Vrock 3.0 → **6.5** (book 6). Roster-wide book-CR correlation 0.953 → **0.959**,
MAE 1.17 → **1.13** (711 rated).

## Logged, not fixed (each is a named later item, not "deferred-TBD")

- **Casters rate far below book** (15 of 27 overrated outliers are casters). Three compounding
  causes, none a bug: (a) imported spell lists are **thin** — only library spells survive import
  (Archdruid keeps 1 of ~20, Zuggtmoy 1, Lich 11); the shield/misty-step/invisibility defensive
  tier is what the book prices in. Belongs to the spell-library growth item above. (b) A solo
  caster vs an equal-XP squad is focus-fired before acting — *fair* for the arena, and the
  `group_synergy`/`per_composition` axes already expose it. (c) **Spawn distance** (~35 ft)
  erases the 120-ft range advantage — a Drow Mage died in round 1 without taking a turn.
  A "skirmish at range" spawn option for the calibration harness would isolate (c).
- **Signature-mechanic gaps** on specific outliers: Cloaker Attach/Phantasms, Eidolon possession
  (its Sacred Statue pairing is the whole monster), Balhannoth lair ambush, Rakshasa Limited
  Magic Immunity (needs spell-provenance on damage), Vampiric Mist Life Drain (save-based blood
  drain, still unparsed — it imports with no attack), Nabassu/Demilich **max-HP reduction**,
  Demilich legendary actions (empty `attack`), Howl/Wail success-side effects.
- **Methodology**: Bradley-Terry is 1v1-heavy, so AoE specialists (Hellfire Engine: mirror
  per-comp 3.3/12.4/14.9) get dragged down in `refined_cr`; duelists get inflated. Consider
  squad-based BT sampling or comp-weighted blending. Also `--llm` skill-ceiling passes for the
  caster cluster would separate "bad controller play" from "bad chassis."
- **Arena-context, working as intended**: `resist_nonmagical_physical`/incorporeal monsters
  (Allip, Helmed Horror, Wood Woad, Awakened Tree) overperform because low-CR monster squads
  lack magic weapons — the book assumes mid-tier PCs with magic items. The inverse holds for
  anti-PC tech (Rakshasa). These are real facts about monster-vs-monster combat, not errors.

---

# Spell library import + ai=greedy — 2026-07-04

**`ai=greedy`** (new controller, `ravel/controllers.py::GreedyController` +
`tactics.expected_value`): one-ply expected-value argmax using the engine's own probability
math — hit chance vs AC, save-failure chance, damage after resistances, conditions priced as a
fraction of the victim's remaining hp. Deterministic, batch-fast, no rule ladder: a new ability
is valued the day it's imported. Registered as `greedy` / `greedy_vs_heuristic` (CLI + web).
Quality (pinned in `tests/test_greedy.py`): beats Random 9/12 on a dragon mirror, ties the
heuristic on brutes/legendaries, and beats it **12/12** on a caster matchup — the rule ladder
underplays casters; EV pricing doesn't. Full roster × greedy: 0 crashes.

**Spell library** grown 58 → **139** via `tools/import_5etools_spells.py` (see the
**import-spells** skill). Every spell monsters reference lands in a bucket — written / INERT
(no arena effect, with reason) / UNMAPPED (needs a missing engine effect kind) / failed(0 after
triage). Casters re-imported with fuller lists (Lich 11 → 16 slot spells; Archdruid gains its
at-will Entangle + Faerie Fire/Mass Cure innates; Mummy Lord 7 → 10). 712 × {heuristic,
greedy, random}: 0 crashes; determinism holds. Approximations carry an `_approx` note in the
spell file.

**Pathfinding fidelity (2026-07-04, same session):** verified the movement model and made
consequences route-aware. The cost surface was already right — `grid.reachable` is a true
Dijkstra (Euclidean diagonals, difficult ×2 incl. water/hazard/aura cells, squeeze ×2,
climb gating, chasm avoidance, phasing) and hazards being in the difficult set means the AI
already *routes around* lava when practical. What was wrong: `_do_move` teleported to the
destination, so hazards / opportunity attacks / readied triggers only saw the endpoints.
Now: `grid.path_to` extracts the actual route (predecessor Dijkstra, deterministic,
identical cost model via the shared `_reach_kwargs`), `_do_move` walks it — crossing lava
burns even if you end outside it (airborne flyers exempt), running PAST a foe's reach
provokes, readied attacks fire at the first step entering range — and the move event
carries the route in `cells` for the replay (grey chalked path + waypoint walk in the pit).
Six new tests in `tests/test_pathfinding.py`. Ratings note: the open calibration arena has
no hazards and approach paths rarely pass through reach, so stored ratings are unaffected
in practice; map-based (web) fights gain the fidelity.

**AoE templates per XGtE (same session):** `sphere_cells`/`cone_cells` now implement the
XGtE "Areas of Effect on a Grid" template rule — a square is affected if at least half of
it lies inside the area (fixed 10x10 subsample lattice; deterministic). Circles are
centered on a grid intersection and reproduce the book's diagrams exactly (5-ft radius =
2x2 = 4 squares, 10-ft = 12, 15-ft = 32, 20-ft = 52). The cone was the big catch: the old
dot>=0.6 arc was ~53 deg half-angle — **more than double** the RAW cone (width equals
distance, half-angle ~26.6 deg). A 30-ft cone shrank 54 -> 22 squares. Breath monsters
and AoE casters were over-credited; **248 template-affected monsters re-rated** (areas of
sphere/cone/cylinder, death bursts, casters knowing template spells). Template tests
pinned in `tests/test_pathfinding.py`.

**UNMAPPED spell families** (each needs a named engine effect kind; the dominate and
wall-of-force items above already covered part of this list): blocking terrain / persistent
walls (wall of force/stone/ice, blade barrier, forcecage, prismatic wall, resilient sphere,
antilife shell), controller hijack (dominate ×3, crown of madness, compulsion), self-teleport
spell effects (misty step, dimension door, teleport, thunder-step-style), form swaps
(polymorph, gaseous form, enlarge/reduce, true polymorph, shapechange), extra-action economy
(haste, time stop), hp-threshold effects (power word kill, divine word, color spray),
resistance-granting buffs (protection from energy, stoneskin, blade ward), weapon-enchant
riders on others (magic/elemental weapon), summon-of-choice (gate, conjure elemental/fey/
minor/woodland, animate objects, summon fiend), long-fuse effects (contagion, storm of
vengeance, earthquake phases), and sundry singletons (feeblemind, telekinesis, levitate,
barkskin's AC floor, reverse gravity).

- **Gap 13 — once-per-encounter usage caps** (importer). "Recharges after a Short/Long Rest" and
  "N/Day" areas imported as `at-will` fired **every round**. Now mapped to `recharge = "once"`
  (`recharge_min = 7`, unreachable on a d6 → fires once per fight) via the existing recharge
  machinery — no new engine state. Usage parenthetical stripped from the area name. **~5 areas**
  (Lightning Flare, Invoke Nightmare, Merrshaulk's Slumber, Scintillating Shell). Parse + round-trip.
- **Gap 17 — max-HP-reduction (Life Drain)** (importer). Set `reduces_max_hp` (field + engine path
  already existed) when a hit's text says the HP maximum "is reduced by an amount equal to" the
  damage. **7 attacks** (Deathlock Wight, Demogorgon, Molydeus, Nightwalker, …); fixed-amount
  variants (Bulezau 1d8) excluded to avoid over-draining. Parse test.
- **Gap 16 — forced-movement (push/pull) rider** (importer + engine). New `SaveRider.push` (+ft away
  / −ft toward), round-tripped; the spell `_push` primitive gained a `toward` (pull) mode; new
  `Encounter.force_move` wired into the attack-rider and area-rider paths (moves on a failed save,
  walls/creatures stop it, chasm → fall). Parsed for **8 abilities** (Wastrilith Grasping Spout −60,
  Moloch Many-Tailed Whip −30, Canoloth Tongue −30, Force Blast/Cacophony/Iron Fist +push, …).
  Behavioral + parse tests. *(2 misses — Fire Giant Shield Charge, Duergar Iron Fist variants — are
  save-based single-target actions with no `{@atk}`/shape, a separate parser limitation.)*

### Remaining — Priority 3–5 (larger subsystems)
- **Parameterized retaliation reaction** (medium, 12) — Engine of Pain, Deadly Reach, Fire Form,
  Poison Splash, Vicious Reprisal.
- **Self-invisibility toggle + unseen state** (medium, 14) — Shadow Blend, Invisibility Field.
- **Damage-type-triggered self-effect hook** (medium, 7) — Aversion to Fire, Shock Susceptibility.
- **Trait-driven summons → summon path** (large, 12) — Cadaver Collector, the wizard schools,
  Orcus; needs the referenced statblocks in content too.
- **Self-heal / ally-heal action type** (medium, 7) — Second Wind, Healing Light.
- **Disadvantage-on-saves aura zone** (medium, 5) — Infernal Despair, Burden of Time.
- **Save-based single-target actions with no `{@atk}`/shape** (small) — e.g. Fire Giant Dreadnought
  Shield Charge (pull + prone): dropped because the importer needs an attack roll or an area shape.

**Known-unsupported, left as text (by design):** Change Shape (10), False Appearance (5, ambush
already modeled), damage redirection (Zuggtmoy Protective Thrall), Lair actions, behavioral tables
(Mouth of Chaos). Full per-monster findings in the workflow transcript (run `wf_065d4f4c-08e`).
