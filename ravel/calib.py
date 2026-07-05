"""Fair-XP-mirror CR calibration — derive an empirical 'adjusted CR' from playtesting.

Outer analysis layer: it *consumes* the pure engine (`ravel.sim.run_battle`) and adds
no randomness/IO to the engine core. Method + rationale: docs/CR_CALIBRATION.md.

CLI:
  python -m ravel.calib smoke                       # tiny end-to-end self-test
  python -m ravel.calib bench                        # fit calibration.json from bench.json
  python -m ravel.calib rate "Wolf" --group 4 --ablate
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import replace
from pathlib import Path

from . import content
from .sim import run_battle

CALIB_DIR = Path(__file__).resolve().parent.parent / "data" / "calibration"

# --- Official 5e CR -> XP, interpolated in log-XP for a continuous inverse ----
XP_BY_CR = {
    0: 10, 0.125: 25, 0.25: 50, 0.5: 100, 1: 200, 2: 450, 3: 700, 4: 1100,
    5: 1800, 6: 2300, 7: 2900, 8: 3900, 9: 5000, 10: 5900, 11: 7200, 12: 8400,
    13: 10000, 14: 11500, 15: 13000, 16: 15000, 17: 18000, 18: 20000,
    19: 22000, 20: 25000, 21: 33000, 22: 41000, 23: 50000, 24: 62000,
    25: 75000, 26: 90000, 27: 105000, 28: 120000, 29: 135000, 30: 155000,
}
_CRS = sorted(XP_BY_CR)
_XPS = [XP_BY_CR[c] for c in _CRS]
_LOGXPS = [math.log(x) for x in _XPS]


def _interp(x: float, xs: list[float], ys: list[float]) -> float:
    """Piecewise-linear interpolation with flat clamping outside [xs[0], xs[-1]]."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    return ys[-1]


def cr_to_xp(cr: float) -> float:
    return math.exp(_interp(cr, _CRS, _LOGXPS))


def xp_to_cr(xp: float) -> float:
    return _interp(math.log(max(xp, 1e-9)), _LOGXPS, _CRS)


# --- Squad composition -------------------------------------------------------
def _bench_xp(names: list[str]) -> list[tuple[str, float]]:
    """(name, nominal xp) for bench monsters, sorted by XP descending."""
    pairs = [(n, cr_to_xp(content.get(n).cr)) for n in names]
    return sorted(pairs, key=lambda t: -t[1])


def compose_squad(budget: float, bench_xp: list[tuple[str, float]],
                  bodies: int, hard_cap: int = 10) -> tuple[list[str], float]:
    """Compose ~`bodies` opponents summing to ~`budget` XP. `bodies` parameterizes the
    action-economy axis: 1-2 = a few strong peers, 6-10 = a weaker horde for the same XP.

    Pieces are drawn by ROTATING through the same-tier band around budget/bodies, so a
    squad mixes damage types (martial brutes + casters) instead of stacking one piece —
    otherwise a resist-nonmagical monster never faces the magical damage that should test
    it. `hard_cap` bounds squad size to what the arena can place. Returns (squad, XP)."""
    ideal = budget / max(1, bodies)
    affordable = [(n, xp) for n, xp in bench_xp if xp <= budget * 1.15]
    if not affordable:
        n, xp = min(bench_xp, key=lambda t: t[1])
        return [n], xp
    affordable.sort(key=lambda t: abs(t[1] - ideal))
    band = [t for t in affordable if 0.5 * ideal <= t[1] <= 1.8 * ideal] or [affordable[0]]
    squad: list[str] = []
    total = 0.0
    i = 0
    while len(squad) < hard_cap:
        name, xp = band[i % len(band)]
        i += 1
        if total + xp > budget * 1.10 or (budget - total) < xp * 0.5:
            fits = [t for t in band if total + t[1] <= budget * 1.10
                    and (budget - total) >= t[1] * 0.5]
            if not fits or len(squad) >= bodies + 2:
                break
            name, xp = fits[0]
        squad.append(name)
        total += xp
    if not squad:
        name, xp = band[0]
        squad, total = [name], xp
    return squad, total


# --- The mirror --------------------------------------------------------------
# Environment registry: an env NAME -> run_battle kwargs. The engine already models these
# (underwater rules, wind grounding flyers, fog obscurement, terrain maps). Unknown strings
# are treated as a raw map name for back-compat.
ENV_SPECS = {
    None: {}, "open": {},
    "underwater": {"underwater": True},           # aquatic: non-swimmers slog, air-breathers drown
    "windy": {"weather": "wind"},                 # grounds nonmagical flyers, douses fire
    "fog": {"weather": "fog"},                     # heavy obscurement -> special senses shine
    "dungeon": {"map_name": "dark_dungeon"},      # confined, no kiting room
    "lava": {"map_name": "lava_cavern"},          # fire terrain
    "chasm": {"map_name": "chasm_bridge"},        # verticality, shove-into-gap
}


FLAG_ENVS = {"underwater", "windy", "fog"}    # clean: open arena + spawns, only rules change
MAP_ENVS = {"dungeon", "lava", "chasm"}        # spawn-confounded (fixed spawn points)


def _env_kwargs(env) -> dict:
    return dict(ENV_SPECS[env]) if env in ENV_SPECS else {"map_name": env}


def _special_senses(md) -> bool:
    return any(k in (md.senses or {}) for k in ("blindsight", "tremorsense", "truesight"))


def native_env(md) -> str:
    """A monster's home turf, inferred from its movement (poor ground speed + swim/fly/burrow
    => that's where it belongs)."""
    if md.swim > 0 and md.speed <= 15:
        return "underwater"
    if md.fly > 0 and md.speed <= 15:
        return "aerial"          # ~ open arena with verticality; its adverse env is 'windy'
    if md.burrow > 0 and md.speed <= 20:
        return "subterranean"
    return "terrestrial"


def env_relevance(md) -> list:
    """Non-open environments whose rules could plausibly change this monster's effectiveness —
    the ONLY ones worth playtesting for it (effort control: skip the rest)."""
    envs = []
    if md.swim > 0 or md.mtype in ("beast", "monstrosity") and md.swim > 0:
        envs.append("underwater")
    if md.fly > 0:
        envs.append("windy")     # wind grounds nonmagical flyers -> negates the kite
    if _special_senses(md):
        envs.append("fog")       # obscurement: special senses keep working while others blind
    if "fire" in md.immunities or "fire" in md.resistances:
        envs.append("lava")
    if md.fly > 0 or any(a.kind != "melee" for a in md.attacks.values()):
        envs.append("dungeon")   # confined space negates kiting/ranged
    return envs


def env_sensitive(md) -> bool:
    return bool(env_relevance(md))


def _outcomes(target: str, squad: list[str], seeds: list[int], ai: str,
              env, roll_hp: bool, group: int) -> list[float]:
    """Per-seed score for the target team (win=1, draw=0.5, loss=0), in environment `env`."""
    team_a = [target] * group
    kw = _env_kwargs(env)
    out = []
    for s in seeds:
        res = run_battle(team_a, squad, seed=s, ai=ai, roll_hp=roll_hp, **kw)
        out.append(1.0 if res.winner == "A" else 0.5 if res.winner is None else 0.0)
    return out


def _logit(p: float) -> float:
    p = min(max(p, 0.02), 0.98)
    return math.log(p / (1.0 - p))


def _solve_crossing(points: list[dict]) -> tuple[float, str]:
    """Find the budget where score crosses 0.5, via linear interp of logit(score)
    over log(budget). flag: 'ok' | 'right' (still winning at top) | 'left'."""
    pts = sorted(points, key=lambda d: d["xp"])
    xs = [math.log(d["xp"]) for d in pts]
    ys = [_logit(d["p"]) for d in pts]
    for i in range(len(xs) - 1):
        y0, y1 = ys[i], ys[i + 1]
        if (y0 >= 0 >= y1) or (y0 <= 0 <= y1):
            if y0 == y1:
                return math.exp(xs[i]), "ok"
            t = (0.0 - y0) / (y1 - y0)
            return math.exp(xs[i] + t * (xs[i + 1] - xs[i])), "ok"
    if ys[-1] > 0:
        return math.exp(xs[-1]), "right"   # underrated beyond the ladder (lower bound)
    return math.exp(xs[0]), "left"         # overrated below the ladder (upper bound)


def tie_budget(target: str, cfg: dict, bench_xp, group: int = 1,
               env=None, comps=None, center_cr=None) -> dict:
    """Run the mirror ladder for `target` and return the tie budget B* plus points.

    At each budget the target is fought against the squad compositions in `comps` (body
    counts; outcomes pooled across them). The ladder is **adaptive**: if the target wins
    (or loses) across the whole configured ladder, extra rungs are added below/above until
    the 0.5 crossing is bracketed, so B* is a real tie-point rather than a clamped bound.
    A residual left/right flag means even the extended ladder couldn't bracket it."""
    seeds = [cfg["seed_base"] + i for i in range(cfg["seeds"])]
    comps = comps if comps is not None else cfg.get("compositions", [1, 3, 6])
    cap = cfg.get("max_squad", 10)
    # center the ladder on center_cr when given (LLM pass centers on the heuristic tie so
    # the model only has to detect the shift), else on the monster's nominal CR
    nom = cr_to_xp(center_cr if center_cr is not None else content.get(target).cr) * group

    def eval_mult(m):
        budget = nom * m
        outcomes, achs = [], []
        for bodies in comps:
            squad, ach = compose_squad(budget, bench_xp, bodies, cap)
            outcomes.extend(_outcomes(target, squad, seeds, cfg["ai"], env,
                                      cfg["roll_hp"], group))
            achs.append(ach)
        return {"mult": m, "xp": sum(achs) / len(achs),
                "p": sum(outcomes) / len(outcomes), "outcomes": outcomes}

    mults = list(cfg["ladder"])
    points = [eval_mult(m) for m in mults]
    bstar, flag = _solve_crossing(points)
    tries = 0
    while flag != "ok" and tries < 6:
        if flag == "left":                       # too weak — probe smaller opponents
            m = min(mults) / 2.0
            if m < 0.03:
                break
        else:                                    # 'right' — too strong — probe bigger
            m = max(mults) * 2.0
            if m > 48:
                break
        mults.append(m)
        points.append(eval_mult(m))
        bstar, flag = _solve_crossing(points)
        tries += 1
    return {"target": target, "group": group, "bstar": bstar, "flag": flag,
            "points": points}


# --- Calibration curve g: B* -> CR ------------------------------------------
def make_g(cal_points: list[list[float]]):
    """Monotone piecewise-linear map from tie-budget to CR (isotonic via cummax)."""
    pts = sorted(cal_points, key=lambda p: p[0])
    xs = [math.log(b) for b, _ in pts]
    ys = [cr for _, cr in pts]
    for i in range(1, len(ys)):
        ys[i] = max(ys[i], ys[i - 1])
    return lambda B: _interp(math.log(max(B, 1e-9)), xs, ys)


def _bootstrap_cr(points: list[dict], g, group: int, nboot: int = 200) -> tuple:
    """10th/90th percentile adjusted CR by resampling seeds (no re-simulation).
    Deterministic: a fixed LCG keyed off the observed data, no `random`/time."""
    state = 2463534242
    def rnd(n):
        nonlocal state
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        return state % n
    crs = []
    for _ in range(nboot):
        pts = []
        for d in points:
            oc = d["outcomes"]
            samp = [oc[rnd(len(oc))] for _ in oc]
            pts.append({"xp": d["xp"], "p": sum(samp) / len(samp)})
        b, _flag = _solve_crossing(pts)
        crs.append(g(b / group))
    crs.sort()
    lo = crs[int(0.10 * (len(crs) - 1))]
    hi = crs[int(0.90 * (len(crs) - 1))]
    return round(lo, 2), round(hi, 2)


# --- Ablation (group-synergy isolation) -------------------------------------
_ABLATE_FLAGS = dict(pack_tactics=False, leadership=False, reckless=False)


def register_ablated(name: str) -> str:
    """Register an in-memory clone of `name` with group-synergy flags off, same body.
    Returns the clone's lookup name. Diffing rated(clone) vs rated(orig) isolates
    trait synergy from generic action economy."""
    md = content.get(name)
    clone = replace(md, name=f"{md.name} (ablated)", **_ABLATE_FLAGS)
    content._M[clone.name.lower()] = clone
    return clone.name


# --- Top-level operations ----------------------------------------------------
def load_bench(path: Path = None) -> dict:
    path = path or (CALIB_DIR / "bench.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _geomean(xs) -> float:
    return math.exp(sum(math.log(max(x, 1e-9)) for x in xs) / len(xs))


def calibrator_points(name: str, cfg: dict, bench_xp) -> tuple:
    """A calibrator's per-composition tie budgets. Returns (cr, [(B*_c, c, flag), ...])."""
    cr = content.get(name).cr
    pts = []
    for c in cfg.get("compositions", [1, 3, 6]):
        tb = tie_budget(name, cfg, bench_xp, comps=[c])
        pts.append((tb["bstar"], c, tb["flag"]))
    return cr, pts


def cal_points_from_tied(tied) -> list:
    """One (geomean tie budget, CR) point per calibrator — the single canonical curve.
    Averaging in log-budget keeps a monster's absolute strength on ONE scale, so applying
    the curve to each composition's own B* gives absolute action-economy sensitivity."""
    return [[_geomean([b for b, _, _ in pts]), cr] for _, cr, pts in tied]


def _rows_from_tied(tied, g) -> list:
    """(name, cr, geomean B*, fitted CR, flags) display rows."""
    rows = []
    for name, cr, pts in tied:
        gb = _geomean([b for b, _, _ in pts])
        flags = "/".join(sorted({f for _, _, f in pts}))
        rows.append((name, cr, gb, round(g(gb), 2), flags))
    return rows


def fit_calibration(spec: dict) -> dict:
    cfg = spec["config"]
    bench_xp = _bench_xp(spec["bench"])
    tied = [(name, *calibrator_points(name, cfg, bench_xp)) for name in spec["calibrators"]]
    cal_points = cal_points_from_tied(tied)
    g = make_g(cal_points)
    rows = _rows_from_tied(tied, g)
    resid = [round(fit - cr, 2) for _, cr, _b, fit, _f in rows]
    return {"cal_points": cal_points, "config": cfg, "bench": spec["bench"],
            "rows": rows, "self_residuals": resid}


def rate(target: str, calib: dict, group: int = 1, ablate: bool = False,
         environments=None, dispersion: bool = False) -> dict:
    cfg = calib["config"]
    bench_xp = _bench_xp(calib["bench"])
    g = make_g(calib["cal_points"])          # single canonical curve (absolute strength)
    envs = environments if environments is not None else cfg.get("environments", [None])

    def _rate_one(name, grp, env, comps=None):
        # Solve each composition's tie-point separately (avoids the pooled-XP distortion),
        # then apply the ONE canonical curve to each: g(B*_c) is that composition's
        # absolute CR-equivalent, so the few->many spread is real action-economy
        # sensitivity. Canonical = g(geomean B*) keeps calibrators self-consistent.
        comp_list = comps if comps is not None else cfg.get("compositions", [1, 3, 6])
        percaps, los, his, flags = {}, [], [], []
        for c in comp_list:
            tb = tie_budget(name, cfg, bench_xp, group=grp, env=env, comps=[c])
            percaps[c] = tb["bstar"] / grp
            lo, hi = _bootstrap_cr(tb["points"], g, grp)
            los.append(lo)
            his.append(hi)
            flags.append(tb["flag"])
        geo = _geomean(list(percaps.values()))
        return {"adjusted_cr": round(g(geo), 2), "raw_cr": round(xp_to_cr(geo), 2),
                "ci": [round(min(los), 2), round(max(his), 2)],
                "flag": "ok" if all(f == "ok" for f in flags) else "/".join(sorted(set(flags))),
                "per_composition": {c: round(g(p), 2) for c, p in percaps.items()}}

    name = register_ablated(target) if ablate else target
    result = {"target": target, "nominal_cr": content.get(target).cr,
              "ablated": ablate, "by_env": {}}
    for env in envs:
        result["by_env"][env or "open"] = _rate_one(name, 1, env)
    canon = result["by_env"][(envs[0] or "open")]
    result.update(adjusted_cr=canon["adjusted_cr"], raw_cr=canon["raw_cr"],
                  ci=canon["ci"], flag=canon["flag"],
                  per_composition=canon["per_composition"])
    if dispersion:
        pc = canon["per_composition"]
        cc = sorted(pc)
        result["composition"] = {
            "few_strong_cr": pc[cc[0]], "many_weak_cr": pc[cc[-1]],
            "spread": round(pc[cc[0]] - pc[cc[-1]], 2), "per_composition": pc}
    if group > 1:
        solo = _rate_one(name, 1, envs[0])
        grouped = _rate_one(name, group, envs[0])
        result["group"] = {"k": group, "solo_cr": solo["adjusted_cr"],
                           "grouped_cr": grouped["adjusted_cr"],
                           "synergy": round(grouped["adjusted_cr"] - solo["adjusted_cr"], 2)}
    return result


# --- CLI ---------------------------------------------------------------------
def _fmt_calibration(cal: dict) -> str:
    lines = ["Calibration curves per composition (calibrator -> avg tie budget -> fitted CR):",
             f"  {'monster':<14}{'CR':>5}{'avgB*':>9}{'fit':>7}{'flags':>10}"]
    for name, cr, b, fit, flag in cal["rows"]:
        lines.append(f"  {name:<14}{cr:>5}{b:>9.0f}{fit:>7.2f}{flag:>10}")
    lines.append(f"  self-residuals (fitted-nominal): {cal['self_residuals']}")
    return "\n".join(lines)


def _fmt_rating(r: dict) -> str:
    lines = [f"{r['target']}  (nominal CR {r['nominal_cr']})"
             f"{'  [ablated]' if r['ablated'] else ''}",
             f"  adjusted CR: {r['adjusted_cr']}  (90% CI {r['ci']}, "
             f"raw {r['raw_cr']}, flag={r['flag']})"]
    if len(r["by_env"]) > 1:
        lines.append("  by environment: " + ", ".join(
            f"{k}={v['adjusted_cr']}" for k, v in r["by_env"].items()))
    if "group" in r:
        gp = r["group"]
        lines.append(f"  group x{gp['k']}: solo {gp['solo_cr']} -> grouped "
                     f"{gp['grouped_cr']}  (synergy {gp['synergy']:+})")
    if r.get("per_composition"):
        lines.append("  per-composition CR (bodies->CR): " + ", ".join(
            f"{c}b={v}" for c, v in sorted(r["per_composition"].items())))
    if "composition" in r:
        cp = r["composition"]
        lines.append(f"  vs few-strong {cp['few_strong_cr']} / vs many-weak "
                     f"{cp['many_weak_cr']}  (action-economy spread {cp['spread']:+})")
    return "\n".join(lines)


def cmd_bench(args) -> None:
    spec = load_bench(Path(args.spec) if args.spec else None)
    cal = fit_calibration(spec)
    out = Path(args.out) if args.out else (CALIB_DIR / "calibration.json")
    out.write_text(json.dumps({k: cal[k] for k in ("cal_points", "config", "bench")},
                              indent=2) + "\n", encoding="utf-8")
    print(_fmt_calibration(cal))
    print(f"\nWrote {out}")


def cmd_rate(args) -> None:
    if args.fast:
        from . import factor_model as fm
        path = CALIB_DIR / "cr_model.pkl"
        if not path.exists():
            print("No model yet — run 'python -m ravel.calib factors' first.")
            return
        md = content.get(args.monster)
        pred = fm.predict(fm.load_model(path), md)
        arrow = "underrated" if pred > md.cr + 0.5 else ("overrated" if pred < md.cr - 0.5 else "~on par")
        print(f"{args.monster}  (nominal CR {md.cr})")
        print(f"  predicted CR: {pred}  [{arrow}; model estimate from stat block, no simulation]")
        return
    calib = json.loads((Path(args.calib) if args.calib else
                        (CALIB_DIR / "calibration.json")).read_text(encoding="utf-8"))
    r = rate(args.monster, calib, group=args.group, ablate=args.ablate,
             environments=([None] if args.env is None else [args.env]),
             dispersion=args.dispersion)
    print(_fmt_rating(r))
    if args.json:
        print("\n" + json.dumps(r, indent=2))


def _tie_worker(payload):
    """Parallel calibrator points (module-level so multiprocessing can pickle it)."""
    name, cfg, bench = payload
    cr, pts = calibrator_points(name, cfg, _bench_xp(bench))
    return (name, cr, pts)


def _rate_worker(payload):
    """Worker returns the full rate() record so the main process can persist all the
    nuance (per-composition vector, CI, ...) to the store — not a lossy flat row."""
    name, calib = payload
    try:
        return (name, rate(name, calib), None)
    except Exception as e:                                    # pragma: no cover
        return (name, None, f"ERR:{e}")


def cmd_rate_all(args) -> None:
    """Fit the calibration (parallel) then rate the whole roster (parallel), and write
    data/calibration/adjusted_cr.{csv,json} plus the most over/under-rated lists."""
    import csv
    import multiprocessing as mp

    spec = load_bench(Path(args.spec) if args.spec else None)
    cfg, bench = spec["config"], spec["bench"]
    workers = args.workers or min(8, mp.cpu_count() or 2)

    # Phase 1 — calibrate (parallel over calibrators), fit the single canonical curve
    with mp.Pool(workers) as pool:
        tied = pool.map(_tie_worker, [(n, cfg, bench) for n in spec["calibrators"]])
    cal_points = cal_points_from_tied(tied)
    g = make_g(cal_points)
    calib = {"cal_points": cal_points, "config": cfg, "bench": bench}
    (CALIB_DIR / "calibration.json").write_text(json.dumps(calib, indent=2) + "\n",
                                                encoding="utf-8")
    print("Calibrators (monster -> geomean tie budget -> fitted CR):")
    for name, cr, gb, fit, flags in _rows_from_tied(tied, g):
        print(f"  {name:<14}{cr:>5}{gb:>9.0f}{fit:>7.2f}{flags:>10}")

    # Phase 2 — rate every monster within the calibrated range (parallel)
    noncombat = {"spiritual weapon"}          # spell-effect entries, not real monsters
    names = [md.name for md in sorted(content._M.values(), key=lambda m: (m.cr, m.name))
             if md.cr <= args.cap and "(ablated)" not in md.name
             and md.name.lower() not in noncombat]
    if args.sample:
        step = max(1, len(names) // args.sample)
        names = names[::step][:args.sample]
    print(f"\nRating {len(names)} monsters (CR <= {args.cap}) on {workers} workers...")
    results = []
    with mp.Pool(workers) as pool:
        for i, res in enumerate(pool.imap_unordered(_rate_worker,
                                [(n, calib) for n in names]), 1):
            results.append(res)
            if i % 50 == 0:
                print(f"  ...{i}/{len(names)}")

    # Persist into the store as the primary output (workers computed; main writes).
    from . import ratings_store as store
    conn = store.connect()
    run_id = store.record_run(conn, "heuristic", cfg, bench, cal_points, label=args.label)
    ok, errs = [], []
    for name, r, err in results:
        if r is None:
            errs.append((name, err))
            continue
        rec = store.record_from_rate(name, r, cr_to_xp(r["nominal_cr"]),
                                     cr_to_xp(r["adjusted_cr"]))
        store.upsert_rating(conn, rec, run_id)
        ok.append(rec)
    conn.commit()
    n_csv = store.export_csv(conn, CALIB_DIR / "adjusted_cr.csv")   # derived export
    conn.close()

    ok.sort(key=lambda d: d["residual"])
    def show(d):
        return (f"  {d['name']:<24} nom {d['nominal_cr']:>5}  adj {d['adjusted_cr']:>5}  "
                f"({d['residual']:+.2f})  CI[{d['ci_lo']},{d['ci_hi']}] {d['flag']}")
    print("\n=== Most OVERRATED (adjusted << nominal) ===")
    for d in ok[:15]:
        print(show(d))
    print("\n=== Most UNDERRATED (adjusted >> nominal) ===")
    for d in ok[-15:][::-1]:
        print(show(d))
    print(f"\nStored {len(ok)} ratings in ratings.db (run {run_id}); "
          f"exported adjusted_cr.csv ({n_csv} rows), {len(errs)} errors")
    for name, err in errs[:10]:
        print(f"  ERROR {name}: {err}")


# Stratified skill-ceiling set: casters (heuristic likely underplays), dragons
# (breath/legendary tactics), control/complex monsters, and a few brute baselines
# (expected Δ ≈ 0 — a sanity control that the LLM doesn't just inflate everything).
_LLM_TARGETS = [
    "Ogre", "Mage",                                      # lead: one baseline + one caster
    "Archmage", "Drow Mage", "Priest", "Spirit Naga", "Kuo-toa Archpriest",
    "Mind Flayer", "Drow Priestess of Lolth",
    "Young White Dragon", "Young Red Dragon", "Young Blue Dragon", "Adult Brass Dragon",
    "Beholder", "Medusa", "Vrock", "Rakshasa", "Djinni", "Efreeti", "Erinyes",
    "Hill Giant", "Owlbear", "Bugbear",                  # baselines (expect Δ ~ 0)
]


def cmd_llm(args) -> None:
    """Skill-ceiling Δ: re-rate targets with the LLM controlling the monster (heuristic
    squad), centered on each monster's heuristic tie so the slow model does minimal work.
    Δ = llm_cr − heuristic_cr. Checkpointed to llm_delta.csv (resumable)."""
    import csv
    calib = json.loads((CALIB_DIR / "calibration.json").read_text(encoding="utf-8"))
    g = make_g(calib["cal_points"])
    bench_xp = _bench_xp(calib["bench"])
    hcr = {r["name"]: float(r["adjusted_cr"])
           for r in csv.DictReader((CALIB_DIR / "adjusted_cr.csv").open(encoding="utf-8"))}

    targets = (args.targets.split(";") if args.targets else _LLM_TARGETS)
    targets = [t for t in targets if t in hcr]
    out = CALIB_DIR / "llm_delta.csv"
    done = {}
    if out.exists():
        done = {r["name"]: r for r in csv.DictReader(out.open(encoding="utf-8"))}
    else:
        out.write_text("name,nominal_cr,heuristic_cr,llm_cr,delta,flag\n", encoding="utf-8")

    cfg = dict(calib["config"])
    cfg.update(ai="llm_vs_heuristic", seeds=args.seeds, ladder=[0.8, 1.1, 1.5],
               compositions=[1, 3])
    if args.seed_base is not None:
        cfg["seed_base"] = args.seed_base       # independent seeds for a second round

    from . import ratings_store as store
    conn = store.connect()

    if args.rebaseline:
        # Matched baseline: re-measure the HEURISTIC through the identical centered ladder
        # + seeds as the LLM (reusing cached llm_cr), so delta cancels the ladder asymmetry
        # that gave brute baselines a spurious ~+0.3 offset. No Ollama, fast (heuristic only).
        import statistics
        hcfg = dict(cfg)
        hcfg["ai"] = "heuristic"
        base = {"Ogre", "Hill Giant", "Owlbear", "Bugbear"}
        rows = []
        for n, r in done.items():
            center = float(r["heuristic_cr"])
            llm_cr = float(r["llm_cr"])
            percaps = [tie_budget(n, hcfg, bench_xp, comps=[c], center_cr=center)["bstar"]
                       for c in hcfg["compositions"]]
            matched = round(g(_geomean(percaps)), 2)
            delta = round(llm_cr - matched, 2)
            store.upsert_llm(conn, n, float(r["nominal_cr"]), matched, llm_cr, delta,
                             r.get("flag", ""))
            rows.append((n, float(r["nominal_cr"]), matched, llm_cr, delta))
        conn.commit()
        conn.close()
        rows.sort(key=lambda x: -x[4])
        print("=== Matched skill-ceiling delta (llm - heuristic, same centered ladder) ===")
        for n, nom, mh, lc, d in rows:
            tag = "   <- baseline" if n in base else ""
            print(f"  {n:<24} nom {nom:>5}  heur* {mh:>6}  llm {lc:>6}  delta {d:+.2f}{tag}")
        bd = [d for n, _, _, _, d in rows if n in base]
        if bd:
            print(f"\nbaseline mean delta {statistics.mean(bd):+.2f}  (was +0.38 unmatched; "
                  f"target ~0)")
        return

    from .llm import OllamaClient
    if not OllamaClient().available():
        print("Ollama not reachable at localhost:11434 — start it and retry.")
        return
    # Checkpointed results upsert into the store too (integrated backfill, no recompute).
    for n, r in done.items():
        store.upsert_llm(conn, n, float(r["nominal_cr"]), float(r["heuristic_cr"]),
                         float(r["llm_cr"]), float(r["delta"]), r.get("flag", ""))
    rows = [(n, float(r["nominal_cr"]), float(r["heuristic_cr"]), float(r["llm_cr"]),
             float(r["delta"])) for n, r in done.items()]
    for t in targets:
        if t in done:
            print(f"  skip {t} (checkpointed)")
            continue
        center = hcr[t]
        percaps, flags = [], []
        for c in cfg["compositions"]:
            tb = tie_budget(t, cfg, bench_xp, comps=[c], center_cr=center)
            percaps.append(tb["bstar"])
            flags.append(tb["flag"])
        llm_cr = round(g(_geomean(percaps)), 2)
        # MATCHED baseline: heuristic through the identical centered ladder + seeds, so the
        # delta isolates controller skill (not the short-ladder-vs-adaptive asymmetry).
        hcfg = dict(cfg)
        hcfg["ai"] = "heuristic"
        heur_matched = round(g(_geomean(
            [tie_budget(t, hcfg, bench_xp, comps=[c], center_cr=center)["bstar"]
             for c in cfg["compositions"]])), 2)
        delta = round(llm_cr - heur_matched, 2)
        flag = "ok" if all(f == "ok" for f in flags) else "/".join(sorted(set(flags)))
        nom = content.get(t).cr
        with out.open("a", encoding="utf-8") as f:
            f.write(f"{t},{nom},{heur_matched},{llm_cr},{delta},{flag}\n")
        store.upsert_llm(conn, t, nom, heur_matched, llm_cr, delta, flag)
        conn.commit()
        print(f"  {t:<24} heur* {heur_matched:>5} -> llm {llm_cr:>5}  (delta {delta:+.2f})")
        rows.append((t, nom, heur_matched, llm_cr, delta))
    conn.commit()
    conn.close()

    rows.sort(key=lambda r: -r[4])
    print("\n=== Skill-ceiling delta (llm - heuristic), biggest gains first ===")
    for t, nom, hc, lc, d in rows:
        print(f"  {t:<24} nom {nom:>5}  heur {hc:>5}  llm {lc:>5}  delta {d:+.2f}")


def cmd_smoke(_args) -> None:
    """Tiny end-to-end: fit on 3 calibrators, rate one monster. Fast."""
    spec = {"config": {"ai": "heuristic", "seed_base": 1000, "seeds": 4,
                        "ladder": [0.75, 1.0, 1.5, 2.0], "compositions": [1, 3],
                        "max_squad": 8, "roll_hp": False, "environments": [None]},
            "bench": ["Skeleton", "Orc", "Ogre"],
            "calibrators": ["Skeleton", "Orc", "Ogre"]}
    cal = fit_calibration(spec)
    print(_fmt_calibration(cal))
    calib = {"cal_points": cal["cal_points"], "config": spec["config"],
             "bench": spec["bench"]}
    print("\n" + _fmt_rating(rate("Wolf", calib, group=4, dispersion=True)))
    print("\nsmoke OK")


def _synergy_worker(payload):
    """Grouped per-capita CR for k copies (solo already in the DB, so we compute only the
    grouped side). synergy = grouped - solo captures Lanchester + trait (pack tactics) gains."""
    name, calib, k, solo = payload
    try:
        cfg = calib["config"]
        bench_xp = _bench_xp(calib["bench"])
        g = make_g(calib["cal_points"])
        percaps = []
        for c in cfg.get("compositions", [1, 3, 6]):
            tb = tie_budget(name, cfg, bench_xp, group=k, comps=[c])
            percaps.append(tb["bstar"] / k)
        grouped = round(g(_geomean(percaps)), 2)
        return (name, grouped, round(grouped - solo, 2), None)
    except Exception as e:                                    # pragma: no cover
        return (name, None, None, f"ERR:{e}")


def cmd_synergy(args) -> None:
    """Fill the group_synergy ('wants_friends') column: field k copies and diff per-capita
    CR against the stored solo. Targets monsters realistically fielded in numbers."""
    import multiprocessing as mp
    calib = json.loads((CALIB_DIR / "calibration.json").read_text(encoding="utf-8"))
    from . import ratings_store as store
    conn = store.connect()
    solos = {r["name"]: r["adjusted_cr"] for r in
             conn.execute("SELECT name, adjusted_cr FROM ratings "
                          "WHERE adjusted_cr IS NOT NULL")}
    targets = []
    for md in sorted(content._M.values(), key=lambda m: (m.cr, m.name)):
        if md.name not in solos or md.cr > args.max_cr:
            continue
        if args.all or md.pack_tactics or md.leadership or md.cr <= args.low_cr:
            targets.append(md.name)
    workers = args.workers or min(8, mp.cpu_count() or 2)
    print(f"Group-synergy pass: {len(targets)} monsters x{args.k} on {workers} workers...")
    payloads = [(n, calib, args.k, solos[n]) for n in targets]
    done = 0
    with mp.Pool(workers) as pool:
        for name, grouped, syn, err in pool.imap_unordered(_synergy_worker, payloads):
            if err:
                continue
            conn.execute("UPDATE ratings SET group_synergy=?, "
                         "updated_at=CURRENT_TIMESTAMP WHERE name=?", (syn, name))
            done += 1
            if done % 40 == 0:
                conn.commit()
                print(f"  ...{done}/{len(targets)}")
    conn.commit()
    rows = conn.execute("SELECT name, nominal_cr, group_synergy FROM ratings "
                        "WHERE group_synergy IS NOT NULL ORDER BY group_synergy DESC "
                        "LIMIT 15").fetchall()
    print(f"\n=== Biggest group synergy (wants_friends, x{args.k}) ===")
    for r in rows:
        md = content.get(r["name"])
        tag = "pack" if md.pack_tactics else ("leader" if md.leadership else "")
        print(f"  {r['name']:<24} nom {r['nominal_cr']:>5}  synergy {r['group_synergy']:+.2f}  {tag}")
    conn.close()
    print(f"\nFilled group_synergy for {done} monsters.")


def _bt_pair_worker(payload):
    """Run one monster-vs-monster 1v1 pair over seeds; return win/draw counts."""
    a, b, seeds = payload
    aw = bw = dr = 0
    for s in seeds:
        res = run_battle([a], [b], seed=s, ai="heuristic")
        if res.winner == "A":
            aw += 1
        elif res.winner == "B":
            bw += 1
        else:
            dr += 1
    return (a, b, aw, bw, dr)


def cmd_bt(args) -> None:
    """Bradley-Terry cross-check: a tiered 1v1 round-robin (each monster vs its K nearest
    by CR), fit latent strengths, anchor to CR via the calibrators, and store bt_cr +
    refined_cr (consensus with the mirror) + bt_disagreement (matchup-dependent flag)."""
    import multiprocessing as mp
    from . import bradley_terry as bt
    from . import ratings_store as store

    noncombat = {"spiritual weapon"}
    mons = [md for md in sorted(content._M.values(), key=lambda m: (m.cr, m.name))
            if md.cr <= args.cap and md.name.lower() not in noncombat]
    names = [m.name for m in mons]
    n = len(names)
    seeds = [args.seed_base + i for i in range(args.seeds)]
    # Nearest-neighbor-by-CR chain: each monster fights its k nearest-CR peers (competitive,
    # informative games). A wide symmetric window instead makes everyone ~50% (theta collapses),
    # so we keep matches near-equal and let theta be anchored over the whole population below.
    import csv
    cache = CALIB_DIR / "bt_pairs.csv"
    if args.from_cache and cache.exists():
        rd = list(csv.reader(cache.open(encoding="utf-8")))[1:]
        results = [(a, b, int(aw), int(bw), int(dr)) for a, b, aw, bw, dr in rd]
        print(f"Loaded {len(results)} cached pair results (re-fit only, no battles).")
    else:
        pairs = [(names[i], names[j]) for i in range(n)
                 for j in range(i + 1, min(n, i + 1 + args.k))]
        workers = args.workers or min(8, mp.cpu_count() or 2)
        print(f"BT round-robin: {n} monsters, {len(pairs)} pairs x {len(seeds)} seeds "
              f"= {len(pairs) * len(seeds)} battles on {workers} workers...")
        results = []
        with mp.Pool(workers) as pool:
            for i, res in enumerate(pool.imap_unordered(_bt_pair_worker,
                                    [(a, b, seeds) for a, b in pairs]), 1):
                results.append(res)
                if i % 500 == 0:
                    print(f"  ...{i}/{len(pairs)} pairs")
        with cache.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["a", "b", "aw", "bw", "dr"])
            w.writerows(results)

    theta = bt.fit_bt(results, names)
    games = {nm: 0 for nm in names}
    for a, b, aw, bw, dr in results:
        games[a] += aw + bw + dr
        games[b] += aw + bw + dr

    # Anchor theta -> CR by isotonic regression against nominal CR over ALL monsters
    # (robust; "the CR a monster this strong usually has"). Calibrator-only anchoring
    # extrapolated outliers to absurd CRs; the full population does not.
    anchor_pts = [(theta[nm], content.get(nm).cr) for nm in names]
    to_cr = bt.fit_anchor(anchor_pts)
    bt_cr = {nm: round(to_cr(theta[nm]), 2) for nm in names}

    conn = store.connect()
    solos = {r["name"]: r["adjusted_cr"] for r in
             conn.execute("SELECT name, adjusted_cr FROM ratings WHERE adjusted_cr IS NOT NULL")}
    pairs_cmp, disagree = [], []
    for nm in names:
        adj = solos.get(nm)
        b_cr = bt_cr[nm]
        refined = round((adj + b_cr) / 2, 2) if adj is not None else b_cr
        dis = round(adj - b_cr, 2) if adj is not None else None
        store.upsert_bt(conn, nm, b_cr, games[nm], refined, dis)
        if adj is not None:
            pairs_cmp.append((adj, b_cr))
            disagree.append((nm, content.get(nm).cr, adj, b_cr, dis))
    conn.commit()
    conn.close()

    # correlation between mirror and BT
    import statistics
    xs = [p[0] for p in pairs_cmp]
    ys = [p[1] for p in pairs_cmp]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in pairs_cmp) / len(pairs_cmp)
    cor = cov / (statistics.pstdev(xs) * statistics.pstdev(ys))
    print(f"\nMirror vs BT: corr={cor:.3f} over {len(pairs_cmp)} monsters "
          f"(agreement = confidence; disagreement = matchup-dependent)")
    disagree.sort(key=lambda r: -abs(r[4]))
    print("\n=== Biggest mirror/BT disagreements (matchup-dependent / intransitive) ===")
    print(f"  {'monster':<24}{'nom':>5}{'mirror':>8}{'bt':>7}{'diff':>7}")
    for nm, nom, adj, b_cr, dis in disagree[:15]:
        print(f"  {nm:<24}{nom:>5}{adj:>8}{b_cr:>7}{dis:>+7.2f}")
    print(f"\nStored bt_cr/refined_cr for {len(bt_cr)} monsters.")


def cmd_factors(args) -> None:
    """Fit the empirical CR formula: regress the playtested residual on stat-block features.
    Reports the interpretable coefficients + accuracy, writes predicted_cr to the DB, and
    pickles the model for no-simulation prediction of new monsters."""
    import pickle
    from . import factor_model as fm
    from . import ratings_store as store

    conn = store.connect()
    tgt = "refined_cr" if not args.use_adjusted else "adjusted_cr"
    rows = [{"name": r["name"], "nominal_cr": r["nominal_cr"],
             "target": r[tgt] - r["nominal_cr"]}
            for r in conn.execute(f"SELECT name, nominal_cr, {tgt} FROM ratings "
                                  f"WHERE {tgt} IS NOT NULL AND nominal_cr IS NOT NULL "
                                  f"AND nominal_cr <= {args.max_cr}")]
    print(f"Fitting empirical CR formula on {len(rows)} monsters "
          f"(target = {tgt} - nominal_cr)...")
    df = fm.build_frame(rows)
    res = fm.train(df, target_is_residual=True)

    print(f"\nHow explainable is the CR error?  (5-fold CV)")
    print(f"  Ridge (linear): R2={res['ridge_cv_r2']:.2f}  MAE={res['ridge_cv_mae']:.2f} CR")
    print(f"  GBM   (trees):  R2={res['gbm_cv_r2']:.2f}  MAE={res['gbm_cv_mae']:.2f} CR")

    print("\n=== Empirical CR-correction formula (Ridge, CR per unit feature) ===")
    print("  adjusted_CR ~= nominal_CR + intercept + sum(coef * feature)")
    print(f"  intercept: {res['intercept']:+.2f}")
    ranked = sorted(res["std_coef"].items(), key=lambda kv: -abs(kv[1]))
    print(f"  {'feature':<22}{'std_effect':>11}{'per-unit':>11}")
    for f, sc in ranked[:18]:
        print(f"  {f:<22}{sc:>+11.2f}{res['raw_coef'][f]:>+11.3f}")

    print("\n=== GBM feature importance (permutation) ===")
    for f, imp in sorted(res["importances"].items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {f:<22}{imp:>8.3f}")

    # write predictions (nominal + predicted residual) back to the store
    for r in rows:
        pred_resid = res["gbm_cv_pred"][r["name"]]
        conn.execute("UPDATE ratings SET predicted_cr=?, model_residual=? WHERE name=?",
                     (round(r["nominal_cr"] + pred_resid, 2), round(float(pred_resid), 2),
                      r["name"]))
    conn.commit()
    conn.close()

    artifact = {"gbm": res["gbm"], "scaler": res["scaler"], "ridge": res["ridge"],
                "feat_cols": res["feat_cols"], "target_is_residual": True}
    path = CALIB_DIR / "cr_model.pkl"
    with path.open("wb") as f:
        pickle.dump(artifact, f)
    print(f"\nWrote predicted_cr to the store and pickled the model to {path.name}.")


def _env_worker(payload):
    """Rate a monster in each of its environments, plus a MATCHED open baseline (identical
    short config), so delta = env_cr - open_matched isolates the environment effect (not the
    short-vs-full config difference). Centered on the DB open CR to keep the ladder positioned."""
    name, envs, calib, open_cr = payload
    cfg = dict(calib["config"])
    cfg.update(ai="heuristic", seeds=4, ladder=[0.8, 1.1, 1.5], compositions=[1, 3])
    bench_xp = _bench_xp(calib["bench"])
    g = make_g(calib["cal_points"])

    def rate_in(e):
        pc = [tie_budget(name, cfg, bench_xp, comps=[c], center_cr=open_cr, env=e)["bstar"]
              for c in cfg["compositions"]]
        return round(g(_geomean(pc)), 2)

    try:
        base = rate_in(None)                       # matched open baseline
        return (name, base, {e: rate_in(e) for e in envs}, None)
    except Exception as e:                                    # pragma: no cover
        return (name, None, None, f"ERR:{e}")


def cmd_environments(args) -> None:
    """Per-environment CR: playtest env-sensitive monsters in their relevant environments
    (underwater/windy/fog/dungeon/lava), centered on the open rating so each is a cheap shift
    measurement. Fills env_ratings + native_env + env_sensitivity."""
    import multiprocessing as mp
    calib = json.loads((CALIB_DIR / "calibration.json").read_text(encoding="utf-8"))
    from . import ratings_store as store
    conn = store.connect()
    opens = {r["name"]: r["adjusted_cr"] for r in
             conn.execute("SELECT name, adjusted_cr FROM ratings WHERE adjusted_cr IS NOT NULL")}

    if args.targets:
        names = [t for t in args.targets.split(";") if t in opens]
    else:
        names = [m.name for m in sorted(content._M.values(), key=lambda x: (x.cr, x.name))
                 if m.name in opens and m.name.lower() != "spiritual weapon"
                 and m.cr <= args.max_cr and (args.all or env_sensitive(m))]
    allowed = FLAG_ENVS | MAP_ENVS if args.maps else FLAG_ENVS
    tasks = [(nm, [e for e in env_relevance(content.get(nm)) if e in allowed],
              calib, opens[nm]) for nm in names]
    tasks = [t for t in tasks if t[1]]             # only monsters with >=1 allowed env
    n_ratings = sum(len(t[1]) + 1 for t in tasks)  # +1 matched open baseline each
    workers = args.workers or min(8, mp.cpu_count() or 2)
    print(f"Env pass: {len(tasks)} monsters, {n_ratings} ratings on "
          f"{workers} workers (~{max(1, n_ratings * 24 // 1000)}k battles)")

    results: dict = {}
    with mp.Pool(workers) as pool:
        for i, (nm, base, env_crs, err) in enumerate(
                pool.imap_unordered(_env_worker, tasks), 1):
            if err is None:
                store.upsert_env(conn, nm, "open", base, 0.0, "ok")
                for e, cr in env_crs.items():
                    delta = round(cr - base, 2)
                    store.upsert_env(conn, nm, e, cr, delta, "ok")
                    results.setdefault(nm, {})[e] = delta
            if i % 50 == 0:
                conn.commit()
                print(f"  ...{i}/{len(tasks)}")
    for nm in names:
        deltas = results.get(nm, {})
        biggest = max(deltas.values(), key=abs) if deltas else 0.0
        store.set_env_summary(conn, nm, native_env(content.get(nm)), round(biggest, 2))
    conn.commit()

    flat = [(nm, e, d) for nm, ds in results.items() for e, d in ds.items()]
    flat.sort(key=lambda r: -abs(r[2]))
    print("\n=== Biggest environment effects (env CR - open CR) ===")
    print(f"  {'monster':<24}{'env':<12}{'open':>6}{'delta':>8}")
    for nm, e, d in flat[:15]:
        print(f"  {nm:<24}{e:<12}{opens[nm]:>6}{d:>+8.2f}")
    conn.close()
    print(f"\nFilled env_ratings for {len(results)} monsters.")


def _bt_incremental(new_names, seeds_n=9):
    """Add monsters to the BT round-robin incrementally: fight their CR-neighbors, append to
    the pair cache, refit on everything, return bt_cr for the new ones. Existing theta barely
    moves (a few new edges among thousands), so no full re-run is needed."""
    import csv
    import multiprocessing as mp
    from . import bradley_terry as bt
    cache = CALIB_DIR / "bt_pairs.csv"
    results, seen = [], set()
    if cache.exists():
        for a, b, aw, bw, dr in list(csv.reader(cache.open(encoding="utf-8")))[1:]:
            results.append((a, b, int(aw), int(bw), int(dr)))
            seen.add((a, b))
            seen.add((b, a))
    mons = sorted((m for m in content._M.values() if m.name.lower() != "spiritual weapon"),
                  key=lambda m: (m.cr, m.name))
    names_all = [m.name for m in mons]
    idx = {n: i for i, n in enumerate(names_all)}
    seeds = list(range(7000, 7000 + seeds_n))
    new_pairs = []
    for nm in new_names:
        if nm not in idx:
            continue
        i = idx[nm]
        for j in range(max(0, i - 16), min(len(names_all), i + 17)):
            if j != i and (names_all[i], names_all[j]) not in seen:
                new_pairs.append((names_all[i], names_all[j], seeds))
                seen.add((names_all[i], names_all[j]))
                seen.add((names_all[j], names_all[i]))
    if new_pairs:
        with mp.Pool(min(8, mp.cpu_count() or 2)) as pool:
            fresh = list(pool.imap_unordered(_bt_pair_worker, new_pairs))
        results += fresh
        with cache.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(fresh)
    theta = bt.fit_bt(results, names_all)
    to_cr = bt.fit_anchor([(theta[nm], content.get(nm).cr) for nm in names_all])
    return {nm: round(to_cr(theta[nm]), 2) for nm in new_names if nm in theta}


def cmd_rate_new(args) -> None:
    """Run one or more NEW monsters through the whole ranking pipeline, incrementally: mirror
    adjusted CR + per-composition + CI, factor-model prediction, group synergy, flag-environment
    sensitivity, Bradley-Terry (incremental), and (optional) LLM skill ceiling. Reuses the
    existing calibration curve + BT cache — no full recalibration. Stores everything in the DB."""
    content.reload()                                # pick up newly added stat blocks
    calib = json.loads((CALIB_DIR / "calibration.json").read_text(encoding="utf-8"))
    from . import factor_model as fm
    from . import ratings_store as store
    conn = store.connect()
    names = [n.strip() for n in args.monsters.split(";") if n.strip()]
    for n in names:
        try:
            content.get(n)
        except KeyError:
            print(f"unknown monster '{n}'. Add its JSON under data/monsters/ (then it loads "
                  f"automatically), or check the spelling.")
            return
    bench_xp = _bench_xp(calib["bench"])
    g = make_g(calib["cal_points"])
    model_path = CALIB_DIR / "cr_model.pkl"
    model = fm.load_model(model_path) if model_path.exists() else None

    for n in names:
        md = content.get(n)
        print(f"\n### {n}  (nominal CR {md.cr}) ###")
        # 1) mirror rating (the authoritative playtested number)
        r = rate(n, calib)
        store.upsert_rating(conn, store.record_from_rate(
            n, r, cr_to_xp(md.cr), cr_to_xp(r["adjusted_cr"])))
        adjusted = r["adjusted_cr"]
        print(f"  mirror adjusted CR {adjusted}  (90% CI {r['ci']}, flag {r['flag']}, "
              f"per-comp {r['per_composition']})")
        # 2) factor-model no-sim prediction (sanity cross-check)
        if model:
            pred = fm.predict(model, md)
            conn.execute("UPDATE ratings SET predicted_cr=? WHERE name=?", (pred, n))
            print(f"  factor-model predicted CR {pred} (no-sim)")
        # 3) group synergy (only where fielding multiples is realistic)
        if not args.no_synergy and (md.pack_tactics or md.leadership or md.cr <= 5):
            _, _grp, syn, err = _synergy_worker((n, calib, 4, adjusted))
            if err is None:
                conn.execute("UPDATE ratings SET group_synergy=? WHERE name=?", (syn, n))
                print(f"  group synergy x4: {syn:+.2f}")
        # 4) flag-environment sensitivity (matched open baseline)
        envs = [e for e in env_relevance(md) if e in FLAG_ENVS]
        biggest = 0.0
        if not args.no_env and envs:
            _, base, env_crs, err = _env_worker((n, envs, calib, adjusted))
            if err is None:
                store.upsert_env(conn, n, "open", base, 0.0, "ok")
                deltas = {}
                for e, cr in env_crs.items():
                    deltas[e] = round(cr - base, 2)
                    store.upsert_env(conn, n, e, cr, deltas[e], "ok")
                biggest = max(deltas.values(), key=abs) if deltas else 0.0
                print("  environments: " + ", ".join(f"{e} {d:+.2f}" for e, d in deltas.items()))
        store.set_env_summary(conn, n, native_env(md), round(biggest, 2))
        # 5) Bradley-Terry (incremental) + consensus refined_cr
        bt_cr = None
        if not args.no_bt:
            print("  running BT vs CR-neighbors (incremental)...")
            bt_cr = _bt_incremental([n]).get(n)
        use_bt = bt_cr if bt_cr is not None else adjusted
        refined = round((adjusted + use_bt) / 2, 2)
        store.upsert_bt(conn, n, use_bt, None, refined, round(adjusted - use_bt, 2))
        if bt_cr is not None:
            print(f"  BT CR {bt_cr}  ->  refined (mirror+BT consensus) {refined}")
        # 6) LLM skill ceiling (optional, slow)
        if args.llm:
            from .llm import OllamaClient
            if OllamaClient().available():
                lcfg = dict(calib["config"])
                lcfg.update(ai="llm_vs_heuristic", seeds=4, ladder=[0.8, 1.1, 1.5],
                            compositions=[1, 3])
                hcfg = dict(lcfg)
                hcfg["ai"] = "heuristic"
                lc = round(g(_geomean([tie_budget(n, lcfg, bench_xp, comps=[c],
                            center_cr=adjusted)["bstar"] for c in lcfg["compositions"]])), 2)
                hm = round(g(_geomean([tie_budget(n, hcfg, bench_xp, comps=[c],
                            center_cr=adjusted)["bstar"] for c in hcfg["compositions"]])), 2)
                store.upsert_llm(conn, n, md.cr, hm, lc, round(lc - hm, 2), "ok")
                print(f"  LLM skill-ceiling delta {lc - hm:+.2f}  (heur* {hm} -> llm {lc})")
            else:
                print("  (LLM skipped — Ollama not reachable)")
        conn.commit()

    store.export_csv(conn, CALIB_DIR / "adjusted_cr.csv")
    conn.close()
    print(f"\nStored {len(names)} monster(s) in ratings.db / encounter_view "
          f"(query: python -m ravel.calib query --near <CR>).")


def cmd_query(args) -> None:
    """Read the ratings store the way an encounter builder would."""
    from . import ratings_store as store
    conn = store.connect()
    if args.export:
        n = store.export_csv(conn, Path(args.export))
        print(f"Exported {n} ratings to {args.export}")
        conn.close()
        return
    if args.swingy:
        order, where = "action_economy_sensitivity DESC", "action_economy_sensitivity IS NOT NULL"
    elif args.needs_play:
        order, where = "needs_good_play DESC", "needs_good_play IS NOT NULL"
    elif args.near is not None:
        order = "ABS(best_cr - :near)"
        where = "best_cr BETWEEN :lo AND :hi"
    else:
        order, where = "residual", "1=1"
    rows = conn.execute(
        f"SELECT name, nominal_cr, adjusted_cr, best_cr, adjusted_xp, "
        f"action_economy_sensitivity, needs_good_play, wants_friends, flag "
        f"FROM encounter_view WHERE {where} ORDER BY {order} LIMIT :lim",
        {"near": args.near, "lo": (args.near or 0) - args.band,
         "hi": (args.near or 0) + args.band, "lim": args.limit}).fetchall()
    hdr = f"{'monster':<24}{'nom':>5}{'adj':>6}{'best':>6}{'xp':>7}{'swing':>7}{'play+':>7}{'grp+':>6}"
    print(hdr)
    for r in rows:
        swing = f"{r['action_economy_sensitivity']:+.1f}" if r['action_economy_sensitivity'] is not None else "  ."
        play = f"{r['needs_good_play']:+.1f}" if r['needs_good_play'] is not None else "  ."
        grp = f"{r['wants_friends']:+.1f}" if r['wants_friends'] is not None else "  ."
        print(f"{r['name']:<24}{r['nominal_cr']:>5}{r['adjusted_cr']:>6}{r['best_cr']:>6}"
              f"{r['adjusted_xp']:>7.0f}{swing:>7}{play:>7}{grp:>6}")
    conn.close()


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="ravel.calib",
                                description="Fair-XP-mirror CR calibration")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bench", help="fit the calibration curve from a bench spec")
    b.add_argument("--spec", default=None, help="bench json (default data/calibration/bench.json)")
    b.add_argument("--out", default=None, help="output calibration json")
    b.set_defaults(func=cmd_bench)

    r = sub.add_parser("rate", help="rate one monster against the calibration")
    r.add_argument("monster")
    r.add_argument("--calib", default=None, help="calibration json (default calibration.json)")
    r.add_argument("--group", type=int, default=1, help="pack size k for synergy")
    r.add_argument("--ablate", action="store_true", help="turn off pack tactics/leadership")
    r.add_argument("--fast", action="store_true",
                   help="no-simulation CR estimate from the pickled factor model (instant)")
    r.add_argument("--dispersion", action="store_true",
                   help="also report adjusted CR vs few-strong vs many-weak squads")
    r.add_argument("--env", default=None, help="map/environment name (default open arena)")
    r.add_argument("--json", action="store_true", help="also print the full JSON record")
    r.set_defaults(func=cmd_rate)

    ra = sub.add_parser("rate-all", help="fit + rate the whole roster, write adjusted_cr.*")
    ra.add_argument("--spec", default=None)
    ra.add_argument("--cap", type=float, default=13.0, help="max nominal CR to rate")
    ra.add_argument("--sample", type=int, default=0, help="rate only ~N evenly-spaced monsters")
    ra.add_argument("--workers", type=int, default=0, help="processes (default min(8,cpus))")
    ra.add_argument("--label", default="", help="provenance label for this run")
    ra.set_defaults(func=cmd_rate_all)

    lm = sub.add_parser("llm", help="skill-ceiling delta: re-rate targets with the LLM")
    lm.add_argument("--targets", default=None,
                    help="semicolon-separated monster names (default: stratified set)")
    lm.add_argument("--seeds", type=int, default=2, help="paired seeds per point (slow)")
    lm.add_argument("--rebaseline", action="store_true",
                    help="recompute delta vs a matched heuristic ladder (no Ollama; fixes offset)")
    lm.add_argument("--seed-base", type=int, default=None,
                    help="override seed base for an independent round (to average in)")
    lm.add_argument("--label", default="", help="provenance label for this run")
    lm.set_defaults(func=cmd_llm)

    sy = sub.add_parser("synergy", help="fill group_synergy (wants_friends) via k-copy playtests")
    sy.add_argument("--k", type=int, default=4, help="pack size to field")
    sy.add_argument("--low-cr", type=float, default=5.0,
                    help="also include all monsters at/below this CR")
    sy.add_argument("--max-cr", type=float, default=13.0, help="skip monsters above this CR")
    sy.add_argument("--all", action="store_true", help="every monster in range, not just pack/low-CR")
    sy.add_argument("--workers", type=int, default=0)
    sy.set_defaults(func=cmd_synergy)

    bt = sub.add_parser("bt", help="Bradley-Terry round-robin cross-check + refined_cr")
    bt.add_argument("--k", type=int, default=18, help="opponents per monster (sampled across window)")
    bt.add_argument("--band", type=float, default=5.0, help="+/- CR window for opponents")
    bt.add_argument("--seeds", type=int, default=8, help="battles per pair")
    bt.add_argument("--seed-base", type=int, default=7000)
    bt.add_argument("--cap", type=float, default=30.0, help="max nominal CR to include")
    bt.add_argument("--from-cache", action="store_true",
                    help="re-fit/re-anchor from bt_pairs.csv without re-running battles")
    bt.add_argument("--workers", type=int, default=0)
    bt.set_defaults(func=cmd_bt)

    rn = sub.add_parser("rate-new", help="run new monster(s) through the whole pipeline (incremental)")
    rn.add_argument("monsters", help="semicolon-separated monster names (must be in data/monsters/)")
    rn.add_argument("--no-bt", action="store_true", help="skip the Bradley-Terry step")
    rn.add_argument("--no-env", action="store_true", help="skip the environment step")
    rn.add_argument("--no-synergy", action="store_true", help="skip the group-synergy step")
    rn.add_argument("--llm", action="store_true", help="also measure the LLM skill ceiling (slow)")
    rn.set_defaults(func=cmd_rate_new)

    en = sub.add_parser("environments", help="per-environment CR for env-sensitive monsters")
    en.add_argument("--targets", default=None, help="semicolon-separated names (default: screened set)")
    en.add_argument("--all", action="store_true", help="every monster in range, not just env-sensitive")
    en.add_argument("--maps", action="store_true", help="include map-based envs (spawn-confounded)")
    en.add_argument("--max-cr", type=float, default=30.0)
    en.add_argument("--workers", type=int, default=0)
    en.set_defaults(func=cmd_environments)

    fa = sub.add_parser("factors", help="fit the empirical CR formula from the ratings")
    fa.add_argument("--use-adjusted", action="store_true",
                    help="target the mirror adjusted_cr instead of refined_cr")
    fa.add_argument("--max-cr", type=float, default=30.0,
                    help="fit only on monsters at/below this CR (13 = trustworthy subset)")
    fa.set_defaults(func=cmd_factors)

    q = sub.add_parser("query", help="read the ratings store (encounter-builder view)")
    q.add_argument("--near", type=float, default=None,
                   help="show monsters whose best adjusted CR is near this value")
    q.add_argument("--band", type=float, default=1.0, help="+/- CR window for --near")
    q.add_argument("--swingy", action="store_true", help="rank by action-economy sensitivity")
    q.add_argument("--needs-play", action="store_true", help="rank by skill-ceiling delta")
    q.add_argument("--export", default=None, help="export the store to a CSV path")
    q.add_argument("--limit", type=int, default=20)
    q.set_defaults(func=cmd_query)

    sub.add_parser("smoke").set_defaults(func=cmd_smoke)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
