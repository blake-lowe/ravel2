"""New monster abilities: Life Drain, Death Burst, Pounce, Frightful Presence,
Parry, and senses vs invisibility."""
from __future__ import annotations

from ravel import content
from ravel.conditions import attack_mods
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Condition
from ravel.rules import resolve_attack


def enc(combs, seed=1):
    e = Encounter(Grid(24, 18), combs, RNG(seed))
    e.roll_initiative()
    return e


def test_life_drain_reduces_max_hp():
    for s in range(10):
        wr = content.make("Wraith", "A1", "A", (2, 2))
        ogre = content.make("Ogre", "B1", "B", (3, 2))
        base = ogre.max_hp
        if resolve_attack(wr, ogre, wr.md.attacks["Life Drain"], RNG(s), []):
            assert ogre.max_hp_reduction > 0
            assert ogre.max_hp < base
            return
    raise AssertionError("Life Drain never hit across seeds")


def test_death_burst_damages_neighbors_and_can_chain():
    dealt = False
    for s in range(8):
        e = enc([content.make("Ogre", "A1", "A", (5, 5)),
                 content.make("Magmin", "B1", "B", (6, 5))], seed=s)
        ogre, mag = e.combatants["A1"], e.combatants["B1"]
        mag.hp = 0                       # magmin drops
        hp0 = ogre.hp
        e.sweep_death_bursts()
        assert mag.burst_done is True
        if ogre.hp < hp0:
            dealt = True
            break
    assert dealt


def test_pounce_knocks_prone_and_grants_bonus_attack():
    pounced = False
    for s in range(12):
        e = enc([content.make("Saber-Toothed Tiger", "A1", "A", (2, 2)),
                 content.make("Goblin", "B1", "B", (3, 2))], seed=s)
        tiger, gob = e.combatants["A1"], e.combatants["B1"]
        tiger.moved_this_turn = 25       # charged 25 ft
        ghp = gob.hp
        e._try_pounce(tiger, gob)
        if gob.has("prone") or gob.hp < ghp or not gob.alive:
            pounced = True
            break
    assert pounced
    # pounce resets the charge so it can't re-trigger
    assert e.combatants["A1"].moved_this_turn == 0


def test_frightful_presence_frightens_enemies():
    e = enc([content.make("Adult Red Dragon", "A1", "A", (5, 5)),
             content.make("Goblin", "B1", "B", (7, 5)),
             content.make("Goblin", "B2", "B", (7, 6)),
             content.make("Goblin", "B3", "B", (8, 5))], seed=1)
    d = e.combatants["A1"]
    e._do_frightful_presence(d)
    assert d.frightful_used is True
    assert any(e.combatants[g].has("frightened") for g in ("B1", "B2", "B3"))


def test_parry_consumes_reaction_once():
    e = enc([content.make("Gladiator", "A1", "A", (2, 2)),
             content.make("Ogre", "B1", "B", (3, 2))])
    glad = e.combatants["A1"]
    assert e.try_parry(glad) is True
    assert glad.reaction_available is False
    assert e.try_parry(glad) is False      # one reaction per round


def test_blindsight_negates_invisibility():
    dragon = content.make("Adult Red Dragon", "a", "A", (0, 0))  # blindsight 60
    goblin = content.make("Goblin", "b", "B", (0, 1))            # no special senses
    target = content.make("Wolf", "t", "B", (0, 1))
    target.conditions["invisible"] = Condition("invisible", "x")
    # dragon perceives the invisible target -> no disadvantage
    assert attack_mods(dragon, target, "melee", 5)[1] is False
    # goblin can't -> disadvantage
    assert attack_mods(goblin, target, "melee", 5)[1] is True
