"""Death saving throws (SPEC §14.3): PCs fall unconscious at 0 HP and roll death saves;
monsters die outright. Includes damage-while-dying, massive-damage instant death, and revival."""
from __future__ import annotations

from ravel import content
from ravel.character import make_character, to_combatant
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Ability as A
from ravel.rules import _damage_while_dying, apply_damage


def _pc(hp=None, level=5):
    c = to_combatant(make_character("Ser", "Human", "Fighter", level,
                     {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8}),
                     "A", "A", (1, 1))
    if hp is not None:
        c.hp = hp
    return c


def _enc(c):
    return Encounter(Grid(6, 6), [c], RNG(1), roll_hp=False)


def test_pc_falls_unconscious_but_monster_dies():
    c = _pc(hp=8)
    e = _enc(c)
    apply_damage(c, 8, "slashing", e.log, e.rng, enc=e)
    assert c.hp == 0 and c.dying and not c.dead and c.has("unconscious")
    g = content.make("Goblin", "B", "B", (2, 2))
    g.hp = 5
    apply_damage(g, 5, "slashing", e.log, e.rng, enc=e)
    assert g.dead and not g.dying                       # a monster just dies at 0


def test_three_successes_stabilize_three_failures_die():
    for seed in range(200):
        c = _pc(hp=0)
        c.dying = True
        e = Encounter(Grid(6, 6), [c], RNG(seed), roll_hp=False)
        for _ in range(8):
            if not c.dying:
                break
            e.roll_death_save(c)
        if c.stable:
            assert not c.dead and c.death_successes >= 3
            break
    else:
        raise AssertionError("no stabilizing seed found")
    for seed in range(200):
        c = _pc(hp=0)
        c.dying = True
        e = Encounter(Grid(6, 6), [c], RNG(seed), roll_hp=False)
        for _ in range(8):
            if not c.dying:
                break
            e.roll_death_save(c)
        if c.dead:
            assert c.death_failures >= 3 and not c.stable
            break
    else:
        raise AssertionError("no dying seed found")


def test_nat20_death_save_revives_at_1_hp():
    for seed in range(200):
        c = _pc(hp=0)
        c.dying = True
        e = Encounter(Grid(6, 6), [c], RNG(seed), roll_hp=False)
        e.roll_death_save(c)
        if c.hp == 1:
            assert not c.dying and not c.dead and c.death_failures == 0
            break
    else:
        raise AssertionError("no nat-20 seed found")


def test_damage_while_dying_adds_failures_and_crit_doubles():
    c = _pc(hp=0)
    c.dying = True
    e = _enc(c)
    _damage_while_dying(c, False, 3, e, e.log)
    assert c.death_failures == 1
    _damage_while_dying(c, True, 3, e, e.log)            # a crit = two failures -> 3 total -> dead
    assert c.dead and not c.dying


def test_massive_damage_is_instant_death():
    c = _pc(hp=44)                                       # a level-5 fighter (max 44)
    e = _enc(c)
    apply_damage(c, 100, "slashing", e.log, e.rng, enc=e)   # overkill 56 >= max 44
    assert c.dead and not c.dying                        # skips death saves entirely


def test_healing_revives_a_dying_pc():
    c = _pc(hp=0)
    c.dying = True
    c.death_failures = 2
    c.hp = 6                                             # a heal lands
    c.wake_from_dying()
    assert not c.dying and c.death_failures == 0 and not c.has("unconscious")


def test_downed_ally_is_picked_up_by_healing_word():
    from ravel.controllers import HeuristicController
    # a healer (Wizard given Healing Word) and a fragile ally vs a monster; the ally goes down
    healer = to_combatant(make_character("Cleric", "Human", "Wizard", 5,
                          {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 15, A.WIS: 12, A.CHA: 10},
                          spells=("Healing Word", "Fire Bolt")), "A", "A", (2, 3))
    ally = _pc(hp=1)
    ally.id, ally.team, ally.pos = "B", "A", (2, 4)
    e = Encounter(Grid(10, 6), [healer, ally], RNG(1), roll_hp=False)
    e.roll_initiative()
    ally.hp = 0
    ally.dying = True                                    # downed
    from ravel.cast import _wounded_ally
    assert _wounded_ally(e, healer) is ally              # the heal AI targets the downed ally
