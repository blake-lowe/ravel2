"""Action economy (minor actions + bonus phase), temp HP, dice primitives,
innate spellcasting, and swim terrain."""
from __future__ import annotations

from ravel import cast, content
from ravel.dice import RNG, Damage
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Option
from ravel.rules import apply_damage


def mk(n, cid, team, pos):
    return content.make(n, cid, team, pos)


def enc(combs, seed=1, grid=None):
    e = Encounter(grid or Grid(24, 18), combs, RNG(seed))
    e.roll_initiative()
    return e


# -- temp HP ---------------------------------------------------------------

def test_temp_hp_absorbs_then_real_hp():
    c = mk("Ogre", "x", "A", (0, 0))
    c.temp_hp = 10
    apply_damage(c, 6, "slashing", [])
    assert c.temp_hp == 4 and c.hp == 59
    apply_damage(c, 10, "slashing", [])
    assert c.temp_hp == 0 and c.hp == 53     # 6 spilled through to real HP


# -- dice primitives -------------------------------------------------------

def test_dice_primitives():
    assert 3 <= RNG(1).keep(4, 6, 3) <= 18
    assert RNG(2).roll(2, 6, 0, min_die=3) >= 6          # each die floored to 3
    assert Damage(2, 6, 0, "fire", min_die=4).roll(RNG(1)) >= 8
    a, _ = RNG(3).d20(2)                                  # Elven Accuracy: 3 dice
    assert 1 <= a <= 20


# -- minor actions ---------------------------------------------------------

def test_dash_doubles_movement_budget():
    e = enc([mk("Ogre", "A1", "A", (2, 8)), mk("Goblin", "B1", "B", (18, 8))])
    og = e.combatants["A1"]
    base = e._move_budget(og)
    og.dashing = True
    assert e._move_budget(og) == base * 2


def test_disengage_avoids_opportunity_attack():
    e = enc([mk("Goblin", "A1", "A", (10, 10)), mk("Ogre", "B1", "B", (11, 10))])
    gob, og = e.combatants["A1"], e.combatants["B1"]
    e.apply(gob, Option("d", "disengage", "Disengage", None, ""))
    assert og.reaction_available is True


def test_grapple_and_shove_via_contest():
    grappled = proned = False
    for s in range(10):
        e = enc([mk("Ogre", "A1", "A", (5, 5)), mk("Goblin", "B1", "B", (6, 5))], seed=s)
        e._do_grapple(e.combatants["A1"], e.combatants["B1"])
        if e.combatants["B1"].has("grappled"):
            grappled = True
        e2 = enc([mk("Ogre", "A1", "A", (5, 5)), mk("Goblin", "B1", "B", (6, 5))], seed=s)
        e2._do_shove(e2.combatants["A1"], e2.combatants["B1"])
        if e2.combatants["B1"].has("prone"):
            proned = True
        if grappled and proned:
            return
    raise AssertionError("grapple/shove never succeeded")


def test_help_grants_ally_advantage():
    e = enc([mk("Goblin", "A1", "A", (5, 5)), mk("Goblin", "A2", "A", (5, 6)),
             mk("Ogre", "B1", "B", (6, 5))])
    e.apply(e.combatants["A1"], Option("h", "help", "Help", "A2", ""))
    assert e.combatants["A2"].help_advantage is True


def test_hide_works_but_blindsight_sees():
    hid = False
    for s in range(12):
        e = enc([mk("Goblin", "A1", "A", (5, 5)), mk("Ogre", "B1", "B", (9, 5))], seed=s)
        e._do_hide(e.combatants["A1"])
        if e.combatants["A1"].hidden:
            hid = True
            break
    assert hid
    e2 = enc([mk("Goblin", "A1", "A", (5, 5)),
              mk("Adult Red Dragon", "B1", "B", (10, 5))])    # blindsight 60
    e2._do_hide(e2.combatants["A1"])
    assert e2.combatants["A1"].hidden is False


# -- bonus-action economy --------------------------------------------------

def test_bonus_phase_offers_bonus_spells_and_pass():
    e = enc([mk("Priest", "A1", "A", (5, 5)), mk("Skeleton", "A2", "A", (5, 6)),
             mk("Goblin", "B1", "B", (7, 5))])
    e.combatants["A2"].hp = 1
    names = {o.name for o in e.enumerate_bonus_options(e.combatants["A1"])}
    assert "Healing Word" in names and "Pass" in names


def test_bonus_spell_rule_blocks_leveled_after_leveled():
    e = enc([mk("Priest", "A1", "A", (5, 5)), mk("Goblin", "B1", "B", (7, 5))])
    priest = e.combatants["A1"]
    priest.cast_leveled_this_turn = True             # already cast a leveled action spell
    assert "Healing Word" not in {o.name for o in e.enumerate_bonus_options(priest)}


# -- innate spellcasting ---------------------------------------------------

def test_innate_cast_spends_use_not_slot():
    e = enc([mk("Mage", "A1", "A", (5, 5)), mk("Goblin", "B1", "B", (7, 5))])
    mage, gob = e.combatants["A1"], e.combatants["B1"]
    gob.hp = 30
    s1 = mage.slots[1]
    cast.cast(e, mage, Option("o", "spell", "Magic Missile", gob.id, "",
                              spell="Magic Missile", slot_level=-1))
    assert mage.innate_left["Magic Missile"] == 0     # innate use spent
    assert mage.slots[1] == s1                        # slot NOT spent
    assert gob.hp < 30


# -- swim / water terrain --------------------------------------------------

def test_grapple_released_when_grappler_dies_or_far():
    e = enc([mk("Ogre", "A1", "A", (5, 5)), mk("Goblin", "B1", "B", (6, 5))])
    og, gob = e.combatants["A1"], e.combatants["B1"]
    from ravel.models import Condition
    gob.conditions["grappled"] = Condition("grappled", "A1")
    og.hp = 0                                   # grappler dies
    e.start_of_turn(gob)
    assert not gob.has("grappled")              # released


def test_escape_action_offered_and_can_free():
    freed = False
    for s in range(12):
        e = enc([mk("Ogre", "A1", "A", (5, 5)), mk("Bugbear", "B1", "B", (6, 5))], seed=s)
        og, bug = e.combatants["A1"], e.combatants["B1"]
        from ravel.models import Condition
        bug.conditions["grappled"] = Condition("grappled", "A1")
        assert any(o.kind == "escape" for o in e.enumerate_options(bug))
        e._do_escape(bug)
        if not bug.has("grappled"):
            freed = True
            break
    assert freed


def test_grapple_size_limit():
    e = enc([mk("Kobold", "A1", "A", (5, 5)), mk("Hill Giant", "B1", "B", (6, 5))])
    # a Small kobold can't grapple a Huge giant (more than one size larger)
    kinds = [(o.kind, o.target_id) for o in e.enumerate_options(e.combatants["A1"])]
    assert ("grapple", "B1") not in kinds


def test_hidden_cleared_by_offensive_spell():
    e = enc([mk("Mage", "A1", "A", (5, 5)), mk("Goblin", "B1", "B", (7, 5))])
    mage = e.combatants["A1"]
    mage.hidden = True
    cast.cast(e, mage, Option("o", "spell", "Fire Bolt", "B1", "",
                              spell="Fire Bolt", slot_level=0))
    assert mage.hidden is False


def test_prone_dash_is_one_and_a_half_speed():
    e = enc([mk("Ogre", "A1", "A", (2, 8)), mk("Goblin", "B1", "B", (18, 8))])
    og = e.combatants["A1"]
    from ravel.models import Condition
    og.conditions["prone"] = Condition("prone", "x")
    og.dashing = True
    assert e._move_budget(og) == 60             # 40 speed: +40 dash -20 stand = 60


def test_water_difficult_for_nonswimmers_only():
    g = Grid(20, 16, water={(x, 8) for x in range(1, 10)})
    e = Encounter(g, [mk("Ogre", "A1", "A", (0, 8)), mk("Wraith", "B1", "B", (0, 8))],
                  RNG(1))
    assert e.dynamic_difficult(e.combatants["A1"])        # Ogre: water is difficult
    assert not e.dynamic_difficult(e.combatants["B1"])    # Wraith flies: ignores water
