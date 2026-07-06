"""Idle-turn probe: mirror 1v1s across the roster, counting turns where a
monster produces no action line (attack/area/spell/ready/swallow...) — the
signature of a heuristic-controller dead end. Run with PYTHONPATH=. .

    python tools/idle_probe.py [minCR] [maxCR]
"""
import re
import sys

from ravel import content
from ravel.sim import run_battle

SEEDS = (11, 23)
ACT = re.compile(r" vs |'s .* hits| casts | readies | dashes| swallows| uses "
                 r"|breath|Breath| drains| turns to flee| escapes the battle")
TURN = re.compile(r"^-- (A1|B1) \(")


def probe(name: str) -> tuple[float, int, int]:
    idle = turns = draws = 0
    for seed in SEEDS:
        r = run_battle([name], [name], seed=seed, ai="heuristic", roll_hp=False)
        if r.winner not in ("A", "B"):
            draws += 1
        cur, acted, moved = None, True, False
        rounds_seen = 0
        for line in r.log + ["-- A1 (end) turn"]:
            m = TURN.match(line)
            if m:
                if cur is not None and rounds_seen > 1:   # skip round-1 approach
                    turns += 1
                    if not acted:
                        idle += 1
                cur, acted = m.group(1), False
                if m.group(1) == "A1":
                    rounds_seen += 1
                continue
            if ACT.search(line):
                acted = True
    return (idle / turns if turns else 0.0), draws, turns


def main():
    lo = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    hi = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    rows = []
    for name in sorted(content.all_names()):
        md = content.get(name)
        if not (lo <= md.cr <= hi) or name == "Spiritual Weapon":
            continue
        frac, draws, turns = probe(name)
        if frac > 0.15 or draws:
            rows.append((frac, draws, turns, md.cr, name))
    rows.sort(reverse=True)
    print(f"{'idle%':>6s} {'draws':>5s} {'turns':>5s} {'CR':>5s}  name")
    for frac, draws, turns, cr, name in rows:
        print(f"{100 * frac:5.0f}% {draws:5d} {turns:5d} {cr:5.1f}  {name}")


if __name__ == "__main__":
    main()
