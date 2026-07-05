"""Monk (Slice 6 WP1): Martial Arts, Unarmored Defense, Ki (Flurry / Patient Defense),
Stunning Strike, Extra Attack, Unarmored Movement, Evasion, Diamond Soul, and the Open Hand /
Shadow archetypes. PHB-checkable numbers + an arena smoke + a determinism check."""
from __future__ import annotations

from ravel import content
from ravel.character import (compile_character, make_character, martial_arts_die,
                             monk_unarmored_movement, to_combatant)
from ravel.controllers import HeuristicController
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Ability as A
from ravel.rules import area_damage_after_save, resolve_attack

ARR = {A.STR: 12, A.DEX: 16, A.CON: 14, A.INT: 10, A.WIS: 16, A.CHA: 10}


def _monk(level, sub="", ab=None):
    return make_character("Kai", "Human", "Monk", level, ab or ARR, subclass=sub)


def test_martial_arts_unarmored_defense_and_ki():
    # DEX 16 (+3, +1 Human = 17 -> +3) WIS 16 (+3, +1 Human = 17 -> +3): AC = 10 + 3 + 3 = 16
    c = to_combatant(_monk(5), "A", "A", (1, 1))
    assert c.ac == 16
    assert c.resources["Ki"] == 5                        # Ki points = monk level
    ustr = c.attacks["Unarmed Strike"]
    assert ustr.damage[0].sides == 6                     # Martial Arts die d6 at L5
    assert ustr.damage[0].bonus == 3                     # DEX (17) used for unarmed damage
    assert c.multiattack == (("Unarmed Strike", 2),)     # Extra Attack at L5
    assert (martial_arts_die(1), martial_arts_die(5), martial_arts_die(11),
            martial_arts_die(17)) == (4, 6, 8, 10)
    assert (monk_unarmored_movement(2), monk_unarmored_movement(6)) == (10, 15)
    assert c.md.speed == 30 + 10                         # Human 30 + Unarmored Movement +10 at L5


def test_unarmored_movement_scales_by_level():
    assert to_combatant(_monk(2), "A", "A", (1, 1)).md.speed == 40   # +10
    assert to_combatant(_monk(6), "A", "A", (1, 1)).md.speed == 45   # +15
    assert to_combatant(_monk(10), "A", "A", (1, 1)).md.speed == 50  # +20


def test_stunning_strike_spends_ki_and_can_stun():
    stunned = False
    for seed in range(20):
        c = to_combatant(_monk(5), "A", "A", (2, 3))
        foe = content.make("Goblin", "B", "B", (3, 3))   # low CON -> fails the save often
        foe.hp = 300
        e = Encounter(Grid(8, 6), [c, foe], RNG(seed), roll_hp=False)
        e.roll_initiative()
        ki0 = c.resources["Ki"]
        # land a first hit this turn
        for _ in range(6):
            if resolve_attack(c, foe, c.attacks["Unarmed Strike"], e.rng, e.log, enc=e):
                break
        if c.resources["Ki"] == ki0 - 1:                 # a hit spent Ki on Stunning Strike
            assert c.stunning_used
            if foe.has("stunned"):
                stunned = True
                break
    assert stunned                                       # at least one foe was stunned


def test_flurry_and_patient_defense_are_offered_with_ki():
    c = to_combatant(_monk(5), "A", "A", (2, 3))
    e = Encounter(Grid(8, 6), [c, content.make("Ogre", "B", "B", (3, 3))], RNG(1), roll_hp=False)
    e.roll_initiative()
    c.took_attack_action = True                          # Flurry requires having taken the Attack action
    kinds = {o.kind for o in e.enumerate_bonus_options(c)}
    assert "flurry" in kinds and "patient_defense" in kinds
    c.resources["Ki"] = 0
    kinds2 = {o.kind for o in e.enumerate_bonus_options(c)}
    assert "flurry" not in kinds2                        # no Ki -> no Flurry
    assert any(o.kind == "offhand" for o in e.enumerate_bonus_options(c))  # free Martial Arts strike


def test_open_hand_flurry_knocks_prone():
    c = to_combatant(_monk(5, "Way of the Open Hand"), "A", "A", (2, 3))
    assert c.md.open_hand
    proned = False
    for seed in range(20):
        c = to_combatant(_monk(5, "Way of the Open Hand"), "A", "A", (2, 3))
        foe = content.make("Goblin", "B", "B", (3, 3))
        foe.hp = 300
        e = Encounter(Grid(8, 6), [c, foe], RNG(seed), roll_hp=False)
        e.roll_initiative()
        e._do_flurry(c, foe)
        if foe.has("prone"):
            proned = True
            break
    assert proned                                        # Open Hand Technique: a Flurry hit -> prone


def test_evasion_negates_dex_area_damage_on_a_success():
    c = to_combatant(_monk(7), "A", "A", (1, 1))
    assert c.md.evasion
    # DEX save-for-half: Evasion turns a success into no damage, a failure into half
    assert area_damage_after_save(c, A.DEX, True, True, 20) == 0
    assert area_damage_after_save(c, A.DEX, False, True, 20) == 10
    # a non-DEX save is unaffected by Evasion
    assert area_damage_after_save(c, A.CON, True, True, 20) == 10


def test_diamond_soul_grants_all_save_proficiencies():
    c = to_combatant(_monk(14), "A", "A", (1, 1))
    assert set(c.md.save_profs) == set(A)                # proficient in every saving throw
    assert set(to_combatant(_monk(13), "A", "A", (1, 1)).md.save_profs) == {A.STR, A.DEX}


def test_way_of_shadow_uses_the_teleport_primitive_for_shadow_step():
    c = to_combatant(_monk(6, "Way of Shadow"), "A", "A", (1, 1))
    assert c.md.teleport > 0                             # Shadow Step modelled as teleport (no OAs)


def test_ki_empowered_strikes_make_unarmed_magical_at_6():
    assert not compile_character(_monk(5)).magic_weapons  # L5: still nonmagical
    assert compile_character(_monk(6)).magic_weapons       # L6: unarmed counts as magical
    # a creature resistant to nonmagical B/P/S takes FULL damage from a L6 monk's fist
    resistant = content.make("Gargoyle", "B", "B", (1, 2))
    assert resistant.md.resist_nonmagical_physical
    m6 = to_combatant(_monk(6), "A", "A", (1, 1))
    e = Encounter(Grid(6, 6), [m6, resistant], RNG(4), roll_hp=False)
    e.roll_initiative()
    hp0 = resistant.hp
    for _ in range(20):
        if resolve_attack(m6, resistant, m6.attacks["Unarmed Strike"], e.rng, e.log, enc=e):
            break
    hit = next(l for l in reversed(e.log) if "takes" in l and "bludgeoning" in l)
    dealt = hp0 - resistant.hp
    # not halved: a nonmagical fist would deal half (resistance); magical deals the full roll
    assert "immune" not in hit and dealt >= 4


def test_deflect_missiles_reduces_incoming_ranged_damage():
    assert compile_character(_monk(3)).deflect_missiles == 3
    mk = to_combatant(_monk(3), "M", "A", (1, 1))
    from ravel.dice import Damage
    from ravel.models import AttackDef
    archer = content.make("Scout", "S", "B", (1, 3))
    e = Encounter(Grid(6, 6), [mk, archer], RNG(2), roll_hp=False)
    e.roll_initiative()
    shot = AttackDef(name="Longbow", kind="ranged", attack_bonus=20,
                     damage=(Damage(1, 8, 3, "piercing"),), range_normal=150, range_long=600)
    hp0 = mk.hp
    resolve_attack(archer, mk, shot, e.rng, e.log, enc=e)
    assert any("Deflect Missiles" in l for l in e.log)
    assert not mk.reaction_available                       # the reaction was spent
    assert hp0 - mk.hp < 11                                # damage was reduced (1d10+DEX+level)


def _fight(seed, sub="Way of the Open Hand"):
    c = to_combatant(_monk(5, sub), "A", "A", (2, 3))
    e = Encounter(Grid(12, 6), [c, content.make("Ogre", "B", "B", (8, 3))], RNG(seed),
                  roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    return e


def test_monk_arena_smoke_and_determinism():
    e1 = _fight(4)
    e2 = _fight(4)
    assert e1.log == e2.log
    assert e1.winner() in ("A", "B")
