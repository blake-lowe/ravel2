# Battlefield & environment — design scope

Scope for the next round of environment fidelity. Nothing here is built yet; this is the
plan to iterate on. Ordering: **Lighting/Vision → Hazard terrain → Aquatic → Interactive
(future)**. Weather folds into the first three (see §5). Determinism note: everything here is
a pure function of authored state + creature positions — **no new RNG** (light/obscurement are
deterministic; only the saving throws they gate use the existing seeded RNG).

## Current state (already modeled)
3D space + flight altitude; elevation/high-ground; cover ladder (none / half from an intervening
creature / three-quarters from a low wall / total from a wall); difficult terrain; water (difficult
for non-swimmers); chasms & pits (fall damage, shove-into-pit); line of sight via walls; squeezing;
dynamic spell terrain (`Encounter.zones` — Wall of Fire, Spike Growth, Silence/Antimagic); movement
modes (fly/swim/climb/burrow/hover/teleport/phase). Maps: ASCII-authored, 3 built-in.

---

## 1. Lighting & vision  *(task #21 — **DONE**)*

> **IMPLEMENTED (2026-07-01).** `Grid.ambient`/`ambient_sunlight`/`lights` + `Encounter.lights`/
> `darkness`/`fog`; `light_at`/`light_level`/`in_sunlight` (inverse-square, calibrated `k`/`k/4` bands,
> wall shadows); `can_see(observer, target)` (darkvision/blindsight/tremorsense/truesight/invisibility/
> fog) wired into `resolve_attack` + spell attacks (unseen attacker → advantage, unseen target →
> disadvantage) + Sunlight Sensitivity. Importer detects `sunlight_sensitivity` (14 monsters); the
> `Darkness` spell (magical-darkness effect kind); `dark_dungeon` map + `*` torch glyph. **Default is
> bright, non-sunlight — existing battles unchanged (221 tests pass, roster smoke 0 crashes, determinism
> holds).** Playtest: Drow Elite Warrior vs an equal Gladiator swings **bright 37% → pitch-dark 100%**;
> Drow attack at disadvantage in sunlight. Follow-ons: `Light`/`Daylight`/`Fog Cloud` spells, Devil's
> Sight, and fixing **innate `will`/`daily` spellcasting import** (drow/mephits lost their innate spells
> — separate importer gap, tracked in ENGINE_GAPS).
>
> **Polish added (2026-07-01):** the **Fog Cloud** (local `fog` effect kind), **Light** (a magical
> `Light` on the caster), and **Daylight** (bright magical light that dispels ≤3rd-level `Darkness`)
> spells; **Devil's Sight** (`devils_sight` flag — 9 devils — pierces magical & nonmagical darkness in
> `can_see`); and the innate-spellcasting import fix (so the Drow's innate Darkness/Faerie Fire land).

### Representation
A per-cell **light level 0–15** (bright/dim/dark after quantizing, e.g. `>=8` bright, `1–7` dim,
`0` dark — tunable). Rather than baking a static grid, the level is **computed at runtime** from:
- **Ambient** blanket on the map/grid: outdoor day = 15 (flagged *sunlight*), overcast/indoor = dim,
  night/underground = 0.
- A **list of light sources** — `Light(origin, bright_radius, dim_radius, magical, sunlight)` — that
  can be **fixed** (brazier, lava glow, map-authored) on the Grid, or **dynamic** on the Encounter
  (a carried torch that moves with its bearer, a `Light` spell, `Daylight`). This mirrors how
  `Encounter.zones` already layers dynamic terrain over the static Grid.

The grid is tiny (≈400 cells) and lights are few, so `light_at(cell)` is cheap to compute on demand
(optionally cached per light-change). Runtime = spells and movable lights just edit the source list.

### Falloff & combination — inverse-square with calibrated bands (DECIDED)
Physical inverse-square for the raw value, with global bands tuned so 5e's bright/dim radii fall out
automatically. This works because nearly every 5e light has **dim radius = 2× bright radius** (torch
20/40, candle 5/10, lantern 30/60, `Light` 20/40, `Daylight` 60/120) and inverse-square is exactly ¼
intensity at 2× distance.

- One global constant `k` (bright threshold). Each source's intensity from its own bright radius:
  **`I = k · bright_radius²`**.
- Contribution at distance `d` (feet): **`C(d) = I / max(d, 2.5)²`** (the 2.5-ft floor removes the
  `d=0` singularity and keeps the source cell bright).
- Cell level **`L = ambient + Σ C_i(d_i)`** over all sources **with clear line of sight to the cell**
  (walls block light and cast shadows; low cover-obstacles do not). **Summed** — physics.
- Bands: **bright if `L ≥ k`**, **dim if `L ≥ k/4`**, else **dark**. (0–15 hex = render clamp of `L`.)

A lone torch reproduces RAW exactly (bright→20, dim→40). Summing is well-behaved: inverse-square makes
dim-band contributions small, so overlapping dim zones stay dim (0.44k+0.44k < k) while overlapping
bright zones correctly go bright — no false daylight from many candles.

Ambient (sunlight `≥ k`, twilight `k/4..k`, night/underground `0`) is just an additive term; the
outdoor `sunlight` flag is separate (drives Sunlight Sensitivity / vampire sunlight). **Magical
darkness** is not negative light — it's an override that clamps its cells to dark and suppresses
nonmagical + lower-level magical light (Devil's Sight / Truesight pierce it); `Daylight` dispels
≤3rd-level `Darkness`.

**Magical darkness/daylight** interact by level + flags: the `Darkness` spell is a source that clamps
its cells to 0 and suppresses nonmagical light and magical light of lower level (Devil's Sight /
Truesight ignore it); `Daylight` is a bright magical source that dispels ≤3rd-level `Darkness`.

### What lighting *does* (the payoff) — vision resolution
The crux is one predicate, **`can_see(observer, target)`**, considering the target's obscurement and
the observer's senses:
- **Bright**: seen normally.
- **Dim** = lightly obscured: seen, but disadvantage on sight-based Perception (matters for Hide).
- **Dark / heavily obscured**: the observer is effectively **blinded** toward that cell → can't see
  the target **unless** it has **darkvision** reaching it (treats dark→dim within range),
  **blindsight/tremorsense/truesight** (already `can_sense`), or the target sheds light.

`can_see` then drives, reusing the existing unseen-attacker path in `attack_mods` (which already
handles invisible/hidden):
- Attacker can't see target → **disadvantage**; target can't see attacker → attacker has
  **advantage**. (Same mechanic as invisibility, now also lighting-driven.)
- **Sunlight Sensitivity** (drow, kobolds, many undead): in *sunlight* (bright, `sunlight`-flagged) →
  disadvantage on attacks + Perception. Needs a `sunlight_sensitivity` flag detected on import.
- **Devil's Sight / Truesight**: see through magical darkness. **Blindsight/tremorsense**: ignore
  light entirely (and fog). Enables the currently-**dormant** darkvision on nearly every monster.
- **Hide**: a creature that's unseen (heavily obscured / darkness the foe can't pierce) can Hide.

### Two obscurement types
Darkness (light-based, pierced by darkvision) vs **fog/foliage** (blocks *all* sight incl. darkvision,
only blindsight/tremorsense/truesight see through). Model obscurement as `max(light-based, fog-based)`
so `Fog Cloud` and weather fog reuse the same `can_see` path.

### Unlocks
Spells: `Light`, `Darkness`, `Daylight`, `Faerie Fire` (reveal — partly done via
attackers-have-advantage), `Fog Cloud`. Traits: darkvision (dormant today), Sunlight Sensitivity,
Devil's Sight, the vampire's sunlight weakness (Misty Escape's real exception). Maps: an optional
`lights:`/ambient section (sparse source list preferred over a full 0–15 ASCII layer; the layer is a
fine debug render).

### Phasing
A) light field + magical darkness/daylight. B) `can_see` + wire into attack_mods / Sunlight
Sensitivity / Perception-Hide. C) spells + Sunlight-Sensitivity detection + map authoring.

---

## 2. Ground-covering hazard terrain  *(task #22 — **DONE**)*

> **IMPLEMENTED (2026-07-01).** `models.Zone` extended (`on_enter`, `prone_save`, `flammable`,
> `light`) and unified with the spell-zone path via `Encounter._terrain_zones()` = `Grid.hazards`
> (static, from the map) + `self.zones` (spell). **Lava** (6d10 fire on enter/turn, glows — fed into
> `light_at`), **acid** (1d10), **grease** (difficult + Dex-save-or-prone + flammable), **ice**
> (difficult + prone). Damage applies on start-of-turn (`_apply_zones_start_of_turn`) and on entering
> (`_apply_hazard_on_enter`, hooked into `_do_move`); damaging hazards are difficult-for-pathing so the
> AI routes around them but still burns if forced across. **Grease ignites** into fire when a fire
> source touches it (`_spread_fire`, adjacency, each round). Map glyphs `L/&/%/=` + the `lava_cavern`
> demo map. Fire immunity is respected (Fire Giant shrugs off lava). Default maps have no hazards →
> existing battles unchanged (230 tests pass, roster smoke 0 crashes, determinism holds). **Push into
> hazard done (2026-07-01):** `_push` (Thunderwave/Gust of Wind) now fires `_apply_hazard_on_enter`, so a
> shoved foe burns in lava/slips in grease. (The melee Shove action is still knock-prone only.)

Unify with the **spell-zone system** — a static hazard is a permanent `Zone` plus a few fields:
- **Lava**: enter or start-turn → heavy fire damage; emits *light* (ties to §1).
- **Fire** (burning ground): fire damage per turn; sheds light; **dispersed by rain/wind** (§5).
- **Acid**: acid damage per turn.
- **Grease**: not damaging — **difficult** + **Dex save or prone** on entering (like the spell/ice),
  and **flammable**: ignites into a fire hazard when it meets fire damage or a fire/light source.

Per-hazard fields: `damage(dice,type)`, `on_enter` vs `on_start`, `save`/`half`, `difficult`,
`prone_save`, `flammable`. Extend the existing **shove-into-pit** to shove-into-hazard (push a foe
into lava). Cross-system synergy with §1 (fire=light, rain douses fire) and §5.

---

## 3. Aquatic / underwater combat  *(task #23 — **DONE**)*

> **IMPLEMENTED (2026-07-01).** Whole-encounter `Encounter(underwater=True)` (→ `build_encounter`/
> `run_battle`/CLI `--underwater`). Melee: non-piercing weapons from a creature without a swim speed
> attack at disadvantage (piercing — spear/trident/bite — is fine). Ranged weapons: disadvantage
> within normal range, auto-miss beyond. Fully-immersed creatures have fire resistance (fire ×½).
> Non-swimmers slog (whole map is difficult terrain). Air-breathers hold breath `max(5, (1+CON)·10) +
> max(1,CON)` rounds then drop to 0 (drown); `water_breathing` (Amphibious/Water Breathing, incl.
> "Limited Amphibiousness" — 44 monsters) are exempt. Default is dry land, so existing battles are
> unchanged (225 tests pass, roster smoke 0 crashes, determinism holds). Playtest: Merrow×2 vs a
> Veteran swings **land 45% → underwater 95%** (the Veteran's longsword + crossbow are crippled);
> piercing-spear fighters are barely affected — faithful RAW. Follow-on: murky-water obscurement
> reuses §1.

5e underwater rules, for reference (final shape awaits your input):
- **Melee**: a creature without a swim speed has **disadvantage** unless the weapon is a
  dagger/javelin/shortsword/spear/trident (piercing).
- **Ranged weapons**: **auto-miss beyond normal range**, and **disadvantage within** it — except
  crossbow, net, or thrown weapons (javelin) at normal range.
- **Fire**: a fully-immersed creature has **resistance to fire** damage.
- **Movement**: no swim speed → swimming costs extra (already modeled as water = difficult).
- **Breathing / suffocation** (deterministic, no RNG): a creature without water breathing holds its
  breath for **`1 + CON mod` minutes** (min 30 s), then survives **`CON mod` rounds** (min 1) of
  choking, then at the start of its next turn **drops to 0 HP and is dying** and can't heal/stabilize
  until it can breathe. A held-breath counter starts when a non-water-breather is submerged. In
  practice it only bites in long fights — which correctly makes "land creatures fighting in deep
  water" a losing proposition; aquatic monsters have Amphibious / water breathing and are exempt.
- **Vision**: water can be murky → obscurement (reuses §1).

Strongly favors the aquatic roster (sahuagin, sharks, merfolk, kraken, water elemental, sea hag).
**DECIDED:** a **whole-encounter `underwater` flag** (simplest, ideal for testing the aquatic roster)
— per-cell deep-water regions deferred.

---

## 4. Interactive & destructible terrain  *(task #24 — future)*

Objects with HP/AC/damage-threshold (statues, furniture, walls) that provide cover and can be
destroyed to reshape the map and LoS; doors (open/close → movement + sight); movable cover; breakable
walls (giants/siege); levers/traps. Needs an `object` entity (position + HP) tied into the existing
LoS/cover systems. Larger scope; sequence last.

---

## 5. Weather & environmental effects  *(**DONE**)*

> **IMPLEMENTED (2026-07-01).** `Encounter(weather=...)` — `"clear"` (default) / `"fog"` / `"rain"` /
> `"wind"`, threaded through `build_encounter`/`run_battle`/CLI `--weather`. **Fog:** the whole field
> is heavily obscured — `can_see` returns False for everyone except blindsight/tremorsense/truesight
> (they dominate; e.g. a blindsight Grimlock's win rate vs sighted archers ~doubles). **Rain:**
> non-magical lights (torches) are extinguished in `light_at`, and open flames — spell fires (Wall of
> Fire) and burning ground, but not lava — are doused each round (`_douse_flames`). **Wind:**
> disadvantage on ranged weapon attacks (`resolve_attack`); nonmagical flyers can't gain altitude
> (`_desired_alt` → 0) and are forced to land (`enforce_flight`); flames doused too. Extreme
> cold/heat/altitude left out by design (per-hour exhaustion, combat-inert). Default `"clear"` → no
> effect, so existing battles are unchanged (234 tests pass, roster smoke 0 crashes, determinism holds).

---

### Reference — what the rules are



You asked whether these have real rules. They do (DMG ch. 5 "The Environment"; Xanathar's hazards),
but **most fold into the systems above rather than forming a separate subsystem**, and the rest are
per-*hour* effects that don't matter in a fight:

| Weather | Official rule (DMG) | Where it lands here |
|---|---|---|
| **Fog** (heavy) | Heavily obscured area | **Obscurement (§1)** — blinds sight, *not* pierced by darkvision; = the `Fog Cloud` spell |
| **Rain / snow** (heavy) | Lightly obscured (Perception disadvantage); **extinguishes open flames**; hearing disadvantage | Light obscurement (§1) + **douses fire hazards/torches (§2)** |
| **Strong wind** | **Disadvantage on ranged attacks**; disperses fog & extinguishes flames; nonmagical flyers must land or fall | Ranged-attack disadvantage + **disperses fog/fire (§1/§2)** + **grounds nonmagical flyers** (hooks the existing flight/`enforce_flight` system) |
| **Extreme cold / heat / high altitude** | CON save **each hour** or a level of exhaustion | **Combat-inert** (per-hour) — recognize & skip, like Rejuvenation |
| **Slippery ice** | Difficult terrain; Dex save or fall prone | A **grease-like hazard (§2)** |
| **Frigid water** | CON save each **minute** of immersion → exhaustion | Edge case; note under Aquatic (§3) |

**So weather isn't its own big feature.** The three combat-relevant conditions — **fog, rain, wind** —
attach to the vision, hazard, and flight systems we're already scoping (fog = obscurement, rain =
douse-flames + light-obscure, wind = ranged-disadvantage + ground-flyers + disperse-fog). Temperature
is per-hour exhaustion → out of scope for a combat engine. That's the honest picture; no separate
"weather subsystem" is warranted — a small `Encounter.weather` enum feeding those three hooks covers
the real rules.
