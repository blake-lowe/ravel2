"""Deterministic 5e rules: attacks, saves, damage, conditions.

All condition/situational logic is delegated to `conditions.py`. No LLM, no
module-level randomness; all randomness comes from the passed RNG.
"""
from __future__ import annotations

from .conditions import (IMPLIES, INCAPACITATING, attack_mods, cleanup_implied,
                         save_mods)
from .dice import RNG
from .effects import (attackers_have_advantage, attackers_have_disadvantage,
                      break_concentration, damage_riders_vs, has_attack_disadvantage,
                      total_ac_bonus, total_attack_bonus, total_save_bonus)
from .grid import dist3d, feet_between
from .models import Ability, AttackDef, Combatant, Condition, SaveRider

_PHYSICAL = ("bludgeoning", "piercing", "slashing")


def damage_multiplier(target: Combatant, dtype: str, magical: bool = False) -> float:
    """Combined damage multiplier vs a target: immunity (0), vulnerability (x2),
    resistance / nonmagical-physical / petrified (x0.5 each). Single source of truth.
    `magical=True` (a magic weapon / spell) bypasses nonmagical-physical resistance."""
    if dtype in target.md.immunities:
        return 0.0
    m = 1.0
    if dtype in target.md.vulnerabilities:
        m *= 2
    if dtype in target.md.resistances:
        m *= 0.5
    if target.md.resist_nonmagical_physical and dtype in _PHYSICAL and not magical:
        m *= 0.5
    if target.raging:                        # Barbarian Rage: resist B/P/S (Bear Totem: all but psychic)
        if target.md.rage_all_damage:
            if dtype != "psychic":
                m *= 0.5
        elif dtype in _PHYSICAL:
            m *= 0.5
    if target.has("petrified"):
        m *= 0.5
    return m


def area_damage_after_save(target: Combatant, ability: Ability, saved: bool,
                           half_on_save: bool, amount: int, *,
                           negate_on_save: bool = False) -> int:
    """Post-save area/effect damage, honouring Evasion (Monk/Rogue): on a DEX save-for-half
    effect a success takes no damage and a failure takes half. For non-evaders `half_on_save`
    halves the damage on a save; `negate_on_save` (a spell where a save otherwise negates the
    damage) zeroes it. Defaults preserve each existing call site's prior behaviour."""
    if target.md.evasion and ability == Ability.DEX and half_on_save:
        return 0 if saved else amount // 2
    if not saved:
        return amount
    if half_on_save:
        return amount // 2
    return 0 if negate_on_save else amount


def _leadership_bonus(enc, creature: Combatant, rng: RNG) -> int:
    """+1d4 to an attack roll while an allied leader (Leadership) is within 30 ft."""
    if enc is None:
        return 0
    for lead in enc.living():
        if (lead.md.leadership and lead.team == creature.team and lead.id != creature.id
                and enc.dist(lead, creature) <= 30):
            return rng.d(4)
    return 0


def _net(adv: bool, dis: bool) -> int:
    if adv and not dis:
        return 1
    if dis and not adv:
        return -1
    return 0


def contest(rng: RNG, a: Combatant, a_ability: Ability, b: Combatant,
            b_abilities: tuple[Ability, ...]) -> bool:
    """Opposed check; the initiator `a` wins ties (5e Grapple/Shove). Non-proficient armor
    gives disadvantage on STR/DEX ability checks."""
    _sd = (Ability.STR, Ability.DEX)
    a_dis = -1 if (a.armor_penalty and a_ability in _sd) else 0
    b_dis = -1 if (b.armor_penalty and all(x in _sd for x in b_abilities)) else 0
    ra = (a.md.prof_bonus + 1) // 2 if (a.md.remarkable_athlete and a_ability in _sd) else 0
    a_total = rng.d20(a_dis)[0] + a.md.mod(a_ability) + a.md.prof_bonus + ra   # Remarkable Athlete
    b_best = max(b.md.mod(x) for x in b_abilities) + b.md.prof_bonus
    return a_total >= rng.d20(b_dis)[0] + b_best


_ALIGN_CODE = {"L": "lawful", "N": "neutral", "C": "chaotic", "G": "good",
               "E": "evil", "U": "unaligned", "NX": "neutral", "NY": "neutral",
               "A": "any"}


def kit_advantage(attacker_md, target_md) -> bool:
    """Slayer arms and talismans (SPEC 18.8.6): advantage on attack rolls against
    a favored creature type ("dragon", "giant"...) or alignment word ("evil",
    "good"). Alignment data comes both as 5e.tools codes ("C E") and prose
    ("chaotic evil"); both are matched."""
    if attacker_md.adv_against_types:
        t = target_md.mtype.lower()
        if any(k in t for k in attacker_md.adv_against_types):
            return True
    if attacker_md.adv_against_aligns:
        a = target_md.alignment
        words = (a.lower().split() if any(c.islower() for c in a)
                 else [_ALIGN_CODE.get(tok, "") for tok in a.split()])
        if any(k in words for k in attacker_md.adv_against_aligns):
            return True
    return False


def _dist_ft(attacker: Combatant, target: Combatant) -> float:
    return min(dist3d(attacker.pos, attacker.alt, s, target.alt)
               for s in target.occupied_squares())


def is_auto_crit(attacker: Combatant, target: Combatant, atk: AttackDef) -> bool:
    return attack_mods(attacker, target, atk.kind, _dist_ft(attacker, target))[3]


def _concentration_save(target: Combatant, taken: int, rng: RNG | None,
                        log: list[str], enc=None) -> None:
    if rng is not None and taken > 0 and target.concentration is not None:
        if target.md.focused_conjuration:                # damage can't break a conjuration spell
            from . import spells
            try:
                if spells.get(target.concentration.spell).school == "conjuration":
                    return
            except KeyError:
                pass
        dc = max(10, taken // 2)
        if not saving_throw(target, Ability.CON, dc, rng, advantage=target.md.war_caster):
            break_concentration(target, log, f"failed DC {dc} CON save", enc=enc)


def _die(target: Combatant, enc, log: list[str], dtype: str = "") -> None:
    target.dying = target.stable = False
    target.dead = True
    log.append(f"    *** {target.id} ({target.name}) drops! ***")
    if enc is not None:
        enc.emit(kind="death", actor=target.id, dtype=dtype)
        enc._release_swallowed(target)         # a slain swallower frees its prey
    if target.concentration is not None:
        break_concentration(target, log, "dropped to 0 HP", enc=enc)


def revert_wild_shape(target: Combatant, log: list[str], enc, rng: RNG | None,
                      overkill: int = 0) -> None:
    """A druid's beast form drops to 0 HP: it reverts to its own body (Wild Shape), with any
    excess damage carrying over to its normal HP. If that carryover also drops the druid, the
    normal drop machinery then takes over (base_md is cleared first, so no recursion loop)."""
    beast = target.md.name
    target.md = target.base_md                       # restore the druid's own stat block
    target.equipment = target.base_equipment
    target.rolled_max_hp = target.base_rolled
    target.temp_hp = target.base_temp_hp
    target.base_md = None
    carry = max(0, overkill)
    target.hp = target.base_hp - carry               # excess damage carries to the druid's HP
    log.append(f"    {target.id} reverts from {beast} form to {target.md.name} "
               f"({max(0, target.hp)}/{target.max_hp} HP)")
    if enc is not None:
        enc.emit(kind="condition", actor=target.id, info="revert_wild_shape")
    if target.hp <= 0:                               # carryover finished the druid off
        handle_drop(target, carry, "", False, enc, log, rng, carry,
                    overkill=carry - target.base_hp)


def handle_drop(target: Combatant, dmg_for_dc: int, dtype: str, crit: bool,
                enc, log: list[str], rng: RNG | None, taken: int, overkill: int = 0) -> None:
    """A creature is at 0 HP after a *complete* damage event. A 'would drop to 0'
    ability (Undead Fortitude) may keep it alive. A creature that uses death saves falls
    unconscious (unless the leftover damage >= its HP max, which is instant death);
    everything else dies. `dmg_for_dc` is the whole event's total."""
    if getattr(target, "base_md", None) is not None:   # Wild Shape: revert instead of dropping
        revert_wild_shape(target, log, enc, rng, overkill=overkill)
        return
    target.hp = 0
    if enc is not None and enc.survive_check(target, dmg_for_dc, dtype, crit):
        _concentration_save(target, taken, rng, log, enc)   # survived -> still hold concentration
        return
    if (target.md.relentless_endurance and overkill < target.max_hp   # Half-Orc: drop to 1, not 0
            and target.resources.get("Relentless Endurance", 0) > 0):
        target.resources["Relentless Endurance"] -= 1
        target.hp = 1
        log.append(f"    {target.id} endures the blow (Relentless Endurance) — 1 HP!")
        _concentration_save(target, taken, rng, log, enc)
        return
    if target.uses_death_saves and overkill < target.max_hp:
        target.dying = True                    # falls unconscious and begins death saving throws
        apply_condition(target, "unconscious", target.id, rng, log)
        log.append(f"    {target.id} falls unconscious (dying)")
        if target.concentration is not None:
            break_concentration(target, log, "dropped to 0 HP", enc=enc)
        return
    _die(target, enc, log, dtype)


def apply_damage(target: Combatant, amount: int, dtype: str, log: list[str],
                 rng: RNG | None = None, enc=None, crit: bool = False,
                 finalize: bool = True, magical: bool = False) -> int:
    """Apply one damage instance. `finalize=False` reduces HP and emits the event but
    leaves the drop/concentration handling to the caller — so a multi-type attack can be
    resolved as ONE damage event (see resolve_attack). `magical=True` bypasses
    nonmagical-physical resistance (a magic weapon / spell)."""
    mult = damage_multiplier(target, dtype, magical)
    if enc is not None and getattr(enc, "underwater", False) and dtype == "fire":
        mult *= 0.5                          # fully immersed -> resistance to fire
    if mult == 0:
        log.append(f"    {target.id} is immune to {dtype} (0 dmg)")
        return 0
    amount = int(amount * mult)
    if target.md.regen > 0 and dtype in target.md.regen_stopped_by:
        target.regen_disabled = True
    taken = amount                       # damage dealt (for the concentration DC)
    if target.temp_hp > 0 and amount > 0:
        absorbed = min(target.temp_hp, amount)
        target.temp_hp -= absorbed
        amount -= absorbed
        log.append(f"    {target.id} absorbs {absorbed} with temp HP "
                   f"({target.temp_hp} left)")
    if target.arcane_ward > 0 and amount > 0:            # Abjurer Arcane Ward soaks damage first
        soaked = min(target.arcane_ward, amount)
        target.arcane_ward -= soaked
        amount -= soaked
        taken -= soaked                                  # the ward takes it instead of you (no conc. save)
        log.append(f"    {target.id}'s Arcane Ward absorbs {soaked} "
                   f"({target.arcane_ward} left)")
    was_alive = target.hp > 0
    hp_before = target.hp
    target.hp = max(0, target.hp - amount)
    log.append(f"    {target.id} takes {amount} {dtype} -> "
               f"{target.hp}/{target.max_hp} HP")
    if amount > 0 and target.turned_by is not None:   # Turn Undead ends the moment it takes damage
        target.turned_by = None
        target.conditions.pop("frightened", None)
        target.routed = False
        log.append(f"    {target.id} is no longer turned (took damage)")
    if enc is not None:                  # canonical event stream (see reducer.py)
        enc.emit(kind="damage", actor=target.id, amount=amount, dtype=dtype, hp=target.hp)
    if not finalize:
        return amount                    # caller finalizes the whole hit's drop/conc save
    if target.hp <= 0 and was_alive:
        handle_drop(target, amount, dtype, crit, enc, log, rng, taken,
                    overkill=amount - hp_before)
    elif not was_alive and target.dying and amount > 0:
        _damage_while_dying(target, crit, amount, enc, log)
    else:
        _concentration_save(target, taken, rng, log, enc)
    return amount


def _damage_while_dying(target: Combatant, crit: bool, amount: int, enc, log: list[str]) -> None:
    """Taking damage at 0 HP: one death-save failure (two on a crit); a blow >= HP max kills."""
    if amount >= target.max_hp:
        _die(target, enc, log)
        return
    target.death_failures += 2 if crit else 1
    log.append(f"    {target.id} takes damage while dying "
               f"({target.death_failures}/3 failures)")
    if target.death_failures >= 3:
        _die(target, enc, log)


def aura_of_protection_bonus(c: Combatant) -> int:
    """Paladin Aura of Protection: a bonus to every save equal to the highest CHA modifier of a
    conscious allied paladin within 10 ft (the paladin itself included). Auras don't stack — take
    the best. Consulted on every save via a back-reference to the encounter the combatant is in
    (positional + deterministic; no RNG). Radius is a flat 10 ft (30 ft at L18 is a follow-on)."""
    enc = getattr(c, "enc", None)
    if enc is None:
        return 0
    best = 0
    for p in enc.combatants.values():
        if (p.md.aura_of_protection and p.team == c.team and p.alive
                and not p.incapacitated and enc.dist(p, c) <= 10):
            best = max(best, p.md.aura_of_protection)
    return best


def saving_throw(c: Combatant, ability: Ability, dc: int, rng: RNG,
                 important: bool = False, log: list[str] | None = None,
                 vs_magic: bool = False, disadvantage: bool = False,
                 advantage: bool = False, vs: str | None = None) -> bool:
    adv, dis, auto_fail = save_mods(c, ability)
    aura = aura_of_protection_bonus(c)                   # Paladin Aura of Protection (self + allies)
    if disadvantage:
        dis = True                       # e.g. Eldritch Knight Eldritch Strike
    if advantage:
        adv = True                       # e.g. War Caster (concentration)
    if vs is not None and vs in c.md.save_advantages:
        adv = True                       # Fey Ancestry (charm) / Dwarven Resilience (poison)
    if vs_magic and (c.md.magic_resistance or c.md.spell_resistance):
        adv = True                       # Magic Resistance / Abjurer Spell Resistance vs spells
    if ability == Ability.DEX and c.md.danger_sense:
        adv = True                       # Barbarian Danger Sense (advantage on DEX saves)
    if c.armor_penalty and ability in (Ability.STR, Ability.DEX):
        dis = True                       # non-proficient armor: disadvantage on STR/DEX saves
    if auto_fail:
        success = False
    else:
        roll, _ = rng.d20(_net(adv, dis))
        success = roll + c.md.save_bonus(ability) + total_save_bonus(c, rng) + aura >= dc
    # Indomitable (Fighter): reroll a failed save; you must use the new roll
    if (not success and not auto_fail and important
            and c.resources.get("Indomitable", 0) > 0):
        c.resources["Indomitable"] -= 1
        roll, _ = rng.d20(_net(adv, dis))
        success = roll + c.md.save_bonus(ability) + total_save_bonus(c, rng) + aura >= dc
        if log is not None:
            log.append(f"    {c.id} uses Indomitable to reroll "
                       f"({c.resources['Indomitable']} left)")
    if (not success and not auto_fail and important        # Lucky: reroll and keep the better
            and c.md.lucky and c.resources.get("Lucky", 0) > 0):
        c.resources["Lucky"] -= 1
        roll, _ = rng.d20(_net(adv, dis))
        success = roll + c.md.save_bonus(ability) + total_save_bonus(c, rng) + aura >= dc
        if log is not None:
            log.append(f"    {c.id} uses Luck to reroll ({c.resources['Lucky']} left)")
    # Legendary Resistance: turn a failed important save into a success
    if not success and important and c.legendary_resistance_left > 0:
        c.legendary_resistance_left -= 1
        if log is not None:
            log.append(f"    {c.id} uses Legendary Resistance "
                       f"({c.legendary_resistance_left} left)")
        return True
    return success


def _paladin_aura_suppresses(target: Combatant, cond_name: str) -> bool:
    """Paladin Aura of Courage (frightened) / Oath of Devotion Aura of Devotion (charmed):
    a conscious aura-paladin within 10 ft makes its allies immune to the named condition."""
    flag = {"frightened": "aura_of_courage", "charmed": "aura_of_devotion"}.get(cond_name)
    if flag is None:
        return False
    enc = getattr(target, "enc", None)
    if enc is None:
        return False
    for p in enc.combatants.values():
        if (getattr(p.md, flag, False) and p.team == target.team and p.alive
                and not p.incapacitated and enc.dist(p, target) <= 10):
            return True
    return False


def apply_condition(target: Combatant, cond_name: str, source_id: str, rng: RNG,
                    log: list[str], duration: int | None = None,
                    save_ability: Ability | None = None, save_dc: int = 0,
                    spell_level: int = 0, escalates_to: str | None = None) -> None:
    if cond_name in target.md.condition_immunities:
        log.append(f"    {target.id} is immune to {cond_name}")
        return
    if _paladin_aura_suppresses(target, cond_name):
        log.append(f"    {target.id} is unaffected by {cond_name} (paladin aura)")
        return
    target.conditions[cond_name] = Condition(cond_name, source_id, duration,
                                             save_ability, save_dc, spell_level,
                                             escalates_to)
    for implied in IMPLIES.get(cond_name, []):
        target.conditions.setdefault(implied, Condition(implied, source_id, duration))
    log.append(f"    {target.id} is now {cond_name}"
               + (f" ({duration} rds)" if duration else
                  " (save ends)" if save_ability else ""))
    if cond_name in INCAPACITATING and target.concentration is not None:
        break_concentration(target, log, f"became {cond_name}")


def _apply_rider(rider: SaveRider, attacker: Combatant, target: Combatant,
                 rng: RNG, log: list[str], enc=None) -> None:
    saved = saving_throw(target, rider.ability, rider.dc, rng)
    log.append(f"    {target.id} {rider.ability.value} save vs DC {rider.dc}: "
               f"{'success' if saved else 'FAIL'}")
    if rider.extra_damage is not None:
        dmg = rider.extra_damage.roll(rng)
        if saved:
            dmg = dmg // 2 if rider.half_on_save else 0
        if dmg:
            apply_damage(target, dmg, rider.extra_damage.type, log, rng, enc=enc)
    if not saved and rider.on_fail_condition and target.alive:
        se = rider.condition_save_ends
        apply_condition(target, rider.on_fail_condition, attacker.id, rng, log,
                        duration=rider.condition_duration,
                        save_ability=rider.ability if se else None,
                        save_dc=rider.dc if se else 0,
                        escalates_to=rider.escalates_to)
    if not saved and rider.push and target.alive and enc is not None:
        enc.force_move(attacker, target, abs(rider.push), toward=rider.push < 0)


def resolve_attack(attacker: Combatant, target: Combatant, atk: AttackDef,
                   rng: RNG, log: list[str], cover_ac: int = 0,
                   ranged_in_melee: bool = False, long_range: bool = False,
                   flanking: bool = False, enc=None, reckless_ok: bool = True,
                   is_reaction: bool = False) -> bool:
    """Resolve a single weapon attack. Returns True if it hit."""
    if enc is not None and not is_reaction and not target.md.sentinel:
        enc.sentinel_reaction(attacker, target)   # a Sentinel ally punishes the attacker
        if not attacker.alive:
            return False
    dist = _dist_ft(attacker, target)
    adv, dis, cannot, auto_crit = attack_mods(attacker, target, atk.kind, dist)
    if cannot:
        log.append(f"  {attacker.id} cannot attack {target.id} (charmed)")
        return False
    if attackers_have_advantage(target) or flanking or attacker.help_advantage:
        adv = True
    if attacker.md.reckless and atk.kind == "melee" and reckless_ok:
        adv = True                           # Reckless Attack: advantage on melee (own turn
        attacker.reckless_active = True      # only)...but attackers gain advantage in return
    if attacker.md.assassinate and target.surprised:
        adv = True                           # Assassin Assassinate: advantage + auto-crit vs surprised
        auto_crit = True
    if attacker.md.blood_frenzy and target.hp < target.max_hp:
        adv = True                           # Blood Frenzy: advantage vs a wounded creature
    if ((attacker.md.adv_against_types or attacker.md.adv_against_aligns)
            and kit_advantage(attacker.md, target.md)):
        adv = True                           # slayer arms / talismans: a favored foe
    if attacker.vow_target_id == target.id:
        adv = True                           # Oath of Vengeance: Vow of Enmity (advantage vs the sworn foe)
    if enc is not None and not enc.can_see(target, attacker):
        adv = True                           # unseen attacker (darkness/invisible) has advantage
    attacker.help_advantage = False          # Help grants advantage to one attack
    attacker.hidden = False                  # attacking reveals a hidden creature
    sharp = attacker.md.sharpshooter and atk.kind == "ranged"   # ignores long range + cover
    if (has_attack_disadvantage(attacker) or ranged_in_melee
            or (long_range and not sharp)
            or attackers_have_disadvantage(target)):     # Blur / Mirror Image
        dis = True
    if enc is not None and not enc.can_see(attacker, target):
        dis = True                           # can't clearly see the target (darkness/fog)
    if attacker.md.sunlight_sensitivity and enc is not None and enc.in_sunlight(attacker.pos):
        dis = True                           # Sunlight Sensitivity
    if enc is not None and enc.underwater:   # underwater combat penalties
        if atk.kind == "melee" and attacker.md.swim == 0 and (
                not atk.damage or atk.damage[0].type != "piercing"):
            dis = True                       # non-piercing melee flails underwater (no swim speed)
        elif atk.kind == "ranged":
            if dist > atk.range_normal:
                log.append(f"  {attacker.id}'s {atk.name} auto-misses "
                           f"(underwater, beyond normal range)")
                return False                 # ranged weapon auto-misses beyond normal range
            dis = True                       # ranged weapon attacks hampered underwater
    if enc is not None and enc.weather == "wind" and atk.kind == "ranged":
        dis = True                           # strong wind hampers ranged weapon attacks
    if attacker.armor_penalty:
        dis = True                           # non-proficient armor: disadvantage on STR/DEX attacks
    if enc is not None and not dis and enc.protection_reaction(attacker, target):
        dis = True                           # an ally's Protection fighting style
    # Inspiration (§5.7): if this attack still lacks advantage, spend Inspiration for it. Spent
    # on the combatant's first qualifying attack (the resource then reads 0), never on a
    # reaction/opportunity attack. Deterministic — no roll is consumed by the decision.
    if (not adv and not is_reaction and attacker.resources.get("Inspiration", 0) > 0):
        attacker.resources["Inspiration"] -= 1
        adv = True
        log.append(f"    {attacker.id} uses Inspiration for advantage")
    # Wild Magic Tides of Chaos: spend to gain advantage on an attack that lacks it (1/rest)
    elif (not adv and not is_reaction and attacker.resources.get("Tides of Chaos", 0) > 0):
        attacker.resources["Tides of Chaos"] -= 1
        adv = True
        log.append(f"    {attacker.id} draws on the Tides of Chaos (advantage)")
    if target.md.elusive and not target.incapacitated:
        adv = False                      # Rogue Elusive (L18): no attack roll has advantage vs you
    net = _net(adv, dis)
    if net == 1 and attacker.md.elven_accuracy:
        net = 2                          # Elven Accuracy: advantage rolls three dice
    roll, _ = rng.d20(net)
    tag = {2: " (adv3)", 1: " (adv)", -1: " (disadv)", 0: ""}[net]
    ac = target.ac + (0 if sharp else cover_ac) + total_ac_bonus(target)   # Sharpshooter ignores cover
    cover_note = f" (+{cover_ac} cover)" if (cover_ac and not sharp) else ""
    if roll == 1:
        log.append(f"  {attacker.id} {atk.name} vs {target.id}: NAT 1 - miss{tag}")
        return False
    crit = roll >= atk.crit_range or auto_crit
    total = (roll + atk.attack_bonus + total_attack_bonus(attacker, rng)
             + _leadership_bonus(enc, attacker, rng))
    # Great Weapon Master / Sharpshooter power attack: -5 to hit, +10 damage when EV favours it
    power_bonus = 0
    heavy_pa = attacker.md.gwm and atk.kind == "melee" and atk.heavy
    if roll != 20 and (heavy_pa or sharp):
        dmg_avg = sum(d.average() for d in atk.damage)
        fixed = total - roll
        p = max(0.05, min(0.95, (21 - (ac - fixed)) / 20))
        p5 = max(0.05, min(0.95, (21 - (ac - fixed + 5)) / 20))
        if p5 * (dmg_avg + 10) > p * dmg_avg:
            total -= 5
            power_bonus = 10
    hit = roll == 20 or total >= ac
    if not hit and roll != 1 and enc is not None:      # Battle Master Precision Attack
        bonus = enc.battle_master_precision(attacker, ac - total)
        if bonus:
            total += bonus
            hit = total >= ac
    if not hit and roll != 1 and enc is not None:      # War Domain Guided Strike (+10 to hit)
        gbonus = enc.cleric_guided_strike(attacker, ac - total)
        if gbonus:
            total += gbonus
            hit = total >= ac
    if not hit and roll != 1 and enc is not None:      # War Domain L6 War God's Blessing (ally reaction)
        wgb = enc.cleric_war_gods_blessing(attacker, ac - total)
        if wgb:
            total += wgb
            hit = total >= ac
    fixed = total - roll
    if (not hit and attacker.md.lucky and attacker.resources.get("Lucky", 0) > 0
            and ac - fixed <= 15):                     # Lucky: reroll a plausible-to-hit miss
        attacker.resources["Lucky"] -= 1
        roll = rng.d20()[0]
        total = roll + fixed
        hit = roll == 20 or total >= ac
        log.append(f"    {attacker.id} uses Luck to reroll the attack "
                   f"({attacker.resources['Lucky']} left)")
    if (not hit and attacker.md.stroke_of_luck              # Rogue L20 Stroke of Luck (1/short rest)
            and attacker.resources.get("Stroke of Luck", 0) > 0):
        attacker.resources["Stroke of Luck"] -= 1
        hit = True
        log.append(f"    {attacker.id} turns the miss into a hit (Stroke of Luck)")
    # Bardic Inspiration: an ally banked a die on this creature; add it to a missed attack roll
    if not hit and roll != 1 and attacker.inspiration_die:
        die = attacker.inspiration_die
        bump = rng.roll(1, die)
        attacker.inspiration_die = 0
        total += bump
        hit = total >= ac
        log.append(f"    {attacker.id} adds Bardic Inspiration (d{die}: +{bump}) -> {total}")
    # College of Lore Cutting Words: an enemy bard subtracts an inspiration die from this attack
    if hit and roll != 20 and enc is not None:
        cut = enc.bard_cutting_words(attacker, target, total - ac)
        if cut:
            total -= cut
            hit = total >= ac
    # Great Old One Entropic Ward: the target's reaction imposes disadvantage on the attack
    if hit and roll != 20 and enc is not None and target.md.entropic_ward:
        other = enc.try_entropic_ward(target)
        if other:
            new_roll = min(roll, other)
            total = new_roll + (total - roll)
            hit = new_roll != 1 and total >= ac
            log.append(f"  >> {target.id} Entropic Ward: {attacker.id} rerolls "
                       f"(disadv {roll}/{other}) -> {'HIT' if hit else 'miss'}")
    # Shield reaction: only worth it if +5 AC would turn the hit into a miss
    if hit and roll != 20 and enc is not None and total < ac + 5 and enc.try_shield(target):
        hit = False
        ac += 5
    # Parry reaction (melee only): a martial monster raises AC to dodge the blow
    if (hit and roll != 20 and enc is not None and atk.kind == "melee"
            and target.md.parry and total < ac + target.md.parry
            and enc.try_parry(target)):
        hit = False
        ac += target.md.parry
    # Illusory Self reaction (Illusionist): interpose an illusory duplicate to dodge one hit
    if hit and enc is not None and target.md.illusory_self and enc.try_illusory_self(target):
        hit = False
    log.append(f"  {attacker.id} {atk.name} vs {target.id}: d20={roll}{tag}"
               f"+{atk.attack_bonus}={total} vs AC {ac}{cover_note} -> "
               f"{'HIT' if hit else 'miss'}{' CRIT!' if crit and hit else ''}")
    if enc is not None:                  # display-only: the replay animates the swing/shot
        enc.emit(kind="attack", actor=attacker.id, info=target.id,
                 dtype=atk.kind, amount=int(hit))
    if atk.kind == "melee" and attacker.md.mobile:     # Mobile: no OA from a foe you melee'd
        attacker.attacked_this_turn.add(target.id)
    if not hit:
        return False
    # Uncanny Dodge (Rogue L5): spend the reaction to halve this attack's damage (RAW: only
    # against an attacker the rogue can SEE)
    halve = False
    if (enc is not None and target.md.uncanny_dodge and target.reaction_available
            and target.alive and not target.incapacitated and enc.can_see(target, attacker)):
        target.reaction_available = False
        halve = True
        log.append(f"  >> {target.id} uses Uncanny Dodge (halves the damage)")

    # Monk Deflect Missiles (L3): reaction to reduce an incoming ranged-weapon attack's damage by
    # 1d10 + DEX + monk level. (Catch/throw-back is simplified: at 0, the damage is negated.)
    deflect_amt = 0
    if (enc is not None and atk.kind == "ranged" and target.md.deflect_missiles
            and target.reaction_available and target.alive and not target.incapacitated
            and enc.can_see(target, attacker)):
        target.reaction_available = False
        deflect_amt = rng.roll(1, 10) + target.md.mod(Ability.DEX) + target.md.deflect_missiles
        log.append(f"  >> {target.id} uses Deflect Missiles (-{deflect_amt} ranged damage)")

    def _hd(x: int) -> int:                            # halve if Uncanny Dodge was used
        return x // 2 if halve else x

    if attacker.md.eldritch_strike:                    # disadvantage on its next save vs your spell
        target.eldritch_strike_by = attacker.id
    alive_before = target.hp > 0
    hp_before = target.hp
    dealt = 0
    radiant = False
    magical = attacker.md.magic_weapons           # bypasses nonmagical-physical resistance
    # a Swarm deals half damage once bloodied (its numbers are thinned)
    swarm_mult = 0.5 if (attacker.md.swarm and attacker.hp * 2 <= attacker.max_hp) else 1.0
    savage = (attacker.md.savage_attacker and not attacker.savage_used
              and atk.kind in ("melee", "ranged"))   # feat: reroll a weapon's damage once/turn
    for i, dmg in enumerate(atk.damage):          # apply the hit's damage as ONE event
        rolled = dmg.roll(rng, crit=crit)
        if savage and i == 0:                     # reroll and keep the better total
            rolled = max(rolled, dmg.roll(rng, crit=crit))
            attacker.savage_used = True
        if deflect_amt and i == 0:                # Deflect Missiles reduces the first damage die
            rolled = max(0, rolled - deflect_amt)
        amt = _hd(int(rolled * swarm_mult))
        dealt += apply_damage(target, amt, dmg.type, log, rng,
                              enc=enc, crit=crit, finalize=False, magical=magical)
        radiant = radiant or dmg.type == "radiant"
    if power_bonus:                               # GWM / Sharpshooter power attack (+10)
        dealt += apply_damage(target, _hd(power_bonus), atk.damage[0].type if atk.damage else "bludgeoning",
                              log, rng, enc=enc, finalize=False, magical=magical)
    if crit and attacker.md.savage_attacks and atk.kind == "melee" and atk.damage:   # Half-Orc
        d0 = atk.damage[0]
        # Savage Attacks: roll ONE of the weapon's damage dice one extra time (not d0.count dice)
        dealt += apply_damage(target, _hd(rng.roll(1, d0.sides or 1)), d0.type,
                              log, rng, enc=enc, finalize=False, magical=magical)
    if attacker.raging and atk.kind == "melee" and attacker.md.rage_damage and atk.damage:
        dealt += apply_damage(target, _hd(attacker.md.rage_damage), atk.damage[0].type,   # Rage bonus
                              log, rng, enc=enc, finalize=False, magical=magical)
    if crit and attacker.md.brutal_critical and atk.kind == "melee" and atk.damage:   # Brutal Critical
        d0 = atk.damage[0]
        # Brutal Critical: N extra weapon dice of the weapon's die size (not N x d0.count)
        dealt += apply_damage(target, _hd(rng.roll(attacker.md.brutal_critical,
                              d0.sides or 1)), d0.type, log, rng, enc=enc, finalize=False, magical=magical)
    # Battle Master maneuver on a hit: bonus superiority-die damage + a save-or-condition rider
    if enc is not None and attacker.md.superiority_die and target.hp > 0:
        bonus = enc.battle_master_maneuver(attacker, target, crit)
        if bonus:
            dtype = atk.damage[0].type if atk.damage else "bludgeoning"
            dealt += apply_damage(target, _hd(bonus), dtype, log, rng, enc=enc, crit=crit,
                                  finalize=False, magical=magical)
    # Paladin Divine Smite: spend a spell slot on a melee hit for a radiant burst (folded into
    # this hit's single damage event, so it can help drop the target). Radiant is magical.
    if (enc is not None and attacker.md.divine_smite and atk.kind == "melee"
            and target.hp > 0):
        smite = enc.paladin_divine_smite(attacker, target, crit)
        if smite:
            dealt += apply_damage(target, _hd(smite), "radiant", log, rng, enc=enc, crit=crit,
                                  finalize=False, magical=True)
    # a single drop / concentration resolution for the whole hit (one Undead Fortitude
    # save at DC 5 + the hit's total, not one per damage type)
    if target.hp <= 0 and alive_before:
        dt = "radiant" if radiant else (atk.damage[0].type if atk.damage else "")
        handle_drop(target, dealt, dt, crit, enc, log, rng, dealt, overkill=dealt - hp_before)
    elif target.hp <= 0 and target.dying and dealt > 0:
        _damage_while_dying(target, crit, dealt, enc, log)
    elif dealt > 0:                              # note: a hit fully absorbed by temp HP
        _concentration_save(target, dealt, rng, log, enc)   # (dealt==0) skips the conc save
    if attacker.swallowed_by == target.id:
        attacker.captor_damage += dealt          # damage from inside toward escaping
    if atk.reduces_max_hp and dealt > 0 and target.alive:
        target.max_hp_reduction += dealt        # Life Drain
        if target.hp > target.max_hp:
            target.hp = target.max_hp
            if enc is not None:
                enc.emit(kind="damage", actor=target.id, dtype="drain", hp=target.hp)
        log.append(f"    {target.id} max HP drained to {target.max_hp}")
    for rider in damage_riders_vs(attacker, target.id):
        if target.alive:
            apply_damage(target, rider.roll(rng, crit=crit), rider.type, log, rng, enc=enc)
    # Absorb Elements stored a one-shot elemental rider for the absorber's next melee hit
    if attacker.absorb_rider is not None and atk.kind == "melee" and target.alive:
        ar = attacker.absorb_rider
        attacker.absorb_rider = None
        log.append(f"    {attacker.id}'s Absorb Elements adds {ar.type} damage")
        apply_damage(target, ar.roll(rng), ar.type, log, rng, enc=enc)
    if atk.rider and target.alive:
        _apply_rider(atk.rider, attacker, target, rng, log, enc=enc)
    # conditional on-hit bonus damage (Martial Advantage, Sneak Attack, Charge, ...)
    if enc is not None and target.alive and attacker.md.bonus_damage:
        from . import modifiers
        for m in attacker.md.bonus_damage:
            if m.kind and m.kind != atk.kind:
                continue
            if m.once_per_turn and m.name in attacker.bonus_damage_used:
                continue
            if modifiers.holds(m.when, enc, attacker, target, adv=net > 0, dis=net < 0, mod=m, atk=atk):
                if m.once_per_turn:
                    attacker.bonus_damage_used.add(m.name)
                log.append(f"    {attacker.id}'s {m.name}: +{m.damage.type} damage")
                apply_damage(target, _hd(m.damage.roll(rng, crit=crit)), m.damage.type, log,
                             rng, enc=enc, crit=crit)
    # Monk Stunning Strike: spend Ki on a melee hit -> CON save or stunned (once per turn)
    if (enc is not None and attacker.md.stunning_strike and atk.kind == "melee"
            and target.alive):
        enc.monk_stunning_strike(attacker, target)
    # Great Weapon Master: a melee crit or a kill with a heavy weapon grants a bonus-action attack
    if (attacker.md.gwm and atk.kind == "melee" and atk.heavy
            and (crit or (not target.alive and alive_before))):
        attacker.gwm_bonus_ready = True
    if enc is not None:
        if target.alive:
            enc.offer_hellish_rebuke(target, attacker)   # on-damage reaction
        else:
            enc.fire_on_kill(attacker, target, melee=atk.kind == "melee")  # e.g. Rampage
    return True


def tick_conditions_end_of_turn(c: Combatant, rng: RNG, log: list[str]) -> None:
    """Decrement durations and roll save-ends conditions at end of the turn."""
    expired = []
    for name, cond in list(c.conditions.items()):
        if cond.duration is not None:
            cond.duration -= 1
            if cond.duration <= 0:
                expired.append(name)
        elif cond.save_ability is not None:
            # The recovery save rolls free of the condition's OWN hindrance:
            # restrained gives disadvantage on DEX saves, so a DEX-save-ends
            # restraint (engulf) would nearly never end — and a save-ends
            # paralysis with a STR/DEX save would literally never end (auto-
            # fail). Lift the condition for the roll, reinstate on a failure.
            c.conditions.pop(name, None)
            if saving_throw(c, cond.save_ability, cond.save_dc, rng):
                log.append(f"    {c.id} shakes off {name} (save)")
            elif cond.escalates_to and cond.escalates_to not in c.md.condition_immunities:
                # a multi-stage condition worsens on a repeated failure (e.g. a
                # basilisk's gaze: restrained -> petrified). If the creature is immune
                # to the worse condition, the current one simply persists (save-ends).
                log.append(f"    {c.id}'s {name} worsens to {cond.escalates_to}!")
                apply_condition(c, cond.escalates_to, cond.source_id, rng, log)
            else:
                c.conditions[name] = cond            # still held fast
    for name in expired:
        c.conditions.pop(name, None)
    cleanup_implied(c)
