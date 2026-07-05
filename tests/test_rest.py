"""Rest & recovery (SPEC §14): short/long rests restore HP, Hit Dice, slots, resources."""
from __future__ import annotations

from ravel import rest
from ravel.character import make_character, to_combatant
from ravel.dice import RNG
from ravel.models import Ability as A


def _fighter(level):
    ch = make_character("Ser", "Human", "Fighter", level,
                        {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8})
    return ch, to_combatant(ch, "A", "A", (1, 1))


def test_short_rest_spends_hit_dice_to_heal():
    ch, c = _fighter(5)
    assert rest.hit_dice_left(c) == 5                 # a level-5 character has 5 Hit Dice
    c.hp = 10
    healed = rest.short_rest(c, RNG(1), ch)
    assert healed > 0 and c.hp > 10
    assert rest.hit_dice_left(c) < 5                  # some Hit Dice were spent
    # short rest never overheals
    assert c.hp <= c.max_hp


def test_short_rest_recovers_short_rest_resources_only():
    ch, c = _fighter(9)                               # has Second Wind, Action Surge, Indomitable
    c.resources["Second Wind"] = 0
    c.resources["Action Surge"] = 0
    c.resources["Indomitable"] = 0
    rest.short_rest(c, RNG(1), ch, spend=0)
    assert c.resources["Second Wind"] == 1            # recovers on a short rest
    assert c.resources["Action Surge"] == 1
    assert c.resources["Indomitable"] == 0            # Indomitable is long-rest only


def test_long_rest_restores_everything():
    ch, c = _fighter(9)
    c.hp = 5
    c.resources["Second Wind"] = 0
    c.resources["Indomitable"] = 0
    c.resources["Hit Dice"] = 1                       # spent most Hit Dice
    c.exhaustion = 2
    rest.long_rest(c, ch)
    assert c.hp == c.max_hp                           # full HP
    assert c.resources["Second Wind"] == 1 and c.resources["Indomitable"] == 1  # all resources back (L9 = 1 Indomitable)
    assert c.resources["Hit Dice"] == min(9, 1 + 9 // 2)   # regain half your total Hit Dice
    assert c.exhaustion == 1                          # −1 exhaustion


def test_long_rest_restores_spell_slots():
    ch = make_character("Elara", "High Elf", "Wizard", 5,
                        {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 16, A.WIS: 12, A.CHA: 10},
                        spells=("Fireball", "Magic Missile"))
    c = to_combatant(ch, "A", "A", (1, 1))
    c.slots = {1: 0, 2: 0, 3: 0}                       # all slots spent
    rest.long_rest(c, ch)
    assert c.slots == {1: 4, 2: 3, 3: 2}              # full L5 wizard slots restored


def test_arcane_recovery_restores_slots_on_a_short_rest():
    ch = make_character("Elara", "High Elf", "Wizard", 5,
                        {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 16, A.WIS: 12, A.CHA: 10},
                        spells=("Fireball",))
    c = to_combatant(ch, "A", "A", (1, 1))
    c.slots = {1: 0, 2: 0, 3: 0}                          # all slots expended
    rest.short_rest(c, RNG(1), ch, spend=0)
    assert sum(lvl * n for lvl, n in c.slots.items()) == 3   # recovered up to ceil(5/2)=3 slot-levels
    assert c.resources["Arcane Recovery"] == 0            # once per day
    before = dict(c.slots)
    rest.short_rest(c, RNG(1), ch, spend=0)
    assert c.slots == before                              # no more recovery until a long rest


def test_signature_spells_uses_recover_on_long_rest():
    ch = make_character("Elminster", "Human", "Wizard", 20,
                        {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 18, A.WIS: 12, A.CHA: 10},
                        spells=("Fireball",), signature=("Fireball",))
    c = to_combatant(ch, "A", "A", (1, 1))
    c.innate_left["Fireball"] = 0                     # used the signature casting
    rest.long_rest(c, ch)
    assert c.innate_left["Fireball"] == 1             # innate/daily uses restored
