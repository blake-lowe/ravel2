# Spellcasting — Design

Derived by reading actual SRD spells and extracting every mechanical pattern they need.
Like monsters, spells are **one JSON file each** (`data/spells/`); the engine consumes a
fixed set of effect/targeting/timing primitives, so adding a spell = adding a file.

## Patterns found by reading real spells (the schema must cover all of these)

| Spell | Pattern it forces the engine to support |
|---|---|
| Fire Bolt | cantrip, **ranged spell attack**, damage scales by caster level |
| Sacred Flame | **save, no half** (full damage or none), ignores cover |
| Vicious Mockery | save + **rider effect** (disadvantage on next attack) |
| Magic Missile | **auto-hit**, multiple darts, **+1 dart per slot** (upcast = more projectiles) |
| Scorching Ray | **multiple spell attacks** (rays), +1 ray per slot |
| Burning Hands | **self cone AoE**, DEX save, **half on save**, +1d6 per slot |
| Fireball | **point sphere AoE** at range, save-for-half, +1d6 per slot |
| Lightning Bolt | **self line AoE** |
| Thunderwave | **self cube**, save-half + **forced movement** (push) on fail |
| Cure Wounds | **heal**, touch, + caster mod, +1d8 per slot |
| Healing Word | heal at range, **bonus-action cast** |
| Bless | **concentration buff** on allies: **passive +1d4 to attacks & saves** |
| Bane | concentration debuff on enemies (save): **passive −1d4 to attacks & saves** |
| Shield of Faith | concentration **+2 AC** passive, bonus action |
| Faerie Fire | concentration, save, **attackers gain advantage** vs affected |
| Hold Person | concentration, WIS save, **paralyzed, save-ends each turn** |
| Hex / Hunter's Mark | concentration, **bonus damage rider** on the caster's attacks vs a marked target |
| Spirit Guardians / Moonbeam | **concentration aura** that damages on enter/turn, moves with caster *(advanced — next sub-slice)* |
| Spiritual Weapon / Conjure | **summoned entity** *(advanced — next sub-slice)* |
| Shield / Counterspell | **reaction spell** with a trigger *(needs reaction system — next sub-slice)* |

## Effect primitives (discriminated union, one spell = a list of effects)

- `spell_attack` — d20 + spell attack bonus vs AC (+cover, +target AC effects); crit doubles dice; on-hit rider.
- `save` — target rolls vs spell save DC; carries any of: damage (`half_on_save` true/false), a condition (`save_ends` = repeat the save at end of each turn, else fixed duration), forced movement on fail, a rider modifier.
- `auto_damage` — no roll (Magic Missile).
- `heal` — dice + optional caster ability mod.
- `modifier` — a **passive effect** stored on the target and consulted by the rules layer: `attack_bonus`/`attack_penalty` (dice), `save_bonus`/`save_penalty` (dice), `ac_bonus`, `speed_delta`, `attackers_have_advantage`, `disadvantage_on_attacks`, `damage_rider` (+ marked target).

## Targeting

`target.mode`:
- `self`, `single` (one creature in range with line of effect), `multi` (N projectiles/rays; may focus or split),
- `point` (AoE shape — sphere/cube — centred on a point in range), `self_area` (cone/line/cube originating from the caster toward a direction).
`affects`: `enemies` | `allies` | `self`. Range is enforced; **line of effect (total cover) blocks targeting** (reuses the grid LoS/cover from the combat-fidelity layer). AoE square sets reuse the grid templates (sphere/cube/cone/line).

## Timing

- `casting_time`: `action` | `bonus` | `reaction` is recorded on every spell. The engine currently resolves **one cast per turn**, so the *bonus-action spell rule* (a bonus-action spell limits your action to a cantrip) is not yet relevant — it activates when multi-cast turns land alongside the reaction system (§7.5). Reaction-cast spells are part of that same pending sub-slice.
- Range types: `self`, `touch` (5 ft), `ranged` (N ft). The engine repositions the caster (deterministically) to bring the primary target into range + LoS, exactly like weapon attacks.

## Scaling

- **Upcast**: casting with a slot above the spell's base level adds, per level, either extra damage dice (`damage`), extra targets, or extra missiles/rays — declared per spell.
- **Cantrip scaling**: damage dice multiply by tier from the caster's level (×1 / ×2 / ×3 / ×4 at levels 1/5/11/17).

## Concentration (full rules)

- A caster holds **at most one** concentration spell. Casting a new concentration spell **ends the old** (its applied effects/conditions are removed).
- **Breaking concentration**:
  1. **On damage** — a CON save, DC = `max(10, floor(damage/2))`, per instance of damage. Failure ends it.
  2. **On becoming incapacitated** (or any hard CC) or **dying** — ends automatically.
- Concentration spells have a **duration** (e.g. "up to 1 minute" = 10 rounds), ticked at the end of the caster's turn; at 0 it ends.
- All effects a concentration spell applied are tracked as handles on the caster and removed together when it ends — so Bless's +1d4 vanishes from every ally the instant the caster drops it.

## Passive effects (consulted every roll)

The rules layer aggregates a creature's active modifier effects on every relevant roll:
- attack rolls: `+ Σ attack_bonus − Σ attack_penalty` (Bless/Bane), advantage if any source grants it to attackers (Faerie Fire), disadvantage if the attacker has a disadvantage effect.
- AC when targeted: `+ Σ ac_bonus` (Shield of Faith).
- saving throws: `+ Σ save_bonus − Σ save_penalty` (Bless/Bane apply to saves too).
- on a hit: damage riders from the attacker that name this target (Hex/Hunter's Mark).
- speed: `+ Σ speed_delta`.

## Caster stat block (JSON addition to a monster file)

```json
"spellcasting": {
  "ability": "INT", "save_dc": 14, "attack_bonus": 6, "caster_level": 9,
  "slots": { "1": 4, "2": 3, "3": 3 },
  "spells": ["Fire Bolt", "Magic Missile", "Burning Hands", "Bless", "Fireball"]
}
```

## Reactions (implemented)

A creature has one reaction per round (refreshed at the start of its turn). Reaction-cast
spells are tagged `casting_time: "reaction"` and never appear as normal actions; they fire from
trigger hooks:
- **Shield** — when an attack (weapon or spell) would hit by < 5, or when targeted by Magic
  Missile, the defender casts Shield (reaction + a 1st+ slot): +5 AC until its next turn, turning
  the triggering hit into a miss / negating the missiles.
- **Counterspell** — when a creature casts a spell of level ≥ 2 within 60 ft, a hostile reactor
  with Counterspell and a 3rd+ slot negates it (the original caster still expends the slot).
- **Opportunity attacks** — leaving an enemy's reach (from the combat-fidelity layer).
Decisions use a deterministic policy for all controllers (reactions are too frequent for a model
call per trigger).

## Moving auras (implemented)

`effect.kind = "aura"` creates an `AuraState` on the caster (concentration-linked). At the start
of each creature's turn, enemies standing in the aura make the save and take damage (half on
save); the area is difficult terrain for them. Anchored to the caster, so it moves as the caster
moves. **Spirit Guardians** (15-ft radius, WIS save, 3d8, difficult terrain) ships.

## Summons (implemented)

`effect.kind = "summon"` adds real combatants on the caster's team to the encounter and turn
order; they act via the team's controller. Tracked for teardown by concentration (Conjure
Animals dismisses its wolves when the caster's concentration ends) or by a fixed duration
(Spiritual Weapon). `untargetable` summons (Spiritual Weapon) can't be targeted and don't keep a
team "alive" for victory. **Conjure Animals** (3 Wolves, concentration) and **Spiritual Weapon**
(untargetable force attacker, 10 rounds, non-concentration) ship.

## Round 2 additions (implemented)

- **Hellish Rebuke** — on-damage reaction: when an attack damages a creature with Hellish Rebuke
  (+ a 1st+ slot, reaction available, attacker within 60 ft), it retaliates (DEX save, 2d10 fire
  half). Fires from the attack resolver after damage.
- **Readied actions** — a creature can Ready an attack (`kind:"ready"` option); when a foe moves
  into that attack's range, the readied attack fires as a reaction (`_trigger_readied` in
  `_do_move`). The readied action lapses at the start of the readier's next turn.
- **Moonbeam** — a **movable point-anchored aura** (`anchor:"point"`): cast at a location, it
  damages creatures that start their turn in it, and the caster re-aims it toward the densest
  enemy cluster at the start of each of its turns.

## Round 3+ additions (implemented)

- **Flaming Sphere** — a movable point-anchored fire aura (DEX save, 2d6), re-aimed toward the
  densest enemy cluster each turn, like Moonbeam.
- **Aura on-enter trigger** — auras now hit a creature that *moves into* them, not only one that
  starts its turn there (tracked once per turn so enter + start don't double-dip).
- **Multi-cost legendary options** — the Adult Red Dragon's 2-cost **Wing Attack** (DEX save,
  bludgeoning + prone on a cluster, then the dragon flies up).

All spellcasting patterns from the original design are now implemented. Distances are true
Euclidean and flyers are altitude-aware (see ROADMAP); a spell's range/AoE uses 3D distance.
