"""Combat-fidelity tests: each condition's exact effect, exhaustion, cover/LoS,
AoE geometry, and true save-for-half riders."""
from __future__ import annotations

from ravel import content
from ravel.conditions import attack_mods, can_act, save_mods, speed_multiplier
from ravel.dice import RNG, Damage
from ravel.grid import Grid, cube_cells, line_aoe_cells, sphere_cells
from ravel.models import Ability, Condition, SaveRider
from ravel.rules import _apply_rider, apply_condition, apply_damage


def mk(name="Goblin", cid="x", team="A", pos=(0, 0)):
    return content.make(name, cid, team, pos)


def cond(c, name, source="s"):
    c.conditions[name] = Condition(name, source)


def melee(a, t, dist=5):
    return attack_mods(a, t, "melee", dist)


# -- conditions: attack effects -------------------------------------------

def test_prone_melee_adv_ranged_disadv():
    a, t = mk(), mk(cid="t", team="B")
    cond(t, "prone", "a")
    assert attack_mods(a, t, "melee", 5)[0] is True     # advantage in melee <=5
    assert attack_mods(a, t, "melee", 10)[1] is True    # disadvantage beyond 5
    assert attack_mods(a, t, "ranged", 30)[1] is True   # ranged disadvantage


def test_invisible_attacker_adv_target_disadv():
    a, t = mk(), mk(cid="t", team="B")
    cond(a, "invisible")
    assert melee(a, t)[0] is True
    a2, t2 = mk(), mk(cid="t2", team="B")
    cond(t2, "invisible")
    assert melee(a2, t2)[1] is True


def test_poisoned_disadv_restrained_target_adv():
    a, t = mk(), mk(cid="t", team="B")
    cond(a, "poisoned")
    assert melee(a, t)[1] is True
    a2, t2 = mk(), mk(cid="t2", team="B")
    cond(t2, "restrained")
    assert melee(a2, t2)[0] is True


def test_paralyzed_auto_crit_and_autofail():
    a, t = mk("Ogre"), mk(cid="t", team="B")
    apply_condition(t, "paralyzed", "a", RNG(1), [])
    assert melee(a, t, 5)[3] is True                     # auto crit melee <=5
    assert save_mods(t, Ability.DEX)[2] is True          # auto-fail Dex save
    assert can_act(t) is False                           # implied incapacitated


def test_charmed_cannot_attack_charmer():
    a, charmer = mk(), mk(cid="charmer", team="B")
    cond(a, "charmed", "charmer")
    assert melee(a, charmer)[2] is True


# -- exhaustion -----------------------------------------------------------

def test_exhaustion_levels():
    c = mk("Ogre")
    c.exhaustion = 2
    assert speed_multiplier(c) == 0.5
    c.exhaustion = 3
    assert save_mods(c, Ability.WIS)[1] is True
    base = c.md.hp
    c.exhaustion = 4
    assert c.max_hp == base // 2
    c.exhaustion = 5
    assert speed_multiplier(c) == 0.0


def test_petrified_halves_all_damage():
    log: list[str] = []
    c = mk("Ogre")
    cond(c, "petrified")
    start = c.hp
    apply_damage(c, 20, "slashing", log)
    assert start - c.hp == 10


# -- AoE geometry ----------------------------------------------------------

def test_aoe_shapes():
    g = Grid(20, 20)
    sph = sphere_cells((10, 10), 20, g)                  # radius 4 squares
    assert (10, 10) in sph and (14, 10) in sph and (15, 10) not in sph
    assert len(cube_cells((10, 10), 15, g)) == 9         # 3x3
    line = line_aoe_cells((10, 10), (1, 0), 25, g)       # 5 squares east
    assert len(line) == 5 and (15, 10) in line


# -- cover & line of sight -------------------------------------------------

def test_cover_and_line_of_sight():
    g = Grid(20, 3)
    assert g.cover_bonus((0, 1), [(10, 1)], blockers={(5, 1)}) == 2   # half cover
    assert g.cover_bonus((0, 1), [(10, 1)], blockers=set()) == 0
    g2 = Grid(20, 1, walls={(5, 0)})
    assert g2.cover_bonus((0, 0), [(10, 0)], blockers=set()) is None  # total cover


# -- true save-for-half rider ---------------------------------------------

def test_rider_half_on_save():
    dmg = Damage(7, 6, 0, "poison")
    atk = mk("Wyvern")
    # impossible DC -> save fails -> full damage
    t = mk("Ogre", cid="t", team="B"); t.hp = 300
    _apply_rider(SaveRider(Ability.CON, 999, extra_damage=dmg, half_on_save=True),
                 atk, t, RNG(5), [])
    full = 300 - t.hp
    # DC 0 -> save succeeds, half_on_save -> exactly half (same RNG sequence)
    t.hp = 300
    _apply_rider(SaveRider(Ability.CON, 0, extra_damage=dmg, half_on_save=True),
                 atk, t, RNG(5), [])
    half = 300 - t.hp
    # DC 0 -> save succeeds, NOT half_on_save -> negated
    t.hp = 300
    _apply_rider(SaveRider(Ability.CON, 0, extra_damage=dmg, half_on_save=False),
                 atk, t, RNG(5), [])
    none = 300 - t.hp
    assert none == 0
    assert half > 0 and half == full // 2


def test_wyvern_statblock_has_half_on_save():
    assert content.get("Wyvern").attacks["Stinger"].rider.half_on_save is True
