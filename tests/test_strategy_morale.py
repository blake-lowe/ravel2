"""P0 immunity-aware options, P2a role/INT strategy, P2b free-form, P2c morale."""
from __future__ import annotations

import dataclasses

from ravel import content, tactics
from ravel.controllers import HeuristicController
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Option


def mk(n, cid, t, p):
    return content.make(n, cid, t, p)


def enc(combs, seed=1, w=20, h=12):
    e = Encounter(Grid(w, h), combs, RNG(seed))
    e.roll_initiative()
    return e


# -- P0: immunity-aware options -------------------------------------------

def test_expected_damage_and_tag_vs_immune():
    e = enc([mk("Mage", "A1", "A", (8, 5)), mk("Fire Giant", "B1", "B", (11, 5))])
    mage = e.combatants["A1"]
    fb = Option("o", "spell", "Fireball", "B1", "", spell="Fireball", slot_level=3)
    mm = Option("o", "spell", "Magic Missile", "B1", "", spell="Magic Missile", slot_level=1)
    assert tactics.expected_damage(e, mage, fb) == 0          # fire vs fire-immune
    assert "IMMUNE" in tactics.effectiveness_tag(e, mage, fb)
    assert tactics.expected_damage(e, mage, mm) > 0           # force is fine


def test_heuristic_avoids_immune_attack():
    e = enc([mk("Mage", "A1", "A", (8, 5)), mk("Fire Giant", "B1", "B", (11, 5))])
    mage = e.combatants["A1"]
    choice = HeuristicController().decide(e, mage, e.enumerate_options(mage))
    # whatever it picks, it must not be a 0-damage (immune) attack
    if choice.kind in ("spell", "attack", "multiattack", "area"):
        assert tactics.expected_damage(e, mage, choice) > 0


# -- P2a: role + INT tier --------------------------------------------------

def test_role_and_int_derivation():
    assert tactics.int_tier(content.get("Ogre")) == "animal"          # INT 5
    assert tactics.int_tier(content.get("Mage")) == "genius"          # INT 17
    assert tactics.combat_role(content.get("Mage")) == "controller"   # has AoE spells
    assert "leader" in tactics.combat_role(content.get("Priest"))     # heals/buffs
    assert tactics.combat_role(content.get("Troll")) == "brute"       # melee only, no stealth
    assert tactics.combat_role(content.get("Wolf")) == "lurker"       # Stealth +4 (real MM skills)


def test_strategy_brief_has_role_tier_and_immune_principle():
    brief = tactics.strategy_brief(content.get("Mage"))
    assert "controller" in brief and "genius" in brief
    assert "immune" in brief.lower()       # cunning+ principle: don't attack immune foes


# -- P2b: free-form strategy (LLM-only) -----------------------------------

def test_free_form_strategy_appended():
    md = dataclasses.replace(content.get("Goblin"), strategy="Kill the healer first.")
    assert "Kill the healer first." in tactics.strategy_brief(md)


# -- P2c: morale & fleeing -------------------------------------------------

def test_morale_can_rout_and_flee():
    routed = False
    for s in range(15):
        e = enc([mk("Goblin", "A1", "A", (10, 5)), mk("Ogre", "B1", "B", (12, 5))], seed=s)
        gob = e.combatants["A1"]
        gob.hp = 3                                   # bloodied
        e.take_turn(gob, HeuristicController())
        if gob.routed:
            routed = True
            break
    assert routed


def test_fearless_undead_never_routs():
    e = enc([mk("Skeleton", "A1", "A", (10, 5)), mk("Ogre", "B1", "B", (12, 5))])
    skel = e.combatants["A1"]
    skel.hp = 1                                      # bloodied
    e.take_turn(skel, HeuristicController())
    assert skel.routed is False                      # undead don't check morale


def test_fled_creature_leaves_the_fight():
    e = enc([mk("Goblin", "A1", "A", (0, 5)), mk("Ogre", "B1", "B", (12, 5))])
    gob = e.combatants["A1"]
    gob.fled = True
    assert gob not in e.living()
    assert "A" not in e.teams_alive()               # its team is no longer in the fight
