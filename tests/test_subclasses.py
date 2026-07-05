"""Wizard Arcane Traditions + Eldritch Knight: each subclass's headline combat feature fires."""
from __future__ import annotations

from ravel import content
from ravel.character import compile_character, make_character, to_combatant
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.equipment import ARMORS, WEAPONS, Loadout
from ravel.grid import Grid
from ravel.models import Ability as A, Option
from ravel.rules import apply_damage


def _wiz(sub, lvl, spells=("Fireball",), I=16):
    return make_character("W", "Human", "Wizard", lvl,
                          {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: I, A.WIS: 12, A.CHA: 10},
                          subclass=sub, spells=spells)


def _cast(enc, caster, spell, target_id, slot):
    from ravel import cast
    cast.cast(enc, caster, Option(f"spell:{spell}", "spell", spell, target_id, "",
                                  spell=spell, slot_level=slot))


def test_eldritch_knight_is_a_third_caster_with_war_magic():
    ek = make_character("Valen", "Human", "Fighter", 7,
                        {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 14, A.WIS: 10, A.CHA: 8},
                        subclass="Eldritch Knight", spells=("Fire Bolt", "Shield"),
                        equipment=Loadout(main_hand=WEAPONS["Longsword"]))
    c = to_combatant(ek, "A", "A", (1, 1))
    assert c.slots == {1: 4, 2: 2}                    # third-caster table at fighter level 7
    assert c.md.spell_ability == A.INT and c.md.spell_dc == 13 and c.md.war_magic  # 8 + prof 3 + INT 2


def test_abjurer_arcane_ward_absorbs_damage_then_recharges():
    ch = _wiz("School of Abjuration", 6, spells=("Shield", "Counterspell"))
    c = to_combatant(ch, "A", "A", (1, 1))
    assert c.arcane_ward == c.arcane_ward_max == 2 * 6 + 3   # 2*level + INT mod
    e = Encounter(Grid(6, 6), [c, content.make("Goblin", "B", "B", (2, 2))], RNG(1),
                  roll_hp=False)
    ward0, hp0 = c.arcane_ward, c.hp
    apply_damage(c, 8, "fire", e.log, e.rng, enc=e)
    assert c.arcane_ward == ward0 - 8 and c.hp == hp0   # the ward soaked the whole hit


def test_diviner_portent_forces_an_enemy_to_fail():
    ch = _wiz("School of Divination", 5, spells=("Hold Person",))
    c = to_combatant(ch, "A", "A", (2, 3))
    foe = content.make("Berserker", "B", "B", (4, 3))   # a humanoid
    e = Encounter(Grid(8, 6), [c, foe], RNG(1), roll_hp=False)
    e.roll_initiative()
    c.portent_rolls = [1]                             # a guaranteed-low Portent die
    _cast(e, c, "Hold Person", "B", 2)
    assert foe.has("paralyzed") and c.portent_rolls == []   # forced failure, die consumed


def test_necromancer_grim_harvest_heals_on_a_spell_kill():
    ch = _wiz("School of Necromancy", 5, spells=("Magic Missile",))
    c = to_combatant(ch, "A", "A", (2, 3))
    c.hp = 10
    foe = content.make("Goblin", "B", "B", (4, 3))
    foe.hp = 1                                        # a Magic Missile will kill it
    e = Encounter(Grid(8, 6), [c, foe], RNG(1), roll_hp=False)
    e.roll_initiative()
    _cast(e, c, "Magic Missile", "B", 1)
    assert not foe.alive and c.hp > 10               # reaped HP from the kill


def test_necromancer_inured_to_undeath_blocks_hp_max_reduction():
    ch = _wiz("School of Necromancy", 10)
    c = to_combatant(ch, "A", "A", (1, 1))
    base = c.max_hp
    c.max_hp_reduction = 20                           # a Life-Drain effect tries to lower the max
    assert c.max_hp == base                           # Inured to Undeath ignores it
    assert "necrotic" in c.md.resistances


def test_illusionist_illusory_self_makes_an_attack_miss():
    ch = _wiz("School of Illusion", 10)
    c = to_combatant(ch, "A", "A", (3, 3))
    assert c.md.illusory_self and c.resources["Illusory Self"] == 1
    e = Encounter(Grid(8, 6), [c, content.make("Ogre", "B", "B", (4, 3))], RNG(1),
                  roll_hp=False)
    assert e.try_illusory_self(c) is True and c.resources["Illusory Self"] == 0
    assert e.try_illusory_self(c) is False            # only once per short rest


def test_enchanter_hypnotic_gaze_charms_a_foe():
    ch = _wiz("School of Enchantment", 8, I=18)       # high DC
    c = to_combatant(ch, "A", "A", (2, 3))
    foe = content.make("Goblin", "B", "B", (2, 4))    # weak WIS
    e = Encounter(Grid(6, 6), [c, foe], RNG(1), roll_hp=False)
    charmed = False
    for _ in range(20):
        foe.conditions.clear()
        e._do_hypnotic_gaze(c, foe)
        if foe.has("charmed") and foe.has("incapacitated"):
            charmed = True
            break
    assert charmed


def test_transmuter_stone_grants_fire_resistance():
    ch = _wiz("School of Transmutation", 6)
    c = to_combatant(ch, "A", "A", (1, 1))
    e = Encounter(Grid(6, 6), [c, content.make("Goblin", "B", "B", (2, 2))], RNG(1),
                  roll_hp=False)
    hp0 = c.hp
    apply_damage(c, 10, "fire", e.log, e.rng, enc=e)
    assert hp0 - c.hp == 5                            # fire resistance halves the 10 damage


def test_abjurer_spell_resistance_halves_spell_damage():
    ch = _wiz("School of Abjuration", 14, spells=("Shield",))
    c = to_combatant(ch, "A", "A", (1, 1))
    assert c.md.spell_resistance
    e = Encounter(Grid(6, 6), [c, content.make("Mage", "B", "B", (2, 2))], RNG(1),
                  roll_hp=False)
    assert e.absorb(c, "fire", 20) == 10             # resistance to spell damage


def test_illusory_self_recharges_on_a_short_rest():
    from ravel import rest
    ch = _wiz("School of Illusion", 10)
    c = to_combatant(ch, "A", "A", (1, 1))
    c.resources["Illusory Self"] = 0
    rest.short_rest(c, RNG(1), ch, spend=0)
    assert c.resources["Illusory Self"] == 1


def test_grim_harvest_only_fires_on_a_real_kill():
    ch = _wiz("School of Necromancy", 5, spells=("Magic Missile",))
    c = to_combatant(ch, "A", "A", (2, 3))
    c.hp = 10
    downed = to_combatant(make_character("T", "Human", "Fighter", 5,
                          {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8}),
                          "B", "B", (4, 3))
    downed.hp = 1                                     # a PC who will drop to *dying*, not dead
    e = Encounter(Grid(8, 6), [c, downed], RNG(1), roll_hp=False)
    e.roll_initiative()
    _cast(e, c, "Magic Missile", "B", 1)
    assert downed.dying and not downed.dead and c.hp == 10   # no reap on a knockout


def test_conjurer_focused_conjuration_holds_concentration():
    ch = _wiz("School of Conjuration", 10, spells=("Conjure Animals",))
    c = to_combatant(ch, "A", "A", (1, 1))
    assert compile_character(ch).focused_conjuration
    from ravel.rules import _concentration_save
    from ravel.models import Concentration
    c.concentration = Concentration(spell="Conjure Animals", duration=10)
    _concentration_save(c, 100, RNG(1), [], enc=None)   # a big hit
    assert c.concentration is not None                 # damage can't break a conjuration spell
