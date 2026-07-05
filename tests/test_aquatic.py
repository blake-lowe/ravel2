"""Aquatic / underwater combat (ENVIRONMENT.md §3)."""
from __future__ import annotations

import sys
from pathlib import Path

from ravel import content
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.rules import apply_damage, resolve_attack

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.trait_routing import route_all  # noqa: E402


def _uw(a="Merfolk", b="Commoner"):
    e = Encounter(Grid(20, 8), [content.make(a, "A", "A", (2, 4)),
                  content.make(b, "B", "B", (16, 4))], RNG(1), roll_hp=False,
                  underwater=True)
    return e, e.combatants["A"], e.combatants["B"]


def test_water_breathing_detection():
    for text in ("Amphibious", "Limited Amphibiousness", "Water Breathing"):
        d = {"traits": [{"name": text, "text": "breathes air and water."}]}
        assert "water_breathing" in route_all(d)


def test_air_breather_holds_breath_then_drowns_water_breather_exempt():
    e, merfolk, commoner = _uw()
    assert merfolk.breath_rounds is None            # aquatic: exempt
    assert commoner.breath_rounds == 11             # CON 10 -> 10 hold + 1 choke
    n = 0
    while commoner.alive and n < 40:
        e.start_of_turn(commoner)
        n += 1
    assert n == 11 and commoner.hp == 0             # drowns on schedule
    for _ in range(40):
        e.start_of_turn(merfolk)
    assert merfolk.alive                            # never drowns


def test_fire_resistance_underwater():
    e, _, c = _uw()
    c.hp = 100
    apply_damage(c, 40, "fire", e.log, e.rng, enc=e)
    assert 100 - c.hp == 20                          # fully immersed -> half fire


def test_melee_penalty_non_piercing_non_swimmer():
    from ravel.models import AttackDef, Damage
    slash = AttackDef(name="Sword", kind="melee", attack_bonus=4,
                      damage=(Damage(1, 8, 2, "slashing"),))
    pierce = AttackDef(name="Spear", kind="melee", attack_bonus=4,
                       damage=(Damage(1, 8, 2, "piercing"),))

    def hits(atk):
        h = 0
        for s in range(300):
            e = Encounter(Grid(12, 6), [content.make("Guard", "G", "A", (3, 3)),
                          content.make("Commoner", "T", "B", (4, 3))], RNG(s),
                          roll_hp=False, underwater=True)   # Guard has no swim speed
            t = e.combatants["T"]
            t.hp = 60
            h += resolve_attack(e.combatants["G"], t, atk, e.rng, e.log, enc=e)
        return h
    assert hits(slash) < hits(pierce)               # slashing flails, spear is fine underwater
