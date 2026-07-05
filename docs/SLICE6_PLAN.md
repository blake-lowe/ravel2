# Slice 6 completion plan — the remaining 10 classes + races/feats/multiclass

**Goal (ROADMAP Slice 6 DoD):** build one valid character per class from data; derived
numbers (AC, saves, skills, slots, resources) match known reference characters by test;
multiclass slot table correct. The web builder picks all of this up automatically from
the registries (pinned by `tests/test_builder_api.py::test_meta_mirrors_engine_registries`).

**Standard of done per class** (the bar Fighter/Wizard set):
- `ClassDef` row (hit die, saves, skills, armor/weapons, subclass level, caster type/ability).
- Every combat-relevant BASE feature levels 1-20 in `CLASS_FEATURES` + implemented
  (compile-time stat effects in `compile_character`; in-combat mechanics wired into the
  engine via existing primitives where possible).
- Class resources in `class_resources` with rest-recovery in `ravel/rest.py`
  (`SHORT_REST_RESOURCES` where appropriate).
- ≥2 subclasses with their HEADLINE combat features implemented; minor/out-of-combat
  features listed in `Subclass.features` and noted as follow-ons (Fighter/Wizard precedent).
- A reference-character test with PHB-checkable numbers + an arena smoke (fights an Ogre
  or similar, no crash, deterministic) in `tests/test_class_<name>.py`.
- `validate_character` / `level_choices` extended where the class adds choice points.

**Engine primitives that already exist — REUSE, don't reinvent:**
reckless (self-adv + adv-against), `bonus_damage` riders with predicates
(`sneak_attack`, `charged`, `ally_adjacent_to_target`), conditional modifiers registry
(`modifiers.py`), triggers registry (`triggers.py`: on_kill, would_drop_to_0,
on_turn_start/end), reactions (Shield/Counterspell/Hellish Rebuke/OA/Parry pattern),
concentration auras (caster-anchored), summons, temp HP, crit_range, extra attacks
(`multiattack`), innate (X/day) casting, save advantages (`save_advantages`),
resist/immunity sets, escalating/save-ends conditions, `Combatant.resources`,
full/half/third caster slot tables (`caster_slots`), skills layer w/ expertise + JoAT.

## Work packages (SEQUENTIAL — they share character.py/engine.py/rules.py)

### WP0 — scaffold + data (no combat mechanics) — ✅ DONE (2026-07-02)

**Delivered** (`ravel/character.py` unless noted; `tests/test_slice6_scaffold.py`, 13 tests; full
suite 389 green):
- All 10 `ClassDef` rows (Barbarian…Warlock) with PHB hit die, save profs, skill lists,
  armor/weapon profs, subclass levels, caster type + ability. `ASI_LEVELS` (Rogue +10; rest
  default). `CLASS_FEATURES` base-feature NAME tables L1-20 for all ten (mechanics = WP1-3).
- Numeric `class_resources`: Rage (2/3/4/5/6/∞ by tier), Ki (=monk lvl), Sorcery Points (=sorc
  lvl), Bardic Inspiration (=CHA mod, min 1), Channel Divinity (Cleric 1/2/3, Paladin 1),
  Lay on Hands (5×lvl). Rest recovery via `ravel/rest.py`: Ki/Channel Divinity already in
  `SHORT_REST_RESOURCES`; **Warlock pact slots now restore on a short rest** (`_pact_slots`);
  Rage/Sorcery Points/Lay on Hands/Bardic Inspiration restore on a long rest (all-resources sweep).
- `caster_slots("pact", …)` (PHB Warlock table, `PACT_SLOTS`) + `multiclass_slots(full_half, third)`
  (§11.5 combined caster level → full-caster row; pact separate). `compile_character` switches to
  the multiclass table when 2+ spellcasting sources are present; **single-class behaviour unchanged**
  (pinned by existing tests). Fixed: half-casters (Paladin/Ranger) correctly get **no slots at L1**.
- Races: Mountain Dwarf, Wood Elf, Lightfoot + Stout Halfling, Dragonborn (Red), Rock Gnome,
  Half-Elf, Tiefling. Backgrounds: Noble, Folk Hero, Hermit, Entertainer, Urchin, Charlatan,
  Guild Artisan. Dragonborn **breath weapon** compiles to a self-emanating cone `AreaDef`
  (level-scaled 2/3/4/5 d6, DC 8+CON+prof) and **Tiefling innate Hellish Rebuke** (1/day) fires as
  the existing on-damage reaction (small `triggers.py` fallback: consume an innate use when no slot).
- **Inspiration** (§5.7): `Character.inspiration: bool` → `"Inspiration"` resource ×1; spent in
  `rules.resolve_attack` for advantage on the combatant's first own-turn attack that lacks it
  (deterministic, never on a reaction). Serialized in `character_to_dict`/`from_dict` (round-trip
  tested). Web builder auto-follows the registries (meta mirrors all 12 classes; pinned test green).

**Approximations / follow-ons (honest notes for later WPs):**
- Halfling **Lucky** (reroll natural 1s) needs a per-d20 dice hook that doesn't exist — Brave
  (adv vs frightened) IS modelled; Lucky is a follow-on.
- Rock Gnome **Gnome Cunning** approximated with the `magic_resistance` flag (adv on ALL saves
  vs spells) — slightly broader than "INT/WIS/CHA vs magic only".
- Half-Elf's "+1 to two of choice" and "two skills of choice" are fixed (DEX/CON;
  Persuasion/Perception) — build-time choices are a follow-on.
- Dragonborn breath is modelled as **Recharge 5-6** (existing area primitive), not strictly
  1/rest; the heuristic AI rarely picks it over Extra Attack (it *is* enumerated + resolves).
- Tiefling **Thaumaturgy**/**Darkness** (non-combat / situational) omitted; Hellish Rebuke kept.
- Multiclass **pact slots merge into the shared `slots` pool** (single-class Warlock is exact; a
  clean pact/slot split for pact-heavy multiclasses is a follow-on).
- Paladin/Ranger/Bard **fighting-style selection** isn't yet a `level_choices` prompt (WP2/WP3).

_Original scope for reference:_
- All 10 `ClassDef` rows: Barbarian d12 (STR/CON), Bard d8 (DEX/CHA, full CHA caster),
  Cleric d8 (WIS/CHA, full WIS), Druid d8 (INT/WIS, full WIS), Monk d8 (STR/DEX),
  Paladin d10 (WIS/CHA, half CHA), Ranger d10 (STR/DEX, half WIS), Rogue d8 (DEX/INT),
  Sorcerer d6 (CON/CHA, full CHA), Warlock d8 (WIS/CHA, pact CHA). PHB skill lists,
  armor/weapon profs, subclass levels (Cleric/Sorcerer/Warlock 1, Druid/Wizard 2, rest 3).
- `ASI_LEVELS` for each (standard {4,8,12,16,19}; Rogue adds 10).
- Pact magic: `caster_slots("pact", level)` — Warlock slot count/level table (PHB).
- **Multiclass slots (§11.5):** `multiclass_slots(class_levels)` = full + ⌈half/2⌉…
  actually PHB: full levels + ⌊half/2⌋ + ⌊third/3⌋ → FULL_CASTER_SLOTS row; pact stacks
  separately. `compile_character` uses it when >1 casting class.
- Races (§12.1): Mountain Dwarf, Wood Elf, Lightfoot + Stout Halfling (Lucky reroll-1s
  via dice `reroll_below`? if not cheap, note follow-on; Brave = save adv vs frightened),
  Dragonborn (breath weapon as innate area 1/rest, damage resist by ancestry — pick one
  default ancestry choice via race name e.g. "Dragonborn (Red)"), Rock Gnome (Gnome
  Cunning = save adv vs magic INT/WIS/CHA — approximate with magic_resistance-style flag
  if partial coverage, note it), Half-Elf, Tiefling (fire resist + innate Hellish Rebuke).
- Backgrounds: add Noble, Folk Hero, Hermit, Entertainer, Urchin, Charlatan, Guild Artisan.
- Inspiration (§5.7): `Character.inspiration: bool` → resource "Inspiration" ×1; engine:
  when attacking without advantage and the attack matters (heuristic: first attack of the
  fight), spend for advantage. Deterministic, tested.
- Tests: every class builds L1 + L5 via `make_character`, compiles, HP/saves/skills right;
  multiclass slot table matches PHB examples (Paladin 2/Wizard 3 → 3rd-level slots? No:
  2/2+3 = 4 → full row 4); pact slots correct at 1,2,5,11,17.

### WP1 — martial pack: Barbarian, Monk, Rogue — ✅ DONE (2026-07-02)

**Delivered** (mechanics + subclasses + choice plumbing; full suite 419 green, +30 tests in
`tests/test_class_barbarian.py` / `test_class_monk.py` / `test_class_rogue.py`). Engine files
touched: `models.py` (MonsterDef + Combatant fields), `character.py` (compile + helpers +
Expertise plumbing + subclasses), `equipment.py` (Unarmored Defense + Monk unarmed strike),
`rules.py` (rage/brutal/uncanny-dodge/stroke/assassinate/stunning hooks + Evasion helper +
Danger Sense), `engine.py` (bonus-action Rage/Frenzy/Flurry/Patient Defense/Cunning Action +
Stunning Strike + Evasion at area sites), `triggers.py` (Relentless Rage), `controllers.py`
(Rage/Flurry/Patient-Defense heuristics), `rest.py` (Stroke of Luck short-rest), `skills.py`
(Reliable Talent), `cast.py` (Evasion on spell saves).

- **Barbarian**: Rage (bonus action → `Combatant.raging`; +2/+3/+4 melee damage, B/P/S resist via
  `damage_multiplier`; heuristic rages when a foe is within 10 ft), Reckless Attack (reuses the
  `reckless` flag, always-on from L2), Unarmored Defense 10+DEX+CON, Fast Movement (+10), Brutal
  Critical (+1/2/3 weapon dice on a melee crit), Danger Sense (advantage on DEX saves), Relentless
  Rage (`would_drop_to_0` trigger while raging), Primal Champion (+4 STR/CON, cap 24). Subclasses:
  **Berserker** (Frenzy: bonus melee attack while raging), **Totem Warrior (Bear)** (`rage_all_damage`
  = resist all but psychic while raging).
- **Monk**: Martial Arts (unarmed d4→d10, DEX for unarmed, bonus strike after the Attack action),
  Unarmored Defense 10+DEX+WIS, Ki — Flurry of Blows (1 Ki, two strikes) / Patient Defense (1 Ki,
  Dodge), Stunning Strike (on a melee hit, 1 Ki → CON save DC 8+prof+WIS or stunned; once/turn),
  Extra Attack, Unarmored Movement (+10..+30), Evasion (DEX save-for-half → none on success),
  Diamond Soul (all save profs at L14). Subclasses: **Way of the Open Hand** (Flurry hit → DEX save
  or prone), **Way of Shadow** (Shadow Step via the `teleport` primitive — no OAs).
- **Rogue**: Sneak Attack (1d6/2 levels via the `sneak_attack` `bonus_damage` predicate, once/turn),
  Cunning Action (bonus Dash/Disengage/Hide), Uncanny Dodge (reaction halves one hit), Evasion,
  Reliable Talent (proficient checks floor a d20 at 10), Expertise (chosen at Rogue 1 & 6 →
  `level_choices` + `LevelUp.expertise` + round-trip serialization + `validate_character`), Stroke
  of Luck (L20, turn a miss into a hit, 1/short rest). Subclasses: **Assassin** (Assassinate:
  advantage + auto-crit vs surprised), **Arcane Trickster** (third caster, INT/wizard list via the
  EK pattern), **Thief** (registered; headline is out-of-combat — a follow-on).

**Approximations / follow-ons (honest notes for later WPs):**
- Rage upkeep (attack/take-damage each turn) isn't tracked — a rage lasts the fight or until the
  barbarian is incapacitated (PHB simplification; Persistent Rage is therefore already the baseline).
- Because the engine's bonus action resolves *after* the action, a barbarian rages/monk flurries on
  turn 1 but only benefits from turn 2 (shared limitation with Second Wind etc.).
- Relentless Rage uses a flat DC 10 (the +5-per-use escalation needs new per-rest state — a follow-on).
- Rage melee bonus + Brutal Critical apply to any melee weapon hit while raging (not gated to STR).
- Uncanny Dodge halves the weapon + feature damage of the hit (dice, power attack, rage, brutal,
  maneuver, Sneak Attack); incidental save-rider damage on the same hit isn't halved (minor).
- Monk Martial Arts DEX/scaling die applies to the unarmed strike; wielding a monk weapon uses the
  plain weapon numbers (a follow-on).
- Stunning Strike / Flurry ride the unarmed strike; the AI spends Stunning Strike once per turn on
  the first hit vs an un-stunned foe (a deliberate policy so the Ki lasts the fight).
- Way of Shadow's Shadow Step is modelled as the `teleport` primitive (move without provoking);
  its dim-light requirement + Cloak of Shadows invisibility are honest follow-ons. Thief's
  out-of-combat Fast Hands / Use Magic Device are listed only.
- Assassinate needs a surprised target; the arena rarely sets surprise, so it's proven by a unit
  test rather than fired in a standard bout.

_Original scope for reference:_
- Barbarian: Rage (resource, bonus action: +2/+3/+4 melee damage, resist B/P/S while
  raging — model as toggled state on Combatant), Reckless Attack (existing `reckless`),
  Unarmored Defense (10+DEX+CON), Extra Attack, Fast Movement, Brutal Critical (+1/2/3
  crit dice), Danger Sense (DEX save adv), Relentless Rage (would_drop_to_0 trigger,
  existing), Persistent Rage, Primal Champion (+4 STR/CON, cap 24). Subclasses:
  Berserker (Frenzy bonus-action attack, exhaustion after), Totem-Bear (resist all but
  psychic while raging).
- Monk: Martial Arts (unarmed d4→d10, DEX for unarmed, bonus unarmed attack), Unarmored
  Defense (10+DEX+WIS), Ki + Flurry of Blows/Patient Defense (dodge)/Step of Wind,
  Unarmored Movement, Extra Attack, Stunning Strike (on-hit CON save or stunned — spend
  ki; heuristic uses it), Evasion (half/none DEX-save AoE), Diamond Soul (all save profs),
  Purity/Empty Body follow-ons noted. Subclass: Open Hand (Flurry riders: prone/push),
  Shadow (noted, minor).
- Rogue: Sneak Attack scaling dice via existing `sneak_attack` predicate `bonus_damage`,
  Cunning Action (bonus Dash/Disengage/Hide), Uncanny Dodge (reaction: halve one hit),
  Evasion, Reliable Talent, Expertise (skills layer), Stroke of Luck (L20, 1/rest turn a
  miss into a hit). Subclasses: Thief (Fast Hands minor, note), Assassin (Assassinate:
  adv + auto-crit vs surprised).
- Reference tests per class (e.g. Monk 5: AC 10+DEX+WIS, 2 attacks + bonus, ki 5).

### WP2 — divine pack: Cleric, Paladin, Ranger — ✅ DONE (2026-07-02)

**Delivered** (full suite 448 green; +23 tests in `tests/test_class_cleric.py` /
`test_class_paladin.py` / `test_class_ranger.py`). This completes work a prior session left
half-wired: it had authored all three `ClassDef` rows, all six subclasses, the compile-time
flags/riders, `class_resources`, the fighting-style prompts at Paladin 2 / Ranger 2, the
`validate_character` prepared/known limits (Cleric/Paladin/Ranger), and the *engine methods*
for the Channel Divinity effects — but those methods were **orphaned** (never enumerated as
options, never dispatched in `apply`, no heuristics) and Lay on Hands / War Priest / Hunter's
Mark were missing entirely. This WP wired them up.

- **Cleric**: full WIS caster (prepared limit = WIS + level, like the Wizard); Channel Divinity
  1/2/3 per rest at 2/6/18 (short-rest resource). **Turn Undead** now enumerated as an action
  and dispatched (`_do_turn_undead`): undead within 30 ft save vs `spell_dc` or are frightened +
  routed; **Destroy Undead** instantly slays a turned undead at/under the CR threshold (1/2..4 at
  5/8/11/14/17). Guided Strike (War) already fired in `resolve_attack`; Divine Strike rider
  (Life/War L8, +1d8→2d8) already compiled. Subclasses: **Life Domain** — **Preserve Life** now
  an enumerated action (`_do_preserve_life`): shares 5×level HP among wounded allies within 30 ft,
  none past half max; **War Domain** — **War Priest** now a bonus-action weapon attack after the
  Attack action (WIS-mod uses/rest), Guided Strike +10 to a would-miss.
- **Paladin**: half CHA caster; **Lay on Hands** now an enumerated action (`_do_lay_on_hands`,
  5×level pool, touch heal); **Divine Smite** (already in `resolve_attack`: highest slot ≤5th,
  2d8 +1d8/level, +1d8 vs undead/fiend, crit-doubled, once/turn, conserved vs near-dead foes);
  Extra Attack; **Aura of Protection** (+CHA to saves of allies within 10 ft, via
  `aura_of_protection_bonus`); Improved Divine Smite rider (L11, +1d8 every melee hit). Subclasses:
  **Oath of Devotion** — Sacred Weapon now a bonus-action Channel (`_do_sacred_weapon`, +CHA to
  hit for 10 rounds); **Oath of Vengeance** — Vow of Enmity now a bonus-action Channel (`_do_vow`,
  advantage vs one foe, read in `resolve_attack`).
- **Ranger**: half WIS caster (Spells Known table); Fighting Style at Ranger 2; Extra Attack.
  **Hunter's Mark** added — `data/spells/hunters_mark.json` (bonus-action concentration) + a new
  `mark` spell-effect kind in `cast.py` that places a `damage_rider` **ActiveEffect on the caster**
  keyed to the marked foe (`rider_target_id`), so `effects.damage_riders_vs` adds +1d6 on every
  weapon hit vs that target — the same machinery Hex would use, no new damage path. Subclasses:
  **Hunter** — Colossus Slayer (+1d8 once/turn vs a wounded foe, `target_wounded` predicate,
  stacks with Hunter's Mark); **Beast Master** — companion flag ("Wolf").
- **Heuristics** (so the features fire in bouts): Turn Undead when undead are in range; Preserve
  Life / Lay on Hands when badly wounded; Vow of Enmity + Sacred Weapon in the bonus phase before
  wading in; Hunter's Mark cast (once) when not already concentrating; War Priest folded into the
  bonus-attack heuristic. Divine Smite / Aura / Guided Strike / Colossus fire automatically in the
  resolution path.

**Approximations / follow-ons (honest notes for WP3+):**
- Bonus actions resolve *after* the action this turn, so a ranger marks / a paladin vows on turn 1
  but only benefits from turn 2 (shared engine limitation with Rage/Second Wind).
- **Hunter's Mark** extra damage is modelled as **force** (a fixed type) rather than the weapon's
  damage type, and moving the mark to a new target as a bonus action when the marked foe dies is
  not modelled (once its target is dead the rider is inert) — both follow-ons.
- **Vow of Enmity** lasts until the sworn foe falls (then it may be re-sworn) rather than a strict
  1-minute timer; **Sacred Weapon** is a flat 10-round buff. **Aura of Protection** radius is a
  flat 10 ft (the 30-ft bump at L18 is a follow-on, already noted in `rules.py`).
- **Preserve Life** distributes to the most-wounded allies first (PHB lets the cleric choose the
  split); functionally equivalent for the arena.
- **Turn Undead** models "turned" as frightened + routed for 10 rounds (the must-flee/dash-away
  behaviour), not the precise "can't willingly move within 30 ft" clause.
- **War Priest** rarely fires in a bout because the cleric AI prefers spells to the Attack action
  (correct behaviour); it is proven by a direct unit test. **Lay on Hands**' disease/poison-cure
  use is a non-combat follow-on. **Beast Master** is a companion *flag* only — summoning the
  companion as a real combatant via the summon machinery is a WP-later follow-on.
- **Divine Intervention** (Cleric L10) and **Favored Enemy / Natural Explorer** (Ranger) are
  listed in `CLASS_FEATURES` but out-of-combat / flavor — noted follow-ons.

_Original scope for reference:_
- Cleric: full WIS caster (prepared model like Wizard limits), Channel Divinity uses
  (Turn Undead: mass WIS save frighten-undead using existing area/condition machinery;
  Destroy Undead CR threshold), Divine Intervention (L10, note as follow-on if
  non-combat). Subclasses: Life (Disciple of Life: +2+spell-level healing; Preserve Life
  channel: distribute healing), War (War Priest bonus attacks WIS/mods per rest).
- Paladin: half CHA caster, Lay on Hands pool (5×level, action heal), Fighting Style,
  Divine Smite (on melee hit, spend slot: +2d8 +1d8/slot-level, +1d8 vs undead/fiend —
  heuristic spends when it has slots), Extra Attack, Aura of Protection (+CHA to saves
  self+allies 10ft — implement via existing aura machinery as a passive save-bonus aura),
  Improved Divine Smite (L11 +1d8 melee always). Subclass: Devotion (Sacred Weapon:
  channel, +CHA to hit), Vengeance (Vow of Enmity: channel, advantage vs one foe).
- Ranger: half WIS caster (knows spells), Fighting Style, Extra Attack, Favored Enemy
  (flavor, note), Hunter's Mark support comes via spell data if present (add the spell
  if cheap: concentration +1d6 on hits vs marked target). Subclass: Hunter (Colossus
  Slayer +1d8 vs wounded — bonus_damage predicate `target_wounded` new), Beast Master
  (companion via summons machinery, simplified — note approximations).
- Reference tests (e.g. Paladin 5 smite math; Cleric 5 slots 4/3/2 + Spirit Guardians).

### WP3 — arcane pack: Bard, Sorcerer, Warlock, Druid — ✅ DONE (2026-07-02)

**Delivered** (full suite 478 green; +30 tests in `tests/test_class_bard.py` /
`test_class_sorcerer.py` / `test_class_warlock.py` / `test_class_druid.py`). Engine files
touched: `models.py` (12 MonsterDef fields + 6 Combatant fields incl. the Wild Shape body
handles), `character.py` (compile + helpers + subclasses + Expertise/wild-shape choice
plumbing + known-spell caps), `rules.py` (Bardic Inspiration die, Cutting Words, Entropic
Ward, Tides of Chaos, `revert_wild_shape` + the handle_drop hook), `engine.py` (Bardic
Inspiration grant / Quickened / Wild Shape / Combat-Wild-Shape-heal enumeration + dispatch +
the `apply_wild_shape` / `bard_cutting_words` / `try_entropic_ward` methods), `cast.py`
(Eldritch Blast beams, Agonizing Blast, Empowered Spell, Elemental Affinity), `controllers.py`
(inspire/wild-shape/moon-heal/quicken heuristics), `rest.py` (Song of Rest, Font of Inspiration,
Natural Recovery, Wild Shape short-rest), `skills.py` (Jack of All Trades), `spelllists.py`
(Warlock list + Eldritch Blast/Hex), and two new spell files (`data/spells/eldritch_blast.json`,
`hex.json`).

- **Bard**: full CHA caster; **Bardic Inspiration** — a bonus action banks a die (d6→d8→d10→d12)
  on an ally (`Combatant.inspiration_die`), spent in `rules.resolve_attack` to rescue a missed
  attack roll; heuristic gives it to the strongest ally. **Font of Inspiration** (short-rest
  recovery at L5, `rest.py`), **Jack of All Trades** (`md.jack_of_all_trades` → half prof on
  non-proficient checks, wired into `skills.skill_modifier`), **Expertise** at 3 & 10 (reuses the
  Rogue `level_choices`→`LevelUp.expertise`→serialization→`validate_character` path), **Song of
  Rest** (`rest.py`: +a growing die to short-rest Hit Dice healing). Subclasses: **College of
  Lore** — Cutting Words (`engine.bard_cutting_words`: reaction spends a Bardic Inspiration die to
  subtract from an enemy attack, Parry/Precision style); **College of Valor** — martial/medium/
  shield profs + Extra Attack at 6.
- **Sorcerer**: full CHA caster; Sorcery Points = level; **Metamagic v1** at 3 — **Quickened**
  (2 pts: cast an action spell as a bonus action, via a `quicken` option that reuses `cast.cast`)
  and **Empowered** (1 pt: reroll low damage dice via the dice layer's `reroll_below`, on leveled
  damage spells). Subclasses: **Draconic Bloodline** — Draconic Resilience (AC 13+DEX unarmored,
  +1 HP/level) + Elemental Affinity at 6 (+CHA to one fire damage roll); **Wild Magic** — Tides of
  Chaos (advantage on one roll, 1/rest, spent in `resolve_attack`).
- **Warlock**: pact caster (short-rest slot recovery from WP0); **Eldritch Blast** cantrip
  (`data/spells/eldritch_blast.json`, `scaling_mode:"beams"` → 1/2/3/4 beams at 1/5/11/17) with
  **Agonizing Blast** (+CHA per beam, auto-granted at 2); **Hex** (`data/spells/hex.json`, the
  mark pattern: +1d6 necrotic per hit, bonus action, concentration); **Mystic Arcanum** (a known
  6th-9th spell becomes innate 1/day at 11/13/15/17). Subclasses: **The Fiend** — Dark One's
  Blessing (temp HP = CHA+level on a kill, via the existing `temp_hp_on_kill` on_kill trigger);
  **The Great Old One** — Entropic Ward (`engine.try_entropic_ward`: reaction, 1/short rest,
  imposes disadvantage by rerolling the attack).
- **Druid**: full WIS prepared caster; **Wild Shape** — the shapechange primitive
  (`engine.apply_wild_shape`): an action (bonus for Moon) swaps in a beast's stat block (physical
  stats/AC/speeds/attacks) via `dataclasses.replace`, keeping the druid's mental scores + save
  profs + prof bonus; beast HP is a separate pool held on the Combatant, and dropping to 0 reverts
  to the druid's body (`rules.revert_wild_shape`, hooked at the top of `handle_drop`, carrying
  excess damage over). Two uses per short rest; the chosen forms are a serialized+validated
  `Character.wild_shapes` field (form must exist, be a beast, within the CR cap). Subclasses:
  **Circle of the Moon** — Combat Wild Shape (bonus-action shape, higher CR cap, spend a slot as a
  bonus action to heal 1d8/level in form); **Circle of the Land** — Natural Recovery (the Arcane
  Recovery clone in `rest.py`).
- **validate_character**: known-spell + cantrip caps for Bard/Sorcerer/Warlock (compact PHB dicts,
  Mystic Arcanum excluded from the Warlock count), Druid prepared limit, and Wild Shape form
  validation (existence + beast + CR cap).

**Approximations / follow-ons (honest notes for WP4+):**
- Bonus actions still resolve *after* the action (shared engine limitation): a sorcerer's
  **Quickened** spell lands after the action spell, so it functions as an extra bonus cast rather
  than reordering the turn; the one-leveled-spell-per-turn rule is enforced (a quickened *cantrip*
  is always allowed, a quickened leveled spell only if none was cast as the action).
- **Bardic Inspiration** is modelled as adding the die to the ally's next *attack roll* only, spent
  to rescue a miss (the engine sees the roll, so it never wastes the die); its use on saves/ability
  checks and the Combat Inspiration (Valor) variant are follow-ons.
- **Song of Rest** is applied to the *resting* combatant (in a full party every ally that spends a
  Hit Die would benefit) — an honest single-combatant simplification of a party effect.
- **Empowered Spell** approximates "reroll up to CHA dice" by rerolling 1s and 2s (`reroll_below=2`)
  on leveled damage spells, and auto-applies when a point is free; **Elemental Affinity** adds CHA
  to the first fire damage die and is fixed to fire (Red-dragon ancestry), and on an area save spell
  benefits every target's roll (same latitude as Empowered Evocation).
- **Wild Magic** implements Tides of Chaos (advantage 1/rest); the random **Surge table** is a
  deliberate follow-on (no unseeded randomness). **Draconic** ancestry is fixed to fire.
- **Hex** extra damage is necrotic (correct) but, like Hunter's Mark, does not hop to a new target
  when the hexed foe dies (the rider goes inert); the ability-check-disadvantage clause is omitted.
- **Mystic Arcanum** is any known 6th-9th spell surfaced as innate 1/day (the fixed one-per-level
  Arcanum *selection* UI is a builder follow-on). **Agonizing Blast** is auto-granted as the
  headline invocation; the full Eldritch Invocation *choice list* (and Pact Boon) is a follow-on.
  Eldritch Blast beams all focus the primary target (splitting beams across foes is a follow-on).
- **Wild Shape**: the md-swap keeps physical stats/AC/attacks/speeds + the druid's mental scores,
  save profs and prof bonus; it does **not** re-derive the druid's own senses/skills/class features
  onto the beast, and the druid can't cast while shaped except the Moon Combat-Wild-Shape heal
  (RAW-correct: only Moon druids act meaningfully in form at low level). Flight/swim form
  restrictions are approximated by the CR cap only. Moon's Primal Strike (magical beast attacks) and
  Elemental Wild Shape are listed as follow-ons.
- **The Great Old One**'s Awakened Mind (telepathy) is non-combat/omitted; Entropic Ward is the
  implemented headline. **College of Lore** Cutting Words fires only when a die could turn a hit
  into a miss (conservative, deterministic).

_Original scope for reference:_
- Bard: full CHA caster (knows spells), Bardic Inspiration (bonus action: grant ally a
  die banked as a one-use attack-roll bonus — new small Combatant field consumed on
  attack; d6→d12 scaling; Font of Inspiration short-rest recovery), Jack of All Trades
  (existing skills layer), Expertise, Song of Rest (rest.py bonus), Countercharm (note).
  Subclasses: Lore (Cutting Words reaction: subtract die from enemy attack), Valor
  (medium armor/shield + Extra Attack 6).
- Sorcerer: full CHA caster (knows spells), Sorcery Points, Font of Magic
  (points↔slots at rest level, keep simple: points fuel metamagic only), Metamagic v1:
  Quickened (bonus-action cast for 2 pts — engine has bonus-cast plumbing) + Empowered
  (reroll damage dice — dice layer reroll) — others noted. Subclass: Draconic Bloodline
  (AC 13+DEX unarmored, +1 HP/level, elemental affinity +CHA dmg), Wild Magic (surge
  table is nondeterministic-flavored — implement as noted follow-on, NO RNG outside
  seeded engine paths).
- Warlock: pact caster (slots all at max pact level, short-rest recovery in rest.py),
  Eldritch Invocations v1: Agonizing Blast (+CHA to Eldritch Blast damage — needs the
  Eldritch Blast cantrip data w/ multi-beam scaling), Pact Boon note. Mystic Arcanum
  (6th+ spells as innate 1/day). Subclass: Fiend (Dark One's Blessing: temp HP on kill
  via on_kill trigger), Hexblade noted (SCAG) — skip, PHB scope.
- Druid: full WIS caster (prepared), Wild Shape: v1 = swap physical stat block to a
  chosen beast form (from the monster registry, CR capped by druid level per PHB
  table), beast HP as a separate pool that reverts to druid HP at 0 (the shapechange
  primitive — build it on `Combatant.md` swap with revert trigger; document exactly
  what's approximated). Circle of the Moon (combat forms CR 1+, bonus-action shape) and
  Circle of the Land (Natural Recovery = arcane-recovery clone). If the md-swap proves
  too invasive in one WP, implement Land fully + Moon with the swap and flag remaining
  edges honestly in the ledger.
- Reference tests per class (Warlock 5: two 3rd-level pact slots; Bard inspiration die).

**Independent review (2026-07-02): no blockers.** Two should-fixes applied by the
orchestrator afterwards: Divine Smite's once-per-turn gate was never reset at turn start
(fired once per FIGHT — fixed in `engine.start_of_turn` + regression test), and the Druid
wild-shape form pick is now surfaced through `level_choices` + the builder (CR-capped
option lists per circle, `wild_shape_options`/`_moon`). Recorded nit/follow-on:
`_sneak_attack` doesn't check the weapon is finesse/ranged (a Reckless barbarian/rogue
with a greataxe would illegally sneak — needs the AttackDef threaded into modifier
predicates).

### WP4 — DoD closure (orchestrator) — ✅ DONE (2026-07-02)

**Delivered** (`tests/test_slice6_dod.py`, 15 tests; full suite **493 green**):
- **DoD test**: one leveled reference character per class (subclass + equipment/spells), compiled,
  2-3 PHB-checkable numbers asserted each (AC/HP/saves/slots/resources — re-derived from the PHB in
  the file so a regression in any class surfaces), then a deterministic Ogre bout asserted to complete
  with a winner and be byte-identical when re-run. Plus a **multiclass DoD case** (Paladin 2/Wizard 3
  → combined Multiclass Spellcaster row 4, `{1:4, 2:3}`) and a **prereq-warning case**.
- **Completeness audit** (SPEC §11.1-11.6, §12.1-12.5) walked item-by-item. Two genuine gaps closed
  cheaply: **languages §12.4** (race concrete languages + background bonus-language count →
  `character_languages` on the compiled stat block and the builder sheet; choice-granting grants shown
  as `Any (N)` — the picker is a follow-on) and **multiclass prerequisites §11.5** (`MULTICLASS_PREREQS`
  min-13 checks as build warnings in `validate_character`, never blocking). All six **fighting styles
  §11.4** confirmed working (incl. Protection's reaction) and applied to Paladin/Ranger via the generic
  `ch.fighting_styles` path. **§11.3 resource recovery** verified: Ki/Channel Divinity/Wild Shape/pact
  slots on a short rest; Rage/Sorcery Points/Lay on Hands/Bardic Inspiration on a long rest.
- **Builder auto-follow** confirmed: `/api/builder/meta` = 12 classes / 32 subclasses (pinned by
  `test_builder_api.py`), `/api/builder/preview` compiles a Barbarian L3 with Rage; languages now on
  the sheet. **Ledger** (`docs/ROADMAP.md`): the two remaining Slice 6 `[~]` boxes → `[x]`, a dated
  WP4 DONE note, and the top status banner updated (Slice 6 complete; test count 493).

**Follow-ons recorded (not "deferred")**: language/skill/ability *pickers* for choice-granting races &
backgrounds; feats §12.3 mechanics beyond the current flag set; tool proficiencies §12.5; the
multiclass *reduced* proficiency grant (currently unions full class lists); the WP0-3 per-subclass/
per-race approximations catalogued above. None are combat blockers.

_Original scope for reference:_
- One reference character per class test (`test_slice6_dod.py`): builds via
  `make_character`, checks 2-3 PHB numbers each, arena smoke, determinism.
- Full suite green; builder headless check (new classes/races appear, level-up choices
  render); ROADMAP Slice 6 boxes checked with honest follow-on notes; Opus review pass.

**Rules for every WP:** engine stays pure/seeded (no random/time); prefer existing
primitives; new choice points must flow through `level_choices`/`validate_character`
and `character_to_dict`/`from_dict` (round-trip!); run the FULL test suite before
finishing (sequential WPs — no parallel edits); update this file's checklist and the
ROADMAP status notes in the same change; keep additions faithful to the PHB.

### WP5 — PC-feature audit fixes (orchestrator) — ✅ DONE (2026-07-03)

Applied the fix list from the three PC audits (`docs/PC_AUDIT_MARTIAL.md`,
`PC_AUDIT_DIVINE_CHARGEN.md`, `PC_AUDIT_ARCANE.md`). Full suite **511 green**. Each fix has a
regression test in the relevant `tests/test_class_*.py` / `test_feats.py` / `test_pc.py` /
`test_modifiers.py`.

**RAW-correctness fixes (were INACCURATE, now OK):**
- **Savage Attacks** (`rules.py`): one extra weapon die on a melee crit, not `d0.count` dice.
- **Brutal Critical** (`rules.py`): N extra weapon dice, not `N × d0.count`.
- **Cantrip damage tier** scales by **character** level for multiclass casters (new
  `MonsterDef.cantrip_level = ch.level`; slots stay on class level). Single-class & monsters unchanged.
- **Jack of All Trades / Remarkable Athlete** add half-proficiency to **initiative** (`roll_initiative`).
- **Aura of Protection**: RAW minimum **+1** (`max(1, cha)`); conscious/alive/≤10 ft gate already present.
- **Uncanny Dodge** only fires against an attacker the rogue can **see** (`enc.can_see`).
- **Sneak Attack** requires a **finesse or ranged** weapon — the triggering `AttackDef` (with a new
  `finesse` property from `weapon_attack`) is threaded into `modifiers.holds`/predicates.
- **Turn Undead** ends the instant the turned creature **takes damage** (`turned_by` flag cleared in
  `apply_damage`; clears `frightened` + `routed`).
- **Ki-Empowered Strikes (Monk L6)**: unarmed strikes count as **magical** (`compile_character` sets
  `magic_weapons` at monk≥6). *Residual divergence:* the flag makes ALL the monk's weapon attacks
  magical, not only the unarmed strike (documented over-broad simplification — a monk-scoped magic flag
  is the honest follow-on).
- **Divine Smite**: removed the RAW-illegal once-per-turn cap from the resolution path; the spend
  **policy** now lives in `HeuristicController.should_smite` (engine falls back to
  `engine.default_smite_policy` for Random/LLM/direct calls). Policy: always smite a crit; otherwise at
  most one worthwhile (≥15 HP) target per turn (bounded so slots aren't dumped). Paladin tests updated
  (the once-per-turn assertions are now policy tests).

**New cheap features (existing machinery):**
- Paladin **Aura of Courage** (L10, frighten-immunity aura) + Devotion **Aura of Devotion** (L7,
  charm-immunity aura) — suppressed in `apply_condition` via a conscious aura-paladin ≤10 ft.
- War Domain **War God's Blessing** (L6 reaction, +10 to an ally's attack ≤30 ft) — mirrors Guided Strike.
- **Great Weapon Master** bonus-action attack on a heavy-melee crit or kill (`gwm_bonus_ready` → an
  `offhand`-kind bonus option).
- Monk **Deflect Missiles** (L3 reaction, reduce a ranged-weapon hit by 1d10+DEX+level; catch/throw-back
  simplified to negate-at-0 — documented).
- Barbarian **Feral Instinct** (L7, advantage on initiative + no surprise).
- **Lay on Hands** can now target a wounded **ally** in reach (enumeration + a heuristic ally-heal).
- Rogue **Elusive** (L18, no attack roll has advantage vs you while not incapacitated).

**Still open (recorded follow-ons, not implemented):**
- Bard **Magical Secrets** (L10/14/18 cross-list spells) — the highest-value remaining gap.
- Diviner **Portent** broadening (currently only forces enemy saves vs the diviner's own spells; RAW
  covers any visible creature's attack/save/check incl. the diviner's own d20s and enemy attacks).
- Abjurer **Arcane Ward** pre-charge (starts at max instead of being created by the first abjuration cast).
- **Multiclass spell DC/ability** uses only the first caster class (per-spell ability by originating
  class is the honest fix).
- Late capstones: **Quivering Palm** (Monk 17), **Death Strike** (Assassin 17), **Foe Slayer** (Ranger 20),
  plus Superior Inspiration, Sorcerous Restoration, Eldritch Master, Beast Spells, Avatar of Battle,
  and the assorted L14-20 subclass finishers (Retaliation, Opportunist, Thief's Reflexes, Magical Ambush…).
- **Hunter's Mark / Hex** damage type (deals `force`/`necrotic`, not weapon type) + no target-hop on kill.
- Monk-scoped magic-weapon flag (so Ki-Empowered Strikes magic-ifies only the unarmed strike).
