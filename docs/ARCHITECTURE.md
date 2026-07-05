# Architecture

Ravel 2 separates the deterministic rules engine from the one nondeterministic decision point (the LLM) behind two seams. Get these two seams right and everything else is mechanical.

## The two seams

### Seam A — the Controller boundary (the only place an LLM may live)

```
engine.enumerate_options(state, actor) -> list[Option]   # deterministic
controller.decide(state, actor, options) -> Choice        # the ONLY nondeterministic step
engine.apply(state, choice) -> list[Event]                # deterministic
```

`Controller` is a `Protocol` with interchangeable implementations:

- `RandomController` — picks a legal option using the injected seeded RNG (fully deterministic given the seed). The default for tests.
- `ScriptedController` — replays a fixed list of choices; powers golden-master scenarios.
- `LLMController` — the only nondeterministic controller. Builds a constrained schema from the supplied `Option`s, asks Claude to select one option id + targets, validates the response against the engine's option list, and returns a `Choice`. **It can only choose from what the engine already validated** — it is structurally incapable of an illegal move.
- `HumanController` — drives the web UI's action menu (Slice 12d): the browser renders the enumerated legal options; a click is the `decide`.

This is the most important abstraction in the codebase: the entire engine is testable with deterministic controllers, and the LLM swaps in without touching mechanics.

### Seam B — event-sourced core (state is a fold over events)

`apply()` never mutates game state in place; it produces an ordered list of immutable `Event`s (`AttackRolled`, `DamageDealt`, `SaveRolled`, `ConditionApplied`, `MovementTaken`, ...). The new state is the reduction of the old state over those events.

This buys, for free:
- the **combat log** — exactly what the narration LLM later consumes;
- **replay & undo** — fold a prefix of the event stream;
- **golden-master tests** — `seed + scripted choices` must produce a byte-identical event stream;
- a natural home for **reactions** — certain events open reaction windows (see below).

**Status (milestone build, 2026-06-30) — event stream + reducer/replay live; imperative core.**
The engine still mutates state in place and drives a prose `self.log`, but it now emits a
**canonical typed-event stream** (`ravel/events.py`: `spawn/turn_start/move/damage/heal/death/
survive/condition`, each carrying an absolute HP/pos snapshot) on `Encounter.events`, and
`ravel/reducer.py` folds it: `reduce(events)` → per-combatant state, `state_at(n)` reconstructs
any prefix (**replay/undo** without re-running). A consistency test proves the fold reproduces
the engine's final HP + alive exactly, and the stream is byte-identical per seed (the **golden
master**). What's *not* done is the strong §2.2 form — a pure "state in → events out → reduce"
engine (deferred as high-churn / low marginal value now that replay works off the emitted
stream). The **trigger layer** (`ravel/triggers.py`) is the other half — see below.

#### Triggered abilities (the trigger layer)
Reactive monster/PC abilities ("when X happens, do Y") subscribe to **named triggers**
fired at engine interception points, instead of being hard-coded one-by-one in the core:

```
triggers.on(ability_id, trigger)(handler)      # register
enc.survive_check(target, amount, dtype, crit) # fires `would_drop_to_0` handlers
enc.fire_on_kill(killer, victim, melee)        # fires `on_kill` handlers
```

A stat block opts in via its `triggered_abilities: [id, …]` list (explicit, e.g.
**Undead Fortitude** `would_drop_to_0`, **Rampage** `on_kill`), or implicitly via
`triggers.effective_abilities(md)`, which derives ids from existing stat fields. **All the
pre-existing reactions have been migrated onto this one registry**: Shield/Parry
(`incoming_attack`), Counterspell (`on_spell_cast`), Hellish Rebuke (`on_damaged`), and
Death Burst (`on_death`) now live as handlers in `triggers.py`; the engine's `try_*`/`offer_*`
methods are thin dispatchers that own only the iteration/reaction-window. So there is **one**
mechanism for every reactive behavior. New trigger points (`on_missed`, `on_condition`,
`on_turn_end`) are added as abilities need them; when the declarative ability schema (see
below) lands, it registers handlers through this **same** registry — the dispatch path never
changes. This is the enabler that unlocks the whole reactive-ability class (Relentless,
Redirect Attack, Aggressive, ooze Split, create-spawn, …).

## Layers (strict dependency direction: outer may import inner, never the reverse)

```
core/        pure engine: state models, dice, RNG, options, effects, events, reducer, rules
  ├─ no imports of: anthropic, rich, textual, typer, fastapi, requests, filesystem
controllers/ Random, Scripted, LLM, Human (LLM controller owns the anthropic SDK usage)
content/     Pydantic content models + importers (5e.tools / Foundry JSON -> internal schema)
runtime/     the encounter driver: initiative, round/turn loop, reaction windows, calls controllers
app/         CLI entry points (`ravel/cli.py`), narration LLM
web/         FastAPI service + no-build static frontend (Bestiary, Blood Pit, builder — Slice 12)
tests/       unit, golden (syrupy), property (hypothesis), eval (live, LLM-judged)
```

## The interruptible turn loop

The encounter driver must be **pausable and resumable mid-action** so it can open a reaction window (query controllers for reactions) before continuing. This is designed in from Slice 0 even though reactions arrive in Slice 3 — retrofitting a synchronous loop is expensive. Model the loop as a generator/state machine that yields decision requests, rather than a recursive synchronous call.

## The option / effect model (the schema crux)

Everything an actor can do — a weapon attack, a cantrip, Dash, Grapple, a class feature, a magic-item activation — compiles to a uniform `Option`:

```
Option:
  id, source (what granted it), name
  cost: action economy (action | bonus | reaction | free | movement) + resource costs (slot, ki, charge, ...)
  range / target rule: who/what is targetable, how many, valid target set (computed against the grid)
  effects: list[Effect]            # a discriminated union
  conditions: usage limits (per turn, recharge, once/rest, concentration)
```

`Effect` is a **Pydantic discriminated union** (tagged by `kind`): `AttackRollEffect`, `SavingThrowEffect`, `AutoDamageEffect`, `HealEffect`, `ApplyConditionEffect`, `MoveEffect`, `GrantAdvantageEffect`, `TempHPEffect`, etc. Effects compose; a single spell is a list of effects, some gated by a save. Modeling these five archetypes proves the schema (see ROADMAP Slice 5): a weapon attack, a save-for-half AoE (Fireball), a buff (Bless), a condition (Prone), and a heal (Cure Wounds).

Monsters and PCs share the **exact same** creature + option representation. A stat block is just a pre-built option list. Source breadth from 5e.tools; model after Foundry's dnd5e *Activities* structure.

#### Conditional modifiers (the declarative-ability core)
The first slice of the Activities model is live: **conditional combat modifiers** — a bonus
(advantage or on-hit damage) that applies when a **predicate** holds at attack-resolution time.
`ravel/modifiers.py` is a **predicate registry** (mirroring the trigger registry): a predicate is
`(enc, attacker, target, adv, dis, mod) -> bool`. A stat block declares `bonus_damage: [{when,
damage, once_per_turn, threshold, kind}]` (data, not code) and `resolve_attack` evaluates each
rider generically. Live: **Reckless** (`MonsterDef.reckless`), **Martial Advantage**
(`ally_adjacent_to_target`), **Sneak Attack** (`sneak_attack`), **Charge** (`charged`). A new
conditional ability is a data entry plus (only if the condition is novel) one predicate function —
and the same layer will drive PC features (Sneak Attack, Great Weapon Master, Charger feat).

#### Movement / space modes (the pather's capability flags)
Movement is a Dijkstra over the grid (`grid.reachable`) parameterised by capability flags the
engine derives from the stat block: `can_fly`, `can_climb`, `can_burrow`, and **`can_phase`**
(incorporeal / teleport — passes through walls, creatures, chasms and cliffs). `MonsterDef`
carries `fly/swim/climb/burrow/hover/teleport/incorporeal`. **Containment** (swallow/engulf) is a
separate relationship, not a pather flag: `Combatant.swallowed_by` + `SwallowDef` model a
creature held *inside* another — blinded/restrained, total cover (filtered out of everyone's
target lists except the captor's), acid each turn, escape by dealing `escape_threshold` damage
from inside (regurgitation save), and auto-freed prone when the captor dies. New movement modes
are a flag + a few `reachable` lines; containment is the one genuinely bespoke piece.

## Shared spell library (monsters today, PCs later — author once)

A spell is **defined once** as data in `data/spells/*.json` (loaded by `spells.py` into a
`Spell`, resolved by `cast.py`) and **referenced by name** from any caster — a monster's
`spellcasting.spells` / `innate` list today, a PC's prepared/known list tomorrow. Stat
blocks must never inline spell mechanics; they only *reference* the shared library. This is
the load-bearing decision that stops the future PC work from re-authoring the SRD.

For this to hold, `cast.py` resolves a spell against a small **caster interface** — the
values a spell needs from whoever casts it: `spell_dc`, `spell_attack`, `spell_ability`,
`spell_mod`, `caster_level`, `prof_bonus`, `slots`, and `concentration`. **This is now live**:
`Combatant` exposes these as properties delegating to `md`, and `cast.py` reads
`actor.spell_dc` etc. — so a future PC-backed combatant supplies the same fields from
class+level and the shared library is reused unchanged. The rule for the §10 spell-library
buildout (an ongoing data effort):
- **Spell effects stay caster-agnostic** — they read the caster's DC/attack/ability/level at
  cast time, never a monster-specific field. ~70% of the SRD then maps to the existing effect
  kinds (attack/save/auto/heal/modifier/aura/summon/condition/dispel/silence/antimagic) as
  **pure data files**; the remaining ~30% need a handful of new effect kinds (control-another-
  creature, remove-from-combat, terrain-creation) added once and shared.
- **Before adding PCs**, route every caster-attribute read in `cast.py` through the interface
  (e.g. `actor.spell_dc` delegating to `md` for monsters) so the PC swap is a provider change,
  not a spell rewrite. The library, the resolver, and `concentration` lifecycle are reused
  verbatim across monsters and PCs.

## The grid

- 2D integer coordinates, squares = 5 ft. Creatures occupy a footprint by size category.
- Distance: default PHB "every square = 5 ft" (Chebyshev); DMG 5-10-5 diagonals selectable via a rules-config flag.
- The grid is authoritative for: ranges, reach, movement cost, opportunity-attack triggers, line of sight / line of effect, cover, and area-of-effect templates (sphere/cube/cone/line/cylinder → set of affected squares).
- "Theater of the mind" is a **presentation** choice (describe positions in prose), never an engine choice. The engine always has coordinates.

## Determinism rules (enforced; violations are bugs)

1. The core takes a seeded RNG (`random.Random(seed)`, or a small injected PRNG) passed explicitly. **No module-level `random`, no `time`, no `uuid4`, no `datetime.now()` in `core/` or `runtime/`.**
2. No reliance on `set` iteration order. Sort before iterating when order is observable. Use ordered structures for anything that feeds the event log.
3. Integer math only for game quantities (5e is integer; no floats in damage/HP/AC paths).
4. The event stream is the canonical output. Two runs with the same seed + same controller decisions must produce identical event streams (the golden-master invariant).
5. The LLM is mocked in correctness tests; its decisions are recorded as fixtures or scripted. Live model calls happen only in `eval` tests, which are never gating CI on exact output.
