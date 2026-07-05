"""Spellcasting fidelity: attack/save/auto/heal/modifier effects, AoE, scaling,
concentration set/swap/break, and slot consumption."""
from __future__ import annotations

from ravel import cast, content, spells
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Option
from ravel.rules import apply_damage


def enc_with(a_names, b_names, seed=1, b_x=6):
    combs = []
    for i, n in enumerate(a_names):
        combs.append(content.make(n, f"A{i + 1}", "A", (2, 2 + i * 2)))
    for i, n in enumerate(b_names):
        combs.append(content.make(n, f"B{i + 1}", "B", (b_x, 2 + i)))
    enc = Encounter(Grid(20, 16), combs, RNG(seed))
    enc.roll_initiative()
    return enc


def opt(spell, target_id, slot):
    return Option("o", "spell", spell, target_id, "", spell=spell, slot_level=slot)


def test_spell_library_loads():
    assert len(spells.known()) >= 16
    for name in ("Fire Bolt", "Fireball", "Magic Missile", "Hold Person", "Bless"):
        assert spells.get(name)


def test_magic_missile_auto_damage_and_slot_spend():
    enc = enc_with(["Mage"], ["Goblin"])
    mage, gob = enc.combatants["A1"], enc.combatants["B1"]
    gob.hp = 30
    before = mage.slots[1]
    cast.cast(enc, mage, opt("Magic Missile", gob.id, 1))
    assert mage.slots[1] == before - 1
    assert 6 <= 30 - gob.hp <= 15            # 3 darts of 1d4+1, auto-hit


def test_fireball_aoe_hits_cluster_and_saves():
    enc = enc_with(["Mage"], ["Goblin", "Goblin"])    # B1,B2 adjacent
    mage = enc.combatants["A1"]
    b1, b2 = enc.combatants["B1"], enc.combatants["B2"]
    cast.cast(enc, mage, opt("Fireball", b1.id, 3))
    assert b1.hp < b1.max_hp and b2.hp < b2.max_hp    # both in the sphere
    assert mage.slots[3] == 2


def test_cure_wounds_heals():
    enc = enc_with(["Priest", "Skeleton"], ["Goblin"])
    priest = enc.combatants["A1"]
    ally = enc.combatants["A2"]
    ally.hp = 1
    cast.cast(enc, priest, opt("Cure Wounds", ally.id, 1))
    assert ally.hp > 1


def test_bless_grants_attack_bonus_effect():
    enc = enc_with(["Priest", "Skeleton"], ["Goblin"])
    priest = enc.combatants["A1"]
    cast.cast(enc, priest, opt("Bless", priest.id, 1))
    blessed = [c for c in (enc.combatants["A1"], enc.combatants["A2"])
               if any(e.name == "Bless" and e.attack_bonus for e in c.effects)]
    assert blessed
    assert priest.concentration is not None and priest.concentration.spell == "Bless"


def test_concentration_swap_removes_old_effects():
    enc = enc_with(["Priest", "Skeleton"], ["Goblin"])
    priest, ally, gob = (enc.combatants["A1"], enc.combatants["A2"],
                         enc.combatants["B1"])
    cast.cast(enc, priest, opt("Bless", priest.id, 1))
    assert any(e.name == "Bless" for e in ally.effects)
    # Shield of Faith always lands (no save) -> deterministic concentration swap
    cast.cast(enc, priest, opt("Shield of Faith", priest.id, 1))
    assert priest.concentration.spell == "Shield of Faith"
    assert not any(e.name == "Bless" for e in ally.effects)   # old effect cleaned up
    assert gob.alive


def test_concentration_breaks_on_damage():
    enc = enc_with(["Priest", "Skeleton"], ["Goblin"])
    priest, ally = enc.combatants["A1"], enc.combatants["A2"]
    priest.hp = 200
    cast.cast(enc, priest, opt("Bless", priest.id, 1))
    apply_damage(priest, 60, "fire", enc.log, enc.rng)   # DC 30 -> auto-fail
    assert priest.concentration is None
    assert not any(e.name == "Bless" for e in ally.effects)


def test_hold_person_paralyzes_on_failed_save():
    # over several seeds at least one failure should paralyze the goblin
    paralyzed = False
    for s in range(10):
        enc = enc_with(["Priest"], ["Goblin"], seed=s)
        priest, gob = enc.combatants["A1"], enc.combatants["B1"]
        cast.cast(enc, priest, opt("Hold Person", gob.id, 2))
        if gob.has("paralyzed"):
            paralyzed = True
            break
    assert paralyzed


def test_upcast_and_cantrip_scaling():
    mage = content.make("Mage", "x", "A", (0, 0))
    fb = spells.get("Fireball")
    d5 = cast._scaled_damage(fb, fb.effects[0], 5, mage)   # 8d6 + 2d6
    assert d5[0].count == 10 and d5[0].sides == 6
    firebolt = spells.get("Fire Bolt")
    dc = cast._scaled_damage(firebolt, firebolt.effects[0], 0, mage)  # lvl 9 -> 2 dice
    assert dc[0].count == 2 and dc[0].sides == 10


def test_caster_loaded_with_spellcasting():
    m = content.get("Mage")
    assert m.spell_dc == 14 and m.spell_ability.value == "INT"
    assert "Fireball" in m.spells and m.spell_slots[3] == 3


def test_breaking_concentration_clears_implied_incapacitated():
    from ravel.effects import break_concentration
    for s in range(15):
        enc = enc_with(["Priest"], ["Goblin"], seed=s)
        priest, gob = enc.combatants["A1"], enc.combatants["B1"]
        cast.cast(enc, priest, opt("Hold Person", gob.id, 2))
        if gob.has("paralyzed"):
            assert gob.has("incapacitated")        # implied while held
            break_concentration(priest, enc.log, "test")
            assert not gob.has("paralyzed")
            assert not gob.has("incapacitated")     # implied cleared immediately
            return
    raise AssertionError("Hold Person never landed across seeds")


def test_speed_delta_modifier_applied():
    from ravel.models import ActiveEffect
    enc = enc_with(["Ogre"], ["Goblin"])
    ogre = enc.combatants["A1"]
    base = enc._move_budget(ogre)               # speed 40 ft
    ogre.effects.append(ActiveEffect(name="Slow", source_id="x", speed_delta=-20))
    assert enc._move_budget(ogre) == base - 20  # budget is now in feet


def test_heuristic_spell_damage_ignores_heal():
    from ravel import tactics
    mage = content.make("Mage", "x", "A", (0, 0))
    heal = Option("o", "spell", "Cure Wounds", "x", "", spell="Cure Wounds")
    bolt = Option("o", "spell", "Fire Bolt", "x", "", spell="Fire Bolt")
    assert tactics._option_damages(mage, heal) == []     # heal isn't offensive output
    assert tactics._option_damages(mage, bolt) != []


def test_zero_target_offensive_spell_does_not_spend_slot():
    enc = enc_with(["Mage"], ["Goblin"])
    mage, gob = enc.combatants["A1"], enc.combatants["B1"]
    gob.hp = 0                                   # no living enemy to catch
    before = mage.slots[3]
    cast.cast(enc, mage, opt("Fireball", gob.id, 3))
    assert mage.slots[3] == before              # slot refunded / never spent
    assert mage.concentration is None


def test_shield_reaction_spends_slot_and_reaction():
    enc = enc_with(["Mage"], ["Goblin"])
    mage = enc.combatants["A1"]
    s1 = mage.slots[1]
    assert enc.try_shield(mage) is True
    assert any(e.name == "Shield" and e.ac_bonus == 5 for e in mage.effects)
    assert mage.reaction_available is False
    assert mage.slots[1] == s1 - 1
    assert enc.try_shield(mage) is False         # only one reaction per round


def test_counterspell_negates_fireball():
    enc = enc_with(["Mage"], ["Mage"])
    a, b = enc.combatants["A1"], enc.combatants["B1"]
    b3, bhp = b.slots[3], b.hp
    cast.cast(enc, a, opt("Fireball", b.id, 3))
    assert b.hp == bhp                           # countered: no damage
    assert b.slots[3] == b3 - 1                  # B spent a 3rd-level slot
    assert b.reaction_available is False
    assert a.slots[3] == 2                       # A's slot expended anyway


def test_counterspell_policy_by_level():
    enc = enc_with(["Mage"], ["Mage"])
    a = enc.combatants["A1"]
    assert enc.offer_counterspell(a, spells.get("Fire Bolt")) is False   # cantrip
    assert enc.offer_counterspell(a, spells.get("Magic Missile")) is False  # lvl 1
    assert enc.offer_counterspell(a, spells.get("Fireball")) is True     # lvl 3


def test_reaction_spells_not_enumerated_as_actions():
    enc = enc_with(["Mage"], ["Goblin"])
    names = {o.name for o in cast.enumerate_spell_options(enc, enc.combatants["A1"])}
    assert "Shield" not in names and "Counterspell" not in names
    assert "Fireball" in names


# -- auras -----------------------------------------------------------------

def test_spirit_guardians_aura_damages_and_makes_difficult_terrain():
    enc = enc_with(["Priest"], ["Goblin"], b_x=4)   # goblin 10 ft away, inside 15 ft
    priest, gob = enc.combatants["A1"], enc.combatants["B1"]
    cast.cast(enc, priest, opt("Spirit Guardians", priest.id, 3))
    assert priest.aura is not None and priest.concentration.spell == "Spirit Guardians"
    enc._apply_auras_start_of_turn(gob)             # goblin starts its turn in the aura
    assert gob.hp < 7                                # took radiant (full or half)
    assert enc.dynamic_difficult(gob)               # aura cells are difficult for the goblin
    from ravel.effects import break_concentration
    break_concentration(priest, enc.log, "test")
    assert priest.aura is None                       # aura cleared with concentration


# -- summons ---------------------------------------------------------------

def test_conjure_animals_adds_allied_combatants():
    enc = enc_with(["Priest"], ["Goblin"])
    priest = enc.combatants["A1"]
    n0 = len(enc.combatants)
    cast.cast(enc, priest, opt("Conjure Animals", priest.id, 3))
    wolves = [c for c in enc.combatants.values() if c.summoner_id == priest.id]
    assert len(wolves) == 3 and all(w.team == "A" and w.alive for w in wolves)
    assert len(enc.combatants) == n0 + 3
    assert priest.concentration.spell == "Conjure Animals"
    from ravel.effects import break_concentration
    break_concentration(priest, enc.log, "test")
    assert all(not w.alive for w in wolves)          # summons dismissed


def test_spiritual_weapon_is_untargetable_and_temporary():
    from ravel.controllers import HeuristicController
    enc = enc_with(["Priest"], ["Goblin"], b_x=4)
    priest, gob = enc.combatants["A1"], enc.combatants["B1"]
    cast.cast(enc, priest, opt("Spiritual Weapon", priest.id, 2))
    weap = next(c for c in enc.combatants.values() if c.summoner_id == priest.id)
    assert weap.untargetable
    assert weap not in enc.enemies_of(gob)           # foes can't target it
    assert "A" in enc.teams_alive()                  # priest still keeps team alive
    weap.summon_duration = 1
    enc.take_turn(weap, HeuristicController())        # acts, then duration expires
    assert not weap.alive


# -- Round 2: Hellish Rebuke, readied actions, Moonbeam --------------------

def test_hellish_rebuke_retaliates_on_being_hit():
    enc = enc_with(["Mage"], ["Goblin"], b_x=3)
    mage, gob = enc.combatants["A1"], enc.combatants["B1"]
    s1, ghp = mage.slots[1], gob.hp
    enc.offer_hellish_rebuke(mage, gob)
    assert mage.slots[1] == s1 - 1
    assert mage.reaction_available is False
    assert gob.hp < ghp                               # attacker took fire (full or half)


def test_readied_attack_fires_only_on_entering_range():
    enc = enc_with(["Skeleton"], ["Goblin"], b_x=8)
    skel, gob = enc.combatants["A1"], enc.combatants["B1"]
    skel.readied_attack = "Shortsword"                # melee reach 5
    # already adjacent (no transition along the route) -> does NOT fire
    gob.pos = (3, 2)
    enc._trigger_readied(gob, [(3, 2), (3, 2)])
    assert skel.readied_attack == "Shortsword" and skel.reaction_available

    # was 30 ft away, route steps adjacent -> the readied attack fires
    enc._trigger_readied(gob, [(8, 2), (3, 2)])
    assert skel.readied_attack is None
    assert skel.reaction_available is False


def test_multiattack_stops_when_attacker_killed_by_reaction():
    for s in range(20):
        enc = enc_with(["Mage"], ["Saber-Toothed Tiger"], b_x=3, seed=s)
        mage, tiger = enc.combatants["A1"], enc.combatants["B1"]
        mage.hp = 200
        tiger.hp = 1                                   # any rebuke damage kills it
        tiger.pos = (3, 2)
        enc._do_attack_action(tiger, mage, "multiattack")
        if not tiger.alive:
            # at most ONE attack landed before the rebuke killed it (loop stopped)
            assert 200 - mage.hp <= 17                 # max of a single Bite/Claw
            return
    raise AssertionError("tiger never died to Hellish Rebuke across seeds")


def test_hellish_rebuke_scales_with_slot():
    def rebuke(slots, seed):
        enc = enc_with(["Mage"], ["Goblin"], b_x=3, seed=seed)
        mage, gob = enc.combatants["A1"], enc.combatants["B1"]
        mage.slots = dict(slots)
        gob.hp = 500
        enc.offer_hellish_rebuke(mage, gob)
        return 500 - gob.hp
    assert rebuke({3: 1}, 5) > rebuke({1: 1}, 5)        # upcast deals more


def test_moonbeam_is_a_point_anchored_aura():
    enc = enc_with(["Priest"], ["Goblin"], b_x=4)
    priest, gob = enc.combatants["A1"], enc.combatants["B1"]
    cast.cast(enc, priest, opt("Moonbeam", gob.id, 2))
    assert priest.aura is not None and priest.aura.anchor == "point"
    assert priest.concentration.spell == "Moonbeam"
    enc._apply_auras_start_of_turn(gob)               # goblin starts in the beam
    assert gob.hp < 7


def test_ready_option_enumerated():
    enc = enc_with(["Skeleton"], ["Goblin"])
    names = {o.kind for o in enc.enumerate_options(enc.combatants["A1"])}
    assert "ready" in names
