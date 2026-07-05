"""Seeded randomness and dice. The ONLY source of nondeterminism in the engine.

Everything that needs randomness takes an RNG instance explicitly. No module-level
random, no time, no uuid. Same seed + same decisions => identical results.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


class RNG:
    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._r = random.Random(seed)

    def randint(self, a: int, b: int) -> int:
        return self._r.randint(a, b)

    def choice(self, seq):
        return self._r.choice(seq)

    def d(self, sides: int) -> int:
        return self._r.randint(1, sides)

    def d20(self, advantage: int = 0) -> tuple[int, int | None]:
        """Roll a d20. advantage: +1 advantage (2 dice keep high), -1 disadvantage,
        0 normal, +2 Elven Accuracy (3 dice keep high). Returns (used, other_or_None);
        the raw die is returned so callers can detect natural 1 / natural 20.
        """
        a = self._r.randint(1, 20)
        if advantage == 0:
            return a, None
        if advantage >= 2:                         # Elven Accuracy: roll three, keep best
            return max(a, self._r.randint(1, 20), self._r.randint(1, 20)), a
        b = self._r.randint(1, 20)
        if advantage > 0:
            return (a, b) if a >= b else (b, a)
        return (a, b) if a <= b else (b, a)

    def _one_die(self, sides: int, reroll_below: int, min_die: int, exploding: bool) -> int:
        v = self._r.randint(1, sides)
        if reroll_below and v <= reroll_below:     # Great Weapon Fighting: reroll 1s/2s once
            v = self._r.randint(1, sides)
        if min_die and v < min_die:
            v = min_die
        total = v
        while exploding and v == sides:            # exploding dice: max rolls again
            v = self._r.randint(1, sides)
            total += v
        return total

    def roll(self, count: int, sides: int, bonus: int = 0, crit: bool = False,
             reroll_below: int = 0, min_die: int = 0, exploding: bool = False) -> int:
        n = count * 2 if crit else count
        total = bonus
        for _ in range(n):
            total += self._one_die(sides, reroll_below, min_die, exploding)
        return total

    def keep(self, count: int, sides: int, keep_n: int, highest: bool = True) -> int:
        """Roll `count` dice, keep the best/worst `keep_n` (e.g. 4d6 keep 3)."""
        rolls = sorted((self._r.randint(1, sides) for _ in range(count)),
                       reverse=highest)
        return sum(rolls[:keep_n])


import re

_DICE_RE = re.compile(r"^\s*(\d+)\s*d\s*(\d+)\s*([+-]\s*\d+)?\s*$", re.I)


def parse_dice(expr: str) -> tuple[int, int, int]:
    """Parse 'NdM', 'NdM+K', 'NdM-K' -> (count, sides, bonus)."""
    m = _DICE_RE.match(expr)
    if not m:
        raise ValueError(f"bad dice expression: {expr!r}")
    bonus = int(m.group(3).replace(" ", "")) if m.group(3) else 0
    return int(m.group(1)), int(m.group(2)), bonus


@dataclass(frozen=True)
class Damage:
    count: int
    sides: int
    bonus: int
    type: str  # DamageType value
    reroll_below: int = 0     # Great Weapon Fighting rerolls dice <= this once
    min_die: int = 0
    exploding: bool = False

    def roll(self, rng: RNG, crit: bool = False) -> int:
        return max(0, rng.roll(self.count, self.sides, self.bonus, crit=crit,
                               reroll_below=self.reroll_below, min_die=self.min_die,
                               exploding=self.exploding))

    def average(self) -> int:
        return int(self.count * (self.sides + 1) / 2) + self.bonus
