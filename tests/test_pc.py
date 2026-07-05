"""Player characters (SPEC §11-12): the Fighter vertical — build compilation, derived
numbers, races, fighting styles, Extra Attack, and class resources in the arena."""
from __future__ import annotations

from ravel import content
from ravel.character import (Character, class_resources, compile_character,
                             extra_attacks, level_up, make_character, to_combatant)
from ravel.controllers import HeuristicController
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.equipment import ARMORS, WEAPONS, Loadout
from ravel.grid import Grid
from ravel.models import Ability as A


def _ref_fighter(style="Defense", cid="A", team="A", pos=(1, 1)):
    ch = make_character("Borin", "Human", "Fighter", 5,
                        {A.STR: 15, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8},
                        background="Soldier", skills=("Athletics", "Perception"),
                        fighting_style=style,
                        equipment=Loadout(armor=ARMORS["Chain Mail"], shield=True,
                                          main_hand=WEAPONS["Longsword"]))
    return ch, to_combatant(ch, cid, team, pos)


def test_reference_fighter_derived_numbers():
    ch, c = _ref_fighter()
    md = c.md
    assert md.abilities == {A.STR: 16, A.DEX: 15, A.CON: 15, A.INT: 11, A.WIS: 13, A.CHA: 9}
    assert md.prof_bonus == 3
    assert c.hp == 44                                    # d10: 10 + 2 + 4*(6+2)
    assert c.ac == 19                                    # chain 16 + shield 2 + Defense 1
    assert md.save_bonus(A.STR) == 6 and md.save_bonus(A.CON) == 5    # Fighter saves
    assert md.save_bonus(A.DEX) == 2                     # unproficient: mod only
    assert md.skills == {"Athletics": 6, "Perception": 4, "Intimidation": 2}
    ls = c.attacks["Longsword"]
    assert ls.attack_bonus == 6 and ls.damage[0].bonus == 3   # STR +3, prof +3
    assert md.multiattack == (("Longsword", 2),)        # Extra Attack
    assert c.resources == {"Second Wind": 1, "Action Surge": 1}


def test_fighting_styles():
    assert _ref_fighter("Defense")[1].ac == 19
    assert _ref_fighter("Dueling")[1].attacks["Longsword"].damage[0].bonus == 5   # +2 dmg
    _, archer = _ref_fighter("Archery")
    archer.equipment.main_hand = WEAPONS["Longbow"]     # ranged: +2 to hit
    archer.equipment.ammo = 20
    assert archer.attacks["Longbow"].attack_bonus == 2 + 3 + 2   # dex(+2)+prof(+3)+archery(+2)
    _, gwf = _ref_fighter("Great Weapon Fighting")
    gwf.equipment.main_hand = WEAPONS["Greatsword"]     # two-handed: reroll 1s/2s
    assert gwf.attacks["Greatsword"].damage[0].reroll_below == 2


def test_extra_attack_tiers_and_resources():
    assert extra_attacks("Fighter", 4) == 0
    assert extra_attacks("Fighter", 5) == 1 and extra_attacks("Fighter", 11) == 2
    assert class_resources("Fighter", 1) == {"Second Wind": 1}
    assert class_resources("Fighter", 5)["Action Surge"] == 1


def test_racial_traits_apply():
    ch = make_character("Dain", "Hill Dwarf", "Fighter", 5,
                        {A.STR: 16, A.DEX: 12, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8})
    md = compile_character(ch)
    assert md.abilities[A.CON] == 16                     # Hill Dwarf +2 CON
    assert md.senses["darkvision"] == 60
    assert "poison" in md.resistances
    assert md.speed == 25
    # Dwarven Toughness: +1 HP/level -> 5 more than the same build without it
    assert md.hp == 10 + 3 + 4 * (6 + 3) + 5             # CON 16 -> +3, +5 toughness


def test_second_wind_heals_and_spends_the_resource():
    _, c = _ref_fighter(cid="A")
    e = Encounter(Grid(10, 6), [c, content.make("Goblin", "B", "B", (8, 3))], RNG(1),
                  roll_hp=False)
    c.hp = 10
    e._do_second_wind(c)
    assert c.hp > 10 and c.resources["Second Wind"] == 0


def test_advancement_is_the_source_of_truth():
    # a character is BUILT by levelling up; the flat numbers are derived from the sequence
    ch = Character("Aria", "Human", {A.STR: 15, A.DEX: 14, A.CON: 14, A.INT: 10,
                                     A.WIS: 12, A.CHA: 8}, background="Soldier")
    assert ch.level == 0 and ch.class_levels == {}
    level_up(ch, "Fighter", skills=("Athletics", "Perception"), fighting_style="Dueling")
    level_up(ch, "Fighter")
    level_up(ch, "Fighter")
    level_up(ch, "Fighter", asi={A.STR: 2})            # ASI chosen AT level 4
    assert ch.level == 4 and ch.class_levels == {"Fighter": 4}
    assert ch.fighting_style == "Dueling"              # recalled from the level it was chosen
    assert ch.skill_profs == ("Athletics", "Perception")
    assert compile_character(ch).abilities[A.STR] == 15 + 1 + 2   # base + Human + the ASI


def test_multiclass_hp_uses_max_die_only_at_first_character_level():
    base = {A.STR: 14, A.DEX: 14, A.CON: 14, A.INT: 12, A.WIS: 10, A.CHA: 10}   # CON 14 -> +2
    # start Fighter (d10 max at level 1), then a Wizard-die level (use a d6 class stand-in):
    a = Character("A", "Human", dict(base))
    level_up(a, "Fighter")            # char L1: max d10 = 10, +2 CON
    level_up(a, "Fighter")            # char L2: avg d10 = 6, +2 CON
    # HP = (10+3) + (6+3) = ... CON 14 + Human +1 = 15 -> +2
    assert compile_character(a).hp == (10 + 2) + (6 + 2)


def test_cantrip_damage_scales_by_character_level_for_multiclass_casters():
    # RAW: a cantrip scales at CHARACTER level 5/11/17, not class level. A Wizard 4 / Fighter 4
    # (character level 8) casts Fire Bolt for 2d10, not 1d10.
    from ravel import spells as spellmod
    from ravel.cast import _scaled_damage
    ARR = {A.STR: 8, A.DEX: 12, A.CON: 12, A.INT: 16, A.WIS: 10, A.CHA: 10}
    fb = spellmod.get("Fire Bolt")
    eff = next(e for e in fb.effects if getattr(e, "damage", None))
    mc = make_character("M", "Human", "Wizard", 4, ARR, spells=("Fire Bolt",))
    for _ in range(4):
        level_up(mc, "Fighter")                            # -> character level 8
    md = compile_character(mc)
    assert md.caster_level == 4 and md.cantrip_level == 8  # slots by class level; cantrips by char level
    c = to_combatant(mc, "A", "A", (1, 1))
    assert [(d.count, d.sides) for d in _scaled_damage(fb, eff, 0, c)] == [(2, 10)]
    # a single-class Wizard 4 is unchanged (class level == character level)
    sc = to_combatant(make_character("W", "Human", "Wizard", 4, ARR, spells=("Fire Bolt",)), "B", "B", (2, 2))
    assert [(d.count, d.sides) for d in _scaled_damage(fb, eff, 0, sc)] == [(1, 10)]


def test_level_choices_query_drives_a_builder():
    ch = make_character("Q", "Human", "Fighter", 3,
                        {A.STR: 15, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8})
    from ravel.character import level_choices
    nxt = level_choices(ch, "Fighter")                 # what does Fighter level 4 require?
    assert nxt["class_level"] == 4 and nxt["asi_or_feat"] is True


def _ref_wizard(cid="A", team="A", pos=(2, 4)):
    ch = make_character("Elara", "High Elf", "Wizard", 5,
                        {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 15, A.WIS: 12, A.CHA: 10},
                        background="Sage", skills=("Arcana", "Investigation"),
                        spells=("Fire Bolt", "Magic Missile", "Shield", "Scorching Ray",
                                "Mirror Image", "Fireball", "Lightning Bolt"))
    return ch, to_combatant(ch, cid, team, pos)


def test_indomitable_rerolls_a_failed_save():
    from ravel.rules import saving_throw
    f = make_character("Ser", "Human", "Fighter", 9,
                       {A.STR: 16, A.DEX: 12, A.CON: 14, A.INT: 10, A.WIS: 10, A.CHA: 8})
    c = to_combatant(f, "A", "A", (1, 1))
    assert c.resources["Indomitable"] == 1                # 1 at L9 (2 at 13, 3 at 17)
    log: list = []
    saving_throw(c, A.WIS, 30, RNG(1), important=True, log=log)   # DC 30 -> fails -> reroll
    assert c.resources["Indomitable"] == 0                # the reroll was spent
    assert any("Indomitable" in line for line in log)
    # a non-important save (or no uses left) does not trigger it
    c.resources["Indomitable"] = 1
    saving_throw(c, A.WIS, 30, RNG(1), important=False)
    assert c.resources["Indomitable"] == 1


def test_protection_fighting_style_imposes_disadvantage():
    prot = make_character("Guard", "Human", "Fighter", 3,
                          {A.STR: 15, A.DEX: 12, A.CON: 14, A.INT: 10, A.WIS: 10, A.CHA: 8},
                          fighting_style="Protection",
                          equipment=Loadout(armor=ARMORS["Chain Mail"], shield=True,
                                            main_hand=WEAPONS["Longsword"]))
    ally = make_character("Mage", "High Elf", "Wizard", 3,
                          {A.STR: 8, A.DEX: 14, A.CON: 12, A.INT: 15, A.WIS: 12, A.CHA: 10},
                          spells=("Fire Bolt",))
    pg = to_combatant(prot, "A", "A", (2, 3))
    am = to_combatant(ally, "B", "A", (2, 4))             # allied, adjacent to the protector
    e = Encounter(Grid(10, 6), [pg, am, content.make("Orc", "Z", "B", (3, 4))], RNG(1))
    assert e.protection_reaction(e.combatants["Z"], am) is True
    assert pg.reaction_available is False                 # it cost the protector's reaction
    assert e.protection_reaction(e.combatants["Z"], am) is False   # reaction already spent


def test_wizard_capstones_spell_mastery_and_signature():
    w18 = make_character("Elminster", "Human", "Wizard", 18,
                         {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 17, A.WIS: 12, A.CHA: 10},
                         spells=("Fire Bolt", "Magic Missile", "Shield"),
                         at_will=("Magic Missile", "Shield"))
    c18 = to_combatant(w18, "A", "A", (2, 3))
    assert c18.md.innate == {"Magic Missile": 0, "Shield": 0}      # Spell Mastery = at-will
    # the mastered spell is offered as an innate (slotless) option in combat
    e = Encounter(Grid(12, 6), [c18, content.make("Ogre", "B", "B", (9, 3))], RNG(1))
    e.roll_initiative()
    innate_opts = [o for o in e.enumerate_options(c18) if o.id.startswith("innate:")]
    assert any("Magic Missile" in o.name for o in innate_opts)

    w20 = make_character("Elminster", "Human", "Wizard", 20,
                         {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 18, A.WIS: 12, A.CHA: 10},
                         spells=("Fireball", "Counterspell"),
                         signature=("Fireball", "Counterspell"))
    assert to_combatant(w20, "A", "A", (1, 1)).md.innate == {"Fireball": 1, "Counterspell": 1}


def test_base_class_feature_progression():
    from ravel.character import class_features
    assert class_features("Fighter", 1) == ("Fighting Style", "Second Wind")
    assert class_features("Fighter", 9) == ("Indomitable",)
    assert "Indomitable (three uses)" in class_features("Fighter", 17)
    assert class_features("Fighter", 5) == ("Extra Attack",)
    assert class_features("Wizard", 18) == ("Spell Mastery",)
    assert class_features("Wizard", 20) == ("Signature Spells",)


def _cast(enc, caster, spell, target_id, slot):
    from ravel import cast
    from ravel.models import Option
    cast.cast(enc, caster, Option(f"spell:{spell}", "spell", spell, target_id, "",
                                  spell=spell, slot_level=slot))


def test_champion_improved_critical_crits_more_often():
    from ravel.rules import resolve_attack

    def crit_count(subclass):
        ch = make_character("C", "Human", "Fighter", 5,
                            {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8},
                            subclass=subclass, equipment=Loadout(main_hand=WEAPONS["Greatsword"]))
        n = 0
        for s in range(400):
            e = Encounter(Grid(8, 6), [to_combatant(ch, "A", "A", (2, 3)),
                          content.make("Ogre", "B", "B", (3, 3))], RNG(s), roll_hp=False)
            t = e.combatants["B"]
            t.hp = 500
            resolve_attack(e.combatants["A"], t, e.combatants["A"].attacks["Greatsword"],
                           e.rng, e.log, enc=e)
            n += sum("CRIT" in line for line in e.log)
        return n
    champ, plain = crit_count("Champion"), crit_count("")
    assert to_combatant(make_character("C", "Human", "Fighter", 5,
                        {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8},
                        subclass="Champion", equipment=Loadout(main_hand=WEAPONS["Greatsword"])),
                        "A", "A", (1, 1)).attacks["Greatsword"].crit_range == 19
    assert champ > plain * 1.5              # crit on 19-20 ~doubles crit rate vs 20 only


def test_evocation_empowered_evocation_adds_damage():
    def total_fireball_damage(subclass):
        total = 0
        for s in range(40):
            w = make_character("W", "Human", "Wizard", 10,
                               {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 16, A.WIS: 12, A.CHA: 10},
                               subclass=subclass, spells=("Fireball",))
            c = to_combatant(w, "A", "A", (2, 3))
            e = Encounter(Grid(14, 8), [c, content.make("Ogre", "B", "B", (8, 3))], RNG(s),
                          roll_hp=False)
            t = e.combatants["B"]
            t.hp = 900
            _cast(e, c, "Fireball", "B", 3)
            total += 900 - t.hp
        return total
    # Empowered Evocation adds +INT (3) to one damage roll each cast -> strictly more over 40 casts
    assert total_fireball_damage("School of Evocation") > total_fireball_damage("")


def test_potent_cantrip_deals_half_on_a_save():
    def sacred_flame_damage(subclass):
        total = 0
        for s in range(60):
            w = make_character("W", "Human", "Wizard", 6,
                               {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 16, A.WIS: 12, A.CHA: 10},
                               subclass=subclass, spells=("Sacred Flame",))
            c = to_combatant(w, "A", "A", (2, 3))
            e = Encounter(Grid(10, 6), [c, content.make("Scout", "B", "B", (5, 3))], RNG(s),
                          roll_hp=False)
            t = e.combatants["B"]
            t.hp = 500
            _cast(e, c, "Sacred Flame", "B", 0)
            total += 500 - t.hp
        return total
    # with Potent Cantrip, a target that SAVES still takes half -> more total than without
    assert sacred_flame_damage("School of Evocation") > sacred_flame_damage("")


def test_battle_master_superiority_dice_scale():
    from ravel.character import superiority_dice
    assert superiority_dice(3) == (4, 8) and superiority_dice(7) == (5, 8)
    assert superiority_dice(10) == (5, 10) and superiority_dice(18) == (6, 12)
    ch = make_character("Kael", "Human", "Fighter", 3,
                        {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8},
                        subclass="Battle Master")
    c = to_combatant(ch, "A", "A", (1, 1))
    assert c.md.superiority_die == 8 and c.md.maneuver_dc == 13   # 8 + prof 2 + STR 3
    assert c.resources["Superiority Dice"] == 4


def test_battle_master_maneuver_fires_once_per_turn():
    ch = make_character("Kael", "Human", "Fighter", 5,
                        {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8},
                        subclass="Battle Master",
                        equipment=Loadout(main_hand=WEAPONS["Longsword"]))
    c = to_combatant(ch, "A", "A", (2, 3))
    e = Encounter(Grid(12, 6), [c, content.make("Ogre", "B", "B", (9, 3))], RNG(4),
                  roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    assert c.resources["Superiority Dice"] < 4                    # dice were spent
    assert any("Trip Attack" in line or "Menacing" in line for line in e.log)
    # Extra Attack = 2 hits/turn, but only ONE maneuver spent per turn -> dice drop by <= rounds
    assert c.resources["Superiority Dice"] >= 4 - e.round


def test_battle_master_crit_doubles_die_and_respects_size():
    from ravel.models import SIZE_ORDER, Size
    ch = make_character("Kael", "Human", "Fighter", 5,
                        {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8},
                        subclass="Battle Master",
                        equipment=Loadout(main_hand=WEAPONS["Longsword"]))
    # a crit doubles the superiority die (2d8 can exceed a single d8)
    best = 0
    for s in range(200):
        c = to_combatant(ch, "A", "A", (1, 1))
        e = Encounter(Grid(6, 6), [c, content.make("Ogre", "B", "B", (2, 1))], RNG(s),
                      roll_hp=False)
        best = max(best, e.battle_master_maneuver(c, e.combatants["B"], True))
    assert best > 8                                       # only possible with a doubled die
    # a Huge+ creature can't be knocked prone by Trip (Menacing instead)
    c = to_combatant(ch, "A", "A", (1, 1))
    huge = content.make("Fire Giant", "B", "B", (2, 1))   # Huge
    assert SIZE_ORDER[huge.md.size] > SIZE_ORDER[Size.LARGE]
    e = Encounter(Grid(6, 6), [c, huge], RNG(1), roll_hp=False)
    e.battle_master_maneuver(c, huge, False)
    assert not huge.has("prone")


def test_subclass_recorded_in_advancement():
    ch = make_character("Ser", "Human", "Fighter", 5,
                        {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8},
                        subclass="Champion")
    assert ch.subclass == {"Fighter": "Champion"}          # recorded at level 3
    assert ch.levels[2].subclass == "Champion"


def test_wizard_derived_spellcasting():
    ch, c = _ref_wizard()
    md = c.md
    assert md.abilities[A.INT] == 16                    # High Elf +1 INT
    assert md.spell_ability == A.INT
    assert md.spell_dc == 14 and md.spell_attack == 6   # 8/+prof3/+INT3
    assert md.caster_level == 5
    assert c.slots == {1: 4, 2: 3, 3: 2}                # L5 full caster
    assert c.hp == (6 + 2) + 4 * (4 + 2)                # d6: 8 + 24 = 32 (CON 14 -> +2)
    assert "Fireball" in md.spells and "Fire Bolt" in md.spells


def test_full_caster_slot_table():
    from ravel.character import caster_slots
    assert caster_slots("full", 1) == {1: 2}
    assert caster_slots("full", 5) == {1: 4, 2: 3, 3: 2}
    assert caster_slots("full", 9)[5] == 1              # 5th-level slot at char level 9
    # single-class half-caster (Paladin/Ranger) = full caster of ceil(level/2)
    assert caster_slots("half", 5) == {1: 4, 2: 2}      # Paladin 5 = full-caster 3
    assert caster_slots("half", 2) == {1: 2}            # Paladin 2 = full-caster 1


def test_non_caster_has_no_spellcasting():
    _, fighter = _ref_fighter()
    assert fighter.md.spell_ability is None and fighter.md.spell_slots == {}
    assert fighter.md.spells == ()


def test_wizard_casts_and_wins_in_the_arena():
    def battle(seed):
        _, w = _ref_wizard()
        e = Encounter(Grid(16, 8), [w, content.make("Orc", "B", "B", (12, 3)),
                      content.make("Orc", "C", "B", (12, 5))], RNG(seed), roll_hp=False)
        return e.run({"A": HeuristicController(), "B": HeuristicController()}), e
    assert sum(battle(s)[0] == "A" for s in range(20)) >= 14    # a L5 Wizard handles two Orcs
    _, e = battle(4)
    assert any("A casts" in line for line in e.log)             # it actually cast spells


def test_weapon_and_armor_proficiency_enforced():
    # a Wizard is proficient with neither plate nor a greatsword
    wiz = make_character("Cheater", "Human", "Wizard", 5,
                         {A.STR: 14, A.DEX: 10, A.CON: 12, A.INT: 15, A.WIS: 12, A.CHA: 8},
                         spells=("Fire Bolt", "Magic Missile"),
                         equipment=Loadout(armor=ARMORS["Plate"], shield=True,
                                           main_hand=WEAPONS["Greatsword"]))
    c = to_combatant(wiz, "A", "A", (1, 1))
    assert c.attacks["Greatsword"].attack_bonus == 2      # STR +2, no proficiency bonus
    assert c.armor_penalty is True
    e = Encounter(Grid(10, 6), [c, content.make("Goblin", "B", "B", (8, 3))], RNG(1))
    e.roll_initiative()
    assert not [o for o in e.enumerate_options(c) if o.kind == "spell"]   # can't cast in armor
    # a Fighter is proficient with all of it -> no penalty, full bonus
    _, fc = _ref_fighter()
    assert fc.armor_penalty is False and fc.attacks["Longsword"].attack_bonus == 6


def test_two_weapon_fighting_offhand_damage():
    lo = Loadout(main_hand=WEAPONS["Shortsword"], off_hand=WEAPONS["Shortsword"])
    assert lo.weapon_attacks(3, 2, 2)["Off-hand Shortsword"].damage[0].bonus == 0   # no ability mod
    lo.fighting_style = "Two-Weapon Fighting"
    assert lo.weapon_attacks(3, 2, 2)["Off-hand Shortsword"].damage[0].bonus == 3   # TWF adds it


def test_two_weapon_offhand_attack_fires_in_combat():
    # a dual-wielder must actually get its bonus-action off-hand attack (BUG: it was inert)
    f = make_character("Twin", "Human", "Fighter", 5,
                       {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8},
                       fighting_style="Two-Weapon Fighting",
                       equipment=Loadout(main_hand=WEAPONS["Shortsword"],
                                         off_hand=WEAPONS["Shortsword"]))
    c = to_combatant(f, "A", "A", (2, 3))
    assert c.md.offhand_attack == "Off-hand Shortsword" and c.md.offhand_attack in c.attacks
    e = Encounter(Grid(12, 6), [c, content.make("Ogre", "B", "B", (9, 3))], RNG(3),
                  roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    assert any("Off-hand" in line for line in e.log)     # the bonus-action attack fired
    # a two-handed weapon grants no off-hand attack
    solo = make_character("Solo", "Human", "Fighter", 5,
                          {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8},
                          equipment=Loadout(main_hand=WEAPONS["Greatsword"]))
    assert to_combatant(solo, "A", "A", (1, 1)).md.offhand_attack == ""


def test_ability_scores_capped_at_20():
    ch = make_character("Hulk", "Half-Orc", "Fighter", 12,
                        {A.STR: 17, A.DEX: 10, A.CON: 14, A.INT: 8, A.WIS: 10, A.CHA: 8},
                        asis={4: {A.STR: 2}, 6: {A.STR: 2}, 8: {A.STR: 2}})
    assert compile_character(ch).abilities[A.STR] == 20   # 17 + Half-Orc 2 + 6 ASI, capped


def test_fighter_beats_an_ogre_using_its_features():
    def battle(seed):
        _, f = _ref_fighter("Dueling", pos=(2, 4))
        e = Encounter(Grid(14, 8), [f, content.make("Ogre", "B", "B", (11, 4))], RNG(seed),
                      roll_hp=False)
        return e.run({"A": HeuristicController(), "B": HeuristicController()}), e
    wins = sum(battle(s)[0] == "A" for s in range(20))
    assert wins >= 15                                    # a L5 Fighter should dominate one Ogre
    _, e = battle(7)
    assert any("Action Surge" in line for line in e.log)
