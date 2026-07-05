# PC Audit — Martial classes (Fighter, Barbarian, Monk, Rogue) + Fighting Styles + Feats

Scope: base features L1-20, the registered subclasses, the six fighting styles, and the
`FEATS` registry. Method: traced every `CLASS_FEATURES` / `SUBCLASSES` / `FIGHTING_STYLES` /
`FEATS` entry from `ravel/character.py:compile_character` into the code that fires it
(`engine.py`, `rules.py`, `modifiers.py`, `triggers.py`, `equipment.py`, `controllers.py`,
`rest.py`, `skills.py`, `dice.py`). Claims in `docs/SLICE6_PLAN.md` were checked against code.

Status key: **OK** = mechanized + RAW-accurate; **APPROX** = simplified AND documented;
**INACCURATE** = implemented but silently violates RAW; **MISSING** = name-only, no mechanics
(with a note on whether the gap is disclosed anywhere). "AI:no" = the heuristic
`controllers.py` never selects it in a bout (de-facto inert in the arena).

---

## Fighter

| Feature | Lvl | Status | Note |
|---|---|---|---|
| Fighting Style | 1 | OK | `equipment.Loadout` applies the chosen style (see Fighting Styles table). |
| Second Wind | 1 | OK | `engine._do_second_wind` bonus action, 1d10+level; short-rest resource. |
| Action Surge | 2 | OK | `engine.take_turn` grants 1 extra action (2 at L17); once/rest; `apply` spends it. |
| Martial Archetype | 3 | OK | subclass dispatch in compile. |
| ASI | 4/6/8/12/14/16/19 | OK | `ASI_LEVELS["Fighter"]`; feats routed via `feats_taken`. |
| Extra Attack (1/2/3) | 5/11/20 | OK | `extra_attacks("Fighter",…)` → `multiattack`. |
| Indomitable (1/2/3 uses) | 9/13/17 | APPROX | `rules.saving_throw` rerolls a failed save and keeps the new roll (RAW-correct), **but only when `important=True`** — spell saves (`cast.py:528`) and high-stakes areas (`engine.py:1726`, ≥20 avg dmg or a condition rider). A failed save vs a weak/trap area or minor effect is never rerolled. Long-rest resource. Covers the cases that matter; edge gap undisclosed. |

### Champion
| Feature | Lvl | Status | Note |
|---|---|---|---|
| Improved Critical | 3 | OK | `champion_crit_range`→19-20 via `loadout.crit_range`. |
| Remarkable Athlete | 7 | APPROX | `rules.contest` adds ⌈½prof⌉ to STR/DEX only in Grapple/Shove contests; RAW adds it to *all* STR/DEX/CON checks (initiative, Athletics) + running-jump bonus. Partial, undisclosed. |
| Additional Fighting Style | 10 | OK | second style via `fighting_style2`/`ch.fighting_styles`. |
| Superior Critical | 15 | OK | crit range 18-20. |
| Survivor | 18 | OK | `engine.start_of_turn`: +5+CON at ≤½ HP, not at 0. RAW-correct. |

### Battle Master
| Feature | Lvl | Status | Note |
|---|---|---|---|
| Combat Superiority / Maneuvers | 3 | APPROX | `engine.battle_master_maneuver`: Trip/Menacing/Pushing/Sweeping/Precision, DC=8+prof+max(STR,DEX), die scales 8/10/12, crit doubles the die. Capped at **one maneuver per turn** (RAW: one per *attack*) as a deliberate AI die-conservation policy — documented. |
| Know Your Enemy | 7 | MISSING | non-combat (out-of-combat study); name-only. Undisclosed but non-combat. |
| Relentless | 15 | OK | `engine.roll_initiative` regains 1 die if none remain at initiative. RAW-correct. |

### Eldritch Knight
| Feature | Lvl | Status | Note |
|---|---|---|---|
| Spellcasting | 3 | OK | third-caster INT/wizard list; slots via `caster_slots("third",…)`. |
| Weapon Bond | 3 | MISSING | non-combat (can't be disarmed / summon weapon); name-only. |
| War Magic | 7 | OK | `enumerate_bonus_options` offers a bonus weapon attack after a cantrip (`cast.py:283`). |
| Eldritch Strike | 10 | OK | `rules.resolve_attack:515` marks target → disadvantage on its next save vs your spell (`cast.py:423`). |
| Arcane Charge | 15 | MISSING | teleport 30 ft on Action Surge; name-only, undisclosed. |
| Improved War Magic | 18 | OK | `cast.py:283` extends War Magic to any spell. |

---

## Barbarian

| Feature | Lvl | Status | Note |
|---|---|---|---|
| Rage | 1 | APPROX | `engine._do_rage` bonus action → `raging`; `rules.damage_multiplier` resists B/P/S; +rage_damage in `resolve_attack:542`. **Rage never ends early** (no attack/damage upkeep, no 1-min timer) — lasts the fight or until incapacitated (`start_of_turn:2191`); documented. **Rage damage rides any melee weapon, not just STR** (RAW: STR melee only) — documented. AI rages when a foe ≤10 ft. |
| Unarmored Defense | 1 | OK | `unarmored_defense_mod` adds CON when no armor; `Loadout.ac`. |
| Reckless Attack | 2 | APPROX | `resolve_attack:361` advantage on melee + sets `reckless_active` so foes get advantage in return (`conditions.py:103`). Modelled as **always-on from L2** (not a per-turn choice) and applies to any melee incl. DEX-finesse (RAW: STR melee). Reasonable policy; the DEX-finesse breadth is undisclosed. |
| Danger Sense | 2 | OK | `rules.saving_throw:270` advantage on DEX saves. |
| Primal Path | 3 | OK | subclass. |
| ASI | 4/8/12/16/19 | OK | |
| Extra Attack | 5 | OK | |
| Fast Movement | 5 | OK | +10 speed if not heavy armor (`compile_character:1455`). |
| Feral Instinct | 7 | **MISSING** | name-only. RAW: advantage on initiative + can't be surprised while conscious. No `alert`-style flag set. Undisclosed. |
| Brutal Critical (1/2/3 dice) | 9/13/17 | **INACCURATE** | `resolve_attack:547` rolls `brutal_critical * (d0.count or 1)` dice — for a multi-die weapon (Greatsword/Maul 2d6) this doubles/triples the intended bonus. RAW adds *N weapon dice* of size `d0.sides`, not `N × count`. Fine for 1-die weapons (Greataxe). |
| Relentless Rage | 11 | APPROX | `triggers._relentless_rage` `would_drop_to_0` CON save → 1 HP while raging; flat **DC 10** (RAW starts 10, +5 per use) — documented. |
| Persistent Rage | 15 | APPROX | Rage already lasts the whole fight, so this is the baseline — documented (no distinct mechanic). |
| Indomitable Might | 18 | MISSING | STR check result can't be < STR score; non-combat, name-only. |
| Primal Champion | 20 | OK | `final_abilities` +4 STR/CON, cap 24. |

### Berserker
| Feature | Lvl | Status | Note |
|---|---|---|---|
| Frenzy | 3 | APPROX | `enumerate_bonus_options:1082` bonus melee attack while raging. RAW Frenzy also causes one level of exhaustion when the rage ends — **not modelled** (undisclosed). |
| Mindless Rage | 6 | MISSING | can't be charmed/frightened while raging; name-only, undisclosed. |
| Intimidating Presence | 10 | MISSING | fear action; name-only. |
| Retaliation | 14 | MISSING | reaction melee attack when damaged by a foe within 5 ft; combat-relevant, name-only, undisclosed. |

### Totem Warrior (Bear)
| Feature | Lvl | Status | Note |
|---|---|---|---|
| Spirit Seeker / Bear Totem Spirit | 3 | OK | `rage_all_damage` → resist all but psychic while raging (`damage_multiplier:34`). |
| Aspect of the Bear | 6 | MISSING | carry capacity / non-combat. |
| Spirit Walker | 10 | MISSING | ritual Commune with Nature; non-combat. |
| Bear Totemic Attunement | 14 | MISSING | forced-approach on hit; name-only, undisclosed. |

---

## Monk

| Feature | Lvl | Status | Note |
|---|---|---|---|
| Unarmored Defense | 1 | OK | adds WIS when no armor/shield (`unarmored_defense_mod`). |
| Martial Arts | 1 | APPROX | `equipment.weapon_attacks` gives the unarmed strike a scaling die (d4→d10) + DEX, and `enumerate_bonus_options:1091` offers the bonus unarmed strike after the Attack action. **Only fires when truly unarmed** (`main_hand`/`off_hand` both None) — wielding a monk weapon (Shortsword) uses plain weapon numbers and grants no bonus strike; documented. `md.martial_arts_die` is not re-gated on armor, but the bonus strike needs the unarmed attack to exist. |
| Ki / Flurry / Patient Defense | 2 | OK | Ki pool = level (short rest). `_do_flurry` (2 strikes, gated on `took_attack_action`), `_do_patient_defense` (Dodge). Flurry only after the Attack action — RAW-correct. |
| Deflect Missiles | 3 | **MISSING** | name-only. RAW: reaction to reduce ranged-weapon damage by 1d10+DEX+level (and possibly throw it back). No reaction wired. Undisclosed. |
| Slow Fall | 4 | MISSING | no falling damage rules engaged; non-combat here. |
| Extra Attack | 5 | OK | |
| Stunning Strike | 5 | OK | `engine.monk_stunning_strike` on a melee hit, 1 Ki, CON save DC 8+prof+WIS, stunned **until end of monk's next turn** (`duration=1`, decremented at the monk's end-of-turn) — RAW-correct. Once/turn policy (documented). |
| Ki-Empowered Strikes | 6 | **MISSING** | name-only. RAW: unarmed strikes count as magical for overcoming resistance/immunity to nonmagical damage. `resolve_attack:521` reads `md.magic_weapons`, but `compile_character` never sets it for a monk — a L6+ monk deals half vs any creature resistant to nonmagical B/P/S. Undisclosed. |
| Evasion | 7 | OK | `rules.area_damage_after_save` (DEX save-for-half → 0 on success). |
| Stillness of Mind | 7 | MISSING | end charm/fright on self; name-only. |
| ASI | 4/8/12/16/19 | OK | |
| Unarmored Movement (+/imp) | 2/9 | OK | `monk_unarmored_movement` +10…+30 if no armor/shield. |
| Purity of Body | 10 | MISSING | poison/disease immunity; name-only (minor). |
| Tongue of Sun and Moon | 13 | MISSING | language; non-combat. |
| Diamond Soul | 14 | OK | `compile_character:1461` proficiency in all saves. |
| Timeless Body | 15 | MISSING | aging; non-combat. |
| Empty Body | 18 | MISSING | ki invisibility / Astral Projection; name-only, undisclosed. |
| Perfect Self | 20 | MISSING | regain 4 Ki when starting with none; name-only, undisclosed. |

### Way of the Open Hand
| Feature | Lvl | Status | Note |
|---|---|---|---|
| Open Hand Technique | 3 | APPROX | `_do_flurry:1589` — a Flurry hit forces DEX save or prone. RAW offers a choice of prone / push 15 ft / no reactions on any Flurry hit; only the **prone** clause is modelled (undisclosed which). |
| Wholeness of Body | 6 | MISSING | self-heal 3×level 1/rest; name-only, undisclosed. |
| Tranquility | 11 | MISSING | Sanctuary at rest; non-combat. |
| Quivering Palm | 17 | MISSING | headline finisher; name-only, undisclosed. |

### Way of Shadow
| Feature | Lvl | Status | Note |
|---|---|---|---|
| Shadow Arts | 3 | MISSING | spend Ki for Darkness/Silence/Pass w/o Trace; name-only, documented follow-on. |
| Shadow Step | 6 | APPROX | `teleport` primitive (move w/o provoking). Dim-light requirement omitted; documented. Note: registered at subclass level 3 AND 6 in `SUBCLASSES`, gated to L6 in compile — the L3 duplicate is a data smell only. |
| Cloak of Shadows | 11 | MISSING | invisibility in dim light; documented follow-on. |
| Opportunist | 17 | MISSING | reaction attack when a creature near you is hit; combat-relevant, name-only, undisclosed. |

---

## Rogue

| Feature | Lvl | Status | Note |
|---|---|---|---|
| Expertise | 1/6 | OK | `level_choices`+`LevelUp.expertise`→`_skill_bonuses` doubles prof; validated + round-tripped. |
| Sneak Attack | 1 | **INACCURATE** | `modifiers._sneak_attack` fires on advantage OR an adjacent ally, and is blocked at disadvantage (RAW-correct on those) and `once_per_turn` — **but never checks the weapon is finesse or ranged**. A Rogue (or Sneak-Attack multiclass) swinging a Greataxe/Maul still sneaks; the rider even takes the main-hand's damage type. Disclosed as a known nit in `SLICE6_PLAN.md` (line 371-373) but silently wrong in code. |
| Thieves' Cant | 1 | MISSING | language; non-combat. |
| Cunning Action | 2 | OK | `enumerate_bonus_options:1104` bonus Dash/Disengage/Hide. |
| Roguish Archetype | 3 | OK | subclass. |
| ASI | 4/8/10/12/16/19 | OK | `ASI_LEVELS["Rogue"]` incl. bonus L10. |
| Uncanny Dodge | 5 | APPROX | `resolve_attack:506` reaction halves one hit's damage. **Doesn't verify the attacker is seen** (RAW: "attacker you can see"); halves weapon+feature damage but not incidental save-riders — documented. |
| Evasion | 7 | OK | shared with Monk. |
| Reliable Talent | 11 | OK | `skills.reliable_roll` floors a proficient-skill d20 at 10. |
| Blindsense | 14 | MISSING | detect hidden within 10 ft; name-only (minor). |
| Slippery Mind | 15 | MISSING | WIS save proficiency; name-only, undisclosed. |
| Elusive | 18 | **MISSING** | name-only. RAW: no attack roll has advantage against you while not incapacitated. No flag set; undisclosed. |
| Stroke of Luck | 20 | OK | `resolve_attack:456` turns a miss into a hit, 1/short rest. |

### Assassin
| Feature | Lvl | Status | Note |
|---|---|---|---|
| Assassinate | 3 | OK (AI:no) | `resolve_attack:364` advantage + auto-crit vs a surprised target. The arena rarely sets surprise, so it fires only in unit tests — de-facto inert in bouts; documented. |
| Bonus Proficiencies | 3 | MISSING | tools/disguise; non-combat. |
| Infiltration Expertise / Impostor | 9/13 | MISSING | non-combat. |
| Death Strike | 17 | MISSING | double damage vs surprised (CON save); combat-relevant, name-only, undisclosed. |

### Thief
| Feature | Lvl | Status | Note |
|---|---|---|---|
| Fast Hands / Second-Story Work | 3 | MISSING | out-of-combat; documented follow-on. |
| Supreme Sneak | 9 | MISSING | stealth; non-combat. |
| Use Magic Device | 13 | MISSING | non-combat. |
| Thief's Reflexes | 17 | MISSING | two turns in round 1 (combat-relevant); name-only, disclosed only as "Thief headline is out-of-combat". |

### Arcane Trickster
| Feature | Lvl | Status | Note |
|---|---|---|---|
| Spellcasting | 3 | OK | third-caster INT/wizard (enchantment+illusion), via the EK pattern; slots + validation. |
| Mage Hand Legerdemain | 3 | MISSING | utility; non-combat. |
| Magical Ambush | 9 | MISSING | disadvantage on saves vs your spell when hidden; combat-relevant, name-only, undisclosed. |
| Versatile Trickster | 13 | MISSING | Mage Hand → advantage; name-only. |
| Spell Thief | 17 | MISSING | name-only. |

---

## Fighting Styles

| Style | Status | Note |
|---|---|---|
| Defense | OK | `Loadout.ac` +1 AC while armored. |
| Archery | OK | `weapon_attacks` +2 to hit, ranged only. |
| Dueling | OK | +2 dmg when a one-handed melee weapon and no other weapon (`one_handed` check). RAW-correct. |
| Great Weapon Fighting | OK | `reroll_below=2` on two-handed melee; `dice._one_die` rerolls a 1-2 once and keeps the new roll. RAW-correct. |
| Two-Weapon Fighting | OK | off-hand adds the ability mod (`damage_ability=twf`); base TWF requires two light melee weapons (`twf_legal`). Minor: the bonus off-hand attack isn't gated on having taken the Attack action (offered any turn). |
| Protection | OK | `engine.protection_reaction`: shield + within 5 ft of the protected ally + can see attacker → disadvantage (reaction). RAW-correct. |

---

## Feats (`FEATS`)

| Feat | Status | Note |
|---|---|---|
| Great Weapon Master | **INACCURATE (partial)** | `resolve_attack:427` does the -5/+10 on heavy melee (EV-gated). **The second half — a bonus-action melee attack after a crit or a kill — is not implemented.** Undisclosed. |
| Sharpshooter | OK | -5/+10 ranged, ignores cover (`sharp` skips cover AC), no long-range disadvantage (`long_range and not sharp`). All three clauses. |
| Sentinel | OK | (1) OA reduces speed to 0 (`movement_halted`), (2) Disengage still provokes from a Sentinel (`_do_move` OA path), (3) `sentinel_reaction` melee when a foe within 5 ft hits an ally. All three clauses. |
| Polearm Master | OK | both halves: bonus butt-end 1d4 (`_do_polearm`) and OA when a foe enters reach (`engine.py:1328`). `_POLEARMS` set matches PHB. |
| Mobile | OK (mostly) | +10 speed; no OA from a foe you melee'd (`resolve_attack:500`, `attacked_this_turn`). Third clause (Dash ignores difficult terrain) not modelled; minor. |
| Lucky | APPROX | 3 luck points; rerolls a plausible-to-hit attack miss (`resolve_attack:448`) and a failed *important* save (`saving_throw:288`, keep better). **The "force an attacker to reroll against you" use and ability-check use are not implemented.** Partly disclosed (resource present). |
| Tough | OK | +2 HP/level, applied retroactively over the whole advancement (`max_hp`). |
| Resilient (CON/DEX/WIS) | OK | +1 to the ability + save proficiency (`feat_save_profs`). |
| Savage Attacker | OK | reroll a weapon's damage once/turn, keep better (`resolve_attack:524`). |
| War Caster | OK (headline) | advantage on concentration saves (`_concentration_save`). Cast-on-OA / reaction-cast clauses omitted; minor. |
| Alert | OK (mostly) | +5 initiative + can't be surprised (`roll_initiative:180-181`). Third clause (unseen attackers don't gain advantage on you) not modelled; minor. |
| Magic Initiate (Wizard) | APPROX | grants Fire Bolt (cantrip, usable) + Magic Missile. The 1st-level spell is added to the spell list but a non-caster has no slot, so **Magic Missile is effectively uncastable** (RAW: once/day without a slot). Minor. |

---

## Findings (ranked by combat impact)

> **STATUS UPDATE (2026-07-03, audit-fix WP5).** Fixed with regression tests (suite 511 green):
> **#1 Ki-Empowered Strikes** — `compile_character` now sets `magic_weapons` at monk≥6 (residual: it
> magic-ifies all the monk's weapon attacks, not only the unarmed strike — a monk-scoped flag is the
> follow-on). **#2 Sneak Attack finesse/ranged** — `AttackDef.finesse` added + the triggering attack
> threaded into `modifiers.holds`/predicates; a Greataxe rogue no longer sneaks. *Note:* monster
> stat-block attacks don't carry the finesse property, so a monster's melee sneak rider only fires
> with a ranged (or explicitly-finesse) attack; PC rogues are exact. **#3 Brutal Critical** — now N
> weapon dice, not N×count. **#4 GWM bonus attack** — a heavy-melee crit/kill sets `gwm_bonus_ready`,
> enumerated as an `offhand`-kind bonus attack. **#5 Deflect Missiles** — Monk L3 reaction reduces a
> ranged-weapon hit by 1d10+DEX+level (catch/throw-back simplified to negate-at-0). **#6 Feral
> Instinct** — advantage on initiative + no surprise. **#7 Uncanny Dodge** — now gated on
> `enc.can_see`. **#8 Elusive** — L18 flag cancels advantage against a non-incapacitated rogue.
> **#10 Remarkable Athlete** — half-prof now added to **initiative** (the Grapple/Shove-only
> narrowing for other checks remains). The Savage Attacks over-roll flagged in #3 was fixed too (see
> the Divine/Chargen audit #1). **Still open:** #9 (combat-relevant subclass finishers: Retaliation,
> Quivering Palm, Opportunist, Death Strike, Thief's Reflexes, Magical Ambush — recorded follow-ons).

1. **Monk Ki-Empowered Strikes (L6) missing — `character.py:compile_character` never sets `magic_weapons`.** A level-6+ monk's unarmed strikes should count as magical; against any creature with resistance to nonmagical B/P/S (common mid-tier monsters) the monk silently deals half damage. `rules.py:521` already reads `md.magic_weapons`. Fix: in the Monk block of `compile_character`, set the attack as magical when `monk >= 6` (ideally a monk-scoped flag so only the unarmed strike is magical, not future off-hand weapons). Undisclosed.

2. **Rogue Sneak Attack ignores the finesse/ranged weapon requirement — `modifiers.py:45` `_sneak_attack`.** Any weapon triggers Sneak Attack (e.g. a Reckless barbarian/rogue multiclass with a Greataxe), and the rider copies the main-hand damage type. RAW requires a finesse or ranged weapon. Disclosed only as a nit in `SLICE6_PLAN.md`. Fix: thread the triggering `AttackDef` (or a `finesse|ranged` boolean) into the predicate signature and gate on it.

3. **Barbarian Brutal Critical over-rolls for multi-die weapons — `rules.py:547`.** `brutal_critical * (d0.count or 1)` yields 2×/3× the extra dice for a Greatsword/Maul (2d6): a L17 Greatsword barbarian gets +6d6 instead of +3d6. RAW adds N dice of the weapon's die size. Fix: `rng.roll(attacker.md.brutal_critical, d0.sides)` (drop `* (d0.count or 1)`). (Greataxe/1-die weapons unaffected.) The same `* count` pattern in the Half-Orc Savage Attacks branch at `rules.py:540` has the identical bug — out of martial scope but worth flagging to that owner.

4. **Great Weapon Master's bonus-action attack half is missing — `rules.py:427`.** Only the -5/+10 power attack exists; the bonus melee attack on a crit or on dropping a creature to 0 is not wired. A GWM fighter/barbarian loses a meaningful chunk of throughput. Undisclosed. Fix: on a crit or kill with a heavy melee weapon, offer/queue a bonus-action attack (mirror the Frenzy/`_do_offhand` path).

5. **Monk Deflect Missiles (L3) missing.** No reaction to reduce incoming ranged-weapon damage; a monk takes full damage from archers/casters that a real monk would blunt. Undisclosed. Fix: add an incoming-ranged-attack reaction (1d10+DEX+level reduction) alongside the Uncanny Dodge / Shield reaction windows.

6. **Barbarian Feral Instinct (L7) missing.** No advantage-on-initiative / no-surprise flag (an `alert`-style hook already exists for the Alert feat and could be reused). Undisclosed, name-only.

7. **Uncanny Dodge fires against unseen attackers — `rules.py:506`.** RAW requires an attacker you can see; the code halves any hit while the reaction is available. Low impact (arena visibility is usually clear) but a silent RAW deviation.

8. **Rogue Elusive (L18) missing.** "No attack roll has advantage against you" is not modelled (no flag). Only relevant at L18+, undisclosed, name-only.

9. **Combat-relevant subclass finishers are name-only and undisclosed:** Berserker *Retaliation* (L14) and *Mindless Rage* (L6), Open Hand *Quivering Palm* (L17) and *Wholeness of Body* (L6), Way of Shadow *Opportunist* (L17), Assassin *Death Strike* (L17), Thief *Thief's Reflexes* (L17), Arcane Trickster *Magical Ambush* (L9). Each is listed in `SUBCLASSES.features` with no mechanic and no follow-on note. Low priority (high level / narrow), but they are true undisclosed MISSINGs.

10. **Champion Remarkable Athlete is only partial — `rules.py:86`.** Half-proficiency is added to STR/DEX in Grapple/Shove contests only, not to initiative or other STR/DEX/CON checks. Undisclosed narrowing.

### Documented approximations (correctly flagged in SLICE6_PLAN — not defects)
Rage never ends early / no upkeep; Rage damage + Reckless on any melee (not STR-gated); Relentless
Rage flat DC 10; Battle Master & Stunning Strike once-per-turn (vs once-per-attack) AI policy;
Martial Arts benefits only the true unarmed strike; Shadow Step ignores the dim-light gate;
Assassinate proven by unit test (surprise rarely set in the arena).

### Test pinning
`tests/test_class_barbarian.py`, `test_class_monk.py`, `test_class_rogue.py`, `test_subclasses.py`,
`test_feats.py` pin the headline numbers/flags (rage tiers, brutal-critical *die count* helper,
unarmored defense, sneak dice, stunning, evasion, styles, feat flags). Note: the Brutal Critical
*multi-die over-roll* (finding 3) is **not** covered — only `brutal_critical_dice()` the helper is
tested, not the `resolve_attack` roll expression.
