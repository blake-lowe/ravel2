"""§3.7 3D AoE (sphere vs cylinder), §4.6 burrow/hover, §10.4 Silence/verbal,
§10.10 Dispel Magic / Antimagic Field / Absorb Elements."""
from __future__ import annotations

from ravel import cast, content, spells
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import AuraState, Option
from ravel.rules import apply_condition, apply_damage


def enc_with(a_names, b_names, seed=1, b_x=6, w=24, h=18):
    combs = []
    for i, n in enumerate(a_names):
        combs.append(content.make(n, f"A{i + 1}", "A", (2, 2 + i * 2)))
    for i, n in enumerate(b_names):
        combs.append(content.make(n, f"B{i + 1}", "B", (b_x, 2 + i)))
    enc = Encounter(Grid(w, h), combs, RNG(seed))
    enc.roll_initiative()
    return enc


def opt(spell, target_id, slot=0):
    return Option("o", "spell", spell, target_id, "", spell=spell, slot_level=slot)


# -- §3.7 3D AoE: sphere respects altitude, cylinder does not -------------

def test_sphere_is_3d_a_flyer_above_the_blast_escapes():
    enc = enc_with(["Mage"], ["Goblin", "Goblin"], b_x=8)
    mage, ground, flyer = (enc.combatants["A1"], enc.combatants["B1"],
                           enc.combatants["B2"])
    ground.pos = flyer.pos = (8, 4)         # same column, the blast point
    ground.alt = 0
    flyer.alt = 40                          # 40 ft up — outside a 20 ft Fireball sphere
    sp = spells.get("Fireball")             # sphere, radius 20
    caught = cast.area_targets(enc, mage, sp, ground)
    assert ground in caught
    assert flyer not in caught              # 3D: the high flyer is out of the ball


def test_cylinder_catches_any_altitude_within_radius():
    enc = enc_with(["Priest"], ["Goblin"], b_x=8)
    priest, flyer = enc.combatants["A1"], enc.combatants["B1"]
    flyer.pos = (8, 4)
    flyer.alt = 60                          # far overhead
    sp = spells.get("Moonbeam")             # now a cylinder, radius 5
    caught = cast.area_targets(enc, priest, sp, flyer)
    assert flyer in caught                  # a cylinder reaches any altitude in its column


# -- §4.6 burrow & hover --------------------------------------------------

def test_burrower_tunnels_under_a_chasm():
    # a full-height ravine: columns 4-7 are chasm across every row
    grid = Grid(12, 8, chasm={(c, y): 999 for c in range(4, 8) for y in range(8)})
    walk = grid.reachable((1, 3), 1, 200, set())
    burrow = grid.reachable((1, 3), 1, 200, set(), can_burrow=True)
    assert (9, 3) not in walk               # a walker can't cross the ravine
    assert (9, 3) in burrow                 # a burrower tunnels under it


def test_nonhover_flyer_falls_when_stunned():
    enc = enc_with(["Manticore"], ["Goblin"])
    m = enc.combatants["A1"]
    m.alt = 30
    apply_condition(m, "stunned", "x", enc.rng, enc.log)
    hp0 = m.hp
    enc.enforce_flight(m)
    assert m.alt == 0
    assert m.hp < hp0                       # took fall damage
    assert m.has("prone")


def test_restrained_flyer_falls():
    # PHB: a non-hovering flyer reduced to speed 0 (restrained/grappled) falls
    enc = enc_with(["Manticore"], ["Goblin"])
    m = enc.combatants["A1"]
    m.alt = 30
    apply_condition(m, "restrained", "x", enc.rng, enc.log)
    enc.enforce_flight(m)
    assert m.alt == 0 and m.has("prone")


def test_hover_flyer_stays_aloft_when_stunned():
    from dataclasses import replace
    enc = enc_with(["Manticore"], ["Goblin"])
    m = enc.combatants["A1"]
    m.md = replace(m.md, hover=True)         # isolated copy — don't mutate the shared def
    m.alt = 30
    apply_condition(m, "stunned", "x", enc.rng, enc.log)
    enc.enforce_flight(m)
    assert m.alt == 30                       # hover: no fall


# -- §10.4 Silence blocks verbal-component casting ------------------------

def test_silence_blocks_verbal_spells():
    enc = enc_with(["Priest"], ["Mage"], b_x=6)
    priest, mage = enc.combatants["A1"], enc.combatants["B1"]
    mage.reaction_available = False                      # so it can't Counterspell the Silence
    cast.cast(enc, priest, opt("Silence", mage.id, 2))   # zone lands on the mage
    assert enc.is_silenced(mage)
    opts = cast.enumerate_spell_options(enc, mage, "action")
    assert opts == []                        # every wizard spell here needs a verbal component
    before = mage.slots.get(3, 0)
    cast.cast(enc, mage, opt("Fireball", priest.id, 3))  # try anyway
    assert mage.slots.get(3, 0) == before    # cast was blocked, no slot spent


def test_silence_blocks_counterspell_reaction():
    enc = enc_with(["Mage"], ["Mage"], b_x=5)
    caster, foe = enc.combatants["A1"], enc.combatants["B1"]
    # silence the would-be counterspeller
    caster.aura = AuraState(spell="Silence", source_id=caster.id, shape="sphere",
                            size=20, save=None, dc=0, anchor="point", point=foe.pos,
                            silence=True)
    assert enc.offer_counterspell(caster, spells.get("Fireball")) is False


# -- §10.10 Dispel Magic --------------------------------------------------

def test_dispel_ends_enemy_concentration_and_buff():
    enc = enc_with(["Mage"], ["Priest"], b_x=5)
    mage, priest = enc.combatants["A1"], enc.combatants["B1"]
    cast.cast(enc, priest, opt("Bless", priest.id, 1))   # priest concentrates on Bless
    assert priest.concentration is not None
    assert any(e.name == "Bless" for e in priest.effects)
    cast.cast(enc, mage, opt("Dispel Magic", priest.id, 3))
    assert priest.concentration is None                   # 1st-lvl spell, auto-dispelled
    assert not any(e.name == "Bless" for e in priest.effects)


def test_dispel_removes_spell_condition():
    enc = enc_with(["Mage"], ["Goblin"], b_x=5)
    mage, gob = enc.combatants["A1"], enc.combatants["B1"]
    apply_condition(gob, "paralyzed", "src", enc.rng, enc.log, spell_level=2)
    cast.cast(enc, mage, opt("Dispel Magic", gob.id, 3))
    assert not gob.has("paralyzed")


# -- §10.10 Antimagic Field ----------------------------------------------

def test_antimagic_blocks_casting_and_spells_fizzle():
    enc = enc_with(["Mage"], ["Mage"], b_x=5)
    a, b = enc.combatants["A1"], enc.combatants["B1"]
    a.aura = AuraState(spell="Antimagic Field", source_id=a.id, shape="sphere",
                       size=10, save=None, dc=0, anchor="caster", antimagic=True)
    assert enc.in_antimagic(a)
    # the antimagic caster cannot cast other spells
    assert cast.enumerate_spell_options(enc, a, "action") == []
    # a spell from outside has no effect on someone standing in the field
    b.pos = a.pos                            # B steps into A's field
    hp0 = b.hp
    out = content.make("Mage", "C1", "A", (12, 12))
    enc.combatants["C1"] = out
    cast.cast(enc, out, opt("Fireball", b.id, 3))
    assert b.hp == hp0                       # fizzled inside the antimagic field


# -- §10.10 Absorb Elements ----------------------------------------------

def test_absorb_elements_halves_and_riders_next_melee():
    enc = enc_with(["Mage"], ["Mage"], b_x=5)
    attacker, mage = enc.combatants["A1"], enc.combatants["B1"]
    mage.reaction_available = True
    before = mage.slots.get(1, 0)
    taken = enc.absorb(mage, "fire", 20)
    assert taken == 10                       # resisted to half
    assert mage.slots.get(1, 0) == before - 1
    assert mage.absorb_rider is not None and mage.absorb_rider.type == "fire"


def test_absorb_does_nothing_for_nonelemental():
    enc = enc_with(["Mage"], ["Mage"], b_x=5)
    mage = enc.combatants["B1"]
    assert enc.absorb(mage, "force", 20) == 20   # force isn't an Absorb element
    assert mage.absorb_rider is None


def test_silence_zone_does_not_wander():
    enc = enc_with(["Priest"], ["Goblin"], b_x=6)   # Goblin can't Counterspell
    p, g = enc.combatants["A1"], enc.combatants["B1"]
    cast.cast(enc, p, opt("Silence", g.id, 2))
    where = p.aura.point
    enc.start_of_turn(p)                              # Moonbeam would re-aim here; Silence must not
    assert p.aura.point == where


def test_absorb_rider_clears_at_end_of_turn():
    from ravel.controllers import HeuristicController
    from ravel.dice import Damage
    enc = enc_with(["Mage"], ["Goblin"], b_x=12)      # too far to melee-consume the rider
    mage = enc.combatants["A1"]
    mage.absorb_rider = Damage(1, 6, 0, "fire")
    enc.take_turn(mage, HeuristicController())
    assert mage.absorb_rider is None                  # lapses at end of its next turn
