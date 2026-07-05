"""Sorcerer (Slice 6 WP3): full CHA caster, Sorcery Points, Metamagic (Quickened + Empowered),
and the Draconic Bloodline (Draconic Resilience / Elemental Affinity) / Wild Magic (Tides of
Chaos) origins. PHB-checkable numbers + an arena smoke + a determinism check."""
from __future__ import annotations

from ravel import content
from ravel.character import compile_character, make_character, to_combatant
from ravel.controllers import HeuristicController
from ravel.dice import RNG, Damage
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Ability as A, AttackDef
from ravel.rules import resolve_attack

# Tiefling: CHA 16 +2 -> 18 (+4). Sorcerer is a full CHA caster (d6 hit die).
ARR = {A.STR: 10, A.DEX: 14, A.CON: 14, A.INT: 8, A.WIS: 10, A.CHA: 16}


def _sorc(level, sub="", spells=("Fire Bolt", "Fireball", "Burning Hands"), **kw):
    return make_character("Zae", "Tiefling", "Sorcerer", level, ARR, subclass=sub,
                          spells=spells, **kw)


def test_sorcerer5_points_slots_and_metamagic():
    md = compile_character(_sorc(5))
    assert md.spell_slots == {1: 4, 2: 3, 3: 2}            # full caster at level 5
    assert md.spell_ability == A.CHA
    pc = to_combatant(_sorc(5), "A", "A", (1, 1))
    assert pc.resources["Sorcery Points"] == 5             # Sorcery Points = sorcerer level
    assert md.quicken_spell and md.empowered_spell         # Metamagic v1 known from level 3
    assert compile_character(_sorc(2)).quicken_spell is False


def test_quickened_spell_costs_two_sorcery_points():
    pc = to_combatant(_sorc(5), "A", "A", (1, 1))
    foe = content.make("Ogre", "B", "B", (1, 2))
    e = Encounter(Grid(6, 6), [pc, foe], RNG(2), roll_hp=False)
    e.roll_initiative()
    quick = next(o for o in e.enumerate_bonus_options(pc)
                 if o.kind == "quicken" and o.name == "Fire Bolt")
    pts = pc.resources["Sorcery Points"]
    e.apply(pc, quick)
    assert pc.resources["Sorcery Points"] == pts - 2       # Quickened Spell: 2 points
    assert any("quickens Fire Bolt" in ln for ln in e.log)


def test_empowered_spell_spends_a_point_and_rerolls_damage():
    pc = to_combatant(_sorc(5), "A", "A", (1, 1))
    foe = content.make("Ogre", "B", "B", (1, 2))
    e = Encounter(Grid(6, 6), [pc, foe], RNG(1), roll_hp=False)
    e.roll_initiative()
    fireball = next(o for o in e.enumerate_options(pc) if o.name == "Fireball")
    pts = pc.resources["Sorcery Points"]
    e.apply(pc, fireball)
    assert pc.resources["Sorcery Points"] == pts - 1       # Empowered Spell: 1 point on a leveled spell
    assert any("empowers Fireball" in ln for ln in e.log)


def test_draconic_resilience_ac_and_bonus_hp():
    md = compile_character(_sorc(5, "Draconic Bloodline"))
    assert md.ac == 13 + 2                                 # Draconic Resilience: 13 + DEX (14 -> +2)
    # +1 HP per level over a plain sorcerer of the same build
    plain = compile_character(_sorc(5))
    assert md.hp == plain.hp + 5


def test_draconic_elemental_affinity_adds_cha_to_a_fire_spell_at_6():
    md = compile_character(_sorc(6, "Draconic Bloodline"))
    assert md.elemental_affinity == 4 and md.elemental_affinity_dtype == "fire"
    assert compile_character(_sorc(5, "Draconic Bloodline")).elemental_affinity == 0


def test_wild_magic_tides_of_chaos_grants_advantage():
    pc = to_combatant(_sorc(3, "Wild Magic",
                            equipment=None), "A", "A", (1, 1))
    assert pc.resources["Tides of Chaos"] == 1
    # a Tiefling sorcerer has no weapon; give it a jab to prove the advantage spend fires
    foe = content.make("Ogre", "B", "B", (1, 2))
    e = Encounter(Grid(6, 6), [pc, foe], RNG(3), roll_hp=False)
    e.roll_initiative()
    atk = AttackDef(name="Jab", kind="melee", attack_bonus=2,
                    damage=(Damage(1, 4, 0, "bludgeoning"),))
    resolve_attack(pc, foe, atk, e.rng, e.log, enc=e)
    assert pc.resources["Tides of Chaos"] == 0             # spent for advantage
    assert any("Tides of Chaos" in ln for ln in e.log)


def _fight(seed):
    pc = to_combatant(_sorc(5, "Draconic Bloodline"), "A", "A", (2, 3))
    e = Encounter(Grid(14, 6), [pc, content.make("Ogre", "B", "B", (9, 3))], RNG(seed),
                  roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    return e


def test_sorcerer_arena_smoke_and_determinism():
    e1 = _fight(2)
    e2 = _fight(2)
    assert e1.log == e2.log
    assert e1.winner() in ("A", "B")
