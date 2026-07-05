"""Lighting & vision (ENVIRONMENT.md §1): light field, can_see, attack (dis)advantage."""
from __future__ import annotations

from ravel import content
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Light
from ravel.rules import resolve_attack


def _enc(grid, a="Drow", b="Guard", seed=1):
    e = Encounter(grid, [content.make(a, "A", "A", (3, 4)),
                  content.make(b, "B", "B", (4, 4))], RNG(seed), roll_hp=False)
    return e, e.combatants["A"], e.combatants["B"]


def test_default_grid_is_bright_not_sunlit():
    e, a, b = _enc(Grid(20, 10))
    assert e.light_level((5, 5)) == "bright"
    assert e.in_sunlight((5, 5)) is False          # default bright is NOT sunlight
    assert e.can_see(a, b) and e.can_see(b, a)     # everyone sees -> no combat change


def test_torch_bands_match_5e_radii():
    g = Grid(30, 10, ambient=0.0)
    g.lights.append(Light(bright_radius=20, origin=(10, 5)))   # bright 20, dim 40
    e, _, _ = _enc(g)
    assert e.light_level((10, 5)) == "bright"      # at the source
    assert e.light_level((14, 5)) == "bright"      # 20 ft
    assert e.light_level((18, 5)) == "dim"         # 40 ft
    assert e.light_level((19, 5)) == "dark"        # 45 ft


def test_walls_cast_shadow():
    g = Grid(30, 10, ambient=0.0, walls={(12, 5)})
    g.lights.append(Light(bright_radius=20, origin=(10, 5)))
    e, _, _ = _enc(g)
    assert e.light_level((14, 5)) == "dark"        # behind the wall


def test_darkvision_sees_in_darkness_others_dont():
    e, drow, guard = _enc(Grid(16, 8, ambient=0.0))
    assert drow.md.senses.get("darkvision", 0) >= 60     # Drow has darkvision
    assert guard.md.senses.get("darkvision", 0) == 0
    assert e.can_see(drow, guard) is True          # darkvision pierces the dark
    assert e.can_see(guard, drow) is False         # the guard is blind here


def test_unseen_attacker_advantage_and_target_disadvantage_in_dark():
    def hits(ambient, atk_id, def_id):
        h = 0
        for s in range(300):
            e, _, _ = _enc(Grid(16, 8, ambient=ambient), seed=s)
            a, d = e.combatants[atk_id], e.combatants[def_id]
            d.hp = 50
            atk = next(iter(a.md.attacks.values()))
            h += resolve_attack(a, d, atk, e.rng, e.log, enc=e)
        return h
    # the sighted Drow hits the blind Guard MORE in the dark (unseen attacker = advantage)
    assert hits(0.0, "A", "B") > hits(1.0, "A", "B")
    # the blind Guard hits the Drow LESS in the dark (can't see it = disadvantage)
    assert hits(0.0, "B", "A") < hits(1.0, "B", "A")


def _mage_caster(pos):
    m = content.make("Mage", "A", "A", pos)
    for lv in range(1, 6):
        m.slots[lv] = 3
    return m


def test_vision_spells_fog_light_daylight():
    from ravel import cast, spells
    from ravel.effects import break_concentration
    from ravel.models import Option

    def O(sp, t):
        return Option("o", "spell", sp, t, "", spell=sp, slot_level=spells.get(sp).level)

    # Fog Cloud: local heavy obscurement, dispersed when concentration ends
    e = Encounter(Grid(20, 10), [_mage_caster((2, 5)), content.make("Guard", "B", "B", (8, 5))],
                  RNG(1), roll_hp=False)
    e.roll_initiative()
    e.combatants["B"].reaction_available = False
    cast.cast(e, e.combatants["A"], O("Fog Cloud", "B"))
    assert e.fog and not e.can_see(e.combatants["A"], e.combatants["B"])
    break_concentration(e.combatants["A"], e.log, "t", enc=e)
    assert not e.fog

    # Light: the caster sheds bright light in a dark arena
    e2 = Encounter(Grid(20, 10, ambient=0.0), [_mage_caster((5, 5))], RNG(1), roll_hp=False)
    e2.roll_initiative()
    assert e2.light_level((5, 5)) == "dark"
    cast.cast(e2, e2.combatants["A"], O("Light", "A"))
    assert e2.light_level((5, 5)) == "bright"

    # Daylight dispels a lower-level Darkness zone
    e3 = Encounter(Grid(20, 10, ambient=0.0), [_mage_caster((5, 5)),
                   content.make("Guard", "B", "B", (10, 5))], RNG(1), roll_hp=False)
    e3.roll_initiative()
    e3.darkness.append({"cells": {(10, 5)}, "level": 2})
    cast.cast(e3, e3.combatants["A"], O("Daylight", "B"))
    assert not e3.darkness and e3.light_level((10, 5)) == "bright"


def test_devils_sight_pierces_magical_darkness():
    e = Encounter(Grid(16, 8), [content.make("Imp", "A", "A", (3, 4)),
                  content.make("Guard", "B", "B", (5, 4))], RNG(1), roll_hp=False)
    e.darkness.append({"cells": {(3, 4), (5, 4)}, "level": 2})
    imp, guard = e.combatants["A"], e.combatants["B"]
    assert imp.md.devils_sight
    assert e.can_see(imp, guard) is True         # Devil's Sight pierces magical darkness
    assert e.can_see(guard, imp) is False


def test_sunlight_sensitivity_disadvantage_in_sun():
    def hits(sunlit):
        h = 0
        for s in range(300):
            g = Grid(16, 8, ambient_sunlight=sunlit)   # sunlit vs plain indoor bright
            e, drow, guard = _enc(g, seed=s)
            guard.hp = 50
            atk = next(iter(drow.md.attacks.values()))
            h += resolve_attack(drow, guard, atk, e.rng, e.log, enc=e)
        return h
    assert content.get("Drow").sunlight_sensitivity
    assert hits(True) < hits(False)                # disadvantage under the sun
