"""Euclidean distance, 3D verticality/flyby, monster traits, wing attack,
on-enter auras, and squeezing."""
from __future__ import annotations

import math

from ravel import cast, content
from ravel.dice import RNG
from ravel.engine import SAFE_ALT, Encounter
from ravel.grid import Grid, dist3d, feet_between
from ravel.models import Ability, Option
from ravel.rules import apply_damage, saving_throw


def enc_of(a, b, seed=1, w=24, h=18):
    combs = [content.make(n, f"A{i+1}", "A", (2, 2 + i * 2)) for i, n in enumerate(a)]
    combs += [content.make(n, f"B{i+1}", "B", (8, 2 + i * 2)) for i, n in enumerate(b)]
    enc = Encounter(Grid(w, h), combs, RNG(seed))
    enc.roll_initiative()
    return enc


# -- Euclidean distance ----------------------------------------------------

def test_true_euclidean_distance():
    assert feet_between((0, 0), (3, 0)) == 15
    assert abs(feet_between((0, 0), (1, 1)) - 5 * math.sqrt(2)) < 1e-9   # diagonal ~7.07
    assert abs(dist3d((0, 0), 0, (0, 0), 20) - 20) < 1e-9               # pure altitude
    assert abs(dist3d((0, 0), 0, (3, 0), 20) - 25) < 1e-9               # 15 horiz + 20 up


# -- verticality -----------------------------------------------------------

def test_grounded_melee_cannot_reach_airborne_flyer():
    enc = enc_of(["Ogre"], ["Giant Eagle"])
    ogre, eagle = enc.combatants["A1"], enc.combatants["B1"]
    eagle.alt = SAFE_ALT
    ok, _ = enc.reachable_within(ogre, eagle, 5)     # Ogre reach 5, can't fly
    assert ok is False
    assert enc.dist(ogre, eagle) > 5


def test_desired_altitude():
    enc = enc_of(["Manticore"], ["Ogre"])
    mant, ogre = enc.combatants["A1"], enc.combatants["B1"]
    assert enc._desired_alt(mant, "ranged", ogre) == SAFE_ALT     # climb to shoot
    assert enc._desired_alt(mant, "melee", ogre) == ogre.alt      # descend to bite
    assert enc._desired_alt(ogre, "ranged", mant) == 0.0          # non-flyer stays grounded


def test_flyby_provokes_no_opportunity_attack():
    enc = enc_of(["Giant Eagle"], ["Ogre"])
    eagle, ogre = enc.combatants["A1"], enc.combatants["B1"]
    eagle.pos, ogre.pos = (11, 10), (10, 10)          # adjacent
    enc._do_move(eagle, (16, 10))                      # fly away
    assert ogre.reaction_available is True             # Flyby: no OA

    enc2 = enc_of(["Wyvern"], ["Ogre"])
    wyv, ogre2 = enc2.combatants["A1"], enc2.combatants["B1"]
    wyv.pos, ogre2.pos = (11, 10), (10, 10)
    enc2._do_move(wyv, (16, 10))                        # no flyby -> provokes
    assert ogre2.reaction_available is False


# -- monster traits --------------------------------------------------------

def test_pack_tactics_grants_advantage():
    enc = enc_of(["Wolf", "Wolf"], ["Ogre"])
    w1, w2, ogre = (enc.combatants["A1"], enc.combatants["A2"], enc.combatants["B1"])
    ogre.pos = (10, 10)
    w1.pos, w2.pos = (9, 10), (11, 10)                 # both within 5 ft of the ogre
    assert enc._positional_advantage(w1, ogre, "melee") is True
    w2.pos = (20, 16)                                  # ally far away
    assert enc._positional_advantage(w1, ogre, "melee") is False


def test_magic_resistance_helps_saves_vs_spells():
    golem = content.get("Stone Golem")
    assert golem.magic_resistance
    g = content.make("Stone Golem", "x", "A", (0, 0))
    plain = content.make("Ogre", "y", "B", (0, 0))
    # over many seeds, advantage from MR yields more successes at the same DC
    gw = sum(saving_throw(g, Ability.WIS, 15, RNG(s), vs_magic=True) for s in range(80))
    pw = sum(saving_throw(g, Ability.WIS, 15, RNG(s), vs_magic=False) for s in range(80))
    assert gw > pw
    _ = plain


def test_resist_nonmagical_physical():
    g = content.make("Stone Golem", "x", "A", (0, 0))
    g.hp = 100
    apply_damage(g, 20, "slashing", [])
    assert g.hp == 90        # halved (nonmagical physical)
    apply_damage(g, 20, "fire", [])
    assert g.hp == 70        # fire unaffected


# -- multi-cost legendary (Wing Attack) -----------------------------------

def test_wing_attack_spends_two_actions_on_a_cluster():
    combs = [content.make("Adult Red Dragon", "A1", "A", (5, 5)),
             content.make("Goblin", "B1", "B", (6, 5)),
             content.make("Goblin", "B2", "B", (5, 6)),
             content.make("Goblin", "B3", "B", (6, 6))]
    enc = Encounter(Grid(24, 18), combs, RNG(1))
    enc.roll_initiative()
    d = enc.combatants["A1"]
    d.legendary_actions_left = 3
    enc.legendary_actions_after(enc.combatants["B1"])
    assert d.legendary_actions_left == 1     # Wing Attack cost 2
    assert d.alt == SAFE_ALT                  # dragon flew up


# -- aura on-enter ---------------------------------------------------------

def test_aura_triggers_on_entering():
    enc = enc_of(["Priest"], ["Goblin"], w=24)
    priest, gob = enc.combatants["A1"], enc.combatants["B1"]
    priest.pos = (10, 10)
    cast.cast(enc, priest, Option("o", "spell", "Spirit Guardians", priest.id, "",
                                  spell="Spirit Guardians", slot_level=3))
    gob.pos = (20, 10)                         # well outside the 15 ft aura
    gob.auras_taken_this_turn = set()
    ghp = gob.hp
    enc._do_move(gob, (11, 10))               # steps into the aura
    assert gob.hp < ghp                        # took radiant on entering


# -- squeezing -------------------------------------------------------------

def test_squeezing_detection_and_penalties():
    from ravel.conditions import attack_mods, save_mods
    # a 1-wide vertical corridor: a Large (2x2) creature can only squeeze through
    walls = {(x, y) for x in (4, 6) for y in range(6)}   # gap is column x=5
    g = Grid(12, 6, walls=walls)
    assert g.fits_squeezing((5, 0), 2, set()) is True    # 2x2 won't fit, squeezes
    assert g.footprint_fits((5, 0), 2, set()) is False
    # combat penalties while squeezing
    a = content.make("Ogre", "a", "A", (0, 0))
    t = content.make("Ogre", "t", "B", (0, 1))
    a.squeezing = True
    assert attack_mods(a, t, "melee", 5)[1] is True       # attacker disadvantage
    assert save_mods(a, Ability.DEX)[1] is True           # disadvantage on Dex saves
    a.squeezing = False
    t.squeezing = True
    assert attack_mods(a, t, "melee", 5)[0] is True        # attackers get advantage
