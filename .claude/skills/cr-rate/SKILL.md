---
name: cr-rate
description: Rate a monster's real combat effectiveness as an adjusted-CR float by playtesting it against equal-XP squads, using the calibration yardstick from the cr-benchmark skill. One command runs the whole pipeline (mirror adjusted CR + CI, per-composition sensitivity, group synergy, flag-environment sensitivity, Bradley-Terry consensus, factor-model prediction, optional LLM skill ceiling) and stores it in ratings.db. Use to evaluate whether a monster's book CR matches how it actually fights, or to rate a new/homebrew stat block.
---

# CR Rate — the full ranking pipeline for a monster (new or existing)

Rates a monster's **real** combat effectiveness against the calibrated yardstick and stores
the complete profile in `data/calibration/ratings.db`. Works incrementally — a new monster
reuses the existing calibration curve and Bradley-Terry cache, **no full recalibration**.
Method + all axes: `docs/CR_CALIBRATION.md`. Needs `calibration.json` (from **cr-benchmark**).

## Rate a NEW monster (the main workflow)
1. **Add the stat block** as one JSON file under `data/monsters/` (schema:
   `ravel/statblock.py`; copy any file in `data/monsters/mm/` as a template). It loads
   automatically — no code change.
2. **Instant screen (optional, no battles):**
   `python -m ravel.calib rate "<Monster>" --fast`
   → factor-model predicted CR from the stat block. corr 0.96 / MAE ~0.8 vs the full playtest;
   good for a first look, but it can miss rare stat combos (it under-called a tanky+resistant
   homebrew CR 4 as 4.5 when the playtest found ~8.5) — so it's a screen, not the answer.
3. **Full playtest (authoritative):**
   `python -m ravel.calib rate-new "<Monster>"`
   Runs and stores, in one shot: mirror adjusted CR (+ 90% CI, per-composition vector, flag),
   factor prediction, group synergy (if pack/leadership/low-CR), flag-environment sensitivity
   (underwater/windy/fog, if relevant), and Bradley-Terry (incremental) → `refined_cr`
   consensus. Add `--llm` for the (slow) skill-ceiling delta. Skips: `--no-bt`, `--no-env`,
   `--no-synergy`. Multiple at once: `rate-new "Name A;Name B"`.
4. **Read it back** from the store: `python -m ravel.calib query --near <CR>` (encounter view),
   or query `ratings.db` directly.

## Rate an EXISTING monster (single axis, ad-hoc)
`python -m ravel.calib rate "<Monster>"` — mirror adjusted CR + CI + per-composition, plus:
- `--group k` → pack of k, reports **synergy** (grouped − solo); add `--ablate` to isolate the
  pack-tactics trait from generic action economy (Lanchester).
- `--dispersion` → few-strong vs many-weak adjusted CR (action-economy sensitivity).
- `--env <name>` → a flag environment (`underwater` / `windy` / `fog`; open by default).
- `--fast` → the no-sim factor estimate; `--json` → full record.

## Reading the numbers
- **adjusted CR** — headline, anchored to the calibrators, with a bootstrap **90% CI**.
- **flag** — `ok` = bracketed tie-point; `left`/`right` = the adaptive ladder couldn't bracket
  it (upper / lower bound — very over/under-costed monster).
- **refined_cr** — mirror + Bradley-Terry consensus (the best single number).
- **per-composition** — CR vs 1/3/6-body squads; a big spread = action-economy-swingy.
- **group synergy** — grouped − solo; "wants friends" (pack/horde value).
- **environment deltas** — `windy` grounds flyers, `underwater` favors aquatic, `fog` favors
  special senses; `native_env` + `terrain_swing` summarize.
- **skill_ceiling_delta** (with `--llm`) — how much more the monster is worth played by the
  LLM; big + means the heuristic underplays it (casters, nova/breath monsters).

## Interpreting deviations
- **adjusted ≫ nominal**: action economy (multiattack/legendary), tough defenses
  (resist-nonmagical-physical, high HP/AC, regen), or control that neutralizes a squad.
- **adjusted ≪ nominal**: squishy single-target monsters that get focus-fired, or CR banked in
  utility/control that "last team standing" doesn't reward (casters) — check the LLM delta.

## Notes
- Heuristic controller by default (fast, deterministic). Engine stays pure/stdlib; this is the
  outer analysis layer.
- When to re-run **cr-benchmark** instead: only if you change the bench/calibrators. Adding
  monsters does **not** need it — `rate-new` is incremental.
