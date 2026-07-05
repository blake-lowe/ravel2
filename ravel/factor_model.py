"""Empirical CR formula — regress the playtested rating on stat-block features.

Turns the residual (refined_cr - nominal_cr) into an interpretable model: which monster
features make it stronger or weaker than its book CR, in CR units. A Ridge fit gives the
readable coefficients (the "formula"); a gradient-boosted fit captures interactions and
predicts a new monster's CR without simulating. Analysis layer — uses numpy/pandas/sklearn;
the engine stays stdlib. See docs/CR_CALIBRATION.md sec.7.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import KFold, cross_val_predict, cross_val_score
from sklearn.preprocessing import StandardScaler

from . import content
from .models import Ability, SIZE_ORDER, ability_mod

HARD_CC = {"paralyzed", "stunned", "restrained", "frightened", "petrified",
           "unconscious", "incapacitated", "prone", "grappled", "poisoned", "blinded"}


def _avg(damage) -> float:
    return sum(d.count * (d.sides + 1) / 2 + d.bonus for d in damage)


def _dpr(md) -> float:
    """Rough offensive proxy: multiattack damage + amortized best AoE."""
    total = 0.0
    if md.multiattack:
        for name, count in md.multiattack:
            a = md.attacks.get(name)
            if a:
                total += count * _avg(a.damage)
    elif md.attacks:
        total = max((_avg(a.damage) for a in md.attacks.values()), default=0.0)
    if md.areas:
        total += 0.5 * max(_avg(ar.damage) for ar in md.areas)
    return total


def _cc_conditions(md) -> set:
    conds = set()
    for a in md.attacks.values():
        if a.rider and a.rider.on_fail_condition:
            conds.add(a.rider.on_fail_condition)
        if a.rider and a.rider.escalates_to:
            conds.add(a.rider.escalates_to)
    for ar in md.areas:
        if ar.rider and ar.rider.on_fail_condition:
            conds.add(ar.rider.on_fail_condition)
    for r in getattr(md, "eye_rays", ()):
        if r.condition:
            conds.add(r.condition)
    if md.frightful_presence is not None:
        conds.add("frightened")
    return conds & HARD_CC


def features(md) -> dict:
    ab = md.abilities
    top_speed = max(md.speed, md.fly, md.swim, md.climb, md.burrow, md.teleport)
    return {
        "nominal_cr": md.cr,
        "ac": md.ac,
        "hp": md.hp,
        "size": SIZE_ORDER[md.size],
        "dpr": round(_dpr(md), 1),
        "n_attacks_per_turn": sum(c for _, c in md.multiattack) or (1 if md.attacks else 0),
        "has_ranged": int(any(a.kind != "melee" for a in md.attacks.values())),
        "best_to_hit": max((a.attack_bonus for a in md.attacks.values()), default=0),
        # defense
        "n_resist": len(md.resistances),
        "n_immune": len(md.immunities),
        "n_vuln": len(md.vulnerabilities),
        "n_cond_immune": len(md.condition_immunities),
        "resist_nonmagical": int(md.resist_nonmagical_physical),
        "regen": int(md.regen > 0),
        "magic_resistance": int(md.magic_resistance),
        "legendary_resistance": md.legendary_resistance,
        # action economy
        "legendary_actions": md.legendary_actions,
        "parry": int(md.parry > 0),
        # mobility
        "speed": md.speed,
        "top_speed": top_speed,
        "flies": int(md.fly > 0),
        "flyby": int(md.flyby),
        "teleport": int(md.teleport > 0),
        "pounce": int(md.pounce_distance > 0),
        # control / novas
        "n_hard_cc": len(_cc_conditions(md)),
        "n_areas": int(len(md.areas)),
        "frightful": int(md.frightful_presence is not None),
        "swallow": int(md.swallow is not None),
        # advantage engines
        "pack_tactics": int(md.pack_tactics),
        "reckless": int(md.reckless),
        "elven_accuracy": int(md.elven_accuracy),
        # caster
        "is_caster": int(md.spell_ability is not None or bool(md.innate)),
        "caster_level": md.caster_level,
        "n_spells": len(md.spells),
        "spell_dc": md.spell_dc,
        "incorporeal": int(md.incorporeal),
        # ability mods that matter for saves/defense
        "con_mod": ability_mod(ab[Ability.CON]),
        "dex_mod": ability_mod(ab[Ability.DEX]),
    }


def load_model(path):
    import pickle
    with open(path, "rb") as f:
        return pickle.load(f)


def predict(artifact, md) -> float:
    """No-simulation CR estimate for a MonsterDef (or name) from the pickled model."""
    if isinstance(md, str):
        md = content.get(md)
    x = np.array([[features(md)[c] for c in artifact["feat_cols"]]], dtype=float)
    out = float(artifact["gbm"].predict(x)[0])
    return round(md.cr + out if artifact.get("target_is_residual", True) else out, 2)


def build_frame(rows: list[dict]) -> pd.DataFrame:
    """rows: [{name, nominal_cr, target}]. Returns a feature frame + target column."""
    recs = []
    for r in rows:
        md = content.get(r["name"])
        f = features(md)
        f["name"] = r["name"]
        f["target"] = r["target"]
        recs.append(f)
    return pd.DataFrame(recs)


def train(df: pd.DataFrame, target_is_residual: bool = True) -> dict:
    """Fit Ridge (interpretable) and GBM (accurate) with K-fold CV.
    target = residual (refined_cr - nominal_cr) if target_is_residual, else refined_cr."""
    feat_cols = [c for c in df.columns if c not in ("name", "target")]
    X = df[feat_cols].to_numpy(dtype=float)
    y = df["target"].to_numpy(dtype=float)
    cv = KFold(n_splits=5, shuffle=True, random_state=0)

    # Ridge on standardized features -> comparable + raw coefficients
    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)
    ridge = RidgeCV(alphas=np.logspace(-2, 3, 40)).fit(Xs, y)
    std_coef = dict(zip(feat_cols, ridge.coef_))
    raw_coef = {c: ridge.coef_[i] / (scaler.scale_[i] or 1.0) for i, c in enumerate(feat_cols)}
    ridge_r2 = cross_val_score(RidgeCV(alphas=np.logspace(-2, 3, 40)), Xs, y,
                               cv=cv, scoring="r2").mean()
    ridge_mae = -cross_val_score(RidgeCV(alphas=np.logspace(-2, 3, 40)), Xs, y,
                                 cv=cv, scoring="neg_mean_absolute_error").mean()

    # GBM: interactions + honest CV predictions
    gbm = GradientBoostingRegressor(n_estimators=300, max_depth=3, learning_rate=0.05,
                                    subsample=0.8, random_state=0)
    gbm_pred = cross_val_predict(gbm, X, y, cv=cv)
    ss_res = float(np.sum((y - gbm_pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    gbm_r2 = 1 - ss_res / ss_tot
    gbm_mae = float(np.mean(np.abs(y - gbm_pred)))
    gbm.fit(X, y)
    perm = permutation_importance(gbm, X, y, n_repeats=10, random_state=0)
    importances = dict(zip(feat_cols, perm.importances_mean))

    return {
        "feat_cols": feat_cols,
        "std_coef": std_coef, "raw_coef": raw_coef, "intercept": float(ridge.intercept_),
        "ridge_cv_r2": ridge_r2, "ridge_cv_mae": ridge_mae,
        "gbm_cv_r2": gbm_r2, "gbm_cv_mae": gbm_mae,
        "importances": importances,
        "gbm": gbm, "scaler": scaler, "ridge": ridge,
        "gbm_cv_pred": dict(zip(df["name"], gbm_pred)),
        "target_is_residual": target_is_residual,
    }
