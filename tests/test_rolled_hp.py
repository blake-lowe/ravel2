"""Rolling HP from hit dice at initialization (default on; opt out with roll_hp=False)."""
from __future__ import annotations

from ravel import content
from ravel.dice import RNG
from ravel.engine import Encounter, _roll_hit_points
from ravel.grid import Grid


def _one(name, roll_hp, seed=1):
    c = content.make(name, "A0", "A", (1, 1))
    g = content.make("Goblin", "B0", "B", (5, 1))
    Encounter(Grid(12, 8), [c, g], RNG(seed), roll_hp=roll_hp)
    return c


def test_roll_hp_default_on_sets_rolled_max_and_current():
    ogre = _one("Ogre", roll_hp=True)
    assert ogre.rolled_max_hp is not None
    assert ogre.hp == ogre.rolled_max_hp == ogre.max_hp   # starts full at the rolled value


def test_roll_hp_opt_out_uses_average():
    ogre = _one("Ogre", roll_hp=False)
    assert ogre.rolled_max_hp is None
    assert ogre.hp == ogre.max_hp == ogre.md.hp           # the stat-block average


def test_rolled_hp_is_deterministic_per_seed():
    assert _one("Troll", True, seed=42).hp == _one("Troll", True, seed=42).hp
    # different seeds generally give different rolls across a spread
    rolls = {_one("Troll", True, seed=s).hp for s in range(12)}
    assert len(rolls) > 1


def test_roll_within_hit_dice_bounds():
    # 7d10+21 -> between 7+21=28 and 70+21=91
    for s in range(30):
        hp = _roll_hit_points("7d10+21", RNG(s))
        assert 28 <= hp <= 91


def test_no_hit_dice_falls_back_to_average():
    assert _roll_hit_points("", RNG(1)) is None
    # a summon with no hit dice keeps its average HP even with rolling on
    sw = _one("Spiritual Weapon", roll_hp=True) if "Spiritual Weapon" in \
        content.all_names() else None
    if sw is not None:
        assert sw.rolled_max_hp is None
