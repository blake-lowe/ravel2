# SPEC — Complete Capability Inventory

This is the **committed scope**. Every item here will be built. Items are not optional and are not "deferred" — each is assigned to a numbered slice in `ROADMAP.md`. The `[Sn]` tag after each group is its slice. The ROADMAP coverage matrix proves every section below is covered.

Goal: fully support the **entire D&D 5e character sheet** and **every type of action**, grid-based, deterministic, with LLM-driven enemy choices.

> Content sourcing: prefer SRD 5.1 content (openly licensed) as the canonical demo set; 5e.tools is the human reference for breadth; model the internal schema after Foundry dnd5e *Activities*. Keep raw source files in-repo so imports are reproducible. (SRD vs. non-SRD matters only if this is ever distributed; the importer should track source/license per item.)

---

## 1. Core randomness & dice `[S0]`
- 1.1 Seeded RNG abstraction, injected explicitly everywhere; reproducible streams.
- 1.2 Dice expression parser + roller: `NdM`, modifiers, `NdM+K`, multiple terms, keep-highest/lowest, reroll, minimum-die (e.g. Great Weapon Fighting), exploding (where needed).
- 1.3 Advantage / disadvantage (roll two, take higher/lower; cancellation rules; elven accuracy = three).
- 1.4 Critical hit dice doubling; critical-range modifiers (e.g. crit on 19-20).
- 1.5 d20 test primitive (attack roll, ability check, saving throw share one mechanism: d20 + mods vs target number, with adv/dis).

## 2. Game state, events, reducer `[S0]`
- 2.1 Immutable state models (creatures, grid, encounter, turn/round counters, effect timers).
- 2.2 Event types (discriminated union) + the reducer that folds events into new state.
- 2.3 Event log as canonical output (drives golden master and later narration).
- 2.4 Replay / fold-prefix support.

## 3. Grid & space `[S0 base; S8 completeness]`
- 3.1 2D integer coordinate grid; 5 ft squares. `[S0]`
- 3.2 Creature footprint by size (Tiny, Small, Medium, Large, Huge, Gargantuan) and occupied squares. `[S0]`
- 3.3 Distance metric (PHB Chebyshev default; DMG 5-10-5 optional via rules config). `[S0]`
- 3.4 Difficult terrain (movement cost x2). `[S8]`
- 3.5 Line of sight & line of effect. `[S8]`
- 3.6 Cover: half (+2 AC/Dex save), three-quarters (+5), total (cannot target). `[S8]`
- 3.7 Area-of-effect templates → set of affected squares: sphere, cylinder, cube, cone, line; origin placement and targeting. `[S5 for spell AoE consumes this; S8 for full template geometry]`
- 3.8 Flanking (optional rule, config flag). `[S8]`
- 3.9 Squeezing into smaller spaces; size-vs-space rules. `[S8]`

## 4. Creature core stats `[S1]`
- 4.1 Six ability scores (STR DEX CON INT WIS CHA) + modifiers.
- 4.2 Proficiency bonus (by level/CR).
- 4.3 Armor Class (computed from armor/dex/shield/natural/bonuses — see Equipment).
- 4.4 Initiative (Dex + bonuses; advantage sources).
- 4.5 Hit points: max, current, temporary HP (non-stacking rules).
- 4.6 Speeds: walk, fly (+ hover), swim, climb, burrow.
- 4.7 Size category.
- 4.8 Senses: normal, darkvision, blindsight, tremorsense, truesight; passive Perception.

## 5. d20 mechanics & checks `[S1 attack/save/check core; S6 skills layer]`
- 5.1 Attack rolls vs AC; hit/miss; natural 20 auto-hit + crit; natural 1 auto-miss. `[S1]`
- 5.2 Saving throws: d20 + ability + proficiency vs DC. `[S1]`
- 5.3 Ability checks. `[S1]`
- 5.4 All 18 skills mapped to abilities (Acrobatics, Animal Handling, Arcana, Athletics, Deception, History, Insight, Intimidation, Investigation, Medicine, Nature, Perception, Performance, Persuasion, Religion, Sleight of Hand, Stealth, Survival). `[S6]`
- 5.5 Proficiency, Expertise (double), Jack of All Trades (half), passive scores. `[S6]`
- 5.6 Contested checks (e.g. grapple = Athletics vs Athletics/Acrobatics). `[S3]`
- 5.7 Inspiration (advantage token). `[S6]`
- 5.8 Group checks / help (advantage granting). `[S3]`

## 6. Damage & defenses `[S1 base; S4 resist layer]`
- 6.1 Damage types: bludgeoning, piercing, slashing, fire, cold, lightning, thunder, acid, poison, necrotic, radiant, psychic, force. `[S1]`
- 6.2 Damage rolls, multiple damage instances, type tagging. `[S1]`
- 6.3 Resistance (half), vulnerability (double), immunity (none); ordering with other modifiers. `[S4]`
- 6.4 Temporary HP interaction; overkill; 0 HP → unconscious; massive-damage instant death. `[S1 base; death detail S9]`

## 7. Action economy & turn structure `[S1 structure; S3 full action catalog]`
- 7.1 Per-turn budget: 1 action, 1 bonus action (if granted), 1 reaction (per round), movement up to speed, 1 free object interaction, free actions (speak, drop). `[S1 tracking]`
- 7.2 Movement: spend speed, split movement, occupy squares, blocked squares. `[S1 basic; S8 difficult terrain/forced/special modes]`
- 7.3 Standard **Actions** — all of:
  - Attack (incl. Extra Attack; melee, ranged, unarmed). `[S1 melee; S3 ranged/unarmed/multiattack]`
  - Cast a Spell (action casting time). `[S5]`
  - Dash, Disengage, Dodge, Help, Hide, Search, Ready, Use an Object. `[S3]`
  - Grapple, Shove (special melee attacks); also Shove aside, escape grapple. `[S3]`
  - Two-weapon fighting (bonus-action off-hand attack). `[S3]`
  - Improvised / DM-adjudicated actions (generic effect option). `[S3]`
  - Class/feature/item-granted actions (e.g. Action Surge gives an extra action). `[S6 features supply these]`
- 7.4 **Bonus actions**: only when a feature/spell grants one; tracked distinctly. `[S3 framework; sources in S5/S6]`
- 7.5 **Reactions** framework + windows: Opportunity Attack (leaving reach), Readied action triggers, reaction spells, feature reactions. `[S3]`
- 7.6 Ranged attack penalties: in melee (disadvantage), long range (disadvantage), cover. `[S3 + S8 cover]`
- 7.7 Two-handed / loading / ammunition consumption on attacks. `[S7]`

## 8. Conditions `[S4]`
All 15, with full mechanical effects: Blinded, Charmed, Deafened, Frightened, Grappled, Incapacitated, Invisible, Paralyzed, Petrified, Poisoned, Prone, Restrained, Stunned, Unconscious.
- 8.1 Exhaustion (6 levels, cumulative effects, removal on long rest).
- 8.2 Condition durations: start/end-of-turn expiry, "save ends" recurring saves, until-removed.
- 8.3 Condition immunities.
- 8.4 Interactions (e.g. prone → melee adv / ranged disadv; restrained → speed 0, attack disadv, Dex save disadv; unconscious → auto-fail Str/Dex saves, crits in melee).

## 9. Effects engine `[S4]`
- 9.1 Effect application/expiry pipeline (timed, sourced, stackable vs non-stackable).
- 9.2 Buffs/debuffs to rolls, AC, speed, saves (e.g. Bless +1d4, Bane −1d4).
- 9.3 Ongoing/recurring effects (regeneration, damage-over-time, auras).
- 9.4 Triggered effects (on-hit riders, on-damage, on-death, start/end of turn).
- 9.5 Concentration linkage (effect ends when its source's concentration ends).

## 10. Spellcasting `[S5]`
- 10.1 Spell slots levels 1-9; Pact Magic (Warlock) as separate pool; cantrips; multiclass slot table.
- 10.2 Spells known vs prepared; spellcasting ability; spell save DC; spell attack bonus.
- 10.3 Components V / S / M (material cost / focus; somatic-blocked-by-hands).
- 10.4 Casting times: action, bonus action, reaction (with trigger), ritual, longer (minutes/hours).
- 10.5 Ranges (self, touch, ranged, area-origin), durations (instant, rounds, concentration, until dispelled).
- 10.6 Concentration: one at a time; CON save when damaged (DC = max(10, half damage)); broken by incapacitation/death; new concentration ends old.
- 10.7 Upcasting (slot-level scaling) and cantrip scaling by character level.
- 10.8 Area effects on the grid (consumes §3.7), single/multi-target rules.
- 10.9 Attack-roll spells vs save-based spells vs auto-effect spells.
- 10.10 Interaction spells: Counterspell, Dispel Magic, antimagic, Shield (reaction), Hellish Rebuke (reaction), Absorb Elements, etc.
- 10.11 Schema proof set (must resolve correctly before bulk import): attack-roll spell, save-for-half AoE (Fireball), buff (Bless), condition (Hold Person), heal (Cure Wounds), reaction (Shield), concentration buff.

## 11. Character building — classes & progression `[S6]`
- 11.1 Levels 1-20; class + subclass selection; class features per level.
- 11.2 All class spellcasting types: full (Wizard/Cleric/etc.), half (Paladin/Ranger), third (EK/AT), Pact (Warlock), innate.
- 11.3 Class resources & their recovery: Rage, Ki, Channel Divinity, Sorcery Points + Metamagic, Bardic Inspiration, Wild Shape, Superiority Dice + maneuvers, Lay on Hands pool, Action Surge, Second Wind, Extra Attack tiers, Sneak Attack, Divine Smite, Indomitable, Arcane Recovery, Font of Magic, etc.
- 11.4 Fighting styles.
- 11.5 Multiclassing rules (prereqs, proficiency grants, combined slot table, feature stacking).
- 11.6 Ability Score Improvements.

## 12. Character building — race/species, background, feats `[S6]`
- 12.1 Racial/species traits: ability bonuses, size, speed, darkvision, resistances, innate spells, special senses, subraces.
- 12.2 Backgrounds: skill/tool/language proficiencies, background feature.
- 12.3 Feats (incl. half-feats with ASI; combat feats like Sentinel/Polearm Master that add reactions/bonus actions/options).
- 12.4 Languages.
- 12.5 Proficiencies: armor, weapons, tools, saving throws, skills — aggregation from all sources.

## 13. Equipment & inventory `[S7]`
- 13.1 Weapons + all properties: simple/martial, melee/ranged, finesse, versatile, two-handed, light, heavy, reach, thrown, ammunition, loading, special. Weapon attack option generation.
- 13.2 Armor: light/medium/heavy + shield; AC formula per type (Dex cap), don/doff time, stealth disadvantage, strength requirement.
- 13.3 Magic items: rarity, attunement (3-slot limit), charges + recharge, activation actions, bonuses.
- 13.4 Consumables: potions, scrolls (incl. scroll spellcasting checks), ammunition tracking & recovery.
- 13.5 Currency; carrying capacity / encumbrance (optional variant via config).
- 13.6 Equip/unequip changes derived stats and available options.

## 14. Rest, recovery, time, death `[S9]`
- 14.1 Short rest: spend Hit Dice (roll + CON) to heal; recover short-rest resources (Warlock slots, Ki, etc.).
- 14.2 Long rest: full HP, recover half max Hit Dice, all slots, daily resources, exhaustion −1.
- 14.3 Death saving throws: 3 successes/3 failures, nat 20 (regain 1 HP), nat 1 (two failures), damage while dying = 1 failure (2 if crit), stabilization, instant death.
- 14.4 Revival / healing from 0 HP; regeneration; recharge abilities (e.g. breath weapon "Recharge 5-6").
- 14.5 Round/turn time accounting for durations; minute/hour timers for out-of-combat effects.

## 15. Monsters & encounter features `[S10]`
- 15.1 Full stat block model: CR, ability scores, AC/HP, speeds, senses, traits, actions, bonus actions, reactions, damage resistances/immunities/vulnerabilities, condition immunities, languages.
- 15.2 Multiattack.
- 15.3 Legendary actions (budget per round), Legendary Resistance (auto-succeed N saves/day).
- 15.4 Lair actions (initiative count 20) and regional effects.
- 15.5 Recharge abilities; innate spellcasting; at-will/X-per-day abilities.
- 15.6 Encounter scope: surprise, initiative ordering & tie-breaks, start/end-of-turn triggers, mob/multiple combatants.

## 16. Decision layer / LLM control `[S2; evals ongoing]`
- 16.1 Engine emits serialized legal `Option`s + valid target sets for the active actor.
- 16.2 `LLMController`: build constrained schema from options → Claude structured selection → validate → `Choice`.
- 16.3 Decision-context serialization (compact, sufficient state for good tactics).
- 16.4 Tool-framing vs structured-output framing A/B; reasoning field for tactics.
- 16.5 Decision-quality eval harness (live, LLM-judged; separate from correctness tests): focus-fire, AoE clustering, resource conservation, save-vs-attack targeting, retreat/positioning.
- 16.6 Mocked-LLM fixtures for deterministic CI.

## 17. Content importers `[S11]`
- 17.1 Importers: 5e.tools / Foundry JSON → internal Pydantic schema for monsters, spells, items, classes, subclasses, races, backgrounds, feats.
- 17.2 Idempotent & replayable; validation with zero schema errors; source/license tagging.
- 17.3 Raw source data kept in-repo; import is a reproducible build step.
- 17.4 Import the full SRD set as the canonical content corpus.

## 18. Application & presentation `[S12a-S12d]`

> **Product decision (2026-07-01):** the player-facing application is a **web UI**, not a terminal TUI.
> A FastAPI service (`web/`) wraps the pure engine; the frontend is a no-build multi-page static site
> (hand-written HTML/CSS/JS, vendored assets only) in the "dungeon module" ink-on-paper style.

- 18.1 Web foundation: FastAPI app (`web/`) over the pure engine — thin JSON endpoints wrapping `sim.py`; static frontend + shared design-system CSS; monster art from the 5etools-img GitHub mirror (ordered candidate URLs, client-side fallback). `[S12a]`
- 18.2 Bestiary page: filterable monster roster (name/CR/type/source), classic stat-block rendering from `data/monsters/` JSON, monster art, per-monster "Pit Record" adjusted-CR panel (nominal→adjusted CR line with CI, advisory signal bars, per-composition strip, environment deltas) and aggregate rating figures from `ratings.db` (nominal-vs-adjusted scatter, residual leaderboard — pulled forward from 12b by product decision 2026-07-02). `[S12a]`
- 18.3 The Blood Pit (arena page): fight configuration (teams, map, environment, controllers, seed) as a shareable permalink; deterministic single-bout replay (client-side event-log scrubber — grid, combat log, initiative, HP — stepped by event/turn/round); gauntlet batch mode (N seeds → win rates with CIs, round histograms, SSE progress, per-seed replay links); pre-fight odds from ratings. `[S12b]`
- 18.4 Scenario format (define combatants, grid, terrain, starting positions, seed); the arena config serializes to/from it. `[S12b]`
- 18.5 Character builder page: schema-driven advancement — the server enumerates the legal choices at each level (`level_choices`), the UI only selects among them; the character roster persists in the browser (localStorage + round-trippable JSON download/import; product decision 2026-07-02) and characters are fieldable in the arena. `[S12c]`
- 18.6 `HumanController` over the web: a human plays a PC option-by-option in the browser. `[S12d]`
- 18.7 Narration LLM over the event log (flavor prose), strictly isolated from mechanics. `[S12d]`
- 18.8 **The Supertemporal Arena** (auto-battler page; themed on the Fortune's Wheel casino, Sigil — Shemeshka is the purveyor). A roguelite run: assemble a stable of up to **5 monsters** through a shop, battle auto-generated enemy compositions, survive as far as possible before **3 losses** end the run. Monsters-vs-monsters (mode named after the Platinum Room's arena of *Turn of Fortune's Wheel*; every battle ages the world — presentation leans on the 1 round = 10 years conceit). `[S12e]`
  - 18.8.1 **Run state machine (pure).** The whole mode — shop rolls, economy, wheel spins, enemy generation, phase transitions — is a pure, seeded state machine in `ravel/fortune.py` (state + action in → state + events out; RNG only from the injected seed; ratings/catalog injected as data). Same seed + same action script = identical run. Battles resolve through `ravel.sim` with the **heuristic controller on both sides** (human control of battles arrives with §18.6) and average HP (`roll_hp=False`).
  - 18.8.2 **Sources & catalog.** At run start the player selects which source books feed the shop *and* the enemy pool (any subset of the loaded books, e.g. MM / MPMM / Ravel house blocks; source = a stat block's `data/monsters/` subdirectory).
  - 18.8.3 **Currency.** Standard D&D coinage, stored in cp: 1 gp = 10 sp = 100 cp; every price and balance renders as gp/sp/cp change. Starting purse **10 gp**; income **+10 gp** at each shop phase.
  - 18.8.4 **Shop.** 5 monster slots + 2 item slots per roll. Reroll costs **5 sp**; per-slot **freeze** persists a slot through rerolls and into the next shop. Monster price = **3 gp × playtested CR ÷ shop tier**: `max(5, round(300 × best_cr / tier))` cp — weaker stock gets cheaper as the tier climbs, and the adjusted-CR ledger *is* the price tag (unrated monsters price at book CR). Item prices by rarity: common 2 gp, uncommon 4 gp (rare items are wheel-only). Selling a monster refunds half of everything invested in it (purchase + training), rounded down to the cp; items are never refunded.
  - 18.8.5 **CR cap ladder.** Shop and enemy pools admit only CR ≤ cap; `cap(round) = 1 + (round − 1) // 2` (cap rises by 1 after every 2 battles). Shop rolls weight toward the top of the unlocked band (`w = 1/(1 + max(0, cap − cr))`) and **downweight monsters the player already owns ×0.25** — duplicates are a lucky find (see training, 18.8.7).
  - 18.8.6 **Items (kit boons).** Buying an item attaches it to one owned monster (max **3 items per monster**, permanent, lost on sell). An item is a pure stat-block transform applied at battle build time (`apply_kit`): flat deltas to AC, max HP, attack to-hit, attack damage, speed. Catalog is data in `ravel/fortune.py` (4 common / 4 uncommon / 4 rare, planar-flavored names).
  - 18.8.7 **Training (elites).** Two owned copies of the same monster can be **combined**: the survivor becomes an *elite* (★ per training level) with **+1 AC and +1 max HP per level**; levels sum on merge, items transfer up to the 3-item cap (excess lost), invested gold accumulates for sell-back. Rarity comes from the shop's owned-monster downweight, not a rule.
  - 18.8.8 **Fortune's Wheel.** Every battle **won** grants one spin of a three-ring wheel (gold, red accents). Outer ring: 3/10 no prize, 6/10 common prize, 1/10 advance to the middle ring. Middle ring: 1/10 no prize, 8/10 uncommon prize, 1/10 advance to the center. Center ring: always a rare prize. Pools — common: {2 gp, 1 gp 5 sp, random common item}; uncommon: {5 gp, random uncommon item}; rare: {random rare item, +1 life (cap 3; 10 gp if already at cap), 10 gp}. All outcomes drawn from the run RNG server-side; the client only animates to the returned stops.
  - 18.8.9 **Enemy generation.** Seeded from the run: team size `min(5, 2 + (round + 1) // 2)`, filled by weighted sampling from the selected books under the CR cap against an XP budget `size × XP(cap) × 0.75 × U[0.85, 1.15]` (adjusted XP where rated). Duplicates allowed.
  - 18.8.10 **Deployment & scouting.** Before each battle the player drags each stable monster onto a start cell inside the deployment zone (open arena: own half up to 3 columns short of the midline; named maps: within Chebyshev 3 of the team's spawn points, walls excluded). The engine validates zone membership, footprint fit, and non-overlap (`build_encounter` placements override, §18.8.11); unplaced monsters auto-place. The opposing composition is a **secret**: revealing it costs **5 sp** ("Divine the future"), once per round, forgotten again when the battle is fought; enemy placement is never shown. The house sells everything, even information.
  - 18.8.11 **Engine seams.** `build_encounter` accepts (a) explicit team-A placements and (b) team entries given as `MonsterDef` objects (kitted/elite variants), alongside plain names. Both stay pure.
  - 18.8.12 **Foresight queue.** The next 3 rounds' (map, weather) pairs are precomputed from the seed and always visible (Tetris next-piece style) so the player can shop for the terrain ahead.
  - 18.8.13 **Persistence & leaderboard ("the Book of Aeons").** Shown on the mode's landing view only, never during a run. Active runs live in server memory; finished runs persist to sqlite (`data/fortune/runs.db`): seed, books, victories, rounds survived, final stable (with items/elites), timestamp. Endpoints serve a leaderboard (top victories) with each run's final composition. Score = battles won; presentation counts time witnessed (100 years per arena minute).

## 19. Cross-cutting: rules configuration `[S0 scaffold; flags added with their feature]`
- A `RulesConfig` object toggles optional/variant rules (diagonal distance, flanking, encumbrance variant, feats on/off, multiclassing on/off) so house rules never require code edits. Each flag ships with the slice that owns its feature.
