# Monster Manual import & support audit (2026-06-30)

> **HISTORICAL SNAPSHOT (superseded).** This records the early hand-import of 14 stat blocks (roster
> of 46). The full Monster Manual (451 blocks) was later imported wholesale via `tools/import_5etools.py`.
> For current state see **`MONSTER_TODO.md`** (the full roster checklist) and **`ENGINE_GAPS.md`**
> (mechanization status). Kept for the encoding-convention notes below.

Added **14 Monster Manual (2014) stat blocks** spanning CR ¼–9 and eight creature
types, chosen to mix fully-supported, approximated, and unsupported abilities so the
import doubles as a support audit. Roster is now **46** stat blocks. All files load
cleanly (`statblock.monster_from_dict`) and run **0 errors** across 14 matchups ×
{Heuristic, Random} × 12 seeds plus multi-combatant melees.

Encoding rule (faithful to `CLAUDE.md`): every mechanic that maps to an engine
primitive is encoded; anything that doesn't is preserved verbatim in the descriptive
`traits` array, prefixed `[UNSUPPORTED]` or `[APPROXIMATED as …]`, so nothing from the
source block is lost.

## Engine primitives an ability can map to
attack `rider` (save-or-condition / extra-damage on a hit) · `areas` (save area + an
optional condition rider, recharge) · `frightful_presence` · `reduces_max_hp` ·
`regeneration{amount,stopped_by}` · trait-flags (pack_tactics, magic_resistance,
resist_nonmagical_physical, flyby, elven_accuracy, fearless) · `parry` · `pounce` ·
spellcasting (slots/innate, referencing spells in `data/spells/`) · speeds incl.
**burrow/hover**. Anything outside this set is descriptive-only.

## Per-monster support

| Monster | CR | Fully supported | Approximated | Unsupported (trait-only) |
|---|---|---|---|---|
| Zombie | ¼ | Slam, poison/poisoned immunity | — | Undead Fortitude (drop-to-1-HP) |
| Gnoll | ½ | Bite, Spear | — | Rampage (bonus bite on a kill) |
| Orc | ½ | Greataxe, Javelin (thrown) | — | Aggressive (bonus-action dash) |
| Ghoul | 1 | Multiattack, Claws→paralyzed rider, Bite | elf-immunity exception dropped | — |
| Giant Spider | 1 | Bite + 2d8 poison rider, climb (Spider Climb) | **Web** → ranged attack w/ restrained rider (really a Dex save, recharge) | Web Sense, Web Walker, bite-at-0-HP paralysis |
| Berserker | 2 | Greataxe; **Reckless** now grants self-advantage on melee + advantage to attackers (conditional-modifier system) | — | — |
| Scout | ½ | Multiattack, Longbow; **Sneak Attack** (advantage or a flanking ally) — *new monster* | — | — |
| Centaur | 2 | Multiattack, Longbow; **Charge** (+3d6 after a ≥30 ft run-up) — *new monster* | — | — |
| Hobgoblin | ½ | **Martial Advantage** (+2d6 with an adjacent ally) now implemented | — | — |
| Specter | 1 | Life Drain (max-HP drain); **Incorporeal Movement** (phases through walls/creatures) — *new monster* | — | Sunlight Sensitivity |
| Blink Dog | ¼ | Bite; **Teleport** (40 ft, ignores terrain, no OA) — *new monster* | — | — |
| Giant Toad | 1 | Bite (grapple); **Swallow** whole (acid over time, escape-by-damage, freed on the toad's death) — *new monster* | grapple modeled as a STR-save rider | — |
| Ankheg | 2 | Bite (slashing+acid), **Acid Spray** line (recharge 6), **burrow** | bite grapple → STR-save grappled rider | AC-11-while-prone |
| Veteran | 3 | Multiattack (2×Longsword+Shortsword), Heavy Crossbow | — | — |
| Basilisk | 3 | Bite + poison; **Petrifying Gaze** now restrains **then petrifies** on a repeat failed save (condition v2) | "can see it" line-of-sight trigger → at-will area | — |
| Mummy | 3 | Rotting Fist (necrotic), **Dreadful Glare**→frightful_presence, **Mummy Rot** now a lasting curse that blocks all healing (condition v2), fire vuln, immunities | — | per-24h max-HP decay (out of combat) |
| Air Elemental | 5 | Slam multiattack, **Whirlwind** area (recharge 4-6)+prone rider, resist/immunities, fly+**hover** | Whirlwind "flung 20 ft" → prone only | Air Form (move through occupied/1-ft spaces) |
| Vampire Spawn | 5 | Claws+Bite, Bite `reduces_max_hp`, **regeneration 10** (stop: radiant), climb, resistances | regen sunlight/running-water suppression | Claws "grapple instead of damage"; Vampire Weaknesses |
| Mind Flayer | 7 | Tentacles, **Mind Blast** cone (INT DC 15, stun rider), Magic Resistance | tentacle stun-while-grappled → 1-rd stun rider | innate psionics, Extract Brain |
| Young Blue Dragon | 9 | Multiattack (bite+lightning, 2 claws), **Lightning Breath** line (recharge 5-6), lightning immunity, **burrow**, blindsight | — | — |

Two monsters (Veteran, Young Blue Dragon) are **fully faithful** with nothing dropped.
Ankheg and Young Blue Dragon exercise the new **burrow** movement mode; Air Elemental
exercises **hover**.

## Engine gaps surfaced — and fixed

**1. Area abilities were only offered at near-melee range (real bug).**
The option-enumeration gate used `reachable_within(actor, foe, area.origin_range)`. For a
self-emanation (`origin_range 0`: a basilisk's gaze, an elemental's whirlwind) that means
"within 0 ft" → the option was **never** offered; for breath weapons (`origin_range 5`,
`size 30+`) it meant the creature only breathed when ~adjacent. Fixed to gate on
`origin_range + size` (the template's actual reach); the real geometry is still recomputed
on resolution, so a looser gate can't hit anyone outside the template.
**Impact:** the Mind Flayer went **0% → 91%** vs a Stone Giant once it could Mind Blast at
range; dragons now breathe from proper distance; the Basilisk's gaze became usable.

**2. The heuristic ignored no-damage control abilities.**
Its option scorer is damage-greedy, so a 0-damage control **area** (the gaze) was never
chosen — the same blind spot we documented for Silence/Dispel. Added a targeted step that
uses a hard-control area (restrain/paralyze/stun/petrify) on a not-yet-controlled foe. Only
the Basilisk has such an area among the roster, so existing behavior is unchanged.
(Control-only **spells** like Silence/Dispel remain heuristic-invisible by design — they are
available to the Random and LLM controllers.)

## Categories of MM abilities still genuinely unsupported
Recorded as `[UNSUPPORTED]` traits and lossless, but not mechanically modeled:
- **Survival traits** — "drop to 1 HP / regain HP" (Undead Fortitude).
- **Event-triggered bonus actions** — Rampage (on a kill), Aggressive (toward a foe).
- **Multi-stage conditions** — gaze restrain→petrify; disease progression (Mummy Rot).
- **"Instead of damage" replacements & swallow/engulf** — Vampire Spawn claws-grapple.
- **Self-state toggles** — Reckless Attack (per-creature advantage both ways).
- **Bespoke reactions** beyond the built-in set (Shield/Counterspell/Parry/Hellish Rebuke).
- **Random / directional special attacks** — Beholder eye rays + antimagic cone, Medusa's
  gaze line-of-sight; none imported, named here as the class still out of reach.

## Cross-controller playtests (new monster vs a similar-CR existing monster)

`run_battle([new],[opp])` with the **same** controller on both sides (so the % is the new
monster's win rate against an equal-CR opponent under that AI), 12 seeds each.

| Matchup | Heuristic W% | Random W% | avg rds | signature ability seen |
|---|---|---|---|---|
| Zombie vs Skeleton | 66 | 58 | 3.5 | — |
| Gnoll vs Hobgoblin | 50 | 83 | 4.7 | — |
| Orc vs Black Bear | 25 | 8 | 2.2 | — |
| Ghoul vs Dire Wolf | 58 | 58 | 3.2 | paralyzed |
| Giant Spider vs Brown Bear | 33 | 25 | 3.3 | poison, restrained |
| Berserker vs Ogre | 41 | 83 | 5.3 | — |
| Ankheg vs Saber-Toothed Tiger | 8 | 8 | 2.7 | Acid Spray |
| Veteran vs Owlbear | 41 | 16 | 3.6 | Heavy Crossbow |
| Basilisk vs Manticore | 0 | 58 | 13.3 | gaze→restrained |
| Mummy vs Manticore | 0 | 41 | 9.1 | necrotic, frighten |
| Air Elemental vs Gladiator | 83 | 33 | 6.9 | Whirlwind + prone |
| Vampire Spawn vs Troll | 100 | 100 | 10.7 | max-HP drain, regeneration |
| Mind Flayer vs Stone Giant | 91 | 83 | 8.3 | Mind Blast + stun |
| Young Blue Dragon vs Fire Giant | 25 | 66 | 4.9 | Lightning Breath |

Multi-combatant (Heuristic, n=12): Gnoll×3 vs Orc×3 → 58%; Ghoul×2 vs Veteran → 58%;
Vampire Spawn vs Berserker×2 → 100%.

> **Update (2026-06-30):** the "restraining a flyer doesn't ground it" behavior was a
> deviation from RAW and has since been **fixed** — a non-hovering flyer reduced to speed 0
> (restrained/grappled/incapacitated) now falls (PHB Flying Movement). So a basilisk that
> lands its gaze on a flyer now brings it down; rerun the Basilisk row to see the change.

**Reading the results (pre-flyer-fix).** Ground melee monsters (Basilisk 0%, Mummy 0%) lost to
the flying Manticore under the heuristic because it kited at altitude — and at the time
restraining a flyer didn't ground it, so even a landed gaze couldn't save the basilisk. The Heuristic↔Random inversions (Mind Flayer 91/83, Berserker 41/83, Gnoll 50/83) are
the heuristic opponent playing the matchup well; the new monster does better only when both
sides flail randomly. Vampire Spawn vs Troll (100%) is a regen-vs-regen race the max-HP drain
wins. No win rate is wildly off for the CR, and the signature ability fires in every case
where the matchup allows it.

### LLM controller (Ollama `gemma4:12b`, LLM team A vs Heuristic team B, n=2)

| Matchup | LLM wins | legal-choice rate |
|---|---|---|
| Mind Flayer vs Stone Giant | 1 / 2 | 100% |
| Basilisk vs Manticore | 0 / 2 | 100% |
| Young Blue Dragon vs Fire Giant | 0 / 2 | 100% |

**Legal-choice 100% across the board** — the new monsters' enumerated options (gaze,
Mind Blast, breath, multiattacks) are all well-formed and the model never falls back to a
default. Win rates track matchup difficulty rather than controller quality: the Mind Flayer
is competitive, the ground-bound Basilisk is hopeless against a kiting flyer (as under the
heuristic), and the dragon vs an equal-CR Fire Giant is a coin-flip-to-uphill fight. (n is
deliberately small — each decision is a local model call.)
