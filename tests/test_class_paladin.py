"""Paladin (Slice 6 WP2): half CHA caster, Lay on Hands, Divine Smite, Extra Attack,
Aura of Protection, Improved Divine Smite, and the Oath of Devotion / Oath of Vengeance
Channel Divinity options. PHB-checkable numbers + an arena smoke + a determinism check."""
from __future__ import annotations

from ravel import content
from ravel.character import compile_character, make_character, to_combatant
from ravel.controllers import HeuristicController
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.equipment import WEAPONS, Loadout
from ravel.grid import Grid
from ravel.models import Ability as A
from ravel.rules import aura_of_protection_bonus

ARR = {A.STR: 16, A.DEX: 12, A.CON: 14, A.INT: 8, A.WIS: 10, A.CHA: 16}


def _pal(level, sub="", style="Dueling", race="Half-Elf", **kw):
    return make_character("Ser", race, "Paladin", level, ARR, subclass=sub,
                          fighting_style=style,
                          equipment=Loadout(main_hand=WEAPONS["Longsword"]), **kw)


def test_paladin5_extra_attack_and_half_caster_slots():
    md = compile_character(_pal(5))
    assert md.multiattack == (("Longsword", 2),)           # Extra Attack at 5: two swings
    assert md.spell_slots == {1: 4, 2: 2}                  # half caster = full caster of ceil(5/2)=3
    assert md.spell_ability == A.CHA
    # no slots at level 1 (half casters gain Spellcasting at 2)
    assert compile_character(_pal(1)).spell_slots == {}


def test_divine_smite_spends_the_highest_slot_for_radiant():
    pc = to_combatant(_pal(5), "P", "A", (1, 1))
    foe = content.make("Ogre", "B", "B", (1, 2))
    e = Encounter(Grid(6, 6), [pc, foe], RNG(3), roll_hp=False)
    e.roll_initiative()
    assert pc.slots == {1: 4, 2: 2}
    dmg = e.paladin_divine_smite(pc, foe, crit=False)
    # spends the 2nd-level slot -> 2d8 + 1d8 = 3d8 radiant (range 3..24)
    assert 3 <= dmg <= 24
    assert pc.slots == {1: 4, 2: 1}                        # highest slot consumed
    assert pc.smites_this_turn == 1


def test_divine_smite_policy_is_bounded_not_a_rule():
    # RAW (2014) has NO once-per-turn cap; the bound is the controller's spend POLICY:
    # crits always smite, but at most one non-crit smite per turn (so slots aren't dumped).
    pc = to_combatant(_pal(5), "P", "A", (1, 1))
    foe = content.make("Ogre", "B", "B", (1, 2))
    e = Encounter(Grid(6, 6), [pc, foe], RNG(3), roll_hp=False)
    e.roll_initiative()
    assert e.paladin_divine_smite(pc, foe, crit=False) > 0     # first worthwhile hit smites
    # a second NON-crit smite the same turn is refused by policy (bounded), no slot spent
    slots_before = dict(pc.slots)
    assert e.paladin_divine_smite(pc, foe, crit=False) == 0
    assert pc.slots == slots_before
    # ...but a CRIT still smites the same turn (RAW-legal; no per-turn rule cap)
    assert e.paladin_divine_smite(pc, foe, crit=True) > 0
    # a fresh turn resets the non-crit budget
    e.start_of_turn(pc)
    assert pc.smites_this_turn == 0
    assert e.paladin_divine_smite(pc, foe, crit=False) > 0
    # policy refuses to burn a slot on a nearly-dead mook (< 15 HP), even on a fresh turn
    e.start_of_turn(pc)
    foe.hp = 8
    assert e.paladin_divine_smite(pc, foe, crit=False) == 0


def test_smite_adds_a_die_vs_undead():
    pc = to_combatant(_pal(5), "P", "A", (1, 1))
    undead = content.make("Ogre Zombie", "B", "B", (1, 2))
    assert undead.md.mtype == "undead"
    e = Encounter(Grid(6, 6), [pc, undead], RNG(5), roll_hp=False)
    e.roll_initiative()
    dmg = e.paladin_divine_smite(pc, undead, crit=False)   # 3d8 + 1d8 (undead) = 4d8 -> 4..32
    assert 4 <= dmg <= 32


def test_improved_divine_smite_rider_at_11():
    riders = {b.name for b in compile_character(_pal(11)).bonus_damage}
    assert "Improved Divine Smite" in riders               # +1d8 every melee hit at L11
    assert "Improved Divine Smite" not in {
        b.name for b in compile_character(_pal(5)).bonus_damage}


def test_lay_on_hands_pool_and_touch_heal():
    pc = to_combatant(_pal(6), "P", "A", (1, 1))
    assert pc.resources["Lay on Hands"] == 30              # 5 x level
    pc.hp = 10
    foe = content.make("Ogre", "B", "B", (5, 5))
    e = Encounter(Grid(8, 8), [pc, foe], RNG(1), roll_hp=False)
    e.roll_initiative()
    loh = next(o for o in e.enumerate_options(pc) if o.kind == "lay_on_hands")
    e.apply(pc, loh)
    assert pc.hp == 10 + 30                                # spent the whole pool
    assert pc.resources["Lay on Hands"] == 0


def test_aura_of_protection_adds_cha_to_a_nearby_allys_save():
    pc = to_combatant(_pal(6), "P", "A", (1, 1))           # CHA 18 (16 base +2 Half-Elf) -> +4
    ally = content.make("Ogre", "A2", "A", (1, 2))
    e = Encounter(Grid(10, 10), [pc, ally], RNG(1), roll_hp=False)
    e.roll_initiative()
    assert compile_character(_pal(6)).aura_of_protection == 4
    assert aura_of_protection_bonus(ally) == 4             # ally within 10 ft gains +CHA on saves
    ally.pos = (9, 9)
    assert aura_of_protection_bonus(ally) == 0             # ...but not from far away
    # ...and no aura before level 6
    assert compile_character(_pal(5)).aura_of_protection == 0


def test_aura_of_protection_has_a_raw_minimum_of_plus_one():
    # RAW: Aura of Protection grants CHA modifier, minimum +1. A CHA-10 (mod 0) paladin still gives +1.
    lowcha = {A.STR: 16, A.DEX: 12, A.CON: 14, A.INT: 8, A.WIS: 10, A.CHA: 8}   # Half-Elf +2 -> CHA 10 (+0)
    ch = make_character("Meek", "Half-Elf", "Paladin", 6, lowcha,
                        equipment=Loadout(main_hand=WEAPONS["Longsword"]))
    assert compile_character(ch).aura_of_protection == 1
    pc = to_combatant(ch, "P", "A", (1, 1))
    ally = content.make("Ogre", "A2", "A", (1, 2))
    e = Encounter(Grid(10, 10), [pc, ally], RNG(1), roll_hp=False)
    e.roll_initiative()
    assert aura_of_protection_bonus(ally) == 1


def test_aura_of_courage_makes_nearby_allies_immune_to_fright():
    from ravel.rules import apply_condition
    assert compile_character(_pal(10)).aura_of_courage
    assert not compile_character(_pal(9)).aura_of_courage
    pc = to_combatant(_pal(10), "P", "A", (1, 1))
    ally = content.make("Ogre", "A2", "A", (1, 2))         # within 10 ft
    e = Encounter(Grid(12, 12), [pc, ally], RNG(1), roll_hp=False)
    e.roll_initiative()
    apply_condition(ally, "frightened", "x", e.rng, e.log)
    assert not ally.has("frightened")                      # Aura of Courage suppresses it
    ally.pos = (11, 11)                                    # move out of the aura
    apply_condition(ally, "frightened", "x", e.rng, e.log)
    assert ally.has("frightened")                          # ...no protection at range


def test_aura_of_devotion_makes_nearby_allies_immune_to_charm():
    from ravel.rules import apply_condition
    assert compile_character(_pal(7, "Oath of Devotion")).aura_of_devotion
    pc = to_combatant(_pal(7, "Oath of Devotion"), "P", "A", (1, 1))
    ally = content.make("Ogre", "A2", "A", (1, 2))
    e = Encounter(Grid(12, 12), [pc, ally], RNG(1), roll_hp=False)
    e.roll_initiative()
    apply_condition(ally, "charmed", "x", e.rng, e.log)
    assert not ally.has("charmed")                          # Aura of Devotion suppresses charm


def test_lay_on_hands_can_heal_a_wounded_ally_in_reach():
    pc = to_combatant(_pal(6), "P", "A", (1, 1))
    ally = content.make("Ogre", "A2", "A", (1, 2))         # adjacent, wounded
    ally.hp = 5
    e = Encounter(Grid(8, 8), [pc, ally], RNG(1), roll_hp=False)
    e.roll_initiative()
    loh = next(o for o in e.enumerate_options(pc)
               if o.kind == "lay_on_hands" and o.target_id == ally.id)
    e.apply(pc, loh)
    assert ally.hp > 5                                      # the ally was healed from the pool
    assert pc.resources["Lay on Hands"] < 30


def test_devotion_sacred_weapon_channel():
    pc = to_combatant(_pal(6, "Oath of Devotion"), "P", "A", (1, 1))
    assert pc.md.sacred_weapon == 4                        # +CHA to hit
    foe = content.make("Ogre", "B", "B", (1, 2))
    e = Encounter(Grid(6, 6), [pc, foe], RNG(1), roll_hp=False)
    e.roll_initiative()
    sw = next(o for o in e.enumerate_bonus_options(pc) if o.kind == "sacred_weapon")
    cd = pc.resources["Channel Divinity"]
    e.apply(pc, sw)
    assert any(ef.name == "Sacred Weapon" for ef in pc.effects)
    assert pc.resources["Channel Divinity"] == cd - 1


def test_vengeance_vow_of_enmity_gives_advantage():
    pc = to_combatant(_pal(6, "Oath of Vengeance"), "P", "A", (1, 1))
    assert pc.md.vow_of_enmity
    foe = content.make("Ogre", "B", "B", (1, 2))
    e = Encounter(Grid(6, 6), [pc, foe], RNG(1), roll_hp=False)
    e.roll_initiative()
    vow = next(o for o in e.enumerate_bonus_options(pc) if o.kind == "vow")
    e.apply(pc, vow)
    assert pc.vow_target_id == foe.id                      # advantage vs the sworn foe (rules.py)


def _fight(seed):
    pc = to_combatant(_pal(6, "Oath of Vengeance"), "A", "A", (2, 3))
    e = Encounter(Grid(14, 6), [pc, content.make("Ogre", "B", "B", (9, 3))], RNG(seed),
                  roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    return e


def test_paladin_arena_smoke_and_determinism():
    e1 = _fight(11)
    e2 = _fight(11)
    assert e1.log == e2.log
    assert e1.winner() in ("A", "B")
    assert any("Divine Smite" in line for line in e1.log)  # the paladin smote in the fight
