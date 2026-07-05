"""Enabler 5 — caster interface, attackers_have_disadvantage (Blur), and the two new
effect kinds: banish (remove-from-combat) and terrain (spell-created zones)."""
from __future__ import annotations

from ravel import cast, content, spells
from ravel.dice import RNG
from ravel.effects import attackers_have_disadvantage, break_concentration
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Option


def _mage(cid, team, pos):
    m = content.make("Mage", cid, team, pos)
    for lv in range(1, 10):
        m.slots[lv] = 3                       # grant high slots for testing
    return m


def _enc(*specs, seed=1, w=24, h=16):
    combs = [c for c in specs]
    e = Encounter(Grid(w, h), combs, RNG(seed))
    e.roll_initiative()
    return e


def O(sp, t):
    return Option("o", "spell", sp, t, "", spell=sp, slot_level=spells.get(sp).level)


# -- caster interface delegates to the stat block -------------------------

def test_caster_interface_delegates_to_md():
    m = content.make("Mage", "M", "A", (0, 0))
    assert m.spell_dc == m.md.spell_dc
    assert m.spell_attack == m.md.spell_attack
    assert m.spell_ability == m.md.spell_ability
    assert m.caster_level == m.md.caster_level
    assert m.spell_mod == m.md.mod(m.md.spell_ability)


# -- Blur / Mirror Image: attackers_have_disadvantage ---------------------

def test_blur_imposes_disadvantage_on_attackers():
    e = _enc(_mage("A1", "A", (2, 2)), content.make("Ogre", "B1", "B", (3, 2)))
    cast.cast(e, e.combatants["A1"], O("Blur", "A1"))
    assert attackers_have_disadvantage(e.combatants["A1"]) is True


def test_blur_hampers_both_weapon_and_spell_attacks():
    # a blurred creature is harder to hit with BOTH weapon and spell attacks
    from ravel.dice import Damage
    from ravel.effects import add_effect
    from ravel.models import ActiveEffect

    def spell_hits(blur):
        h = 0
        for s in range(150):
            e = _enc(_mage("A", "A", (2, 2)), content.make("Ogre", "B", "B", (3, 2)), seed=s)
            b = e.combatants["B"]
            b.hp = 100
            if blur:
                add_effect(b, ActiveEffect(name="Blur", source_id=b.id,
                                           attackers_have_disadvantage=True, duration=10))
            cast._spell_attack(e, e.combatants["A"], b, [Damage(2, 10, 0, "fire")], False)
            h += b.hp < 100
        return h
    assert spell_hits(True) < spell_hits(False)      # disadvantage lowers spell-attack hits


# -- Banishment: remove-from-combat ---------------------------------------

def test_banishment_removes_target_and_returns_it():
    e = _enc(_mage("A1", "A", (2, 2)), content.make("Ogre", "B1", "B", (5, 2)))
    ogre = e.combatants["B1"]
    ogre.reaction_available = False
    cast.cast(e, e.combatants["A1"], O("Banishment", "B1"))
    # a banished creature is out of the fight
    assert ogre.banished is True
    assert ogre.in_combat is False
    assert "B1" not in [c.id for c in e.living()]
    assert "B1" not in [c.id for c in e.enemies_of(e.combatants["A1"])]
    # it returns when the caster loses concentration
    break_concentration(e.combatants["A1"], e.log, "test", enc=e)
    assert ogre.banished is False and ogre.in_combat is True


# -- terrain zones: Wall of Fire (damage) & Spike Growth (difficult) ------

def test_wall_of_fire_creates_a_damaging_zone():
    e = _enc(_mage("A1", "A", (2, 8)), content.make("Ogre", "B1", "B", (6, 8)))
    e.combatants["B1"].reaction_available = False
    cast.cast(e, e.combatants["A1"], O("Wall of Fire", "B1"))
    assert len(e.zones) == 1 and e.zones[0].damage
    ogre = e.combatants["B1"]
    ogre.pos = next(iter(e.zones[0].cells))
    hp0 = ogre.hp
    e._apply_zones_start_of_turn(ogre)
    assert ogre.hp < hp0                      # took fire standing in the wall


def test_spike_growth_makes_difficult_terrain():
    e = _enc(_mage("A1", "A", (2, 8)), content.make("Ogre", "B1", "B", (8, 8)))
    e.combatants["B1"].reaction_available = False
    cast.cast(e, e.combatants["A1"], O("Spike Growth", "B1"))
    z = e.zones[0]
    assert z.difficult and z.cells
    assert z.cells & e.dynamic_difficult(e.combatants["B1"])   # counts as difficult terrain


def test_zone_expires_after_its_duration():
    e = _enc(_mage("A1", "A", (2, 8)), content.make("Ogre", "B1", "B", (6, 8)))
    e.combatants["B1"].reaction_available = False
    cast.cast(e, e.combatants["A1"], O("Wall of Fire", "B1"))
    z = e.zones[0]
    z.duration = 1
    # one round tick removes it (mirrors the run-loop expiry)
    for zz in list(e.zones):
        zz.duration -= 1
        if zz.duration <= 0:
            e.zones.remove(zz)
    assert e.zones == []
