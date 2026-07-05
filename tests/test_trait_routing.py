"""Routing importer trait-text into engine fields (areas / frightful / pounce / swallow /
grapple riders). Parsers tolerate tag-stripped text, so tests use the stored form."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.trait_routing import (grapple_rider, route_all, trait_area,  # noqa: E402
                                 trait_death_burst, trait_frightful,
                                 trait_pounce_or_charge, trait_swallow)


def test_breath_line_from_stripped_text():
    a = trait_area("Acid Breath {@recharge 5}",
                   "The dragon exhales acid in a 60-foot line that is 5 feet wide. Each "
                   "creature in that line must make a 18 Dexterity saving throw, taking 54 "
                   "(12d8) acid damage on a failed save, or half as much on a success.")
    assert a["shape"] == "line" and a["size"] == 60
    assert a["save"] == "DEX" and a["dc"] == 18
    assert a["damage"] == [{"dice": "12d8", "type": "acid"}]
    assert a["recharge"] == "5-6" and a["half_on_save"]


def test_petrifying_breath_escalation_no_damage():
    a = trait_area("Petrifying Breath {@recharge 5}",
                   "exhales petrifying gas in a 30-foot cone. Each creature must succeed on a "
                   "13 Constitution saving throw. On a failed save, the target is restrained "
                   "and begins to turn to stone; at the end of its next turn it is petrified.")
    assert a["shape"] == "cone" and a["damage"] == []
    assert a["rider"] == {"ability": "CON", "dc": 13,
                          "on_fail_condition": "restrained", "escalates_to": "petrified"}


def test_gaze_becomes_self_sphere():
    a = trait_area("Petrifying Gaze",
                   "When a creature starts its turn within 30 feet of the medusa, ... 14 "
                   "Constitution saving throw ... restrained ... turns to stone ... petrified.")
    assert a["shape"] == "sphere" and a["size"] == 30 and a["origin_range"] == 0
    assert a["rider"]["escalates_to"] == "petrified"


def test_frightful_presence_routes():
    fr = trait_frightful("Frightful Presence",
                         "Each creature within 120 feet of the dragon ... 16 Wisdom saving "
                         "throw or become frightened for 1 minute.")
    assert fr["size"] == 120 and fr["rider"]["on_fail_condition"] == "frightened"


def test_death_burst():
    db = trait_death_burst("Death Burst",
                           "When the mephit dies, it explodes in a burst of lava. Each creature "
                           "within 5 feet must make a 11 Dexterity saving throw, taking 7 (2d6) "
                           "fire damage on a failed save, or half as much on a success.")
    assert db["damage"] == [{"dice": "2d6", "type": "fire"}] and db["save"] == "DEX"


def test_pounce_and_charge():
    p = trait_pounce_or_charge("Pounce",
                               "If the lion moves at least 20 feet straight toward a creature "
                               "and then hits it with a claw attack, ... 12 Strength saving "
                               "throw or be knocked prone. If prone, the lion can make one bite "
                               "attack as a bonus action.", ["Bite", "Claw"])
    assert p[0] == "pounce" and p[1]["distance"] == 20 and p[1]["bonus_attack"] == "Bite"
    c = trait_pounce_or_charge("Charge",
                               "If the boar moves at least 20 feet straight toward a target and "
                               "then hits it with a tusk attack, the target takes an extra 7 "
                               "(2d6) slashing damage.", ["Tusk"])
    assert c[0] == "charge" and c[1]["when"] == "charged" and c[1]["threshold"] == 20


def test_swallow_and_grapple_rider():
    sw = trait_swallow("Swallow",
                       "The behir makes one bite against a Medium or smaller target it is "
                       "grappling. ... the target is swallowed ... takes 21 (6d6) acid damage "
                       "at the start of each of the behir's turns.")
    assert sw["acid"] == {"dice": "6d6", "type": "acid"} and sw["max_size"] == "Medium"
    gr = grapple_rider("The target is grappled (escape DC 14). Until the grapple ends...")
    assert gr["on_fail_condition"] == "grappled" and gr["dc"] == 14


def test_blood_frenzy_flag_and_advantage():
    from ravel import content
    from ravel.dice import RNG
    from ravel.engine import Encounter
    from ravel.grid import Grid
    from ravel.rules import resolve_attack

    # routed from the trait, and the engine grants advantage vs a wounded foe
    d = {"traits_flags": [], "traits": [{"name": "Blood Frenzy",
         "text": "The shark has advantage on melee attacks against any creature that "
                 "doesn't have all its hit points."}]}
    assert "blood_frenzy" in route_all(d)
    assert "blood_frenzy" in d["traits_flags"]

    def hits(wounded):
        h = 0
        for s in range(120):
            e = Encounter(Grid(10, 6), [content.make("Giant Shark", "A", "A", (1, 1)),
                          content.make("Ogre", "B", "B", (2, 1))], RNG(s), roll_hp=False)
            b = e.combatants["B"]
            b.hp = b.max_hp - 1 if wounded else b.max_hp
            atk = next(iter(e.combatants["A"].md.attacks.values()))
            h += resolve_attack(e.combatants["A"], b, atk, e.rng, e.log, enc=e)
        return h
    assert hits(True) > hits(False)          # advantage only vs the wounded target


def test_magic_weapons_bypass_nonmagical_resistance():
    from ravel import content
    from ravel.rules import damage_multiplier

    shadow = content.make("Shadow", "B", "B", (0, 0))     # resist_nonmagical_physical
    base = damage_multiplier(shadow, "slashing", magical=False)
    assert damage_multiplier(shadow, "slashing", magical=True) > base   # bypass
    # routed from the trait
    d = {"traits_flags": [], "traits": [{"name": "Magic Weapons",
         "text": "The golem's weapon attacks are magical."}]}
    assert "magic_weapons" in route_all(d)


def test_leadership_boosts_nearby_allies():
    from ravel import content
    from ravel.dice import RNG
    from ravel.engine import Encounter
    from ravel.grid import Grid
    from ravel.rules import resolve_attack

    d = {"traits_flags": [], "traits": [{"name": "Leadership (Recharges after a Rest)",
         "text": "whenever a nonhostile creature within 30 feet of it makes an attack ..."}]}
    assert "leadership" in route_all(d)

    def hits(with_leader):
        h = 0
        for s in range(250):
            combs = [content.make("Hobgoblin", "A0", "A", (1, 1)),
                     content.make("Ogre", "B0", "B", (2, 1))]
            if with_leader:
                combs.append(content.make("Knight", "A1", "A", (1, 2)))
            e = Encounter(Grid(12, 8), combs, RNG(s), roll_hp=False)
            atk = next(iter(e.combatants["A0"].md.attacks.values()))
            h += resolve_attack(e.combatants["A0"], e.combatants["B0"], atk,
                                e.rng, e.log, enc=e)
        return h
    assert hits(True) > hits(False)          # the +1d4 lands more hits


def test_false_appearance_ambush_and_swarm_half_damage():
    from ravel import content
    from ravel.dice import RNG
    from ravel.engine import Encounter
    from ravel.grid import Grid
    from ravel.rules import resolve_attack

    # False Appearance: hidden (ambush) at the start of the encounter
    fa = {"traits_flags": [], "traits": [{"name": "False Appearance",
          "text": "While motionless, the armor is indistinguishable from a suit of armor."}]}
    assert "false_appearance" in route_all(fa)
    e = Encounter(Grid(8, 6), [content.make("Animated Armor", "A", "A", (1, 1)),
                  content.make("Goblin", "B", "B", (2, 1))], RNG(1))
    assert e.combatants["A"].hidden is True

    # Swarm: half damage once bloodied
    sw = {"traits_flags": [], "traits": [{"name": "Swarm",
          "text": "The swarm can occupy another creature's space. It can't regain hit points."}]}
    assert "swarm" in route_all(sw)

    def total(bloodied):
        t = 0
        for s in range(120):
            e = Encounter(Grid(8, 6), [content.make("Swarm of Rats", "A", "A", (1, 1)),
                          content.make("Ogre", "B", "B", (2, 1))], RNG(s), roll_hp=False)
            a = e.combatants["A"]
            a.hp = a.max_hp // 3 if bloodied else a.max_hp
            b = e.combatants["B"]
            b.hp = 200
            atk = next(iter(a.md.attacks.values()))
            before = b.hp
            resolve_attack(a, b, atk, e.rng, e.log, enc=e)
            t += before - b.hp
        return t
    assert total(True) < total(False)


def test_vampire_misty_escape():
    from ravel import content
    from ravel.dice import RNG
    from ravel.engine import Encounter
    from ravel.grid import Grid
    from ravel.rules import apply_damage, handle_drop

    d = {"traits": [{"name": "Misty Escape",
         "text": "When it drops to 0 hit points ... the vampire transforms into a cloud of "
                 "mist instead of falling unconscious."}]}
    assert "misty_escape" in route_all(d)
    assert "misty_escape" in d["triggered_abilities"]

    e = Encounter(Grid(10, 6), [content.make("Vampire", "A", "A", (2, 2)),
                  content.make("Goblin", "B", "B", (3, 2))], RNG(1), roll_hp=False)
    v = e.combatants["A"]
    v.hp = 10
    apply_damage(v, 50, "slashing", e.log, e.rng, enc=e, finalize=False)
    handle_drop(v, 50, "slashing", False, e, e.log, e.rng, 50)
    # fled as mist instead of dying — alive but out of the fight
    assert v.alive and v.misted and v.fled and not v.in_combat
    # caught at 0 a second time (already misted) -> destroyed
    v.hp = 5
    apply_damage(v, 50, "slashing", e.log, e.rng, enc=e, finalize=False)
    handle_drop(v, 50, "slashing", False, e, e.log, e.rng, 50)
    assert not v.alive


def test_route_all_kill_triggers():
    # Rampage (bonus attack on a kill) and a fixed temp-HP-on-kill blessing both route into
    # the trigger layer; the derived "half its max HP" variant has no number, so it is kept.
    d = {"actions": [{"name": "Bite", "kind": "melee", "attack_bonus": 4,
                      "damage": [{"dice": "1d6+2", "type": "piercing"}]}],
         "traits": [
             {"name": "Rampage (bonus)", "text": "After the gnoll reduces a creature to 0 hit "
              "points with a melee attack, it moves up to half its speed and makes a Bite attack."},
             {"name": "Imix's Blessing", "text": "When the firenewt reduces an enemy to 0 hit "
              "points, the firenewt gains 5 temporary hit points."},
             {"name": "Soul Thirst", "text": "When it reduces a creature to 0 hit points, it "
              "gains temporary hit points equal to half the creature's hit point maximum."}]}
    route_all(d)
    assert "rampage" in d["triggered_abilities"]
    assert "temp_hp_on_kill" in d["triggered_abilities"] and d["temp_hp_on_kill"] == 5
    assert [t["name"] for t in d["traits"]] == ["Soul Thirst"]     # derived variant kept as text


def test_route_all_save_advantages():
    # condition-scoped save advantage is extracted and the descriptive trait is kept
    d = {"traits": [
        {"name": "Fey Ancestry", "text": "The chitine has advantage on saving throws against "
         "being {@condition charmed}, and magic can't put the chitine to sleep."},
        {"name": "Magic Resistance", "text": "advantage on saving throws against spells and "
         "other magical effects."}]}          # vs-spells only -> not a condition advantage
    route_all(d)
    assert d.get("save_advantages") == ["charmed"]
    assert {t["name"] for t in d["traits"]} == {"Fey Ancestry", "Magic Resistance"}


def test_save_advantage_reduces_frightened_end_to_end():
    # the engine actually threads the condition into the save: advantage vs 'frightened'
    # makes a creature resist a Frightful Presence more often than an identical one without.
    import dataclasses

    from ravel import content
    from ravel.dice import RNG
    from ravel.engine import Encounter
    from ravel.grid import Grid
    from ravel.models import AreaDef, Ability

    fp = AreaDef(name="Dread", shape="sphere", size=60, origin_range=0, save=Ability.WIS,
                 dc=16, damage=(), half_on_save=False, recharge_min=0, rider=None)

    def frightened_count(give_adv):
        n = 0
        for seed in range(120):
            e = Encounter(Grid(20, 16),
                          [content.make("Ogre", "O", "A", (2, 2)),
                           content.make("Goblin", "G", "B", (3, 2))], RNG(seed), roll_hp=False)
            o, g = e.combatants["O"], e.combatants["G"]
            o.md = dataclasses.replace(o.md, frightful_presence=fp)
            if give_adv:
                g.md = dataclasses.replace(g.md, save_advantages=frozenset({"frightened"}))
            e._do_frightful_presence(o)
            n += "frightened" in g.conditions
        return n

    base, adv = frightened_count(False), frightened_count(True)
    assert base > 0 and adv < base            # advantage on the save -> frightened fewer times


def test_forced_movement_rider_pulls_and_pushes():
    from ravel import content
    from ravel.dice import RNG
    from ravel.engine import Encounter
    from ravel.grid import Grid
    from ravel.models import Ability, SaveRider
    from ravel.rules import _apply_rider

    def move(push, gpos):
        e = Encounter(Grid(30, 20), [content.make("Ogre", "A", "A", (2, 5)),
                      content.make("Goblin", "G", "B", gpos)], RNG(1), roll_hp=False)
        a, g = e.combatants["A"], e.combatants["G"]
        before = e.dist(a, g)
        _apply_rider(SaveRider(ability=Ability.STR, dc=99, push=push), a, g, e.rng, e.log, enc=e)
        return before, e.dist(a, g)                       # dc 99 -> save fails -> moved

    b, af = move(-20, (20, 5))
    assert af == b - 20                                    # pulled 20 ft toward the attacker
    b, af = move(15, (5, 5))
    assert af == b + 15                                    # pushed 15 ft away


def test_route_all_parry_reaction():
    # a Parry reaction (imported as a trait) sets the top-level parry AC bonus
    d = {"traits": [{"name": "Parry (reaction)", "text": "The drow adds 3 to its AC against "
         "one melee attack roll that would hit it. To do so, the drow must see the attacker."}]}
    assert "parry" in route_all(d)
    assert d["parry"] == 3


def test_route_all_bonus_teleport():
    # a bonus-action teleport sets teleport_bonus; a full-action teleport does not
    d = {"actions": [], "traits": [
        {"name": "Astral Step {@recharge 4} (bonus)", "text": "The githyanki teleports, along "
         "with any equipment it is wearing or carrying, up to 30 feet to an unoccupied space."},
        {"name": "Teleport", "text": "Bael teleports up to 120 feet to an unoccupied space."}]}
    route_all(d)
    assert d.get("teleport_bonus") == 30       # only the bonus-action one


def test_bonus_teleport_closes_distance_and_provokes_no_oa():
    import dataclasses

    from ravel import content
    from ravel.dice import RNG
    from ravel.engine import Encounter
    from ravel.grid import Grid

    e = Encounter(Grid(30, 20), [content.make("Ogre", "T", "A", (2, 2)),
                  content.make("Goblin", "G", "B", (20, 2))], RNG(1), roll_hp=False)
    t = e.combatants["T"]
    t.md = dataclasses.replace(t.md, teleport_bonus=30)
    opts = [o for o in e.enumerate_bonus_options(t) if o.kind == "teleport"]
    assert opts                                # offered when the foe is out of reach
    before = e.dist(t, e.combatants["G"])
    e.apply(t, opts[0])
    after = e.dist(t, e.combatants["G"])
    assert after == before - 30                # teleported the full 30 ft toward the foe
    # once adjacent, it is no longer offered (nothing to close)
    t.md = dataclasses.replace(t.md, teleport_bonus=30)
    g = e.combatants["G"]
    g.pos = (t.pos[0] + 1, t.pos[1])
    assert not [o for o in e.enumerate_bonus_options(t) if o.kind == "teleport"]


def test_incorporeal_movement_flag_and_object_damage():
    from ravel import content
    from ravel.dice import RNG
    from ravel.engine import Encounter
    from ravel.grid import Grid
    from ravel.controllers import HeuristicController
    from ravel.rules import apply_condition

    # routed from the trait -> the creature can phase
    d = {"traits": [{"name": "Incorporeal Movement",
         "text": "The ghost can move through other creatures and objects as difficult "
                 "terrain. It takes 5 (1d10) force damage if it ends its turn in an object."}]}
    assert "incorporeal" in route_all(d) and d["incorporeal"] is True

    # 1d10 force when it is forced to end its turn inside a wall
    g = Grid(10, 6, walls={(5, 3)})
    e = Encounter(g, [content.make("Ghost", "A", "A", (5, 3)),
                  content.make("Guard", "B", "B", (6, 3))], RNG(1), roll_hp=False)
    gh = e.combatants["A"]
    apply_condition(gh, "grappled", "B", e.rng, e.log)     # can't move out of the wall
    hp0 = gh.hp
    e.take_turn(gh, HeuristicController())
    assert gh.hp < hp0 and gh.pos == (5, 3)


def test_swarm_can_share_a_creatures_space():
    from ravel import content
    from ravel.dice import RNG
    from ravel.engine import Encounter
    from ravel.grid import Grid

    e = Encounter(Grid(12, 6), [content.make("Swarm of Rats", "A", "A", (3, 3)),
                  content.make("Guard", "B", "B", (6, 3))], RNG(1), roll_hp=False)
    sw, g = e.combatants["A"], e.combatants["B"]
    # a swarm sees no creature blockers, so its reachable set includes the guard's cell...
    assert e._blocked(sw) == set()
    reach = e.grid.reachable(sw.pos, sw.footprint, e._move_budget(sw), e._blocked(sw))
    assert g.pos in reach
    # ...and a swarm doesn't block others (they move through it)
    assert sw.pos not in e._blocked(g)
    # co-located: distance 0, still able to attack
    sw.pos = g.pos
    assert e.dist(sw, g) == 0 and e.reachable_within(sw, g, 5)[0]


def test_route_all_moves_traits_and_is_idempotent():
    d = {"actions": [], "traits": [
        {"name": "Acid Breath {@recharge 5}", "text": "exhales acid in a 60-foot line. Each "
         "creature must make a 18 Dexterity saving throw, taking 54 (12d8) acid damage, or "
         "half as much on a success."},
        {"name": "Keen Smell", "text": "The dragon has advantage on Perception (smell)."}]}
    routed = route_all(d)
    assert any(r.startswith("area") for r in routed)
    assert len(d["areas"]) == 1
    assert [t["name"] for t in d["traits"]] == ["Keen Smell"]   # flavor trait kept
    assert route_all(d) == []                                   # idempotent


# -- audit 2026-07-04: target caps, condition gates, save-or-drop, drains ------------

def test_area_refinements_target_caps_and_drains():
    from tools.trait_routing import area_refinements
    # Demilich Life Drain: up-to-3 cap + vampiric drain
    mt, req, zero, heal = area_refinements(
        "The demilich targets up to three creatures that it can see within 10 feet of it. "
        "Each target must succeed on a {@dc 19} Constitution saving throw or take 21 "
        "({@damage 6d6}) necrotic damage, and the demilich regains hit points equal to the "
        "total damage dealt to all targets.")
    assert (mt, req, zero, heal) == (3, "", False, True)
    # Sea Hag Death Glare: single frightened-only target, save-or-drop
    mt, req, zero, heal = area_refinements(
        "The hag targets one {@condition frightened} creature she can see within 30 feet "
        "of her. If the target can see the hag, it must succeed on a {@dc 11} Wisdom "
        "saving throw against this magic or drop to 0 hit points.")
    assert (mt, req, zero) == (1, "frightened", True)


def test_area_refinements_rejects_protection_and_death_triggers():
    from tools.trait_routing import area_refinements
    # Sculpt-Spells protection ("to ignore the spell") is NOT a target cap
    assert area_refinements(
        "The evoker can select up to three creatures it can see in the area to ignore "
        "the spell, as the evoker sculpts the spell's energy around them.")[0] == 0
    # a death-burst trigger is NOT a save-or-drop rider
    assert not area_refinements(
        "When the mephit dies, it explodes in a burst of dust. Each creature within 5 "
        "feet of it must then succeed on a {@dc 10} Constitution saving throw or be "
        "{@condition blinded} for 1 minute.")[2]


def test_bare_recharge_tag_means_recharge_6():
    a = trait_area("Howling Babble {@recharge}",
                   "Each creature within 30 feet of the allip that can hear it must make a "
                   "{@dc 14} Wisdom saving throw. On a failed save, a target takes 12 "
                   "({@damage 2d8 + 3}) psychic damage, and it is {@condition stunned}.")
    assert a["recharge"] == "6"


def test_no_damage_death_burst_keeps_its_condition():
    db = trait_death_burst("Death Burst",
                           "When the mephit dies, it explodes in a burst of dust. Each "
                           "creature within 5 feet of it must then succeed on a {@dc 10} "
                           "Constitution saving throw or be {@condition blinded} for 1 minute.")
    assert db is not None and db["damage"] == []
    assert db["rider"]["on_fail_condition"] == "blinded"
