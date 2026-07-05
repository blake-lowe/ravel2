"""Warlock (Slice 6 WP3): pact magic, Eldritch Blast with Agonizing Blast, Hex, Mystic
Arcanum, and the Fiend (Dark One's Blessing) / Great Old One (Entropic Ward) patrons.
PHB-checkable numbers + an arena smoke + a determinism check."""
from __future__ import annotations

from ravel import content
from ravel.character import compile_character, make_character, to_combatant
from ravel.controllers import HeuristicController
from ravel.dice import RNG
from ravel.effects import damage_riders_vs
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Ability as A
from ravel.rest import short_rest

# Tiefling: CHA 16 base +2 -> 18 (+4). Warlock is a pact CHA caster.
ARR = {A.STR: 10, A.DEX: 14, A.CON: 14, A.INT: 8, A.WIS: 10, A.CHA: 16}


def _lock(level, sub="", spells=("Eldritch Blast", "Hex"), **kw):
    return make_character("Bael", "Tiefling", "Warlock", level, ARR, subclass=sub,
                          spells=spells, **kw)


def test_warlock5_two_third_level_pact_slots():
    md = compile_character(_lock(5))
    assert md.spell_slots == {3: 2}                        # Pact Magic: two 3rd-level slots at L5
    assert md.spell_ability == A.CHA
    assert md.spell_dc == 8 + 3 + 4                        # prof 3 + CHA 18 (+4) = DC 15
    assert md.agonizing_blast                              # Agonizing Blast auto-granted at L2


def test_eldritch_blast_fires_two_beams_with_cha_damage():
    pc = to_combatant(_lock(5), "A", "A", (1, 1))
    foe = content.make("Ogre", "B", "B", (1, 2))
    e = Encounter(Grid(6, 6), [pc, foe], RNG(3), roll_hp=False)
    e.roll_initiative()
    eb = next(o for o in e.enumerate_options(pc) if o.name == "Eldritch Blast")
    e.apply(pc, eb)
    beams = [ln for ln in e.log if "spell attack" in ln]
    assert len(beams) == 2                                 # two beams at L5 (1/5/11/17)
    # Agonizing Blast: each beam that hits deals 1d10 + CHA (4) force -> 5..14
    for ln in e.log:
        if "takes" in ln and "force" in ln:
            dealt = int(ln.split("takes")[1].split("force")[0])
            assert 5 <= dealt <= 14


def test_hex_places_a_necrotic_rider_via_the_mark_pattern():
    pc = to_combatant(_lock(5), "A", "A", (1, 1))
    foe = content.make("Ogre", "B", "B", (1, 2))
    e = Encounter(Grid(6, 6), [pc, foe], RNG(1), roll_hp=False)
    e.roll_initiative()
    hexo = next(o for o in e.enumerate_bonus_options(pc) if o.name == "Hex")
    e.apply(pc, hexo)
    assert pc.concentration and pc.concentration.spell == "Hex"   # bonus action, concentration
    riders = damage_riders_vs(pc, foe.id)
    assert [(d.count, d.sides, d.type) for d in riders] == [(1, 6, "necrotic")]


def test_pact_slots_return_on_a_short_rest():
    ch = _lock(5)
    pc = to_combatant(ch, "A", "A", (1, 1))
    pc.slots[3] = 0                                        # both slots expended
    short_rest(pc, RNG(1), ch)
    assert pc.slots[3] == 2                                # Pact Magic recharges on a short rest


def test_fiend_dark_ones_blessing_grants_temp_hp_on_a_kill():
    pc = to_combatant(_lock(5, "The Fiend"), "A", "A", (1, 1))
    assert pc.md.temp_hp_on_kill == 4 + 5                  # CHA mod (4) + warlock level (5)
    assert "temp_hp_on_kill" in pc.md.triggered_abilities
    weak = content.make("Goblin", "B", "B", (1, 2))
    e = Encounter(Grid(6, 6), [pc, weak], RNG(1), roll_hp=False)
    e.roll_initiative()
    weak.hp = 1
    e.fire_on_kill(pc, weak, melee=True)                   # simulate the drop trigger
    assert pc.temp_hp == 9                                 # gains CHA + level temp HP


def test_great_old_one_entropic_ward_is_a_reaction_resource():
    pc = to_combatant(_lock(6, "The Great Old One"), "A", "A", (1, 1))
    assert pc.md.entropic_ward
    assert pc.resources["Entropic Ward"] == 1              # once per short rest
    assert compile_character(_lock(5, "The Great Old One")).entropic_ward is False


def test_mystic_arcanum_makes_a_high_level_spell_an_innate_1_per_day():
    # a warlock 11 that knows a 6th-level spell gets it as an innate 1/day (pact slots cap at 5th)
    md = compile_character(_lock(11, spells=("Eldritch Blast", "Chain Lightning")))
    assert md.innate.get("Chain Lightning") == 1
    # ...but not before level 11
    assert "Chain Lightning" not in compile_character(
        _lock(10, spells=("Eldritch Blast", "Chain Lightning"))).innate


def _fight(seed):
    pc = to_combatant(_lock(5, "The Fiend"), "A", "A", (2, 3))
    e = Encounter(Grid(14, 6), [pc, content.make("Ogre", "B", "B", (9, 3))], RNG(seed),
                  roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    return e


def test_warlock_arena_smoke_and_determinism():
    e1 = _fight(7)
    e2 = _fight(7)
    assert e1.log == e2.log
    assert e1.winner() in ("A", "B")
    assert any("Eldritch Blast" in line for line in e1.log)
