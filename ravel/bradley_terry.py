"""Bradley-Terry latent-strength fit + CR anchoring (stdlib).

Independent cross-check on the fair-XP mirror: from a round-robin of monster-vs-monster
1v1 results, fit one latent strength theta per monster (the model behind Elo), then map
theta -> CR through the trusted calibrators. Where BT and the mirror agree we gain
confidence; where they disagree we flag a matchup-dependent (intransitive) monster.

See docs/CR_CALIBRATION.md sec.3.
"""
from __future__ import annotations

import math


def fit_bt(pair_results, names, iters: int = 5000, tol: float = 1e-10,
           prior: float = 1.0) -> dict:
    """Minorize-maximize fit of Bradley-Terry strengths.

    pair_results: iterable of (a, b, a_wins, b_wins, draws) — draws split 0.5/0.5.
    prior: strength of a virtual game vs a phantom average opponent (pi=1); regularizes
    undefeated/winless monsters so pi stays finite. Returns {name: theta=log(pi)}.
    """
    idx = {n: k for k, n in enumerate(names)}
    n = len(names)
    wins = [prior * 0.5] * n                    # phantom half-win seeds the prior
    adj: list[dict] = [dict() for _ in range(n)]
    for a, b, aw, bw, dr in pair_results:
        ia, ib = idx[a], idx[b]
        wins[ia] += aw + 0.5 * dr
        wins[ib] += bw + 0.5 * dr
        tot = aw + bw + dr
        adj[ia][ib] = adj[ia].get(ib, 0.0) + tot
        adj[ib][ia] = adj[ib].get(ia, 0.0) + tot
    pi = [1.0] * n
    for _ in range(iters):
        newpi = [0.0] * n
        for a in range(n):
            denom = prior / (pi[a] + 1.0)       # phantom opponent at pi=1
            for b, nab in adj[a].items():
                denom += nab / (pi[a] + pi[b])
            newpi[a] = wins[a] / denom if denom > 0 else pi[a]
        gm = math.exp(sum(math.log(p) for p in newpi) / n)   # normalize geo-mean to 1
        newpi = [p / gm for p in newpi]
        rel = max(abs(newpi[a] - pi[a]) / (pi[a] + 1e-12) for a in range(n))
        pi = newpi
        if rel < tol:
            break
    return {names[a]: math.log(pi[a]) for a in range(n)}


def _isotonic(xs: list[float], ys: list[float]) -> list[float]:
    """Pool-adjacent-violators: make ys non-decreasing over xs-sorted order."""
    ys = list(ys)
    w = [1.0] * len(ys)
    i = 0
    while i < len(ys) - 1:
        if ys[i] > ys[i + 1]:
            tot = w[i] + w[i + 1]
            ys[i] = (w[i] * ys[i] + w[i + 1] * ys[i + 1]) / tot
            w[i] = tot
            del ys[i + 1]
            del w[i + 1]
            del xs[i + 1]
            if i > 0:
                i -= 1
        else:
            i += 1
    return xs, ys


def fit_anchor(theta_cr_points):
    """Monotone map theta -> CR through calibrator points [(theta, cr), ...].
    Linear interpolation in theta with isotonic-smoothed CRs; flat-clamps outside."""
    pts = sorted(theta_cr_points)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    xs, ys = _isotonic(xs, ys)

    def m(theta: float) -> float:
        if theta <= xs[0]:
            return ys[0]
        if theta >= xs[-1]:
            return ys[-1]
        for i in range(len(xs) - 1):
            if xs[i] <= theta <= xs[i + 1]:
                t = (theta - xs[i]) / (xs[i + 1] - xs[i])
                return ys[i] + t * (ys[i + 1] - ys[i])
        return ys[-1]
    return m
