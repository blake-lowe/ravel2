"""Enabler 4 — movement/space modes v2: phasing (incorporeal), teleport, and the
swallow/containment mechanic."""
from __future__ import annotations

from ravel import content
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Option
from ravel.rules import apply_condition, apply_damage


def enc_of(*specs, seed=1, w=20, h=16, **grid_kw):
    combs = [content.make(n, cid, team, pos) for (n, cid, team, pos) in specs]
    e = Encounter(Grid(w, h, **grid_kw), combs, RNG(seed))
    e.roll_initiative()
    return e


# -- phasing / incorporeal -------------------------------------------------

def test_phaser_moves_through_walls_but_lands_on_empty_cells():
    walls = {(x, 3) for x in range(20)}          # a solid wall across the map
    g = Grid(20, 8, walls=walls)
    blocked = {(5, 1)}                            # a creature in the way
    normal = g.reachable((4, 1), 1, 100, blocked)
    phase = g.reachable((4, 1), 1, 100, blocked, can_phase=True)
    assert (5, 5) not in normal                   # a walker is stopped by the wall
    assert (5, 5) in phase                        # a phaser passes through and lands beyond
    assert (5, 3) not in phase                    # ...but can't LAND inside the wall
    assert (5, 1) not in phase                    # ...or end on another creature's square


def test_specter_is_incorporeal():
    s = content.get("Specter")
    assert s.incorporeal and s.fly == 50 and s.hover


# -- teleport --------------------------------------------------------------

def test_teleport_counts_toward_move_budget():
    e = enc_of(("Blink Dog", "A", "A", (2, 2)), ("Goblin", "B", "B", (10, 2)))
    dog = e.combatants["A"]
    assert dog.md.teleport == 40
    assert e._move_budget(dog) >= 40              # teleport range is usable movement


# -- swallow / containment -------------------------------------------------

def _swallow(e, toad_id="T", prey_id="V"):
    t, v = e.combatants[toad_id], e.combatants[prey_id]
    apply_condition(v, "grappled", t.id, e.rng, e.log)
    e.apply(t, Option("o", "swallow", "Swallow", v.id, ""))
    return t, v


def test_swallow_sets_containment_state():
    e = enc_of(("Giant Toad", "T", "A", (5, 5)), ("Bugbear", "V", "B", (6, 5)))
    t, v = _swallow(e)
    assert v.swallowed_by == "T"
    assert v.has("blinded") and v.has("restrained")
    assert v.pos == t.pos                          # it rides along inside


def test_swallowed_creature_takes_acid_each_turn():
    e = enc_of(("Giant Toad", "T", "A", (5, 5)), ("Bugbear", "V", "B", (6, 5)))
    t, v = _swallow(e)
    hp0 = v.hp
    e.start_of_turn(v)
    assert v.hp < hp0                              # digestive acid


def test_swallowed_creature_can_only_strike_its_captor():
    e = enc_of(("Giant Toad", "T", "A", (5, 5)), ("Bugbear", "V", "B", (6, 5)),
               ("Giant Toad", "T2", "A", (7, 5)))
    t, v = _swallow(e)
    opts = e.enumerate_options(v)
    tgts = {o.target_id for o in opts if o.kind in ("attack", "multiattack")}
    assert tgts <= {"T"}                           # total cover: only the captor is reachable


def test_a_foe_swallowed_by_another_has_total_cover():
    e = enc_of(("Giant Toad", "T", "A", (5, 5)), ("Bugbear", "V", "B", (6, 5)),
               ("Scout", "S", "A", (8, 5)))
    _swallow(e)
    opts = e.enumerate_options(e.combatants["S"])   # S is an ally of the toad
    tgts = {o.target_id for o in opts}
    assert "V" not in tgts                          # can't be targeted from outside


def test_slaying_the_swallower_expels_the_prey():
    e = enc_of(("Giant Toad", "T", "A", (5, 5)), ("Bugbear", "V", "B", (6, 5)))
    t, v = _swallow(e)
    t.hp = 6
    apply_damage(t, 12, "slashing", e.log, e.rng, enc=e)   # kill the toad
    assert not t.alive
    assert v.swallowed_by is None
    assert not v.has("restrained") and not v.has("blinded")
    assert v.has("prone")                           # expelled, prone
