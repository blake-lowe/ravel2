"""Surprise rounds, flanking (optional rule), and three-quarters cover."""
from __future__ import annotations

from ravel.controllers import HeuristicController
from ravel.grid import Grid
from ravel.sim import build_encounter


# -- surprise --------------------------------------------------------------

def test_surprised_creature_skips_first_turn_and_cannot_react():
    enc = build_encounter(["Goblin"], ["Goblin"], seed=1, surprised="B")
    a, b = enc.combatants["A1"], enc.combatants["B1"]
    assert b.surprised and not b.reaction_available    # can't react before its turn
    ahp = a.hp
    enc.take_turn(b, HeuristicController())
    assert not b.surprised                              # surprise ends after the skipped turn
    assert a.hp == ahp                                 # took no action while surprised
    assert b.reaction_available is True                # reaction restored once its turn ended


def test_surprise_only_affects_named_team():
    enc = build_encounter(["Goblin"], ["Goblin"], seed=1, surprised="B")
    assert enc.combatants["A1"].surprised is False
    assert enc.combatants["B1"].surprised is True


# -- flanking --------------------------------------------------------------

def test_flanking_opposite_sides_of_large_target():
    enc = build_encounter(["Goblin", "Goblin"], ["Ogre"], seed=1, flanking=True)
    a1, a2, ogre = (enc.combatants["A1"], enc.combatants["A2"], enc.combatants["B1"])
    ogre.pos = (10, 10)            # Large -> occupies (10,10)-(11,11)
    a1.pos = (9, 10)               # left of the body
    a2.pos = (12, 10)              # opposite (right of the body) -> target lies between
    assert enc._is_flanking(a1, ogre) is True
    a2.pos = (9, 9)                # same side (NW) -> not flanking
    assert enc._is_flanking(a1, ogre) is False


def test_flanking_requires_adjacency_not_reach():
    enc = build_encounter(["Fire Giant", "Goblin"], ["Ogre"], seed=1, flanking=True)
    giant, ally, ogre = (enc.combatants["A1"], enc.combatants["A2"], enc.combatants["B1"])
    ogre.pos = (10, 10)
    giant.pos = (7, 10)            # 15 ft away — in reach but NOT adjacent
    ally.pos = (12, 10)
    assert enc._is_flanking(giant, ogre) is False   # reach weapons don't flank


def test_flanking_incapacitated_ally_does_not_count():
    from ravel.models import Condition
    enc = build_encounter(["Goblin", "Goblin"], ["Ogre"], seed=1, flanking=True)
    a1, a2, ogre = (enc.combatants["A1"], enc.combatants["A2"], enc.combatants["B1"])
    ogre.pos = (10, 10)
    a1.pos = (9, 10)
    a2.pos = (12, 10)
    a2.conditions["stunned"] = Condition("stunned", "x")
    a2.conditions["incapacitated"] = Condition("incapacitated", "x")
    assert enc._is_flanking(a1, ogre) is False


def test_flanking_disabled_by_config():
    enc = build_encounter(["Goblin", "Goblin"], ["Ogre"], seed=1, flanking=False)
    a1, a2, ogre = (enc.combatants["A1"], enc.combatants["A2"], enc.combatants["B1"])
    ogre.pos = (10, 10)
    a1.pos, a2.pos = (9, 10), (12, 10)
    assert enc._is_flanking(a1, ogre) is False


# -- three-quarters cover --------------------------------------------------

def test_cover_tiers():
    # clear line
    assert Grid(20, 3).cover_bonus((0, 1), [(10, 1)], blockers=set()) == 0
    # intervening creature -> half cover (+2)
    assert Grid(20, 3).cover_bonus((0, 1), [(10, 1)], blockers={(5, 1)}) == 2
    # low wall / pillar on the line -> three-quarters cover (+5), LoS intact
    g = Grid(20, 3, cover_obstacles={(5, 1)})
    assert g.cover_bonus((0, 1), [(10, 1)], blockers=set()) == 5
    # full wall -> total cover (no line of sight)
    assert Grid(20, 1, walls={(5, 0)}).cover_bonus((0, 0), [(10, 0)], blockers=set()) is None
