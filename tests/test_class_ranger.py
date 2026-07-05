"""Ranger (Slice 6 WP2): half WIS caster (knows spells), Fighting Style, Extra Attack,
Hunter's Mark, and the Hunter (Colossus Slayer) / Beast Master archetypes. PHB-checkable
numbers + arena smoke + determinism."""
from __future__ import annotations

from ravel import content
from ravel.character import (compile_character, level_choices, make_character,
                             ranger_spells_known, to_combatant, validate_character)
from ravel.controllers import HeuristicController
from ravel.dice import RNG, Damage
from ravel.effects import add_effect
from ravel.engine import Encounter
from ravel.equipment import WEAPONS, Loadout
from ravel.grid import Grid
from ravel.models import Ability as A, ActiveEffect
from ravel.rules import resolve_attack

ARR = {A.STR: 16, A.DEX: 16, A.CON: 14, A.INT: 8, A.WIS: 14, A.CHA: 10}


def _ranger(level, sub="", style="Dueling", spells=(), **kw):
    return make_character("Aragorn", "Wood Elf", "Ranger", level, ARR, subclass=sub,
                          fighting_style=style, spells=spells,
                          equipment=Loadout(main_hand=WEAPONS["Longsword"]), **kw)


def test_ranger5_extra_attack_and_half_wis_caster():
    md = compile_character(_ranger(5))
    assert md.multiattack == (("Longsword", 2),)           # Extra Attack at 5
    assert md.spell_slots == {1: 4, 2: 2}                  # half caster of ceil(5/2)=3
    assert md.spell_ability == A.WIS
    assert compile_character(_ranger(1)).spell_slots == {}  # Spellcasting starts at level 2


def test_fighting_style_prompted_at_ranger_2():
    # level_choices reports what the *next* Ranger level asks. A fresh build's next level is
    # Ranger 1 (no style); a level-1 ranger's next level is Ranger 2 (Fighting Style).
    from ravel.character import Character
    fresh = Character(name="R", race="Wood Elf", base_abilities=ARR)
    q1 = level_choices(fresh, "Ranger")
    assert q1["class_level"] == 1 and q1["fighting_style"] is False
    lvl1 = make_character("R", "Wood Elf", "Ranger", 1, ARR)
    q2 = level_choices(lvl1, "Ranger")
    assert q2["class_level"] == 2 and q2["fighting_style"] is True


def test_spells_known_limit_validates():
    # Ranger Spells Known: 0 at L1, then 1 + (level+1)//2 -> L5 knows 4
    assert (ranger_spells_known(1), ranger_spells_known(5)) == (0, 4)
    # five leveled spells at L5 is one over the limit -> a validation warning
    ch = _ranger(5, spells=("Hunter's Mark", "Cure Wounds", "Absorb Elements",
                            "Hold Person", "Spike Growth"))
    assert any("knows" in w and "ranger" in w for w in validate_character(ch))
    # Hunter's Mark alone is legal and on the ranger list
    assert not any("ranger list" in w for w in validate_character(_ranger(5, spells=("Hunter's Mark",))))


def test_hunters_mark_marks_a_foe_and_rides_1d6():
    ch = _ranger(5, spells=("Hunter's Mark",))
    rc = to_combatant(ch, "R", "A", (1, 1))
    foe = content.make("Ogre", "B", "B", (1, 2))
    e = Encounter(Grid(6, 6), [rc, foe], RNG(2), roll_hp=False)
    e.roll_initiative()
    hm = next(o for o in e.enumerate_bonus_options(rc)
              if o.kind == "spell" and o.name == "Hunter's Mark")
    e.apply(rc, hm)
    # the rider lives on the CASTER, keyed to the marked foe, via concentration
    mark = next(ef for ef in rc.effects if ef.name == "Hunter's Mark")
    assert mark.rider_target_id == foe.id and mark.damage_rider is not None
    assert rc.concentration is not None
    # every weapon hit vs the marked foe now deals +1d6 (force)
    e.log.clear()
    for _ in range(40):
        if not foe.alive:
            break
        resolve_attack(rc, foe, rc.attacks["Longsword"], e.rng, e.log, enc=e)
    assert any("force" in line for line in e.log)


def test_colossus_slayer_and_hunters_mark_stack():
    # Hunter (Colossus Slayer, +1d8 once/turn vs a wounded foe) + Hunter's Mark (+1d6/hit)
    ch = _ranger(5, sub="Hunter", spells=("Hunter's Mark",))
    assert "Colossus Slayer" in {b.name for b in compile_character(ch).bonus_damage}
    rc = to_combatant(ch, "R", "A", (1, 1))
    foe = content.make("Ogre", "B", "B", (1, 2))
    foe.hp = foe.max_hp - 5                                # already wounded -> Colossus applies
    e = Encounter(Grid(6, 6), [rc, foe], RNG(4), roll_hp=False)
    e.roll_initiative()
    add_effect(rc, ActiveEffect(name="Hunter's Mark", source_id=rc.id,
                                damage_rider=Damage(1, 6, 0, "force"),
                                rider_target_id=foe.id, concentration=True))
    rc_hp = foe.hp
    resolve_attack(rc, foe, rc.attacks["Longsword"], e.rng, e.log, enc=e)
    log = "\n".join(e.log)
    # both riders resolve on the same wounded, marked target
    assert "Colossus Slayer" in log
    assert "force" in log
    assert foe.hp < rc_hp


def test_beast_master_registers_a_companion():
    assert compile_character(_ranger(5, sub="Beast Master")).companion == "Wolf"
    assert compile_character(_ranger(5, sub="Hunter")).companion == ""


def _fight(seed):
    rc = to_combatant(_ranger(5, sub="Hunter", spells=("Hunter's Mark",)), "A", "A", (2, 3))
    e = Encounter(Grid(14, 6), [rc, content.make("Ogre", "B", "B", (9, 3))], RNG(seed),
                  roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    return e


def test_ranger_arena_smoke_and_determinism():
    e1 = _fight(7)
    e2 = _fight(7)
    assert e1.log == e2.log
    assert e1.winner() in ("A", "B")
    assert any("Hunter's Mark" in line for line in e1.log)   # the ranger marked a foe
