"""The 5e.tools content importer (SPEC §17) — unit tests for the tag/stat parsers."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.import_5etools import (cr_value, parse_area, parse_attack,  # noqa: E402
                                  parse_multiattack, strip_tags)


def test_strip_tags_keeps_multiword_display():
    assert strip_tags("{@spell fire bolt}") == "fire bolt"
    assert strip_tags("{@spell cone of cold}") == "cone of cold"
    assert strip_tags("{@item leather armor|phb}") == "leather armor"
    assert strip_tags("take {@damage 2d6} fire") == "take 2d6 fire"
    assert strip_tags("the {@action Dash} action") == "the Dash action"


def test_cr_value_handles_fractions_and_lair():
    assert cr_value({"cr": "1/4"}) == 0.25
    assert cr_value({"cr": "1/8"}) == 0.125
    assert cr_value({"cr": "17"}) == 17.0
    assert cr_value({"cr": {"cr": "13", "lair": "15"}}) == 13.0


def test_parse_attack_melee_ranged_and_flat_damage():
    scim = parse_attack("Scimitar",
                        "{@atk mw} {@hit 4} to hit, reach 5 ft. {@h}5 ({@damage 1d6 + 2}) slashing damage.")
    assert scim["kind"] == "melee" and scim["attack_bonus"] == 4 and scim["reach"] == 5
    assert scim["damage"] == [{"dice": "1d6+2", "type": "slashing"}]
    bow = parse_attack("Shortbow",
                       "{@atk rw} {@hit 4} to hit, range 80/320 ft. {@h}5 ({@damage 1d6+2}) piercing damage.")
    assert bow["kind"] == "ranged" and bow["range"] == [80, 320]
    # tiny beasts deal flat damage with no dice tag
    rat = parse_attack("Bite", "{@atk mw} {@hit 0} to hit, reach 5 ft. {@h}1 piercing damage.")
    assert rat["damage"] == [{"dice": "1d1", "type": "piercing"}]


def test_parse_attack_rider_condition_on_hit():
    # multi-type on-hit damage folds into the attack; the save imposes the condition
    bite = parse_attack("Bite",
                        "{@atk mw} {@hit 5} to hit. {@h}6 ({@damage 1d8+3}) piercing damage plus 3 "
                        "({@damage 1d6}) poison damage, and the target must make a {@dc 11} "
                        "Constitution saving throw or be {@condition poisoned}.")
    assert {"dice": "1d8+3", "type": "piercing"} in bite["damage"]
    assert {"dice": "1d6", "type": "poison"} in bite["damage"]
    assert bite["rider"]["ability"] == "CON" and bite["rider"]["dc"] == 11
    assert bite["rider"]["on_fail_condition"] == "poisoned"


def test_parse_attack_choice_type_damage_and_single_range():
    # damage whose type is chosen, and a single "range N feet" (no long band) — both were dropped
    bolt = parse_attack("Chromatic Bolt",
                        "{@atk rs} {@hit 4} to hit, range 60 feet, one target. {@h}9 "
                        "({@damage 2d6 + 2}) of a type of the kobold's choice: acid, cold, fire, "
                        "lightning, or poison.")
    assert bolt is not None and bolt["kind"] == "ranged"
    assert bolt["damage"] == [{"dice": "2d6+2", "type": "acid"}]   # first listed choosable type
    assert bolt["range"] == [60, 60]


def test_parse_attack_zero_damage_grapple_is_kept():
    # a grapple/restrain attack that deals NO damage must be kept (its control is the point)
    leg = parse_attack("Sticky Leg",
                       "{@atk mw} {@hit 5} to hit, reach 5 ft., one Medium or smaller creature. "
                       "{@h}The target is stuck to the steeder's leg and {@condition grappled} "
                       "(escape {@dc 12}).")
    assert leg is not None and leg["damage"] == []
    assert leg["rider"]["on_fail_condition"] == "grappled" and leg["rider"]["dc"] == 12
    # webbing uses a "DC N Strength check" to burst (no "escape" keyword) -> restrained rider
    web = parse_attack("Web",
                       "{@atk rw} {@hit 5} to hit, range 30/60 ft., one Large or smaller "
                       "creature. {@h}The target is {@condition restrained} by webbing. As an "
                       "action, the {@condition restrained} target can make a {@dc 11} Strength "
                       "check, bursting the web on a success.")
    assert web is not None and web["damage"] == [] and web["kind"] == "ranged"
    assert web["rider"]["on_fail_condition"] == "restrained" and web["rider"]["dc"] == 11


def test_parse_multiattack_makes_n_attacks_using_list():
    # "makes N attacks, using X, Y, or both" — the comma truncates the plain scan; assign all N
    ma = parse_multiattack(
        "The blackguard makes three attacks, using Glaive, Shortbow, or both.",
        ["Glaive", "Shortbow"])
    assert ma == [{"name": "Glaive", "count": 3}]     # all three to the first named (strongest)


def test_parse_multiattack_maps_counts_to_real_attack_names():
    ma = parse_multiattack(
        "The dragon makes three attacks: one with its bite and two with its claws.",
        ["Bite", "Claws"])
    assert {"name": "Bite", "count": 1} in ma
    assert {"name": "Claws", "count": 2} in ma      # 'claws' matched, real name kept


def test_parse_spellcasting_innate_will_and_daily():
    from tools.import_5etools import parse_spellcasting
    known = {"darkness": "Darkness", "faerie fire": "Faerie Fire", "fireball": "Fireball"}
    m = {"spellcasting": [{
        "name": "Innate Spellcasting",
        "headerEntries": ["spell save {@dc 13}."],
        "ability": "cha",
        "will": ["{@spell dancing lights}", "{@spell faerie fire}"],   # at-will
        "daily": {"1e": ["{@spell darkness}"], "3": ["{@spell fireball}"]},
    }]}
    sc = parse_spellcasting(m, known)
    assert sc["ability"] == "CHA" and sc["save_dc"] == 13
    # dancing lights not in library -> dropped; faerie fire at-will (0); darkness 1/day; fireball 3/day
    assert sc["innate"] == {"Faerie Fire": 0, "Darkness": 1, "Fireball": 3}


def test_parse_area_breath_weapon():
    area = parse_area("Fire Breath {@recharge 5}",
                      "The dragon exhales fire in a 60-foot cone. Each creature must make a "
                      "{@dc 21} Dexterity saving throw, taking 63 ({@damage 18d6}) fire damage "
                      "on a failed save, or half as much on a success.")
    assert area["shape"] == "cone" and area["size"] == 60
    assert area["save"] == "DEX" and area["dc"] == 21
    assert area["damage"] == [{"dice": "18d6", "type": "fire"}] and area["half_on_save"]
    assert area["recharge"] == "5-6"
    assert area["rider"] is None                    # a plain breath weapon has no condition


def test_parse_area_populates_condition_rider():
    # an area that also imposes a condition on a failed save carries an on-fail rider
    howl = parse_area("Mind-Breaking Howl {@recharge 4}",
                      "The howler emits a keening howl in a 60-foot cone. Each creature in that "
                      "area must succeed on a {@dc 13} Wisdom saving throw or take 16 "
                      "({@damage 3d10}) psychic damage and be {@condition frightened} until the "
                      "end of the howler's next turn.")
    assert howl["damage"] == [{"dice": "3d10", "type": "psychic"}]
    assert howl["rider"] == {"ability": "WIS", "dc": 13, "on_fail_condition": "frightened"}


def test_parse_attack_life_drain_sets_reduces_max_hp():
    drain = parse_attack("Life Drain",
                         "{@atk mw} {@hit 6} to hit, reach 5 ft., one creature. {@h}9 "
                         "({@damage 2d6 + 2}) necrotic damage. The target must succeed on a "
                         "{@dc 14} Constitution saving throw, or its hit point maximum is reduced "
                         "by an amount equal to the damage taken.")
    assert drain["reduces_max_hp"] is True
    # a fixed "reduced by 4 (1d8)" variant is NOT flagged (engine would drain the full damage)
    barbed = parse_attack("Barbed Tail",
                          "{@atk mw} {@hit 7} to hit, reach 10 ft., one target. {@h}5 "
                          "({@damage 1d6 + 2}) piercing damage, and the target's hit point "
                          "maximum is reduced by 4 ({@dice 1d8}).")
    assert "reduces_max_hp" not in barbed


def test_parse_area_cube_with_save_or_take_and_rider():
    # a cube AoE (engine supports cube) with "save or take" damage + a condition rider
    scream = parse_area("Sonic Scream",
                        "The screamer emits destructive energy in a 15-foot cube. Each creature "
                        "in that area must succeed on a {@dc 11} Strength saving throw or take 7 "
                        "({@damage 2d6}) thunder damage and be knocked {@condition prone}.")
    assert scream["shape"] == "cube" and scream["size"] == 15
    assert scream["damage"] == [{"dice": "2d6", "type": "thunder"}]
    assert scream["half_on_save"] is True                # "save or take" -> half rewards the save
    assert scream["rider"]["on_fail_condition"] == "prone"


def test_parse_area_flat_damage_auto_then_save_vs_condition():
    # flat "takes 45 radiant damage" (no dice tag) with an automatic-damage + save-vs-stun burst
    edict = parse_area("Blazing Edict {@recharge 5}",
                       "Arcane energy emanates from the marut's chest in a 60-foot cube. Every "
                       "creature in that area takes 45 radiant damage. Each creature that takes "
                       "any of this damage must succeed on a {@dc 20} Wisdom saving throw or be "
                       "{@condition stunned}.")
    assert edict["shape"] == "cube" and edict["size"] == 60
    assert edict["damage"] == [{"dice": "45d1", "type": "radiant"}]   # flat -> Nd1
    assert edict["half_on_save"] is False                # auto damage: full even on a success
    assert edict["rider"]["on_fail_condition"] == "stunned"


def test_parse_forced_movement_push_and_pull():
    # an area that pushes on a failed save carries a positive push; a pull is negative
    blast = parse_area("Force Blast",
                       "Energy erupts in a 20-foot cube. Each creature must make a {@dc 16} "
                       "Constitution saving throw, taking 36 ({@damage 8d8}) force damage and "
                       "being pushed up to 10 feet on a failure.")
    assert blast["rider"]["push"] == 10
    spout = parse_area("Grasping Spout",
                       "A geyser fills a 20-foot-radius sphere. Each creature must succeed on a "
                       "{@dc 18} Strength saving throw or be pulled up to 60 feet toward the "
                       "wastrilith and take 21 ({@damage 6d6}) bludgeoning damage.")
    assert spout["rider"]["push"] == -60                 # pull = negative


def test_parse_area_once_per_encounter_rest_or_day():
    # "Recharges after a Short or Long Rest" and "N/Day" areas must fire once per fight, not
    # every round — modelled as recharge "once" (recharge_min 7, unreachable on a d6). Name cleaned.
    from ravel.statblock import _area_from
    flare = parse_area("Lightning Flare (Recharges after a Short or Long Rest)",
                       "The scout releases a burst of light in a 20-foot-radius sphere. Each "
                       "creature there must make a {@dc 13} Constitution saving throw or take 7 "
                       "({@damage 2d6}) radiant damage.")
    assert flare["recharge"] == "once"
    assert flare["name"] == "Lightning Flare"                 # usage parenthetical stripped
    assert _area_from(flare).recharge_min == 7                # never recharges within a fight
    day = parse_area("Merrshaulk's Slumber (1/Day)",
                     "The yuan-ti targets a 30-foot-radius sphere. Each creature must succeed on "
                     "a {@dc 14} Wisdom saving throw or take 10 ({@damage 3d6}) psychic damage.")
    assert day["recharge"] == "once" and day["name"] == "Merrshaulk's Slumber"


def test_parse_attack_charge_damage_not_double_counted():
    # the "extra ... if it moved 20 ft" charge dice must NOT be summed into base hit damage;
    # it is lifted out as a `charged` conditional (marker on the attack dict for convert()).
    gore = parse_attack("Gore",
                        "{@atk mw} {@hit 7} to hit, reach 5 ft., one target. {@h}14 "
                        "({@damage 2d8 + 5}) piercing damage. If the aurochs moved at least 20 "
                        "feet straight toward the target immediately before the hit, the target "
                        "takes an extra 9 ({@damage 2d8}) piercing damage, and the target must "
                        "succeed on a {@dc 15} Strength saving throw or be knocked "
                        "{@condition prone} if it is a creature.")
    assert gore["damage"] == [{"dice": "2d8+5", "type": "piercing"}]   # base only, once
    assert gore["_charge_bonus"] == {"threshold": 20, "dice": "2d8", "type": "piercing"}


def test_parse_attack_buff_form_alternative_dropped():
    # "or M (XdY) damage while <enlarged/raging>" is a buff alternative, not a second hit
    blade = parse_attack("Soulblade",
                         "{@atk ms} {@hit 5} to hit, reach 5 ft., one target. {@h}10 "
                         "({@damage 2d6 + 3}) force damage, or 13 ({@damage 3d6 + 3}) force "
                         "damage while under the effect of Enlarge.")
    assert blade["damage"] == [{"dice": "2d6+3", "type": "force"}]     # base only
    assert "_charge_bonus" not in blade


def test_convert_regeneration_stopped_by_from_trait():
    from tools.import_5etools import convert
    m = {"name": "Trolly", "size": ["M"], "cr": "5",
         "str": 18, "dex": 13, "con": 20, "int": 7, "wis": 9, "cha": 7,
         "trait": [{"name": "Regeneration", "entries": [
             "The troll regains 10 hit points at the start of its turn. If the troll takes "
             "acid or fire damage, this trait doesn't function at the start of the troll's "
             "next turn."]}]}
    out = convert(m, {}, "test")
    assert out["regeneration"] == {"amount": 10, "stopped_by": ["acid", "fire"]}
