"""Druid (Slice 6 WP3): full WIS caster, Wild Shape (the shapechange primitive), and the
Circle of the Moon (Combat Wild Shape) / Circle of the Land (Natural Recovery) circles.
PHB-checkable numbers + an arena smoke + a determinism check."""
from __future__ import annotations

from ravel import content
from ravel.character import (compile_character, make_character, to_combatant,
                             validate_character, wild_shape_max_cr)
from ravel.controllers import HeuristicController
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Ability as A
from ravel.rest import short_rest
from ravel.rules import apply_damage

# WIS 16 (+3). Druid is a full WIS caster.
ARR = {A.STR: 10, A.DEX: 12, A.CON: 14, A.INT: 10, A.WIS: 16, A.CHA: 8}


def _druid(level, sub="", spells=("Cure Wounds", "Healing Word"), forms=("Brown Bear",), **kw):
    return make_character("Fen", "Half-Elf", "Druid", level, ARR, subclass=sub,
                          spells=spells, wild_shapes=forms, **kw)


def test_druid2_slots_wild_shape_uses_and_forms():
    md = compile_character(_druid(2, "Circle of the Moon"))
    assert md.spell_slots == {1: 3}                        # full caster at level 2
    assert md.spell_ability == A.WIS
    assert md.wild_shape_forms == ("Brown Bear",)
    pc = to_combatant(_druid(2, "Circle of the Moon"), "A", "A", (1, 1))
    assert pc.resources["Wild Shape"] == 2                 # two uses per short rest


def test_wild_shape_cr_caps_and_validation():
    assert (wild_shape_max_cr(2, False), wild_shape_max_cr(4, False),
            wild_shape_max_cr(8, False)) == (0.25, 0.5, 1.0)
    assert (wild_shape_max_cr(2, True), wild_shape_max_cr(6, True)) == (1.0, 2.0)
    # a Brown Bear (CR 1) is too big for a land druid 2 (cap 1/4) but fine for a Moon druid 2
    assert any("exceeds" in w for w in validate_character(_druid(2)))
    assert not any("exceeds" in w for w in validate_character(_druid(2, "Circle of the Moon")))


def test_moon_druid_shapes_into_a_bear_fights_and_reverts_at_0_with_druid_hp_intact():
    pc = to_combatant(_druid(2, "Circle of the Moon"), "A", "A", (1, 1))
    druid_hp = pc.hp                                       # the druid's own HP pool
    foe = content.make("Ogre", "B", "B", (1, 2))
    e = Encounter(Grid(6, 6), [pc, foe], RNG(1), roll_hp=False)
    e.roll_initiative()
    # Combat Wild Shape is a bonus action for the Moon druid
    ws = next(o for o in e.enumerate_bonus_options(pc) if o.name == "Brown Bear")
    e.apply(pc, ws)
    assert pc.base_md is not None                          # now in beast form
    assert pc.md.name == "Brown Bear" and pc.hp == 34      # separate beast HP pool
    assert pc.ac == 11 and set(pc.attacks) == {"Bite", "Claws"}   # beast's body + attacks
    assert pc.md.mod(A.WIS) == 3                           # ...but keeps the druid's mental stats
    # drop the beast form to exactly 0 -> revert to the druid, HP intact (no excess carryover)
    apply_damage(pc, 34, "slashing", e.log, e.rng, enc=e)
    assert pc.base_md is None                              # reverted
    assert pc.md.name == "Fen" and pc.hp == druid_hp       # the druid is back, HP untouched


def test_wild_shape_round_trips_through_serialization():
    from ravel.character import character_from_dict, character_to_dict
    ch = _druid(4, "Circle of the Moon", forms=("Brown Bear", "Dire Wolf"))
    ch2 = character_from_dict(character_to_dict(ch))
    assert ch2.wild_shapes == ("Brown Bear", "Dire Wolf")
    assert compile_character(ch2).wild_shape_forms == ("Brown Bear", "Dire Wolf")


def test_combat_wild_shape_heal_spends_a_slot_in_form():
    pc = to_combatant(_druid(4, "Circle of the Moon"), "A", "A", (1, 1))
    foe = content.make("Ogre", "B", "B", (5, 5))
    e = Encounter(Grid(10, 10), [pc, foe], RNG(1), roll_hp=False)
    e.roll_initiative()
    e.apply_wild_shape(pc, "Brown Bear")
    pc.hp = 5                                              # wounded in beast form
    slots = dict(pc.slots)
    heal = next(o for o in e.enumerate_bonus_options(pc) if o.kind == "moon_heal")
    e.apply(pc, heal)
    assert pc.hp > 5                                       # regained 1d8 per slot level
    assert sum(pc.slots.values()) == sum(slots.values()) - 1


def test_land_druid_natural_recovery_restores_slots_on_a_short_rest():
    ch = _druid(4, "Circle of the Land")
    pc = to_combatant(ch, "A", "A", (1, 1))
    assert pc.resources["Natural Recovery"] == 1
    pc.slots[1] = 0
    pc.slots[2] = 0
    short_rest(pc, RNG(1), ch)
    # half druid level (2) budget recovers one 2nd-level slot (highest first)
    assert pc.slots[2] == 1
    assert pc.resources["Natural Recovery"] == 0


def _fight(seed):
    pc = to_combatant(_druid(4, "Circle of the Moon", forms=("Brown Bear", "Dire Wolf")),
                      "A", "A", (2, 3))
    e = Encounter(Grid(14, 6), [pc, content.make("Ogre", "B", "B", (9, 3))], RNG(seed),
                  roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    return e


def test_druid_arena_smoke_and_determinism():
    e1 = _fight(5)
    e2 = _fight(5)
    assert e1.log == e2.log
    assert e1.winner() in ("A", "B")
    assert any("Wild Shape" in line for line in e1.log)
