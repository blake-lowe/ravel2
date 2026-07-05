# CR Calibration — empirical "adjusted CR" from playtesting

> Status: **design + Phase-1 harness landed** (`ravel/calib.py`, skills `cr-benchmark` /
> `cr-rate`). This doc is the source of truth for the method. It is **tooling**, an outer
> analysis layer that *consumes* the engine — not a SPEC slice. It never touches the
> determinism boundary or engine purity (see `CLAUDE.md`).

## 1. The problem

D&D 5e Challenge Rating is a single scalar collapsed from two axes (defensive CR from
HP/AC, offensive CR from DPR and attack-bonus/save-DC), averaged. It structurally ignores
the things this engine *does* model: action economy (CR assumes 1 monster vs a 4-PC party,
not 1-v-N), damage-type resistance/immunity, save-or-suck control, mobility/verticality
kiting, legendary actions/resistance, advantage engines (pack tactics, reckless), and
recharge nova. So real combat effectiveness is **multidimensional and relational** — a
monster's strength depends on *whom it fights, in what numbers, on what terrain*.

We produce an **adjusted CR float** per monster from real playtesting, plus the vector of
sub-signals behind it, so the scalar is a principled projection rather than a lossy guess.

## 2. Canonical method — the fair-XP mirror

> **Adjusted CR of a monster M = the CR whose equal-XP reference squad fights M to a coin
> flip.**

1. **CR↔XP.** The official 5e CR→XP table, interpolated in **log-XP** so the inverse map
   yields a *continuous* CR float (`ravel/calib.py: cr_to_xp / xp_to_cr`).
2. **Reference bench.** A curated pool of trustworthy "yardstick" monsters spanning low CRs
   (plain brutes + a spread of XP denominations) used to *compose* opposing squads to any
   budget (`data/calibration/bench.json`).
3. **Mirror.** For M, compose opposing squads at a **ladder** of budgets (e.g. 0.5×…3× of
   M's nominal XP), run many seeds/positions/environments per budget, and record M's score
   (win = 1, draw = 0.5). At each budget the squad is composed at several **body counts**
   (`compositions`, e.g. `[1, 3, 6]`) — the same XP as a few strong peers vs a weaker
   horde — and outcomes are **pooled**, so B\* averages over action-economy regimes rather
   than one arbitrary composition. Composition is itself a conditioning axis (§4): a horde
   brings more attacks/round and its own pack tactics but folds to AoE and misses high AC;
   `cr-rate --dispersion` reports a monster's few-strong vs many-weak adjusted CR spread.
4. **Tie point.** Fit logit(score) vs log(budget) and solve for score = 0.5. That budget
   `B*` is M's *effective* XP; inverse-map to a CR.

### 2.0 Implementation details that turned out to matter

Three refinements the playtesting forced (each fixed a real artifact):

- **Adaptive ladder.** A fixed 0.5×–3× ladder can't bracket a monster that is far from its
  book CR: an overrated one loses even at 0.5× (a `left` clamp), an underrated one wins at
  3× (`right`). The ladder now **extends rungs down/up until the 0.5 crossing is bracketed**,
  so B\* is a real tie-point. This was decisive — e.g. Rakshasa read a clamped 9.85 before
  and a true **4.85** after (its CR 13 is inflated by non-combat abilities the martial arena
  never rewards, and it folds hard to hordes). A residual `left`/`right` flag now means even
  the extended ladder couldn't bracket it (a genuinely extreme monster).
- **Single canonical curve, geometric-mean aggregation.** Each composition's tie-point is
  solved separately (pooling their heterogeneous XP into one crossing distorts B\*), then the
  **one** canonical curve `g` is applied to each: `g(B*_c)` is that composition's *absolute*
  CR-equivalent, so the few→many spread is real action-economy sensitivity (not normalized
  away). Canonical CR = `g(geomean_c B*_c)`; the geomean tempers a single dominant
  composition (e.g. a dragon's breath spike at 3 bodies) while staying self-consistent for
  calibrators.
- **Calibrators must actually be well-CR'd.** Roc (book CR 11) ties a *lower* budget than
  Fire Giant (CR 9) — a flying beast swarmed on the ground — so it inverted the curve and was
  dropped from the calibrator set (it's now a *rated* monster, correctly overrated). Lesson:
  validate calibrators for monotonicity; `cummax` masking an inversion shows up as non-zero
  self-residuals.

### 2.1 Anchoring away the 1-v-N bias

A solo monster vs an equal-XP *group* is not automatically 50/50 — 5e's own encounter math
says X XP as a group is more dangerous than X XP as one body (the encounter multiplier). We
do **not** hand-apply that multiplier. Instead we **calibrate empirically**:

- Run the mirror for a set of **calibrators** — monsters whose book CR the community
  trusts most (plain brutes, no group tricks) — getting `(B*, nominal_CR)` pairs.
- Fit a monotone curve **g: B\* → CR** through them (piecewise-linear in log-B, isotonic).
- **Adjusted CR of any monster M = g(B\*_M).** The systematic 1-v-N offset is baked into g
  and cancels: M is "underrated" only if it beats squads a *trusted* monster of its nominal
  CR could not.

`raw_cr = xp_to_cr(B*)` is also reported; **`adjusted − raw` is the action-economy
correction** the calibrators taught us.

### 2.2 Bench fairness (fixed point)

The bench may itself be mis-CR'd. Pin a tiny **anchor set** (the simplest brutes), compute
everyone's adjusted CR, re-derive the bench's own effective XP, re-run until adjusted CRs
stabilize within CI (EM-style, ~2–3 passes). Small-scale runs can skip this; the large run
does one iteration.

## 3. Cross-check — round-robin → Bradley–Terry  ✅ landed

`ravel/calib.py bt` runs a tiered 1v1 round-robin (each monster vs its `k` nearest by CR ×
`seeds`, ~60k battles, results cached to `bt_pairs.csv` for free re-anchoring via
`--from-cache`), fits latent strength θ (MM algorithm, `ravel/bradley_terry.py`), and anchors
θ→CR by **isotonic regression over the whole population** (calibrator-only anchoring
extrapolated outliers absurdly; population anchoring is robust). Writes `bt_cr`, `refined_cr`
(mirror+BT consensus), `bt_disagreement`.

**Result (k=16, 9 seeds):** an entirely independent method (pure win/loss) agrees with the
fair-XP mirror at **corr 0.961**, and **independently reproduces the findings** (casters
−0.80 vs mirror −1.11; Archmage overrated and Helmed Horror underrated by *both*). 35 monsters
are flagged overrated and 14 underrated by **both** methods — high-confidence, cross-validated.

**Disagreement = a real axis, not noise.** `bt_disagreement = mirror − bt` traces solo-vs-party
action economy: **BT ≫ mirror = "boss monster"** (dominates 1v1, folds to a party) — ancient
dragons, Balor, Beholder, Purple Worm, Lich; **mirror ≫ BT = stronger in numbers/vs groups**
(Fomorian, Gray Slaad). Surfaced in `encounter_view` as `solo_vs_group`.

**Pairing lesson:** matches must be *near-equal* (nearest-neighbor). A wide symmetric window
makes every monster win-down/lose-up ≈ 50%, collapsing θ. The global scale comes from
anchoring over the population, not from the pairing width.

*Prior wording (kept for the record): "tiered, sparse round-robin within ±k CR fit with BT,
θ→CR curve" — the ±k *window* variant proved wrong (θ collapse); nearest-neighbor + population
anchoring is what works.*

## 4. Conditioning axes — do not average these away

The scalar is a **projection over distributions** of the axes below. Each axis is reported
as a breakdown plus a **sensitivity band** (variance across the axis).

- **Matchup archetype.** Bucket opponents (brute / high-AC / caster / swarm / ranged-kiter /
  elemental-by-damage-type / control) and compute adjusted CR conditional on archetype. Big
  dispersion ⇒ "matchup-dependent" (e.g. single-damage-type monsters vs their immunity).
- **Group size + synergy (ablation).** Some monsters are disproportionately strong *in
  numbers*. Two effects are bundled: generic action economy (Lanchester square law — even
  vanilla brutes gain per-capita in a group) and **trait synergy** (pack tactics, Leadership,
  auras, death-burst chains). We separate them by **ablation**: content is flag/JSON-driven,
  so we emit an in-memory clone with `pack_tactics`/`leadership` off (same body) and diff the
  count-scaling curves.
  - `adjustedCR_solo` (k = 1), `adjustedCR_grouped` (canonical k ≈ 3–4),
    **`synergy = grouped − solo`** — the "band bonus" in CR units (`ravel/calib.py synergy`
    fills the `group_synergy` column). **Measured result (k=4):** synergy is dominated by
    *generic action economy* (Lanchester), not the pack-tactics trait — the top of the list
    is fragile-but-deadly monsters (Intellect Devourer +4.5, Black Pudding +4.1, Wraith,
    Ghost) that overwhelm in numbers, **above** nominal "pack" monsters (wolves rank lower —
    their kit already pays off solo, and pack tactics adds only ~+0.03 of the group bonus per
    the ablation). This is the right *encounter-building* signal (total danger in numbers);
    the pure trait component needs `rate --group k --ablate`.
  - Force-multiplier monsters (a captain's Leadership, a buffer's Bless) are valued by
    ablating the *source* (swap for a vanilla equal-XP body) and diffing the team's adjusted
    strength.
- **Environment.** `adjustedCR` per environment from the map suite the engine supports —
  open ground (canonical), difficult terrain, high ground, confined/dungeon, verticality/open
  sky, and **aquatic** (assumed available as a map flag; the underwater-rules engine slice is
  in work). **Native-environment tagging** (from swim/fly/burrow speeds + type) gives
  `adjustedCR_native` (its element, the fair headline for a shark = its water number) vs
  `adjustedCR_offterrain` (a flagged weakness). The canonical number weights environments by
  where the monster is *meant* to fight, so a degenerate auto-win (aquatic vs land-only, in
  water) is reported *separately* as the terrain-synergy finding rather than polluting the
  average.

## 4a. Environment axis — design & effort (scaffolded)

The aquatic-rules slice landed, so environments are real engine flags, not hypotheticals:
`run_battle` takes `underwater` (non-swimmers slog, air-breathers hold breath → drown),
`weather` (`wind` grounds nonmagical flyers & douses fire; `fog` = heavy obscurement →
special senses shine; `rain`), and terrain **maps** (`dark_dungeon`, `lava_cavern`, …).
`ravel/calib.py` exposes an **env registry** (`ENV_SPECS`: open / underwater / windy / fog /
dungeon / lava / chasm) threaded through the mirror; `rate --env <name>` and the
`environments` command use it.

**Effort control (the whole point):** rating all 450 × every env is ~200k battles and wasteful
— most monsters are terrain-neutral. So:
- **Screen first (free, no battles).** `native_env(md)` tags home turf from movement (386
  terrestrial / 46 aerial / 15 underwater / 3 subterranean); `env_relevance(md)` returns only
  the environments whose rules could move a monster (swim→underwater, fly→windy+dungeon,
  special-senses→fog, fire-defense→lava). **306/450 are env-sensitive; 144 are skipped**
  (env_cr = open_cr).
- **Cheap per-env ratings.** Each env rating is *centered on the monster's open CR* with a
  short ladder (~24 battles, not 90) — it only measures the *shift*. The screened targeted
  pass is ~623 monster×env ratings ≈ **15k battles (~15 min)**, vs ~200k for the naive full grid.

**Two calibration cautions surfaced in validation:**
- **Prefer flag-based envs** (underwater / windy / fog): they keep the open arena + spawns and
  change only the rules, so the delta is clean. `windy` cleanly grounds flyers (Manticore
  −1.08). **Map-based envs** (dungeon/lava/chasm) use *fixed spawn points*, confounding terrain
  with starting position (Manticore reads +1.44 in "dungeon") — treat those as "this map", not
  "confined space in general".
- **`underwater` is mild in short fights** (Giant Shark −0.37): drowning is a multi-round
  countdown that rarely fires in ~4-round battles; aquatic dominance needs attrition. A real
  finding, worth reporting rather than forcing.

**Storage:** `env_ratings(name, environment, env_cr, delta)` (one row per monster×env) +
`ratings.native_env` / `ratings.env_sensitivity` (largest signed deviation from open), surfaced
in `encounter_view` as `native_env` / `terrain_swing`. Scope tiers: **T0** screen-only (free) ·
**T1** flag-envs on the 306 sensitive monsters (~15 min, recommended) · **T2** add map-envs
(spawn-confounded). Run: `python -m ravel.calib environments` (`--all` / `--targets` / `--maps`).

**T1 landed (597 env ratings).** *Critical fix:* the env delta needs a **matched open baseline
measured with the identical short config** — diffing against the full-config DB `adjusted_cr`
(which includes the 6-body horde comp) inflated every env by ~+1 CR (Beholder read a spurious
+8.1 in wind). With `env_cr − open_matched`, the distributions are clean and interpretable:
- **windy** (mean −0.08): grounds flyer/kiters — Cambion −3.4, Erinyes −3.4, Manticore −2.2;
  non-flyers ≈ 0.
- **underwater** (mean +0.52): aquatic specialists soar — Kraken **+7.1**, Aboleth +3.7.
- **fog** (mean +1.13): special-senses monsters exploit blinded foes — dragons/Lich (blindsight/
  truesight) +3–5. Positive by design (fog is only tested where senses see through it).

Same lesson as the LLM baseline: **any centered-short-ladder measurement must be diffed against
a same-config baseline**, never the full-config number.

## 5. Controllers — the skill-ceiling delta

- **Heuristic** (deterministic, fast): full coverage; the canonical number.
- **LLM** (gemma4:12b, one call/decision): a **broad pass** (per the user's call), made
  tractable by (a) reusing the heuristic's `B*` so the LLM only samples 2–3 budgets around
  it, (b) fewer paired seeds with McNemar significance, (c) incremental checkpointing so it
  resumes and can run in the background, (d) multiple Ollama workers if hardware allows.

Report `adjustedCR_heuristic`, `adjustedCR_llm`, and **Δ = skill ceiling** — how much more a
monster is worth when played well. Large Δ = content the heuristic underplays.

**Results (`python -m ravel.calib llm` → `data/calibration/llm_delta.csv`, gemma4:12b, 23
stratified monsters).** Δ is structured, not a blanket lift: the largest gains are monsters
whose power is gated behind a **timing-sensitive nova/control burst** the greedy heuristic
wastes — Vrock +3.41 (Stunning Screech), Spirit Naga +2.15, Young Red Dragon +2.01 (breath),
Archmage +1.91, Beholder +1.58 (→ nominal 13), Mind Flayer +1.20. Several go **negative**
(Erinyes −0.83, Drow Priestess −0.81, Adult Brass −0.34, Priest −0.34) — support/hybrid
casters the model plays *worse* than the tuned heuristic, proving the pass measures play
quality rather than inflating everything.

**Baseline offset — fixed (matched baseline + more seeds).** The first pass had a spurious
+0.38 brute-baseline offset from (a) a measurement asymmetry — the LLM's short centered ladder
vs the heuristic's full adaptive one — and (b) 2-seed noise. Fix: `llm` now measures the
**heuristic through the identical centered ladder + seeds** (matched baseline; `--rebaseline`
re-derives it from cached results without Ollama), so Δ isolates controller skill. Re-run at
seeds=4: **baselines mean −0.24** (Owlbear/Bugbear 0.00, Ogre −0.09; Hill Giant −0.88 is
residual noise), the Beholder outlier collapsed (−5.83 → −0.32), and exact-zero Δs fell from 6
to 2. Tightened table: Archmage **+3.27** (LLM 15.4, above nominal 12), Drow Mage +2.60, Vrock
+2.15, Djinni +1.82; support-casters negative (Erinyes −2.83). `skill_ceiling_delta` in the
store now holds these matched values (`needs_good_play` in `encounter_view`).

**Takeaway.** The caster over-rating decomposes into a *recoverable* skill-ceiling part (the
heuristic under-sequences spells) plus a *genuine* combat-vs-utility part — even LLM-played,
casters stay below nominal (Mage 5.58 < 6, Archmage 10.53 < 12, Spirit Naga 6.83 < 8).

## 6. Confounds and controls

| Confound | Control |
|---|---|
| Initiative / seed / HP-roll luck | average over N seeds; paired seeds across controllers/positions; report rolled- and avg-HP |
| Positioning / range | fixed start configs (adjacent, default ~35 ft, long) averaged, and exposed per-config |
| Terrain | canonical on open arena; environment suite (§4) as its own axis |
| Last-standing win rewards nova/alpha | documented scope bias (CR is per-encounter, so mostly fine); optional resource-capped variant later |
| Round-cap draws | scored 0.5 so score→logit is defined |
| Bench mis-CR | fixed-point anchoring (§2.2) |

## 7. Factor model — the empirical CR formula

With residuals `r = adjustedCR − nominalCR` across the roster, fit an interpretable model
`r ~ features` (engineered from `MonsterDef`): action economy (multiattack count, legendary
actions, bonus attacks), mobility/reach (ranged, fly, speed, teleport, flyby, pounce),
defense (# resistances/immunities/vulnerabilities, resist-nonmagical-physical, regen,
legendary resistance, magic resistance, effective HP), offense-vs-baseline (DPR / expected
DPR-for-CR, save DC & to-hit vs expected), control (save-or-suck riders, AoE, frightful
presence), advantage engines (pack tactics × group-size, reckless, elven accuracy), and
**environment interactions** (has_swim × aquatic, fly × open-sky, blindsight × obscured).
Regularized linear (readable coefficients) **and** gradient-boosted trees (interactions),
cross-validated. `ravel/calib.py factors` (`ravel/factor_model.py`, numpy/pandas/sklearn)
fits the residual `refined_cr − nominal_cr`, writes `predicted_cr` to the store, and pickles
the model (`cr_model.pkl`) for **no-simulation prediction** of a new monster.

**Result — two numbers, both honest:**
- **Predicting a monster's playtested CR from its stat block: corr 0.961, MAE 0.79 CR.** The
  no-sim predictor calls Helmed Horror underrated (pred 8.4 vs nominal 4), Archmage and Iron
  Golem overrated — from features alone. Good enough to pre-screen a homebrew monster.
- **Explaining the CR *error* (the residual): R² ≈ 0.30.** Only ~⅓ of CR mis-estimation is a
  function of stat-block features; the other ~⅔ is matchup/relational/controller-play — i.e.
  **not reducible to a formula**, which is the whole thesis (CR effectiveness is
  multidimensional, §1).

**The empirical CR-correction formula (Ridge, CR≤13, holding CR fixed):** the dominant
systematic term is that higher-CR monsters are increasingly overrated (action economy scales
with CR). Beyond that, what makes a monster *underrated*: DPR (+0.05/pt), HP (+0.01/pt), AC
(+0.12/pt), resist-nonmagical-physical (+1.2), flight (+0.6), hard-CC control (+0.45/condition).
What makes it *overrated*: AoE/breath padding (−0.7/area) and frightful presence (−2.0) — CR
banked in effects that last-team-standing doesn't reward. (Casters carry no explicit negative
coefficient — their weakness is already captured by low DPR/HP.) Feature engineering:
`factor_model.features()`; `predicted_cr`/`model_residual` columns in the store.

## 7a. Findings on bench composition (measured)

The residual `r = adjusted − nominal` was regressed on monster features to find bench
artifacts. Two signals, handled differently:

- **`resist_nonmagical_physical` (bench artifact — mitigated).** An all-martial bench deals
  *nonmagical* B/P/S, which these monsters halve, inflating them. Fix applied: the bench now
  includes casters (Acolyte/Priest/Mage → radiant/fire/force) **and `compose_squad` rotates
  through same-tier pieces so squads mix damage types** (just adding casters did nothing —
  homogeneous squads with equal-XP tie-breaks never picked them). This cut the bias from a
  **+0.65 to a +0.49** CR gap (e.g. Fire Elemental 7.69 → 5.79). The residual +0.49 is largely
  *real* — resistant bruisers (Earth Elemental, Vampire Spawn) genuinely outfight a vanilla
  CR-5 brute.
- **`caster` (real signal, not an artifact — −1.11 CR).** Casters rate ~1 CR low and adding
  magical damage to the bench did **not** change it, because it isn't a damage-type problem:
  squishy single-target casters fold to action economy, and their CR is paid for by
  control/utility/battlefield-shaping that "last team standing" doesn't reward. This is a
  genuine property of measuring *raw combat effectiveness* — and the prime motivation for the
  **LLM skill-ceiling pass** (§5): the heuristic likely underplays casters, so their adjusted
  CR should rise under a better controller. Report caster CR as "combat-only, controller-
  sensitive."
- **High-CR anchors stop at Storm Giant (CR 13).** Monsters at CR 14–30 clamp (`right`) until
  clean higher anchors are added to bench + calibrators.
- **Arena horde cap (10 bodies).** Very-high-XP "many-weak" compositions under-spend the
  budget (can't place 30 goblins), so the many-weak end is approximate for high-CR targets.
- **Last-standing win condition** rewards nova/alpha and ignores adventuring-day attrition
  (documented scope bias; CR is per-encounter so mostly fine).

## 8. Outputs — the ratings store (source of truth)

The nuance (per-composition sensitivity, skill-ceiling Δ, synergy, CIs) is lost by a flat
CSV, so the rating scripts write into a **SQLite store** (`data/calibration/ratings.db`,
`ravel/ratings_store.py`, stdlib) as their *primary* output — not a post-hoc export. CSV/JSON
are derived views. This is deliberately built for the future encounter-building UI to query.

- **`runs`** — provenance per run (kind, bench, seeds, ladder, compositions, calibration
  points, label, timestamp).
- **`ratings`** — one row per monster: `nominal_cr/xp`, `adjusted_cr/xp`, `raw_cr`,
  `ci_lo/hi`, `flag`, `residual`, `per_composition` (json 1b/3b/6b), `composition_spread`,
  `group_synergy`, `environment`, and the nullable LLM fields `adjusted_cr_llm`,
  `skill_ceiling_delta`, `llm_flag`. `rate-all` upserts the heuristic columns; `llm` upserts
  the LLM columns into the same row (each controller writes its own fields).
- **`encounter_view`** — what the UI reads: `best_cr` (LLM if present else heuristic),
  `adjusted_xp` for budgeting, and three advisory signals renamed for the UI:
  `action_economy_sensitivity` (swingy vs few/many — `composition_spread`),
  `needs_good_play` (`skill_ceiling_delta`), `wants_friends` (`group_synergy`).

Query it the way an encounter builder would: `python -m ravel.calib query --near 8`
(monsters whose best effective CR ≈ 8), `--swingy`, `--needs-play`, or `--export out.csv`.

**UI direction (when built):** the encounter builder budgets with `adjusted_xp` (playtested,
not book), shows the CI as an uncertainty band, and surfaces the three signals as badges —
"swingy vs numbers", "rewards good play (+N under an LLM)", "wants a pack". Everything traces
back to a `runs` row for reproducibility.

## 9. The two skills

- **`cr-benchmark`** — *establish the yardstick.* From a set of monsters, fit the calibration
  curve g and write `data/calibration/calibration.json`, with validation (monotone curve;
  same-CR mirrors ≈ 50%; anchors reproduce their own CR). Run this first, and whenever the
  bench changes.
- **`cr-rate`** — *rate a new, unrated monster.* Load `calibration.json`, run the fair-XP
  mirror for the target, and report its adjusted CR ± CI, raw CR, solo/grouped synergy (with
  ablation), and per-environment breakdown.

Both support a **small-scale mode** (few calibrators, few seeds, short ladder) for validation
before the full-roster run.

## 10. Phasing

1. **Harness** (`ravel/calib.py`): CR↔XP, bench, mirror, calibration fit, rate, group-size +
   ablation synergy, JSON emit, `python -m ravel.calib` CLI. ✅ *landed & validated.*
2. **Full-roster heuristic table.** Bench extended through CR 13; `rate-all` fits the curve
   and rates every monster ≤ cap in parallel (multiprocessing), writing
   `data/calibration/adjusted_cr.{csv,json}` + most over/under-rated lists. ✅ *landed.*
   Remaining in this phase: extend calibrators above CR 13 (clean high-CR anchors) so the
   ~40 monsters at CR 14–30 stop clamping (`right` flag); archetype + environment sweeps;
   bench fixed-point (§2.2).
3. **Bradley–Terry cross-check** (`ravel/calib.py bt`, `bradley_terry.py`). ✅ *landed —
   corr 0.961 with the mirror; §3.* Writes `bt_cr`/`refined_cr`/`bt_disagreement`.
4. **Broad LLM pass → skill-ceiling Δ** (`ravel/calib.py llm`, checkpointed to
   `llm_delta.csv`). ✅ *landed — 23 stratified monsters; §5 for results.* Remaining: more
   seeds + a matched heuristic baseline to remove the ~+0.3 control offset; widen the set.
5. **Factor model → empirical CR formula** (`ravel/calib.py factors`, `factor_model.py`).
   ✅ *landed — CR prediction corr 0.961/MAE 0.79; residual R²~0.30; §7.* Writes
   `predicted_cr`, pickles `cr_model.pkl` for no-sim prediction.

### Commands
```
python -m ravel.calib smoke                 # tiny end-to-end self-test
python -m ravel.calib bench                 # fit calibration.json from bench.json
python -m ravel.calib rate "Wolf" --group 4 --ablate   # one monster + synergy
python -m ravel.calib rate-all --cap 13     # full roster -> adjusted_cr.{csv,json}
python -m ravel.calib llm --seeds 2         # LLM skill-ceiling Δ -> llm_delta.csv
python -m ravel.calib bt --k 16 --seeds 9   # Bradley-Terry cross-check -> bt_cr/refined_cr
python -m ravel.calib factors --max-cr 13   # empirical CR formula -> predicted_cr, cr_model.pkl
```
