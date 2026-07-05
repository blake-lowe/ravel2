# PC Audit — Arcane/Nature classes (Wizard, Bard, Sorcerer, Warlock, Druid) + PC spellcasting & Wild Shape

Auditor scope: the five arcane/primal PC classes (base L1–20 + registered subclasses), the shared
PC spellcasting rules (slots incl. pact, prepared/known, cantrip scaling, concentration, upcasting,
bonus-action spell rule), and Wild Shape. Sources read: `ravel/character.py`, `ravel/cast.py`,
`ravel/engine.py`, `ravel/rules.py`, `ravel/rest.py`, `ravel/skills.py`, `ravel/spelllists.py`,
`data/spells/eldritch_blast.json`, `data/spells/hex.json`, `docs/SLICE6_PLAN.md`, and the
`tests/test_class_{bard,sorcerer,warlock,druid}.py` + `test_slice6_dod.py` pins.

Legend: **OK** = RAW-accurate · **APPROX** = simplified *and* documented · **INACCURATE** =
silently violates RAW · **MISSING** = name-only in `CLASS_FEATURES`/`SUBCLASSES`.

---

## Shared PC spellcasting rules

| Rule | Status | Where / note |
|---|---|---|
| Full-caster slot table L1–20 | **OK** | `character.py:196` `FULL_CASTER_SLOTS`, matches PHB |
| Pact slots (all one level, short-rest recharge) | **OK** | `PACT_SLOTS` `character.py:209`; `caster_slots("pact")` `:230`; `rest._pact_slots` `rest.py:121` |
| Multiclass combined slot table (§11.5), pact separate | **OK** | `multiclass_slots` `character.py:238`; pact stacked on top `character.py:1281` |
| Prepared model (Wizard/Cleric/Druid = mod+level) | **OK** | `wizard/cleric/druid_spells_prepared`; enforced in `validate_character` |
| Known model (Bard/Sorcerer/Warlock caps) | **OK** | `_BARD/_SORCERER/_WARLOCK_KNOWN` `character.py:358`; Mystic Arcanum excluded from Warlock count `:826` |
| Concentration: one spell, break-on-damage CON save DC max(10, dmg/2), War Caster adv | **OK** | `rules._concentration_save` `rules.py:101–113`; new-cast ends prior `cast.py:230` |
| Upcast damage scaling per spell data | **OK** | `_scaled_damage` `cast.py:698`; `missiles/rays/targets` count scaling `_scaled_count :714` |
| Bonus-action spell rule (no leveled bonus after a leveled spell; cantrip still allowed) | **OK** | `cast.py:122–123`; `_spend_cast` sets `cast_leveled_this_turn` `:190–199`; Quicken honours it `engine.py:1178` |
| Ritual casting | **N/A (correctly)** | Non-action casts filtered out of the combat loop `cast.py:113`; out of combat scope |
| **Cantrip damage scaling by level (5/11/17)** | **INACCURATE** | Uses **class** level, not **character** level — see Finding #1 |
| Multiclass spell DC / ability | **APPROX (undisclosed)** | `compile_character` picks the *first* caster class for DC/attack/cantrip level `character.py:1250–1257`; each class should use its own ability. Single-class exact; multiclass edge |

---

## Wizard (base + subclasses)

| Feature | Status | Note |
|---|---|---|
| Spellcasting (INT, prepared, cantrips 3/4/5) | **OK** | `wizard_cantrips_known` `:664`, `wizard_spells_prepared` `:668` |
| Arcane Recovery (½ level ≤5th, 1/day on short rest) | **OK** | `rest._arcane_recovery` `rest.py:132`; budget `(wiz+1)//2`, levels 5→1, resource 1/long-rest |
| Spell Mastery (L18 at-will 1st+2nd) | **OK** | compiled to innate `per_day=0` `character.py:1288` |
| Signature Spells (L20 free 1/day) | **OK** | innate `per_day=1` `character.py:1292` |
| School of Evocation — Sculpt/Potent Cantrip/Empowered/Overchannel | **OK / APPROX** | Potent Cantrip `cast.py:385,439`, Empowered Evocation +INT `cast.py:357`; Sculpt Spells (ally-exclusion) and Overchannel = name-only follow-ons |
| School of Abjuration — Arcane Ward | **APPROX** | HP = 2·wiz+INT `arcane_ward_max :851` (RAW ✓); recharge +2·slot on abjuration cast `cast.py:280` (RAW ✓). **Starts pre-charged at max** rather than created by the first abjuration cast — undisclosed simplification (minor) |
| School of Abjuration — Improved Abjuration, Spell Resistance | **OK (partial)** | Spell Resistance flag compiled `:1216`; Improved Abjuration name-only |
| School of Divination — Portent / Greater Portent | **APPROX (undisclosed narrowing)** | 2 (3 at L14) dice pre-rolled at initiative `engine.py:184`; but only ever forces an **enemy save vs the diviner's own spell** and only if it makes them fail `cast.py:79–88`. Cannot replace the diviner's own d20, an ally's roll, or an enemy attack roll — see Finding #3 |
| School of Conjuration — Focused Conjuration (dmg can't break conc.) | **OK** | `rules.py:104`; other features name-only |
| School of Necromancy — Grim Harvest / Inured to Undeath | **OK** | Grim Harvest reap `cast.py:273`; Inured adds necrotic resist `:1226`; Command/Undead Thralls name-only |
| School of Enchantment — Hypnotic Gaze | **OK** | `engine._do_hypnotic_gaze :449`; Instinctive Charm etc. name-only |
| School of Illusion — Illusory Self | **OK** | flag + resource `character.py:651`; other features name-only |
| School of Transmutation — Transmuter's Stone (fire resist) | **APPROX** | one fixed benefit (fire resist) `:1224`; the selectable stone is simplified |

---

## Bard (base + subclasses)

| Feature | Status | Note |
|---|---|---|
| Spellcasting (CHA, known) | **OK** | caps `_BARD_KNOWN`; cantrips 2/3/4 |
| Bardic Inspiration (die d6→d12, bonus action, added after the roll) | **APPROX** | `engine._do_bardic_inspiration :1534`; spent in `rules.py:462`. **Recipient can only add it to an attack roll (to rescue a miss)** — not to saves or ability checks (RAW allows any of the three). Disclosed (SLICE6_PLAN WP3) |
| Font of Inspiration (L5 short-rest recovery) | **OK** | `rest._font_of_inspiration :91` |
| Jack of All Trades (½ prof on non-proficient checks) | **INACCURATE (partial)** | Applied to skills `skills.py:52` ✓ but **not to initiative** (`engine.py:180`) — RAW includes initiative. See Finding #2 |
| Song of Rest (die on short-rest HD healing) | **APPROX** | `rest._song_of_rest_die :82`; single-combatant approximation of a party effect (disclosed) |
| Expertise (L3 & L10) | **OK** | `level_choices :1022`, `_skill_bonuses :1162` |
| Magical Secrets (L10/14/18) | **MISSING** | name-only `character.py:440–443`; no cross-list spell grant |
| Countercharm (L6) | **MISSING** | name-only |
| Superior Inspiration (L20) | **MISSING** | name-only |
| College of Lore — Cutting Words | **APPROX** | `engine.bard_cutting_words :417`; reaction subtracts a die from an enemy **attack roll** only, and only when it flips hit→miss. RAW also covers damage rolls and ability checks. Disclosed |
| College of Lore — Additional Magical Secrets / Peerless Skill | **MISSING** | name-only |
| College of Valor — martial/medium/shield + Extra Attack (6) | **OK** | profs `character.py:1117`, Extra Attack `:1231` |
| College of Valor — Combat Inspiration / Battle Magic | **MISSING** | name-only (Combat Inspiration variant is a disclosed follow-on) |

---

## Sorcerer (base + subclasses)

| Feature | Status | Note |
|---|---|---|
| Spellcasting (CHA, known); cantrips 4/5/6 | **OK** | `_SORCERER_KNOWN`; cantrip cap `validate_character :821` |
| Sorcery Points (= level, long rest) | **OK** | `class_resources :394`; restored by `long_rest` |
| Font of Magic — points↔slots conversion | **APPROX** | **Not implemented**; points fuel metamagic only. Disclosed (SLICE6_PLAN) |
| Metamagic — Quickened | **OK** | `engine.py:1167–1181`; 2 pts, one-leveled-spell rule enforced |
| Metamagic — Empowered | **APPROX** | `cast.py:262`; approximated as reroll 1s+2s (`reroll_below=2`), auto-applied. Disclosed |
| Metamagic — Twinned / Careful / Distant / Heightened / Subtle / Extended | **MISSING** | Absent. Disclosed as "others noted" (SLICE6_PLAN) |
| Sorcerous Restoration (L20, +4 pts on short rest) | **MISSING** | name-only `character.py:491`; not in `rest.py` |
| Draconic Bloodline — Draconic Resilience (AC 13+DEX, +1 HP/lvl) | **OK** | `unarmored_defense_mod :331`, HP `max_hp :1153` |
| Draconic Bloodline — Elemental Affinity (+CHA to one damage roll) | **APPROX** | `cast.py:378`; fixed to fire (Red ancestry). Disclosed |
| Draconic Bloodline — Dragon Wings / Draconic Presence | **MISSING** | name-only |
| Wild Magic — Tides of Chaos (adv 1/rest) | **OK** | resource `subclass_resources :655`, spent `rules.py:407` |
| Wild Magic — Surge table / Bend Luck / Controlled Chaos | **MISSING/APPROX** | Surge table deliberately omitted (no unseeded RNG) — disclosed; Bend Luck etc. name-only |

---

## Warlock (base + subclasses)

| Feature | Status | Note |
|---|---|---|
| Pact Magic (all slots one level, short-rest recharge) | **OK** | `PACT_SLOTS`; `_pact_slots` restores on short rest |
| Eldritch Blast (beams 1/2/4 scale by level, separate attack rolls) | **APPROX** | `eldritch_blast.json` `scaling.mode:"beams"`; `_scaled_count :716` = 1/2/3/4 at 1/5/11/17 ✓; each beam a separate roll `cast.py:389–393` ✓. **All beams focus the primary target** (can't split across foes). Disclosed |
| Agonizing Blast (+CHA per beam) | **OK** | `cast.py:376`, auto-granted at warlock≥2 `character.py:1444`; per-beam ✓ |
| Hex (bonus action, concentration, +1d6 necrotic/hit) | **APPROX** | `hex.json` + `mark` effect `cast.py:463`. **No move-on-kill to a new target; ability-check-disadvantage clause omitted.** Disclosed |
| Mystic Arcanum (6th–9th as innate, 1/**long** rest each) | **OK** | `MYSTIC_ARCANUM :365`; compiled to innate `per_day=1` `character.py:1298`; restored only by `long_rest` (innate_left) ✓. Fixed one-per-level *picker* is a builder follow-on (disclosed) |
| Eldritch Invocations (choice list) / Pact Boon | **APPROX** | only Agonizing Blast auto-granted; full invocation & boon list is a disclosed follow-on |
| Eldritch Master (L20, regain pact slots 1/long rest) | **MISSING** | name-only |
| The Fiend — Dark One's Blessing (temp HP on kill) | **OK** | `temp_hp_on_kill :1466`, on_kill trigger |
| The Fiend — Dark One's Own Luck / Fiendish Resilience / Hurl Through Hell | **MISSING** | name-only |
| The Great Old One — Entropic Ward (reaction, 1/short rest) | **OK** | `engine.try_entropic_ward :438` |
| The Great Old One — Awakened Mind / Thought Shield / Create Thrall | **MISSING** | name-only (Awakened Mind non-combat, disclosed) |

---

## Druid (base + subclasses)

| Feature | Status | Note |
|---|---|---|
| Spellcasting (WIS, prepared); cantrips 2/3/4 | **OK** | `druid_spells_prepared :368`; `validate_character :810` |
| Wild Shape (2 uses/short rest; beast body swap; beast HP pool; revert carries excess) | **APPROX** | `engine.apply_wild_shape :1499`, `rules.revert_wild_shape :127`. Duration (hours = ½ level) not tracked — form lasts the fight or until 0 HP (irrelevant in a bout). Senses/skills/class features not re-derived onto beast; flight/swim gating approximated by CR cap only. All disclosed |
| — can't cast in form, but **can maintain concentration** | **OK** | Beast md has no spells (casting blocked); `apply_wild_shape` does not touch `actor.concentration`, so a pre-existing concentration persists (RAW-correct) |
| — equipment melds; temp HP vs form HP | **OK** | `actor.equipment=None`, beast HP separate pool, druid HP preserved in `base_hp` `:1518–1522` |
| Wild Shape CR cap by level | **OK** | `wild_shape_max_cr :348`; land 1/4·1/2·1 at 2/4/8 |
| Beast Spells (L18 cast while shaped) | **MISSING** | name-only `character.py:455` |
| Timeless Body / Archdruid | **MISSING** | name-only (non-combat) |
| Circle of the Moon — Combat Wild Shape (bonus action; slot→heal 1d8/lvl) | **OK** | bonus-action shape `engine.py:1154`; `_do_moon_heal :1544`; CR = level/3 at 6+ `:352` |
| Circle of the Moon — Primal Strike (magical attacks) / Elemental Wild Shape | **MISSING** | name-only (disclosed follow-ons) |
| Circle of the Land — Natural Recovery (Arcane-Recovery clone) | **OK** | `rest._natural_recovery :101`; ½ level ≤5th, 1/short rest |
| Circle of the Land — Circle Spells / Land's Stride / Nature's Ward / Sanctuary | **MISSING** | name-only |

---

## Heuristic caster AI — do the features actually fire?

Reviewed `controllers.py` (`decide`). The AI **does** exercise the headline arcane resources, so
they are not de-facto missing:

- Wild Shape (Moon, bonus action) — `controllers.py:119–129` (picks beefiest legal form when a foe ≤30 ft).
- Combat-Wild-Shape heal — `:131–134` (when ≤40% HP).
- Bardic Inspiration — `:136–140` (banks on strongest ally).
- Quickened Spell — `:175–180` (blast in the bonus phase).
- Cutting Words / Entropic Ward — automatic reactions in `rules.resolve_attack` (`rules.py:470–477`).
- Empowered Spell / Agonizing Blast / Elemental Affinity — automatic in `cast.py`.

**Never-picked (APPROX-by-omission):**
- **Non-Moon Wild Shape** — enumerated as an **action** (`engine.py:972`) but the AI only shapes on
  the *bonus-action* Moon path; a land druid never wild-shapes in a bout (correct-ish: a land druid
  gains little combat value from shaping, but it is untested in play).
- **Sorcery-point spending is Quicken-only** — Empowered auto-fires, but with no slot↔point conversion
  and no other metamagic the sorcerer rarely drains points; consistent with the documented v1 scope.

---

## Findings (ranked by impact)

> **STATUS UPDATE (2026-07-03, audit-fix WP5).** Fixed with regression tests (suite 511 green):
> **#1 Cantrip scaling** — now by **character** level for multiclass casters via
> `MonsterDef.cantrip_level = ch.level` (slots/known stay on class level); `cast._scaled_damage` and
> `_scaled_count` read `actor.md.cantrip_level or actor.caster_level`. Single-class casters and
> monsters (cantrip_level 0 → falls back to caster_level) are unchanged. A Wizard 4 / Fighter 4 now
> casts Fire Bolt at 2d10. **#2 Jack of All Trades** — half-proficiency now added to **initiative** in
> `engine.roll_initiative` (same term covers Champion Remarkable Athlete). **Still open (recorded
> follow-ons):** #3 Portent broadening (only forces enemy saves vs the diviner's own spells today);
> #4 Arcane Ward pre-charge (starts at max vs created on first abjuration cast); #5 Magical Secrets
> (highest-value gap) + the L20 capstones / Beast Spells; #7 multiclass spell DC/ability (uses only
> the first caster class). #6 (Bardic Inspiration / Cutting Words attack-roll-only) stays a documented
> APPROX.

### 1. Cantrip damage scaling uses **class** level, not **character** level — INACCURATE (undisclosed)
`compile_character` sets `caster_level = ch.class_levels[caster_cls.name]` (the single caster
class's level) at **`character.py:1257`**, and `_scaled_damage` derives the cantrip tier from it:
`lvl = actor.caster_level or 1; tier = 1 + (lvl>=5) + (lvl>=11) + (lvl>=17)` (**`cast.py:696`**).
RAW (PHB, "Cantrips"): a cantrip's damage scales at **character** level 5/11/17, and for a
multiclass character you use total character level. A Wizard 4 / Fighter 4 (character level 8)
casting Fire Bolt should deal **2d10**; here it deals 1d10 (class level 4 < 5).
*Impact:* single-class casters are unaffected (class level = character level); only multiclass
casters underscale — a real but low-frequency arena case. The multiclass section documents the
*slot* handling but is silent on cantrip scaling.
*Fix:* pass the character level to cantrip scaling — e.g. store `caster_level` for cantrips as
`ch.level` (or add a separate `cantrip_level = ch.level` field on `MonsterDef`), leaving slot/known
tables keyed on class level. The non-caster cantrip path already uses `lvl` (character level,
`character.py:1322`), so only the class-caster branch needs the change.

### 2. Jack of All Trades not applied to initiative — INACCURATE (undisclosed)
`roll_initiative` computes `c.initiative = roll + DEX mod + (5 if alert)` at **`engine.py:180`**
with no half-proficiency term. RAW (PHB Bard L2): Jack of All Trades adds half proficiency to any
ability check that doesn't already include it, **including initiative** (a DEX check). Same gap
affects Champion Remarkable Athlete (out of arcane scope; flag exists at `models.py:206`).
*Impact:* a bard's initiative is low by `prof//2` (1–3). Minor but silent.
*Fix:* in `roll_initiative`, add `+ c.md.prof_bonus // 2` when `c.md.jack_of_all_trades`
(and `c.md.remarkable_athlete`) and the creature isn't otherwise proficient in initiative.

### 3. Portent only forces enemy saves against the diviner's own spells — APPROX (undisclosed narrowing)
`_portent_die` (**`cast.py:79–88`**) fires only inside `save`-effect resolution, only for
`target.team != actor.team`, and only when the low die makes the enemy fail. RAW (PHB Divination):
after a long rest you may **replace any attack roll, saving throw, or ability check** made by
**yourself or a creature you can see** with a Portent die. Missing coverage: the diviner's own d20s,
protecting an ally by forcing an enemy's attack roll high→the die, and any non-spell save.
*Impact:* medium — Portent is a subclass headline and functions only in its narrowest slice; the
narrowing is not documented (the model comment merely says "pre-rolled Portent dice").
*Fix:* thread a Portent hook into `resolve_attack`/`saving_throw` so a diviner can substitute a die
on any visible creature's roll (enemy attack vs ally, own attack/save), not just enemy spell saves;
or at minimum document the current scope as an approximation.

### 4. Arcane Ward is pre-charged at max instead of created on first abjuration cast — APPROX (undisclosed)
`to_combatant` seeds `arcane_ward = arcane_ward_max` (**`character.py:1650`**). RAW: the ward
doesn't exist until the abjurer casts a 1st+-level abjuration spell (then HP = 2·wiz+INT); before
that there is no ward. Ours grants the buffer from round 1 for free.
*Impact:* low (a small free damage buffer earlier than RAW). *Fix:* start `arcane_ward = 0` and set
it to max on the first abjuration cast in `cast.py:280`, or document as a simplification.

### 5. Class-capstone / late features that are name-only — MISSING (mostly undisclosed)
`CLASS_FEATURES` lists but does not implement: **Bard** Magical Secrets (L10/14/18), Countercharm
(L6), Superior Inspiration (L20); **Sorcerer** Sorcerous Restoration (L20); **Warlock** Eldritch
Master (L20); **Druid** Beast Spells (L18). These are enumerated as feature *names* only. Magical
Secrets is the most impactful (it materially changes a bard's spell list) and is **not** flagged as
a follow-on in SLICE6_PLAN; the L20 capstones and Beast Spells are low-impact in a 4-CR arena.
*Fix:* implement Magical Secrets as extra cross-list `spells`/known-cap entries; note the rest as
named follow-ons in the ledger so they aren't silently absent.

### 6. Bardic Inspiration & Cutting Words are attack-roll-only — APPROX (disclosed)
Bardic Inspiration adds its die only to a recipient's **attack roll** to rescue a miss
(`rules.py:462`); Cutting Words subtracts only from an enemy **attack roll** (`engine.py:429`).
RAW lets Inspiration apply to any ability check / attack / save the holder chooses, and Cutting
Words to attack **or ability check or damage roll**. Both are documented in SLICE6_PLAN WP3, so
APPROX rather than INACCURATE — flagged here because it narrows two subclass/base headlines.

### 7. Multiclass spell DC/ability uses only the first caster class — APPROX (undisclosed)
`compile_character` (`character.py:1250`) selects one `caster_cls` for `spell_ability`, `spell_dc`,
and `spell_attack`; a Sorcerer/Warlock or Wizard/Cleric build uses a single ability for everything.
Slots are correct (multiclass table). *Impact:* multiclass-caster edge only. *Fix:* per-spell
ability by originating class is a larger change; document the current single-ability approximation.

---

## Status counts (arcane scope)

- **OK:** ~34 (all shared slot/known/prepared/concentration/upcast rules; Arcane Recovery; Spell
  Mastery/Signature; Pact Magic; Agonizing Blast; Mystic Arcanum long-rest timing; Wild Shape body
  swap + concentration-in-form + revert carryover; Moon bonus-action + CR curve; Natural Recovery;
  Dark One's Blessing; Entropic Ward; Draconic Resilience; Quickened; Tides of Chaos; Cutting Words
  mechanism; Font of Inspiration).
- **APPROX (documented):** ~14 (Bardic Inspiration scope; Cutting Words scope; Empowered Spell;
  Elemental Affinity fire-fixed; Font-of-Magic conversion absent; Wild Magic Surge absent; Hex
  hop/check clauses; EB single-target focus; Wild Shape duration/senses/flight; Mystic Arcanum
  picker; Transmuter's Stone; Sculpt/Overchannel; Arcane Ward pre-charge — *undisclosed*; Portent
  narrowing — *undisclosed*; multiclass DC — *undisclosed*).
- **INACCURATE (silent):** 2 — cantrip scaling on class vs character level (#1); Jack of All Trades
  omitted from initiative (#2).
- **MISSING (name-only):** ~9 headline/late features — Magical Secrets, Countercharm, Superior
  Inspiration, Sorcerous Restoration, Eldritch Master, Beast Spells, plus assorted higher-level
  subclass features (Dragon Wings, Bend Luck/Controlled Chaos, Instinctive Charm, Split Enchantment,
  Command Undead, Land's Stride/Nature's Ward/Sanctuary, Fiendish Resilience/Hurl Through Hell,
  Thought Shield/Create Thrall, Improved Abjuration, The Third Eye, etc.).

No determinism-boundary or IO-purity violations found in the arcane path; all randomness flows
through the seeded RNG and no LLM is touched in the mechanics.
