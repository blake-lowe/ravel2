---
name: cr-benchmark
description: Establish the CR-calibration yardstick from a set of monsters — run the fair-XP mirror on trusted "calibrator" monsters and fit the curve that maps a mirror tie-point to an adjusted CR. Produces data/calibration/calibration.json, which the cr-rate skill consumes. Use when setting up or refreshing the benchmark, changing the reference bench, or before a full-roster calibration run.
---

# CR Benchmark — build the calibration yardstick

Fits the empirical CR calibration by playtesting a set of trusted monsters against
equal-XP squads. Full method: `docs/CR_CALIBRATION.md`. This is the **first** of two
skills; `cr-rate` rates new monsters against the yardstick this one produces.

## Concept (one paragraph)
A solo monster is fought against reference squads composed to a ladder of XP budgets; the
budget where it wins 50% is its tie-point `B*`. Because a solo creature vs an equal-XP
*group* is not automatically 50/50 (5e's own encounter-multiplier bias), we do **not**
hand-correct it — we fit a monotone curve `g: B* → CR` through **calibrators** (monsters
whose book CR is trusted, no pack/synergy tricks). That curve bakes the bias in and cancels
it, so later a monster is "underrated" only if it beats squads a trusted peer of its CR
could not.

## Inputs
- A **bench spec** JSON (default `data/calibration/bench.json`):
  - `bench`: pool used to compose opposing squads — plain monsters spanning a range of XP
    denominations (include small pieces like Guard/Commoner/Giant Rat for low-CR resolution).
  - `calibrators`: trusted-CR monsters to fit `g`; **exclude** pack-tactics/Leadership/
    synergy monsters so the baseline is clean.
  - `config`: `ai` (default `heuristic`), `seed_base`, `seeds` (count), `ladder` (budget
    multipliers), `max_squad`, `roll_hp`, `environments` (map flags; `null` = open arena,
    and the in-work `aquatic` flag once available).

## Steps
1. From repo root (`X:\Programs\Ravel2`), confirm the bench/calibrator monsters exist:
   `python -m ravel.cli list` (names match case-insensitively).
2. **Small-scale first.** Sanity-run the tiny built-in end-to-end before any big run:
   `python -m ravel.calib smoke`
   Expect a printed calibration table, a Wolf rating with a positive group synergy, and
   `smoke OK`.
3. Fit the real curve from the bench spec:
   `python -m ravel.calib bench` (add `--spec <path>` / `--out <path>` to override).
   Writes `data/calibration/calibration.json`.
4. **Validate the output** and report:
   - **Monotonicity:** `B*` should rise with calibrator CR (the curve is isotonic-clamped,
     but non-monotone raw `B*` means noise — add seeds).
   - **Self-residuals ≈ 0:** each calibrator's fitted CR should reproduce its nominal CR.
   - **Flags:** `left`/`right` on the lowest/highest calibrators mean the ladder or bench
     couldn't bracket their tie-point — widen the `ladder` or add smaller/larger bench pieces
     (the starter bench bottoms out below ~25 XP; add Commoner/Giant Rat for CR ⅛–¼ work).
5. Summarize for the user: the calibration table, which calibrators reproduced cleanly, any
   flagged ends, and the path written.

## The full ranking pipeline (once the curve is fit)
The bench (`data/calibration/bench.json`) ships calibrated CR 0–30. From the fitted curve:

1. **Whole-roster table:** `python -m ravel.calib rate-all --cap 30`
   Re-fits the curve (parallel), rates every monster ≤ `--cap`, stores full records in
   `ratings.db`, exports `adjusted_cr.csv`, prints most over/under-rated. `--sample N` for a
   quick check.
2. **Bradley-Terry cross-check:** `python -m ravel.calib bt --k 16 --seeds 9`
   → `bt_cr` / `refined_cr` (consensus) / `bt_disagreement`. Caches pairs to `bt_pairs.csv`.
3. **Group synergy:** `python -m ravel.calib synergy` → `group_synergy` ("wants friends").
4. **Flag-environments:** `python -m ravel.calib environments` → per-env deltas +
   `native_env` / `env_sensitivity` (underwater/windy/fog only; map-envs are spawn-confounded).
5. **Empirical CR formula:** `python -m ravel.calib factors` → `predicted_cr` + `cr_model.pkl`
   (for `rate --fast` no-sim estimates).
6. **LLM skill ceiling (slow):** `python -m ravel.calib llm --seeds 4` → `skill_ceiling_delta`.

**Adding monsters later does NOT need any of this** — use the **cr-rate** skill's
`rate-new "<Name>"`, which runs the whole pipeline for just the new monster(s) incrementally
(reuses this curve + the BT cache). Rebuild the curve here only when you change the
bench/calibrators themselves.

## Scaling to the full effort
- Keep `ai: heuristic` for calibration (deterministic, fast). The LLM broad pass is a
  separate skill-ceiling layer, not the yardstick.
- Bump `seeds` (e.g. 8→30) and widen the `ladder` for the committed run; consider a bench
  **fixed-point** pass (re-derive bench XP from a first calibration, re-fit) per
  `docs/CR_CALIBRATION.md §2.2`.
- More calibrators across more CRs = a finer curve. Add small-XP bench pieces before rating
  anything below CR 1.

## Notes
- Outer analysis layer — it only consumes `ravel.sim.run_battle`; the engine core stays pure
  and deterministic (same seeds → identical battles).
- This is tooling, not a SPEC slice; it does not affect ROADMAP slice ordering.
