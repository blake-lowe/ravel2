"""Ground-covering hazard terrain (ENVIRONMENT.md §2): lava/acid/grease/ice."""
from __future__ import annotations

from ravel import content
from ravel.dice import RNG, Damage
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Zone


def _lava():
    return Zone("lava", {(5, 3)}, damage=(Damage(6, 10, 0, "fire"),), on_enter=True,
                half_on_save=False, light=20, duration=999)


def _enc(hazards, a="Ogre", b="Ogre"):
    g = Grid(12, 6, ambient=0.0, hazards=hazards)
    e = Encounter(g, [content.make(a, "A", "A", (1, 3)),
                  content.make(b, "B", "B", (10, 3))], RNG(1), roll_hp=False)
    return e, e.combatants["A"]


def test_lava_damages_on_enter_and_start_of_turn_and_glows():
    e, o = _enc([_lava()])
    o.hp = 300
    assert e.light_level((5, 3)) == "bright"      # lava glows in the dark
    e._do_move(o, (5, 3))
    assert o.hp < 300                             # burned on entering
    hp1 = o.hp
    e._apply_zones_start_of_turn(o)
    assert o.hp < hp1                             # and again for starting its turn there


def test_fire_immune_creature_shrugs_off_lava():
    e, fg = _enc([_lava()], a="Fire Giant")       # immune to fire
    hp0 = fg.hp
    e._do_move(fg, (5, 3))
    assert fg.hp == hp0


def test_grease_trips_prone_and_ignites_into_fire():
    grease = Zone("grease", {(5, 3), (6, 3)}, difficult=True, prone_save=99,   # DC99 = auto-fail
                  flammable=True, duration=999)
    e, gob = _enc([grease], a="Goblin")
    e._do_move(gob, (5, 3))
    assert gob.has("prone")                       # slipped in the grease

    # a fire source touching the grease ignites it
    e.zones.append(Zone("flames", {(7, 3)}, damage=(Damage(1, 6, 0, "fire"),),
                        light=20, duration=5))
    e._spread_fire()
    assert not grease.flammable and any(d.type == "fire" for d in grease.damage)


def test_pushed_into_lava_burns():
    from ravel import cast
    e, o = _enc([_lava()])
    pusher = e.combatants["B"]
    pusher.pos = (3, 3)                            # west of the ogre, so it shoves east
    o.pos = (4, 3)                                 # ogre just west of the lava at (5,3)
    o.hp = 200
    cast._push(e, pusher, o, 5)                    # shove 5 ft east -> into the lava
    assert o.pos == (5, 3) and o.hp < 200


def test_lava_cavern_map_has_hazards():
    from ravel.sim import build_encounter
    enc = build_encounter(["Ogre"], ["Ogre"], 1, map_name="lava_cavern")
    kinds = {z.name for z in enc.grid.hazards}
    assert "lava" in kinds and "grease" in kinds
