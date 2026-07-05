# PC Audit — Divine classes + Chargen (Cleric / Paladin / Ranger, Races, Backgrounds, Multiclass, ASI/Point-buy, Rest)

Auditor scope: Cleric, Paladin, Ranger (base L1-20 + their subclasses), **all races**,
**backgrounds**, **multiclass rules**, **ASI/point-buy**, and **rest/recovery** for these
classes. Method: traced every feature from `ravel/character.py` (CLASS_FEATURES / RACES /
BACKGROUNDS / MULTICLASS_PREREQS / `multiclass_slots` / `compile_character`) into
`engine.py`, `rules.py`, `cast.py`, `triggers.py`, `modifiers.py`, `controllers.py`,
`rest.py`, and cross-checked the `tests/test_class_*.py` pins. `docs/SLICE6_PLAN.md`
claims were verified against code, not trusted.

Legend: **OK** = mechanized & RAW-accurate · **APPROX** = simplified *and* disclosed ·
**INACCURATE** = silently violates RAW · **MISSING** = name-only.

Status counts: **OK 41 · APPROX 22 · INACCURATE 5 · MISSING 14.**

---

## Cleric

| Feature (level) | Status | Note / location |
|---|---|---|
| Spellcasting (full WIS, prepared = WIS+lvl, cantrips 3/4/5) | OK | `character.py:672,792`; `compile_character` DC/attack/slots |
| Channel Divinity uses 1/2/3 at 2/6/18, **short-rest recovery** | OK | `class_resources:398`; `rest.SHORT_REST_RESOURCES:23` |
| Turn Undead — WIS save vs spell DC, 30 ft, turned = frighten+flee | APPROX | `engine.py:1422`. Duration a fixed 10 rounds, but **does not end when the creature takes damage** and turned foes can still take reactions (see Finding 5) |
| Destroy Undead CR 1/2·1·2·3·4 at 5/8/11/14/17 | OK | `character.py:1397`; `engine.py:1434`. (Feature-name table omits the "CR 1 @ L8" label — cosmetic, Finding 12) |
| Divine Intervention (10), Improvement (20) | MISSING | Name-only in `CLASS_FEATURES:448-450`; non-combat, disclosed follow-on (SLICE6 WP2) |
| Life: Disciple of Life (+2+slvl heal), Preserve Life channel | OK | `disciple_of_life` rider in cast path; Preserve Life `engine.py:1442` — 5×lvl pool, half-HP ceiling, 30 ft, excludes undead/construct. RAW-correct |
| Life/War: Divine Strike +1d8→2d8 at 8/14, once/turn | OK | `character.py:1404`; Life=radiant, War=weapon type. Correct |
| War: War Priest (bonus attack, WIS/rest, long-rest recovery) | OK | `subclass_resources:652`; enumerated `engine.py:1134`; long-rest recovery correct |
| War: Guided Strike channel (+10 to a would-miss) | OK | `engine.py:374`; shares Channel Divinity pool. Correct |
| War: **War God's Blessing (6)** — reaction, +10 to an ally's attack | MISSING | Listed `character.py:586`; **no engine mechanic** and **not disclosed** as a follow-on (Finding 3) |
| War: Avatar of Battle (17) | MISSING | Name-only; damage-resistance capstone, undisclosed |

## Paladin

| Feature (level) | Status | Note / location |
|---|---|---|
| Half CHA caster, no slots at L1, prepared = CHA+lvl/2 | OK | `caster_slots("half")` `character.py:227`; `paladin_spells_prepared:677` |
| Lay on Hands pool 5×level (from L1), action heal | APPROX | Pool/heal correct `engine.py:1483`; but the **option only ever targets self** (`engine.py:968`), so allies can't be healed in a bout, and it's only offered while wounded (Finding 8) |
| Divine Smite — highest slot ≤5th, 2d8+1/lvl (max 5d8), +1d8 vs undead/fiend, crit doubles | APPROX | Dice math RAW-correct `engine.py:386`. **But hard-gated to once/turn + only vs targets ≥10 HP, and auto-fires (never a controller choice)** — diverges from RAW no-per-turn-cap (Finding 4) |
| Divine Health (3) — disease immunity | MISSING | Name-only; non-combat, acceptable follow-on |
| Extra Attack (5) | OK | `extra_attacks("Paladin"):289` |
| Aura of Protection (6) — +CHA to saves, allies ≤10 ft, needs paladin conscious | APPROX | `rules.aura_of_protection_bonus:240` — conscious/alive/≤10 ft all correct. **Missing the RAW "minimum +1"** (CHA-0 paladin gives +0), and the 30-ft bump at 18 is a disclosed follow-on (Finding 6) |
| **Aura of Courage (10)** — allies ≤10 ft can't be frightened | MISSING | **No implementation anywhere** — only the name in `CLASS_FEATURES:470`. Combat-relevant (engine has real `frightened`), **undisclosed** (Finding 2) |
| Improved Divine Smite (11) — +1d8 every melee hit | OK | `character.py:1413` rider `when="on_hit", kind="melee", once_per_turn=False`. Correct |
| Cleansing Touch (14), Aura Improvements (18, →30 ft), Sacred Oath Capstone (20) | MISSING/APPROX | 18-ft aura range is a disclosed follow-on; Cleansing Touch & L20 name-only |
| Devotion: Sacred Weapon channel (+CHA to hit, 1 min) | OK | `engine.py:1465`, 10-round buff; bonus-action enumerated `engine.py:1124` |
| Devotion: Turn the Unholy (3), Aura of Devotion (7, charm-immune aura), Purity of Spirit (15), Holy Nimbus (20) | MISSING | Name-only; Aura of Devotion is combat-relevant but undisclosed alongside Aura of Courage |
| Vengeance: Vow of Enmity channel (advantage vs 1 foe) | APPROX | `engine.py:1474`; read in `resolve_attack:369`. Lasts until the foe falls rather than a 1-min timer (disclosed) |
| Vengeance: Abjure Enemy (3), Relentless Avenger (7), Soul of Vengeance (15), Avenging Angel (20) | MISSING | Name-only, undisclosed |

## Ranger

| Feature (level) | Status | Note / location |
|---|---|---|
| Favored Enemy / Natural Explorer (1) + improvements (6) | MISSING | Name-only `CLASS_FEATURES:474`; out-of-combat, disclosed follow-on |
| Half WIS caster, Spells Known table | OK | `ranger_spells_known:682` = `1+(level+1)//2` — matches PHB L2-20 exactly; validated `character.py:805` |
| Fighting Style (2), prompted | OK | `level_choices:1026`; applied via `fighting_styles` |
| Extra Attack (5) | OK | `extra_attacks("Ranger"):289` |
| Hunter's Mark (spell) — bonus action, concentration, +1d6/hit | APPROX | `data/spells/hunters_mark.json` + `cast.py:463` mark rider. **Deals `force`, not the weapon's type**, and does not hop to a new target when the marked foe dies (both disclosed follow-ons, Finding 7) |
| Land's Stride (8), Hide in Plain Sight (10), Vanish (14), Feral Senses (18) | MISSING | Name-only; mostly non-combat, disclosed follow-ons (Feral Senses has a minor combat edge) |
| **Foe Slayer (20)** — +WIS to one attack/damage roll per turn | MISSING | Name-only, undisclosed; a real combat feature |
| Hunter: Colossus Slayer (3) — +1d8 once/turn vs below-max-HP | OK | rider `when="target_wounded", once_per_turn=True` `character.py:1421`; predicate `modifiers.py:67`. Stacks with Hunter's Mark (pinned `test_class_ranger.py:80`) |
| Hunter: Defensive Tactics (7), Multiattack (11), Superior Hunter's Defense (15) | MISSING | Name-only, undisclosed |
| Beast Master: Ranger's Companion | APPROX | Better than the SLICE6 note — actually **spawns a real `Wolf` combatant** (`engine._spawn_companions:864`). Companion gets its own initiative (disclosed simplification), fixed to a Wolf, no level-scaled companion stats |

---

## Races (§12.1)

| Race / trait | Status | Note |
|---|---|---|
| Human (+1 all, +1 language) | OK | `RACES:71` |
| Hill Dwarf — +CON/+WIS, 25 ft, darkvision, poison resist+save adv, +1 HP/lvl, dwarf weapons | OK | `RACES:73`; Toughness `max_hp:1151` |
| Mountain Dwarf — +STR/+CON, light+medium armor training | OK | `RACES:77`, armor union `character_proficiencies:1113` |
| Dwarven Resilience (adv + resistance vs poison) | OK | `save_advantages` + `resistances` both set. RAW-correct |
| High/Wood Elf — +DEX, Fey Ancestry (adv vs charm), Elf weapons, High Elf cantrip | OK | `RACES:82,86` |
| Elf **immunity to magical sleep** | MISSING | Only charm advantage modelled; sleep-immunity not represented (no sleep in engine — low impact, undisclosed) |
| Lightfoot/Stout Halfling — Brave (adv vs frightened), Stout poison resist+adv | OK | `RACES:90,93` |
| Halfling **Lucky** (reroll nat 1s) | APPROX | Disclosed follow-on — needs a per-d20 dice hook (`RACES` note:62). NB: this is the *racial* Lucky, distinct from the Lucky feat (which IS a resource) |
| Halfling **Nimbleness** (move through larger creatures) | MISSING | Not modelled, undisclosed; minor |
| Dragonborn (Red) — +STR/+CHA, fire resist, breath cone 2/3/4/5 d6 @1/6/11/16, DC 8+CON+prof | APPROX | `compile_character:1341`. Save/scaling/DC correct, but modelled as **Recharge 5-6, not 1/short-rest** (disclosed); only the **Red** ancestry exists (one default, disclosed) |
| Rock Gnome — Gnome Cunning | APPROX | `magic_resistance` flag = adv on ALL saves vs spells; RAW is INT/WIS/CHA-only (disclosed, slightly broad) |
| Half-Elf — +CHA/+DEX/+CON, Fey Ancestry, 2 skills | APPROX | Fixed DEX/CON + Persuasion/Perception instead of player choice (disclosed) |
| Tiefling — +CHA/+INT, fire resist, innate Hellish Rebuke 1/day | APPROX | `RACES:108`; Thaumaturgy/Darkness omitted (disclosed). Hellish Rebuke fires via on-damage reaction |
| Half-Orc — +STR/+CON, Intimidation, Relentless Endurance, Savage Attacks | OK*/INACCURATE | Relentless Endurance (drop to 1, not killed outright, 1/long rest) RAW-correct `rules.py:162`. **Savage Attacks over-rolls for multi-die weapons** (Finding 1) |
| Menacing / darkvision / languages across races | OK | `character_languages:1123` surfaces concrete + "Any (N)" choice count |

## Backgrounds (§12.2/12.4)

| Item | Status | Note |
|---|---|---|
| 12 backgrounds, 2 skill profs each | OK | `BACKGROUNDS:858`; folded into `_skill_bonuses:1161` and Expertise eligibility |
| Background bonus languages ("Any (N)") | APPROX | `BACKGROUND_LANGUAGES:875` counts only; the specific-tongue picker is a disclosed follow-on |
| Tool proficiencies, features, equipment | MISSING | §12.5 tools not modelled (disclosed in SLICE6 WP4 follow-ons) |

## Multiclassing (§11.5)

| Rule | Status | Note |
|---|---|---|
| Prerequisites (13+ in each class's key ability, AND/OR clauses) | OK | `MULTICLASS_PREREQS:264` + `_build_warnings:708`; Paladin STR13 **and** CHA13, Fighter STR13 **or** DEX13. Warnings only, never blocking (by design) |
| Extra Attack doesn't stack | OK | `extra = max(...)` `compile_character:1230` |
| Unarmored Defense doesn't stack | OK | `unarmored_defense_mod:321` returns one source (Barb before Monk) |
| Multiclass spell slots — full + half//2 + third//3 → Multiclass table, round down | OK | `multiclass_slots:238`; switched in when ≥2 casting sources `compile_character:1279`. Pinned by DoD test (Pal2/Wiz3 → `{1:4,2:3}`) |
| Warlock Pact Magic separate pool | APPROX | Pact slots are **merged into the shared slot dict** rather than kept separate (disclosed; single-class Warlock exact) |
| Reduced proficiency grant from later classes | APPROX | `character_proficiencies` **unions full class lists** (disclosed follow-on) |

## ASI / Point-buy

| Item | Status | Note |
|---|---|---|
| Point buy budget 27, scores 8-15, PHB costs | OK | `web/builder.py:29` (`14→7, 15→9`); pinned `test_builder_api.py:37` |
| ASI cap 20 (24 for Barbarian Primal Champion) | OK | `final_abilities:1100` caps at 20; Primal Champion raises STR/CON cap to 24 |
| ASI shape (+2 one / +1 two) validation | APPROX | ASIs are free-form `{Ability:+N}` dicts; the +2/+1+1 legality isn't enforced (builder-side concern; not a combat error) |

## Rest / recovery (these classes)

| Resource | Recovery | Status | Note |
|---|---|---|---|
| Channel Divinity (Cleric/Paladin) | short rest | OK | `SHORT_REST_RESOURCES:23` |
| Lay on Hands pool | long rest | OK | long-rest all-sweep `rest.long_rest:152` |
| War Priest uses | long rest | OK | not in short set → restored on long rest (RAW-correct) |
| Half-caster spell slots (Pal/Ranger) | long rest | OK | `long_rest` resets `c.slots` to `md.spell_slots` |
| Relentless Endurance (Half-Orc) | long rest | OK | `all_resources:1527` → long-rest sweep |
| Spells prepared/known re-derivation | n/a | OK | maxima recomputed from the `Character` each rest (`_resource_maxima:39`) |

---

# Findings (ranked by impact)

> **STATUS UPDATE (2026-07-03, audit-fix WP5).** Fixed with regression tests (suite 511 green):
> **#1 Savage Attacks** — one extra weapon die on a crit (`rng.roll(1, d0.sides)`). **#2 Aura of
> Courage (L10)** — `aura_of_courage` flag; `apply_condition` suppresses `frightened` for allies ≤10 ft
> of a conscious aura-paladin (Devotion's **Aura of Devotion**, L7 charm-immunity, added the same way).
> **#3 War God's Blessing (L6)** — `cleric_war_gods_blessing` reaction grants +10 to an ally's
> would-miss attack ≤30 ft (mirrors Guided Strike). **#4 Divine Smite** — the once-per-turn cap +
> ≥10-HP gate were removed from the resolution path; the spend **policy** now lives in
> `HeuristicController.should_smite` (engine falls back to `default_smite_policy`): always smite a crit,
> otherwise at most one ≥15-HP target per turn. **#5 Turn Undead** — ends the instant the creature
> takes damage (`turned_by` cleared in `apply_damage`). **#6 Aura of Protection** — RAW minimum **+1**
> (`max(1, cha)`). **#8 Lay on Hands** — can now target a wounded ally in reach (enumeration +
> heuristic). **Still open:** #7 Hunter's Mark/Hex damage type + target-hop; #9 Foe Slayer (Ranger 20),
> Aura of Devotion range/oath capstones, Avatar of Battle, Divine Intervention (recorded follow-ons).

### 1. Half-Orc Savage Attacks over-rolls the extra crit die for multi-die weapons — INACCURATE
`rules.py:538-541`:
```python
if crit and attacker.md.savage_attacks and atk.kind == "melee" and atk.damage:
    d0 = atk.damage[0]
    dealt += apply_damage(target, _hd(rng.roll(d0.count or 1, d0.sides or 1)), d0.type, ...)
```
`rng.roll(d0.count or 1, d0.sides)` rolls **`count` dice**. PHB Savage Attacks: "roll **one** of
the weapon's damage dice one additional time." For a greatsword/maul (2d6) this adds **2d6
instead of 1d6** on every crit; correct only for single-die weapons. **Fix:** `rng.roll(1, d0.sides or 1)`.

### 2. Paladin Aura of Courage (L10) is entirely unimplemented and undisclosed — MISSING
Only the string `"Aura of Courage"` exists (`character.py:470`); there is no compile flag, no
`MonsterDef` field, and no engine hook. The engine *does* model `frightened` (Turn Undead,
Frightful Presence), so a level-10+ paladin's party should be immune within 10 ft — a real
combat effect that silently does nothing. **Fix:** add an `aura_of_courage` flag (mirror
`aura_of_protection`) and, in `apply_condition`, suppress `frightened` for allies within 10 ft of a
conscious aura-paladin. (Aura of Devotion / charm-immunity at Devotion L7 is the same shape.)

### 3. War Domain "War God's Blessing" (L6) unimplemented and undisclosed — MISSING
Listed at `character.py:586` but only **Guided Strike** (L2) is wired (`engine.py:374`). RAW L6 is a
separate reaction: when a creature within 30 ft makes an attack roll, spend Channel Divinity to
grant +10. Not a disclosed follow-on in SLICE6 WP2. **Fix:** add a reaction mirroring
`cleric_guided_strike` but keyed to allies' attacks, or explicitly log it as a follow-on.

### 4. Divine Smite is hard-gated once/turn + ≥10-HP target, and auto-fires — APPROX (RAW divergence baked into mechanics)
`engine.py:391`: `if attacker.smite_used or target.hp < 10: return 0`. RAW places **no
once-per-turn cap** on Divine Smite — a paladin with Extra Attack may smite on every hit while
slots last. The docstring discloses this as a slot-conservation *policy*, but it is enforced in the
resolution path (not the controller), so it removes a legal option and always fires on the first
qualifying hit (the paladin can never bank slots for spells). Acceptable for AI-vs-AI, but note it
is a deliberate deviation, not RAW. Consider moving the conserve logic into `controllers.py`.

### 5. Turn Undead does not end when the turned creature takes damage — INACCURATE
`engine.py:1438` applies `frightened` + `routed` for a fixed `duration=10`. PHB: a turned creature's
condition **ends if it takes any damage**, and it "can't take reactions." Ours persists the full
minute regardless of damage and doesn't suppress reactions. Low frequency (few undead in the
arena) but a silent RAW break. **Fix:** clear the turned state in `apply_damage`/`handle_drop` when
the source is the turner's team, or tag the condition as damage-breakable.

### 6. Aura of Protection ignores the RAW minimum +1 — INACCURATE (edge)
`character.py:1412` `aura_of_protection = cha if paladin >= 6 else 0`; `rules.py:252` takes the max
mod. RAW grants "Charisma modifier, **minimum +1**." A CHA-10 paladin (mod 0) gives +0. Paladins
almost always have high CHA, so low impact. **Fix:** `max(1, cha)` at L6+.

### 7. Hunter's Mark / Hex damage type + target-hop — APPROX (disclosed)
`data/spells/hunters_mark.json` deals **`force`**; RAW is the weapon's damage type (untyped/weapon).
Neither hops to a new target on the marked foe's death (rider goes inert). Both disclosed in
SLICE6 WP2/WP3. Type only matters against `force`-resistant/immune foes.

### 8. Lay on Hands can only heal the paladin itself in play — APPROX
`_do_lay_on_hands` supports a target (`engine.py:1483`), but the enumerated option is self-only
(`engine.py:968`, target `actor.id`) and only offered while wounded. So a paladin can't spend the
pool on a dying ally. **Fix:** enumerate ally targets within reach when allies are wounded.

### 9. Missing name-only combat features (disclosed follow-ons unless noted) — MISSING
Ranger **Foe Slayer (20, undisclosed)**, Feral Senses (18); Paladin oath L7/15/20 features
(Aura of Devotion charm-immunity is combat-relevant and undisclosed); War Domain Avatar of Battle
(17); Cleric Divine Intervention (10). These are the highest-value remaining unbuilt features.

### 10. Cosmetic / minor
- Cleric feature-name table omits the "Destroy Undead (CR 1)" label at L8 (`character.py:446-450`);
  the *mechanic* (`destroy_undead_cr`) is correct, only the display string is missing.
- Elf magical-sleep immunity and Halfling Nimbleness unmodelled/undisclosed (no engine surface today).
- Dragonborn: only the Red ancestry; breath is Recharge 5-6 rather than 1/rest (both disclosed).

---

## What is solid (spot-checks passed)
- Destroy Undead CR thresholds, Divine Strike dice/type/timing, Preserve Life (half-HP ceiling /
  30 ft / no undead-construct), Colossus Slayer predicate + once/turn, Ranger Spells Known table,
  multiclass slot math + prerequisites, point-buy costs, ASI/Primal-Champion caps, Channel Divinity
  short-rest recovery, and half-caster L1-no-slots are all RAW-correct and test-pinned.
- Divine Smite is auto-fired in bouts; Turn Undead / Preserve Life / Vow / Sacred Weapon / War
  Priest / Hunter's Mark all have working heuristics (`controllers.py:78-169`), so they actually
  trigger in fights (verified against the enumeration + priority ladder). Lay on Hands fires only
  as a self-heal (Finding 8).
