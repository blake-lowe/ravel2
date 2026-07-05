"""Bard (Slice 6 WP3): full CHA caster, Bardic Inspiration, Jack of All Trades, Expertise,
Song of Rest, and the College of Lore (Cutting Words) / College of Valor (Extra Attack)
archetypes. PHB-checkable numbers + an arena smoke + a determinism check."""
from __future__ import annotations

from ravel import content
from ravel.character import (bardic_inspiration_die, compile_character, make_character,
                             to_combatant)
from ravel.controllers import HeuristicController
from ravel.dice import RNG, Damage
from ravel.engine import Encounter
from ravel.equipment import WEAPONS, Loadout
from ravel.grid import Grid
from ravel.models import Ability as A, AttackDef
from ravel.rest import short_rest
from ravel.rules import resolve_attack
from ravel.skills import skill_modifier

# Half-Elf: CHA 16 +2 -> 18 (+4). Bard is a full CHA caster.
ARR = {A.STR: 14, A.DEX: 14, A.CON: 14, A.INT: 8, A.WIS: 10, A.CHA: 16}


def _bard(level, sub="", spells=("Vicious Mockery", "Cure Wounds"), **kw):
    return make_character("Lyra", "Half-Elf", "Bard", level, ARR, subclass=sub,
                          spells=spells, **kw)


def test_bard5_slots_inspiration_die_and_ability():
    md = compile_character(_bard(5))
    assert md.spell_slots == {1: 4, 2: 3, 3: 2}            # full caster at level 5
    assert md.spell_ability == A.CHA
    assert md.bardic_inspiration_die == 8                  # d6->d8 at level 5
    assert (bardic_inspiration_die(1), bardic_inspiration_die(5),
            bardic_inspiration_die(10), bardic_inspiration_die(15)) == (6, 8, 10, 12)


def test_bardic_inspiration_banks_a_die_that_is_spent_on_an_attack():
    pc = to_combatant(_bard(5), "A", "A", (1, 1))
    ally = content.make("Ogre", "A2", "A", (1, 2))
    foe = content.make("Goblin", "B", "B", (1, 3))
    e = Encounter(Grid(6, 6), [pc, ally, foe], RNG(1), roll_hp=False)
    e.roll_initiative()
    uses = pc.resources["Bardic Inspiration"]
    insp = next(o for o in e.enumerate_bonus_options(pc) if o.kind == "bardic_inspiration")
    e.apply(pc, insp)
    assert ally.inspiration_die == 8                       # a d8 is banked on the ally
    assert pc.resources["Bardic Inspiration"] == uses - 1
    # the banked die is spent to rescue a near-miss on the ally's next attack roll
    spent = False
    for seed in range(30):
        a2 = content.make("Ogre", "A2", "A", (1, 2))
        a2.inspiration_die = 8
        og = content.make("Goblin", "B", "B", (1, 3))
        enc = Encounter(Grid(6, 6), [a2, og], RNG(seed), roll_hp=False)
        atk = AttackDef(name="Jab", kind="melee", attack_bonus=0,
                        damage=(Damage(1, 4, 0, "bludgeoning"),))
        resolve_attack(a2, og, atk, enc.rng, enc.log, enc=enc)
        if a2.inspiration_die == 0 and any("Bardic Inspiration" in ln for ln in enc.log):
            spent = True
            break
    assert spent


def test_jack_of_all_trades_adds_half_prof_to_unproficient_skills():
    pc = to_combatant(_bard(5), "A", "A", (1, 1))          # prof +3 at level 5
    assert pc.md.jack_of_all_trades
    # Athletics is not a chosen skill here; JoAT gives half prof (1) + STR mod (2) = 3
    assert skill_modifier(pc, "Athletics") == 2 + 1


class _Max:
    def randint(self, a, b): return b
class _MaxRNG(RNG):
    def __init__(self): self.seed = 0; self._r = _Max()


def test_jack_of_all_trades_applies_to_initiative():
    # RAW: Jack of All Trades adds half proficiency to initiative (a DEX check).
    bard = to_combatant(_bard(5), "A", "A", (1, 1))        # prof +3 -> half = 1
    fighter = to_combatant(make_character("F", "Half-Elf", "Fighter", 5, ARR), "B", "B", (2, 2))
    e = Encounter(Grid(6, 6), [bard, fighter], _MaxRNG(), roll_hp=False)
    e.roll_initiative()
    # both roll a natural 20 (max RNG) with the same DEX; the bard is +1 ahead from JoAT
    assert bard.initiative - fighter.initiative == 1


def test_expertise_is_offered_at_bard_3_and_10():
    from ravel.character import level_choices, Character
    ch = Character(name="x", race="Half-Elf", base_abilities=ARR)
    from ravel.character import level_up
    for _ in range(2):
        level_up(ch, "Bard")
    assert level_choices(ch, "Bard")["expertise"] == 2     # the 3rd Bard level offers Expertise
    # a build that took Expertise doubles proficiency on the chosen skill
    pc = to_combatant(_bard(3, skills=("Persuasion", "Stealth", "Perception"),
                            expertise={3: ("Persuasion",)}), "A", "A", (1, 1))
    # Persuasion: CHA 18 (+4) + 2*prof(2) = 8
    assert pc.md.skills["Persuasion"] == 4 + 2 * 2


def test_lore_cutting_words_subtracts_from_an_enemy_attack():
    seen = False
    for seed in range(40):
        bard = to_combatant(_bard(5, "College of Lore"), "A", "A", (1, 1))
        assert bard.md.cutting_words == 8
        ally = content.make("Goblin", "A2", "A", (1, 2))
        foe = content.make("Ogre", "B", "B", (2, 2))
        e = Encounter(Grid(6, 6), [bard, ally, foe], RNG(seed), roll_hp=False)
        e.roll_initiative()
        atk = AttackDef(name="Club", kind="melee", attack_bonus=3,
                        damage=(Damage(2, 8, 4, "bludgeoning"),))
        resolve_attack(foe, ally, atk, e.rng, e.log, enc=e)
        if any("Cutting Words" in ln for ln in e.log):
            seen = True
            break
    assert seen


def test_valor_grants_extra_attack_and_martial_proficiency():
    md = compile_character(_bard(6, "College of Valor",
                                 equipment=Loadout(main_hand=WEAPONS["Longsword"])))
    assert md.multiattack == (("Longsword", 2),)           # Extra Attack at Valor 6
    assert compile_character(_bard(5, "College of Valor")).multiattack == ()


def test_song_of_rest_adds_a_die_to_short_rest_healing():
    ch = _bard(5)
    pc = to_combatant(ch, "A", "A", (1, 1))
    pc.hp = 1                                              # heavily wounded, plenty of Hit Dice
    healed = short_rest(pc, RNG(2), ch, spend=1)
    # one Hit Die (d8 + CON 2) plus a Song of Rest die (d6): at least 1+2+... > a lone die's max
    assert healed >= 4


def _fight(seed):
    pc = to_combatant(_bard(5, "College of Valor",
                            equipment=Loadout(main_hand=WEAPONS["Longsword"])), "A", "A", (2, 3))
    e = Encounter(Grid(14, 6), [pc, content.make("Ogre", "B", "B", (9, 3))], RNG(seed),
                  roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    return e


def test_bard_arena_smoke_and_determinism():
    e1 = _fight(4)
    e2 = _fight(4)
    assert e1.log == e2.log
    assert e1.winner() in ("A", "B")
