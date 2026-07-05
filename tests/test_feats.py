"""Feats (§12.3): taken instead of an ASI, applying build-time and combat effects."""
from __future__ import annotations

from ravel import content
from ravel.character import make_character, to_combatant
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.equipment import WEAPONS, Loadout
from ravel.grid import Grid
from ravel.models import Ability as A
from ravel.rules import resolve_attack


def _fighter(level, feats=None, **kw):
    return make_character("F", "Human", "Fighter", level,
                          {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 12, A.WIS: 12, A.CHA: 8},
                          feats=feats or {}, **kw)


def test_tough_adds_hp_per_level():
    plain = to_combatant(_fighter(5), "A", "A", (1, 1))
    tough = to_combatant(_fighter(5, {4: "Tough"}), "A", "A", (1, 1))
    assert tough.hp == plain.hp + 10                     # +2 per level


def test_resilient_grants_ability_and_save_proficiency():
    c = to_combatant(_fighter(4, {4: "Resilient (Constitution)"}), "A", "A", (1, 1))
    assert c.md.abilities[A.CON] == 16                   # 14 base + Human 1 + feat 1
    assert A.CON in c.md.save_profs


def test_alert_boosts_initiative_and_prevents_surprise():
    c = to_combatant(_fighter(4, {4: "Alert"}), "A", "A", (1, 1))
    assert c.md.alert
    c.surprised = True
    e = Encounter(Grid(6, 6), [c, content.make("Goblin", "B", "B", (2, 2))], RNG(1))
    e.roll_initiative()
    assert c.surprised is False                          # Alert can't be surprised


def test_magic_initiate_grants_castable_cantrips():
    c = to_combatant(_fighter(4, {4: "Magic Initiate (Wizard)"}), "A", "A", (1, 1))
    assert "Fire Bolt" in c.md.spells and c.md.spell_ability == A.INT   # INT-cast even as a Fighter


def test_great_weapon_master_power_attack_raises_damage_vs_low_ac():
    def total_damage(gwm):
        feats = {4: "Great Weapon Master"} if gwm else {}
        total = 0
        for s in range(200):
            c = to_combatant(_fighter(5, feats, equipment=Loadout(main_hand=WEAPONS["Greatsword"])),
                             "A", "A", (2, 3))
            foe = content.make("Goblin", "B", "B", (3, 3))   # low AC (15) -> -5/+10 pays off
            foe.hp = 500
            e = Encounter(Grid(8, 6), [c, foe], RNG(s), roll_hp=False)
            resolve_attack(c, foe, c.attacks["Greatsword"], e.rng, e.log, enc=e)
            total += 500 - foe.hp
        return total
    assert total_damage(True) > total_damage(False)     # +10 on hits beats the -5 to hit vs low AC


class _Max:
    def randint(self, a, b): return b
class _MaxRNG(RNG):
    def __init__(self): self.seed = 0; self._r = _Max()


def test_great_weapon_master_grants_a_bonus_attack_on_a_crit():
    c = to_combatant(_fighter(5, {4: "Great Weapon Master"},
                              equipment=Loadout(main_hand=WEAPONS["Greatsword"])), "A", "A", (2, 3))
    assert c.md.gwm
    foe = content.make("Ogre", "B", "B", (2, 4))
    foe.hp = 500
    e = Encounter(Grid(8, 6), [c, foe], _MaxRNG(), roll_hp=False)   # nat 20 -> guaranteed crit
    e.roll_initiative()
    c.took_attack_action = True
    assert not c.gwm_bonus_ready
    resolve_attack(c, foe, c.attacks["Greatsword"], e.rng, e.log, enc=e)
    assert c.gwm_bonus_ready                              # a crit unlocks the bonus-action attack
    assert any(o.id.startswith("gwm->") for o in e.enumerate_bonus_options(c))
    # the flag resets at the start of the next turn
    e.start_of_turn(c)
    assert not c.gwm_bonus_ready


def test_savage_attacks_adds_one_weapon_die_on_a_crit():
    # Half-Orc Savage Attacks: roll ONE weapon die extra on a melee crit (not d0.count dice).
    # Greatsword (2d6) crit = 4x6 + STR 4 = 28, + one extra d6 (max 6) = 34; the old bug added 2d6.
    orc = make_character("Grok", "Half-Orc", "Fighter", 1,
                         {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 8, A.WIS: 10, A.CHA: 8},
                         equipment=Loadout(main_hand=WEAPONS["Greatsword"]))
    c = to_combatant(orc, "A", "A", (2, 3))
    assert c.md.savage_attacks
    foe = content.make("Ogre", "B", "B", (2, 4))
    foe.hp = 500
    e = Encounter(Grid(8, 6), [c, foe], _MaxRNG(), roll_hp=False)
    e.roll_initiative()
    resolve_attack(c, foe, c.attacks["Greatsword"], e.rng, e.log, enc=e)
    assert 500 - foe.hp == 34                             # not 40 (the multi-die over-roll)


def test_sharpshooter_ignores_cover():
    # a sharpshooter's attack computes the target AC without the cover bonus
    c = to_combatant(_fighter(5, {4: "Sharpshooter"},
                     equipment=Loadout(main_hand=WEAPONS["Longbow"], ammo=99)), "A", "A", (2, 3))
    plain = to_combatant(_fighter(5, equipment=Loadout(main_hand=WEAPONS["Longbow"], ammo=99)),
                         "C", "A", (2, 3))
    foe = content.make("Goblin", "B", "B", (6, 3))
    foe.hp = 500
    e = Encounter(Grid(10, 6), [c, plain, foe], RNG(2), roll_hp=False)
    resolve_attack(c, foe, c.attacks["Longbow"], e.rng, e.log, enc=e, cover_ac=5)
    assert "cover" not in e.log[-1]                      # Sharpshooter ignores the +5 cover
    resolve_attack(plain, foe, plain.attacks["Longbow"], e.rng, e.log, enc=e, cover_ac=5)
    assert "cover" in e.log[-1]                          # a normal archer still faces it


def test_sharpshooter_and_gwm_raise_damage_via_power_attack():
    def total_damage(feat, weapon, ammo=0):
        total = 0
        for s in range(200):
            c = to_combatant(_fighter(5, {4: feat} if feat else {},
                             equipment=Loadout(main_hand=WEAPONS[weapon], ammo=ammo)),
                             "A", "A", (2, 3))
            foe = content.make("Goblin", "B", "B", (4, 3))
            foe.hp = 800
            e = Encounter(Grid(8, 6), [c, foe], RNG(s), roll_hp=False)
            resolve_attack(c, foe, c.attacks[weapon], e.rng, e.log, enc=e)
            total += 800 - foe.hp
        return total
    assert total_damage("Sharpshooter", "Longbow", 99) > total_damage("", "Longbow", 99)


def test_lucky_rerolls_a_failed_save():
    from ravel.rules import saving_throw
    c = to_combatant(_fighter(5, {4: "Lucky"}), "A", "A", (1, 1))
    assert c.resources["Lucky"] == 3
    saving_throw(c, A.WIS, 30, RNG(1), important=True, log=[])   # auto-fails -> reroll
    assert c.resources["Lucky"] == 2                            # a Luck point was spent


def test_mobile_grants_speed_and_skips_oas_from_attacked_foes():
    c = to_combatant(_fighter(5, {4: "Mobile"}), "A", "A", (5, 3))
    assert c.md.speed == 40 and c.md.mobile                     # +10 speed
    foe = content.make("Ogre", "B", "B", (6, 3))
    e = Encounter(Grid(12, 6), [c, foe], RNG(1), roll_hp=False)
    c.attacked_this_turn.add("B")                               # melee'd the ogre this turn
    n = len([l for l in e.log if "opportunity" in l])
    e._do_move(c, (2, 3))                                       # move away past the ogre's reach
    assert not any("opportunity attack from B" in l for l in e.log[n:])   # no OA from that foe


def test_polearm_master_bonus_attack_and_reach_oa():
    pam = to_combatant(_fighter(5, {4: "Polearm Master"},
                       equipment=Loadout(main_hand=WEAPONS["Glaive"])), "A", "A", (3, 3))
    assert pam.md.polearm_master and pam.attacks["Glaive"].reach == 10
    e = Encounter(Grid(12, 6), [pam, content.make("Goblin", "B", "B", (3, 4))], RNG(1),
                  roll_hp=False)
    e.roll_initiative()
    assert any(o.kind == "polearm" for o in e.enumerate_bonus_options(pam))   # butt-end attack
    # a foe entering the glaive's reach provokes an OA
    g = content.make("Goblin", "Z", "B", (7, 3))
    g.hp = 20
    pam2 = to_combatant(_fighter(5, {4: "Polearm Master"},
                        equipment=Loadout(main_hand=WEAPONS["Glaive"])), "A", "A", (3, 3))
    e2 = Encounter(Grid(12, 6), [pam2, g], RNG(2), roll_hp=False)
    e2.roll_initiative()
    before = len(e2.log)
    e2._do_move(g, (5, 3))                                      # enters the 10-ft reach
    assert any("opportunity attack" in l for l in e2.log[before:])


def test_sentinel_reacts_when_an_ally_is_attacked():
    sen = to_combatant(_fighter(5, {4: "Sentinel"},
                       equipment=Loadout(main_hand=WEAPONS["Longsword"])), "A", "A", (3, 3))
    ally = content.make("Guard", "C", "A", (3, 4))
    foe = content.make("Orc", "B", "B", (4, 3))                # within 5 ft of the Sentinel
    foe.hp = 50
    e = Encounter(Grid(10, 6), [sen, ally, foe], RNG(1), roll_hp=False)
    assert e.sentinel_reaction(foe, ally) is True              # the Sentinel strikes the attacker
    assert sen.reaction_available is False
    assert e.sentinel_reaction(foe, ally) is False             # only once (reaction spent)


def test_savage_attacker_rerolls_damage_once_per_turn():
    def avg_damage(savage):
        feats = {4: "Savage Attacker"} if savage else {}
        total = 0
        for s in range(300):
            c = to_combatant(_fighter(5, feats, equipment=Loadout(main_hand=WEAPONS["Greatsword"])),
                             "A", "A", (2, 3))
            foe = content.make("Goblin", "B", "B", (3, 3))
            foe.hp = 500
            e = Encounter(Grid(8, 6), [c, foe], RNG(s), roll_hp=False)
            if resolve_attack(c, foe, c.attacks["Greatsword"], e.rng, e.log, enc=e):
                total += 500 - foe.hp
        return total
    assert avg_damage(True) > avg_damage(False)          # reroll-and-keep-higher raises damage
