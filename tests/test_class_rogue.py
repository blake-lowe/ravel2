"""Rogue (Slice 6 WP1): Sneak Attack, Cunning Action, Uncanny Dodge, Evasion, Expertise,
Reliable Talent, Stroke of Luck, and the Assassin / Arcane Trickster archetypes. PHB-checkable
numbers + Expertise choice-plumbing (level_choices + round-trip + validate) + arena smoke."""
from __future__ import annotations

from ravel import content, skills
from ravel.character import (caster_slots, character_from_dict, character_to_dict,
                             compile_character, level_choices, level_up, make_character,
                             sneak_attack_dice, to_combatant, validate_character, Character)
from ravel.controllers import HeuristicController
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.equipment import WEAPONS, Loadout
from ravel.grid import Grid
from ravel.models import Ability as A
from ravel.rules import resolve_attack

ARR = {A.STR: 10, A.DEX: 16, A.CON: 14, A.INT: 14, A.WIS: 12, A.CHA: 10}


def _rogue(level, sub="", **kw):
    return make_character("Vex", "Human", "Rogue", level, ARR, subclass=sub,
                          equipment=Loadout(main_hand=WEAPONS["Shortsword"]),
                          skills=("Stealth", "Acrobatics", "Perception", "Investigation"), **kw)


def test_sneak_attack_scales_and_fires_once_per_turn():
    assert (sneak_attack_dice(1), sneak_attack_dice(3), sneak_attack_dice(5)) == (1, 2, 3)
    md = compile_character(_rogue(5))
    sa = md.bonus_damage[0]
    assert sa.name == "Sneak Attack" and sa.damage.count == 3 and sa.damage.sides == 6
    assert sa.once_per_turn
    # with advantage (a prone target) Sneak Attack rides the first hit, once per turn
    c = to_combatant(_rogue(5), "A", "A", (2, 3))
    foe = content.make("Ogre", "B", "B", (3, 3))
    foe.hp = 400
    e = Encounter(Grid(8, 6), [c, foe], RNG(2), roll_hp=False)
    e.roll_initiative()
    foe.conditions["prone"] = __import__("ravel.models", fromlist=["Condition"]).Condition(
        "prone", "A")                                    # melee vs prone (adjacent) = advantage
    fired = False
    for _ in range(8):
        c.bonus_damage_used.clear()                      # simulate a fresh turn
        n0 = len([l for l in e.log if "Sneak Attack" in l])
        resolve_attack(c, foe, c.attacks["Shortsword"], e.rng, e.log, enc=e)
        resolve_attack(c, foe, c.attacks["Shortsword"], e.rng, e.log, enc=e)
        n1 = len([l for l in e.log if "Sneak Attack" in l])
        if n1 > n0:
            assert n1 - n0 == 1                          # at most once per turn
            fired = True
    assert fired


def test_cunning_action_offers_bonus_dash_disengage_hide():
    assert compile_character(_rogue(2)).cunning_action
    c = to_combatant(_rogue(2), "A", "A", (2, 3))
    e = Encounter(Grid(10, 6), [c, content.make("Ogre", "B", "B", (8, 3))], RNG(1), roll_hp=False)
    e.roll_initiative()
    kinds = {o.kind for o in e.enumerate_bonus_options(c)}
    assert "dash" in kinds and "hide" in kinds           # far foe -> Dash (close) + Hide available


def test_uncanny_dodge_halves_one_hit():
    hit_halved = False
    for seed in range(20):
        c = to_combatant(_rogue(5), "A", "A", (2, 3))
        c.hp = 200
        ogre = content.make("Ogre", "B", "B", (3, 3))
        e = Encounter(Grid(8, 6), [c, ogre], RNG(seed), roll_hp=False)
        e.roll_initiative()
        assert c.md.uncanny_dodge
        if resolve_attack(ogre, c, ogre.attacks["Greatclub"], e.rng, e.log, enc=e):
            assert any("Uncanny Dodge" in l for l in e.log)
            assert not c.reaction_available              # the reaction was spent
            hit_halved = True
            break
    assert hit_halved


def test_sneak_attack_requires_a_finesse_or_ranged_weapon():
    # A rogue swinging a Greataxe (heavy, non-finesse, melee) can't Sneak Attack even at advantage.
    axe = make_character("V", "Human", "Rogue", 5, ARR,
                         equipment=Loadout(main_hand=WEAPONS["Greataxe"]),
                         skills=("Stealth", "Acrobatics", "Perception", "Investigation"))
    c = to_combatant(axe, "A", "A", (2, 3))
    foe = content.make("Ogre", "B", "B", (3, 3))
    foe.hp = 400
    foe.conditions["prone"] = __import__("ravel.models", fromlist=["Condition"]).Condition("prone", "A")
    e = Encounter(Grid(8, 6), [c, foe], RNG(2), roll_hp=False)
    e.roll_initiative()
    for _ in range(8):
        c.bonus_damage_used.clear()
        resolve_attack(c, foe, c.attacks["Greataxe"], e.rng, e.log, enc=e)
    assert not any("Sneak Attack" in l for l in e.log)    # gated: not finesse, not ranged


def test_uncanny_dodge_needs_a_seen_attacker():
    c = to_combatant(_rogue(5), "A", "A", (2, 3))
    c.hp = 200
    ogre = content.make("Ogre", "B", "B", (3, 3))
    # heavy fog: the rogue can't see the attacker (enc.can_see is False), so Uncanny Dodge can't fire
    e = Encounter(Grid(8, 6), [c, ogre], RNG(3), roll_hp=False, weather="fog")
    e.roll_initiative()
    assert not e.can_see(c, ogre)
    for seed in range(30):
        e.rng = RNG(seed)
        if resolve_attack(ogre, c, ogre.attacks["Greatclub"], e.rng, e.log, enc=e):
            break
    assert not any("Uncanny Dodge" in l for l in e.log)   # RAW: only vs an attacker you can see
    assert c.reaction_available                            # ...so the reaction is preserved


def test_elusive_denies_advantage_at_18():
    assert not compile_character(_rogue(17)).elusive
    assert compile_character(_rogue(18)).elusive
    c = to_combatant(_rogue(18), "A", "A", (2, 3))
    c.hp = 300
    c.conditions["prone"] = __import__("ravel.models", fromlist=["Condition"]).Condition("prone", "A")
    ogre = content.make("Ogre", "B", "B", (2, 4))         # adjacent melee vs prone = advantage...
    e = Encounter(Grid(8, 6), [c, ogre], RNG(1), roll_hp=False)
    e.roll_initiative()
    resolve_attack(ogre, c, ogre.attacks["Greatclub"], e.rng, e.log, enc=e)
    line = next(l for l in e.log if "Greatclub" in l)
    assert "(adv)" not in line                             # Elusive cancels the advantage


def test_expertise_choice_plumbing_and_double_proficiency():
    # level_choices surfaces the Expertise picks at Rogue 1 and 6
    ch = Character("V", "Human", dict(ARR))
    assert level_choices(ch, "Rogue")["expertise"] == 2
    level_up(ch, "Rogue", skills=("Stealth", "Acrobatics", "Perception", "Investigation"),
             expertise=("Stealth", "Perception"))
    md = compile_character(ch)
    prof = md.prof_bonus
    dex = (md.abilities[A.DEX] - 10) // 2
    assert md.skills["Stealth"] == dex + 2 * prof        # Expertise doubles proficiency
    assert md.skills["Acrobatics"] == dex + prof         # a plain proficient skill
    # round-trips through serialization
    d = character_to_dict(ch)
    assert d["levels"][0]["expertise"] == ["Stealth", "Perception"]
    back = character_from_dict(d)
    assert back.expertise_skills == ("Stealth", "Perception")
    assert character_to_dict(back) == d
    # Expertise on a non-proficient skill is flagged by validate_character
    bad = make_character("V", "Human", "Rogue", 1, ARR, skills=("Stealth", "Acrobatics"),
                         expertise={1: ("Arcana",)})
    assert any("Expertise on Arcana" in w for w in validate_character(bad))


def test_reliable_talent_floors_a_low_roll():
    c = to_combatant(_rogue(11), "A", "A", (1, 1))
    assert c.md.reliable_talent
    assert skills.reliable_roll(c, "Stealth", 3) == 10   # proficient -> treat <=9 as 10
    assert skills.reliable_roll(c, "Stealth", 15) == 15  # a good roll is untouched
    assert skills.reliable_roll(c, "Nature", 3) == 3     # not proficient -> unchanged


def test_stroke_of_luck_turns_a_miss_into_a_hit():
    ch = make_character("V", "Human", "Rogue", 20, ARR,
                        skills=("Stealth", "Acrobatics"),
                        equipment=Loadout(main_hand=WEAPONS["Shortsword"]))
    turned = False
    for seed in range(20):
        c = to_combatant(ch, "A", "A", (2, 3))
        assert c.resources["Stroke of Luck"] == 1
        foe = content.make("Helmed Horror", "B", "B", (3, 3))   # AC 20 -> the rogue sometimes misses
        foe.hp = 400
        e = Encounter(Grid(8, 6), [c, foe], RNG(seed), roll_hp=False)
        e.roll_initiative()
        resolve_attack(c, foe, c.attacks["Shortsword"], e.rng, e.log, enc=e)
        if c.resources["Stroke of Luck"] == 0:
            assert any("Stroke of Luck" in l for l in e.log)
            turned = True
            break
    assert turned


def test_assassinate_auto_crits_a_surprised_foe():
    c = to_combatant(_rogue(3, "Assassin"), "A", "A", (2, 3))
    assert c.md.assassinate
    crit = False
    for seed in range(12):
        c = to_combatant(_rogue(3, "Assassin"), "A", "A", (2, 3))
        foe = content.make("Ogre", "B", "B", (3, 3))
        foe.hp = 400
        foe.surprised = True                             # hasn't acted yet
        e = Encounter(Grid(8, 6), [c, foe], RNG(seed), roll_hp=False)
        e.roll_initiative()
        foe.surprised = True
        if resolve_attack(c, foe, c.attacks["Shortsword"], e.rng, e.log, enc=e):
            assert any("CRIT" in l for l in e.log)       # Assassinate: a hit is an automatic crit
            crit = True
            break
    assert crit


def test_arcane_trickster_is_a_third_caster():
    at = make_character("V", "Human", "Rogue", 3, ARR, subclass="Arcane Trickster",
                        skills=("Stealth", "Acrobatics", "Perception", "Investigation"),
                        spells=("Minor Illusion", "Charm Person"))
    c = to_combatant(at, "A", "A", (1, 1))
    assert c.md.spell_ability == A.INT
    assert c.slots == caster_slots("third", 3)           # third-caster slot table (Rogue level)


def _fight(seed):
    c = to_combatant(_rogue(5, "Assassin"), "A", "A", (2, 3))
    ally = to_combatant(_rogue(5), "C", "A", (2, 4))     # an ally adjacent -> Sneak Attack enabled
    e = Encounter(Grid(12, 6), [c, ally, content.make("Ogre", "B", "B", (8, 3))], RNG(seed),
                  roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    return e


def test_rogue_arena_smoke_and_determinism():
    e1, e2 = _fight(5), _fight(5)
    assert e1.log == e2.log
    assert e1.winner() in ("A", "B")
    assert any("Sneak Attack" in l for l in e1.log)      # sneak attack landed in the melee
