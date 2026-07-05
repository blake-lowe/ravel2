# Playtests — Monster Arena (2026-06-30)

Run via the `monster-arena` skill (`python -m ravel.cli batch/report`), 40–200 battles
each, deterministic heuristic AI on both sides. Focus: matchups exercising magical abilities.

## Results

| Team A | Team B | A win% | Avg rounds | Notes |
|---|---|---|---|---|
| Mage | 3× Bugbear | 52% | 3.6 | Glass-cannon caster; alpha-strikes but dies fast if it doesn't |
| Mage + Priest | 2× Ogre | 35% | 4.5 | Squishy casters vs durable brutes |
| Young Red Dragon | 4× Bugbear | 100% | 4.8 | Breath weapon + multiattack dominates (82% HP left) |
| Priest+2 Skel | Priest+2 Skel | 62/38 | 10.0 | Healing war; long but terminates (max 30 rds) |
| Wyvern | 2× Owlbear | 28% | 4.7 | Wyvern underperforms — see limitation below |
| Troll ×2 | Mage + Priest | 100% (Troll) | 4.8 | Casters die before fire shuts down regen |
| Hill Giant ×2 | Mage ×2 | 100% (Giant) | 3.4 | Rock-throwing giants out-range/out-tank mages |
| Young Red Dragon | 4× Bugbear | 100% | — | breath recharge swings long fights |

Mirror sanity (n=200, after the fix below): Mage 93/107, Goblin 107/93, Ogre 108/92 —
spread now varies in direction (≈first-strike variance), no systematic team bias.

## Issues found and fixed

1. **Initiative tie-break bias (FIXED).** Ties were broken alphabetically by combatant id,
   which in same-DEX mirrors (Mage, Goblin) systematically handed team B the first turn
   (~54% win rate in fast, swingy fights). Now broken by a fair seeded random value
   (`Encounter.roll_initiative`). Mirrors no longer lean to one side.
2. **AI never used its concentration toolkit (FIXED).** The heuristic ranked damage cantrips
   (Sacred Flame) above control/buff, so a Priest only ever cast Sacred Flame + Cure Wounds —
   Bless and Hold Person were dead content. The heuristic now, when not already concentrating,
   casts a control spell (Hold Person) on a strong foe or buffs the party (Bless) before
   falling through to damage. Concentration, paralysis/save-ends, and break-on-damage are now
   exercised in ordinary battles.
3. **Concentration swap on a whiffed spell (FIXED).** Casting a new concentration spell whose
   only target saved used to leave the *old* concentration running. Casting a concentration
   spell now ends the prior one immediately, per the standard ruling.

## Known limitations (not bugs — documented scope)

- **Flying gives no kiting advantage.** The grid is 2D with no verticality, so a flying Wyvern
  can't stay out of a grounded Owlbear's reach; it fights as a melee bruiser and underperforms
  its CR. Verticality is out of current scope (theater-of-mind + flat grid).
- **Healing mirrors are slow.** Two healers can drag a fight toward the round cap; it always
  terminates (cap = 60, winner by remaining HP), but such matchups are grindy by nature.

## Round 2 — verticality & new monster abilities (2026-06-30)

After the Euclidean/verticality refactor and a monster-mechanics audit, exercising the new features
(40 battles each, heuristic AI):

| Matchup | Result | Notes |
|---|---|---|
| Adult Red Dragon | 4× Gladiator | 100% dragon | Frightful Presence frightens the party turn 1; breath + multiattack; Gladiators **Parry** |
| Wraith | 2× Ogre | 75% wraith | **Life Drain** ratchets the ogres' max HP down; resist-nonmagical-physical tanks their clubs |
| 4× Magmin | Hill Giant | 100% giant | Magmins die fast but **Death Burst** chains (one explosion sets off the next) |
| 2× Saber-Tooth | 2× Brown Bear | 98% tigers | **Pounce**: charge ≥20 ft → prone + bonus bite |
| Manticore | Ogre | (kites) | Climbs to 20 ft and rains Tail Spikes; grounded Ogre can only answer with javelins |

Verified live: Frightful Presence (mass frighten), Death Burst chains, Pounce (prone + bonus attack),
Life Drain (max-HP reduction), Parry (+3 AC reaction), and flyer kiting via altitude.

**Tuning change:** starting distance was reduced from ~85 ft to ~35 ft (a realistic encounter range),
so chargers can actually Pounce and fights are less of a slow approach. Flyers still kite (they gain
altitude and out-range melee).

## Round 3 — action economy, minor actions, LLM eval (2026-06-30)

After adding the action+bonus economy, the minor-action catalog, temp HP, dice primitives, and
innate spellcasting (each code-reviewed and fixed):

- **Heuristic:** roster smoke 0 errors, 0 round-cap stalls, determinism holds (32 monsters, 106 tests).
  The bonus-action spell rule is observable — a Priest that casts Spirit Guardians (leveled) correctly
  may *not* also cast a leveled bonus spell, but after a cantrip it casts Spiritual Weapon as a bonus.
  Priest+Gladiator vs 2 Wraiths → Wraiths 68% (Life Drain + resist-nonmagical-physical vs the spear).
- **LLM (gemma4:12b):** drove every combatant with **zero fallbacks** across the expanded option set
  (action + bonus phases = two calls/turn). It used the new **Dash** action, cast **Hold Person**, and
  Life Drain ground a Gladiator's max HP 110→16 over the fight.
- **Decision-quality eval** (`sim.run_eval`, LLM vs heuristic): Mage vs 2 Bugbears → 100% win,
  **100% legal-choice rate** (every model decision was a valid option).

## Takeaway

The engine produces believable, terminating, deterministic outcomes across CR ¼–10 including
spellcasters. The two AI/fairness fixes above made caster battles both fair and tactically
richer (control + concentration now appear). Reaction spells (Shield/Counterspell), moving
auras, and summons were identified as the next gaps to make caster duels fully faithful — built
in the same session (see SPELLCASTING.md / ROADMAP.md).

## New-systems playtest (2026-06-30) — triggers, migrated reactions, flyer grounding

Exercised the event/trigger system, the migrated reactions, and the restrained-flyer fix
across all three controllers (~1,200 Heuristic/Random battles + a small LLM pass). **0 errors;
determinism holds.**

**Headline — gazer vs flyer.** With the area-reach fix (gaze is enumerated), the heuristic's
control-valuation step (it *uses* the gaze), and the restrained-flyer fix (a restrained flyer
falls), **the Basilisk went from 0% (pre-fix, could not touch a flyer) to a competitive
matchup**. Sample chain: `Petrifying Gaze → restrained → "can't stay aloft and falls 20 ft!" →
prone → Bite (adv) HIT`, looping as the Manticore keeps trying to re-take the sky. The
mechanical chain is robust: it fired in **20/20** battles under **both** controllers.

*Controller comparison (paired, n=20, same heuristic Manticore + same seeds, only the Basilisk's
controller differing):* LLM-driven Basilisk **50%** vs heuristic-driven Basilisk **35%**. The
LLM trends better but the +15 pp gap is **not statistically significant** (7 discordant seeds,
5–2 favouring the LLM; McNemar p ≈ 0.45). An earlier n=2 "LLM 2/2" reading over-stated this — at
n=20 the matchup is a seed-sensitive near-coin-flip (~35–75% across seed sets), and no
controller "outplay" is established. Legal-choice rate 100%. Two Basilisks vs two flyers = 100%.

**Trigger abilities.** Undead Fortitude fires wherever zombies fight (they are visibly tankier;
an Owlbear's crits still punch through). Rampage lets Gnoll packs chain bonus bites → 91–100% vs
weak foes.

**Migrated reactions (now handlers on the trigger registry).** All five fire in live battles:
Shield + Counterspell + Hellish Rebuke (Mage duels), Parry (Gladiator), Death Burst (Magmin) —
and Counterspell/Shield fire under the LLM too. New-monster win rates are unchanged from before
the migration, confirming it was behavior-preserving.

**Mixed combinations** (Zombie+Ghoul teams, gazers+mummies vs flyer pairs, Mind Flayer, Air
Elemental, Young Blue Dragon vs zombie hordes, Ankheg+Giant Spider) all ran cleanly with their
signature abilities firing. LLM legal-choice rate: **100%** across every matchup.

## Full-roster playtest after the engine-gap buildout (2026-06-30)

Re-imported all 398 non-curated blocks from `sources/bestiary-mm.json` with the upgraded importer
(trait routing, grapple riders, expanded 51-spell library, nonmagical-immunity fix, all trait
flags). Recovery vs the original import: **88 breath/save areas, 21 frightful presence, 24 pounce,
3 swallow, 32 attacks with grapple riders**, casters un-gutted (**Lich 11 spells**), Werewolf &
17 others no longer wrongly immune to all physical.

**Robustness (all 450 combat monsters):**
- Heuristic + Random, every monster vs a benchmark: **900 battles, 0 crashes, 0 round-cap draws.**
- Determinism: **0/70 sample mismatches**; same seed → identical log.
- LLM sample (5 complex monsters vs Heuristic): **100% legal-choice over 54 decisions.**

**Signature abilities fire in play:** grapplers grapple (11), casters cast (22), petrification (3),
frightful presence (24), swallow, and breath (**18/26** breath-users vs a worthwhile cluster —
high-CR dragons often melee weak foes before breathing). LLM: Behir breathes + swallows, Lich casts.

**Two importer bugs found & fixed by the playtest:**
- **Swarms never attacked** — their Bite is "reach 0 ft. (in the swarm's space)"; with no
  space-sharing, reach 0 = unreachable. Fixed: melee reach clamped to ≥5. Swarm×2 vs Guard×2 went
  **0% → 66%/83%**.
- **"or 1d6 if bloodied" clauses** were parsed as a *second* damage entry (swarms hit for 2d6+1d6).
  Fixed: the bloodied clause is stripped before damage parsing (the swarm flag models the reduction).

**Known balance notes (partial subsystems / heuristic tuning, not blockers):** Gorgon under-uses its
(no-damage) Petrifying Breath under Heuristic; swarm space-sharing + single-target-only mechanics are
not modelled (they resist B/P/S, which suffices for playability).
