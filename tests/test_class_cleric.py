"""Cleric (Slice 6 WP2): full WIS caster (prepared), Channel Divinity — Turn/Destroy
Undead, and the Life Domain (Preserve Life / Divine Strike) and War Domain (War Priest /
Guided Strike / Divine Strike) archetypes. PHB-checkable numbers + arena smoke + determinism."""
from __future__ import annotations

from ravel import content
from ravel.character import (class_resources, compile_character, make_character,
                             to_combatant)
from ravel.controllers import HeuristicController
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.equipment import WEAPONS, Loadout
from ravel.grid import Grid
from ravel.models import Ability as A
from ravel.rules import resolve_attack

ARR = {A.STR: 14, A.DEX: 12, A.CON: 14, A.INT: 8, A.WIS: 16, A.CHA: 12}


def _cleric(level, sub="", **kw):
    return make_character("Cleric", "Human", "Cleric", level, ARR, subclass=sub,
                          equipment=Loadout(main_hand=WEAPONS["Mace"]), **kw)


def test_cleric5_full_caster_slots_and_dc():
    md = compile_character(_cleric(5))
    assert md.spell_slots == {1: 4, 2: 3, 3: 2}            # full caster level-5 row
    assert md.spell_ability == A.WIS
    assert md.spell_dc == 8 + 3 + 3                        # prof 3 + WIS 16 (+3) = 14


def test_channel_divinity_use_progression():
    # Channel Divinity: 1/rest from L2, 2/rest at L6, 3/rest at L18
    assert class_resources("Cleric", 2)["Channel Divinity"] == 1
    assert class_resources("Cleric", 6)["Channel Divinity"] == 2
    assert class_resources("Cleric", 18)["Channel Divinity"] == 3
    assert "Channel Divinity" not in class_resources("Cleric", 1)


def test_turn_undead_routs_high_cr_and_destroys_low_cr():
    # Cleric 5: Destroy Undead threshold CR 1/2. A Skeleton (CR 1/4) that fails is destroyed;
    # a Ghoul (CR 1) that fails is turned (frightened + routed) but survives.
    assert compile_character(_cleric(5)).destroy_undead_cr == 0.5
    destroyed = turned = False
    for seed in range(25):
        cc = to_combatant(_cleric(5), "C", "A", (1, 1))
        skel = content.make("Skeleton", "S", "B", (1, 2))
        ghoul = content.make("Ghoul", "G", "B", (2, 1))
        e = Encounter(Grid(6, 6), [cc, skel, ghoul], RNG(seed), roll_hp=False)
        e.roll_initiative()
        tu = next(o for o in e.enumerate_options(cc) if o.kind == "turn_undead")
        e.apply(cc, tu)
        if not skel.alive:
            destroyed = True
        if ghoul.alive and ghoul.has("frightened") and ghoul.routed:
            turned = True
        if destroyed and turned:
            break
    assert destroyed                                       # Destroy Undead slew the Skeleton
    assert turned                                          # the Ghoul was turned but not destroyed


def test_turn_undead_ends_when_the_creature_takes_damage():
    from ravel.rules import apply_damage
    cc = to_combatant(_cleric(5), "C", "A", (1, 1))        # Destroy threshold CR 1/2: a CR-1 Ghoul is only turned
    ghoul = content.make("Ghoul", "G", "B", (1, 2))
    e = Encounter(Grid(6, 6), [cc, ghoul], RNG(0), roll_hp=False)
    e.roll_initiative()
    turned = False
    for seed in range(30):
        ghoul.conditions.clear(); ghoul.routed = False; ghoul.turned_by = None
        e.rng = RNG(seed)
        e._do_turn_undead(cc)
        cc.resources["Channel Divinity"] = 3               # refund for the next attempt
        if ghoul.has("frightened") and ghoul.routed and ghoul.turned_by == "C":
            turned = True
            break
    assert turned                                          # the ghoul was turned
    apply_damage(ghoul, 3, "slashing", e.log, e.rng, enc=e)  # any damage breaks the turn
    assert not ghoul.has("frightened") and not ghoul.routed and ghoul.turned_by is None


def test_war_gods_blessing_boosts_an_allys_would_miss_attack():
    # War Domain L6: a cleric spends Channel Divinity (reaction) to add +10 to an ally's attack.
    assert compile_character(_cleric(6, "War Domain")).war_gods_blessing
    cleric = to_combatant(_cleric(6, "War Domain"), "C", "A", (1, 1))
    ally = content.make("Goblin", "G", "A", (2, 2))        # a weak ally that would miss
    foe = content.make("Ogre", "B", "B", (2, 3))           # AC 11
    e = Encounter(Grid(6, 6), [cleric, ally, foe], RNG(1), roll_hp=False)
    e.roll_initiative()
    blessed = False
    for seed in range(40):
        cleric.resources["Channel Divinity"] = 2
        cleric.reaction_available = True
        e.rng = RNG(seed)
        e.log.clear()
        resolve_attack(ally, foe, ally.attacks["Scimitar"], e.rng, e.log, enc=e)
        if any("War God's Blessing" in l for l in e.log):
            blessed = True
            break
    assert blessed
    md = compile_character(_cleric(5, "Life Domain"))
    assert md.preserve_life == 25                          # 5 x cleric level
    cc = to_combatant(_cleric(5, "Life Domain"), "C", "A", (1, 1))
    ally = content.make("Ogre", "A2", "A", (1, 2))
    ally.hp = 5                                            # badly wounded (max 59, half = 29)
    foe = content.make("Ogre", "B", "B", (6, 6))
    e = Encounter(Grid(10, 10), [cc, ally, foe], RNG(1), roll_hp=False)
    e.roll_initiative()
    pl = next(o for o in e.enumerate_options(cc) if o.kind == "preserve_life")
    e.apply(cc, pl)
    assert ally.hp == 29                                   # topped up to half its max, no further


def test_war_domain_war_priest_bonus_attack_and_guided_strike():
    md = compile_character(_cleric(6, "War Domain"))
    assert md.war_priest and md.guided_strike
    cc = to_combatant(_cleric(6, "War Domain"), "C", "A", (1, 1))
    assert cc.resources["War Priest"] == 3                 # WIS modifier (+3) uses per rest
    foe = content.make("Ogre", "B", "B", (1, 2))
    e = Encounter(Grid(6, 6), [cc, foe], RNG(1), roll_hp=False)
    e.roll_initiative()
    cc.took_attack_action = True                           # War Priest rides the Attack action
    wp = next(o for o in e.enumerate_bonus_options(cc) if o.kind == "war_priest")
    hp0 = foe.hp
    e.apply(cc, wp)
    assert foe.hp < hp0 and cc.resources["War Priest"] == 2
    # Guided Strike: +10 turns a would-miss (shortfall 1..10) into a hit, spending a Channel use
    cd = cc.resources["Channel Divinity"]
    assert e.cleric_guided_strike(cc, shortfall=6) == 10
    assert cc.resources["Channel Divinity"] == cd - 1
    assert e.cleric_guided_strike(cc, shortfall=11) == 0   # too far off to save


def test_divine_strike_rider_from_level_8():
    riders = {b.name for b in compile_character(_cleric(8, "Life Domain")).bonus_damage}
    assert "Divine Strike" in riders                       # +1d8 once/turn on a weapon hit at L8
    assert "Divine Strike" not in {
        b.name for b in compile_character(_cleric(5, "Life Domain")).bonus_damage}


def _fight(seed):
    cc = to_combatant(_cleric(6, "War Domain"), "A", "A", (2, 3))
    e = Encounter(Grid(14, 6), [cc, content.make("Skeleton", "B", "B", (9, 3))], RNG(seed),
                  roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    return e


def test_cleric_arena_smoke_and_determinism():
    e1 = _fight(4)
    e2 = _fight(4)
    assert e1.log == e2.log
    assert e1.winner() in ("A", "B")
