"""Shared tactical helpers: immunity-aware option value, and the strategy taxonomy
(4e combat role + Intelligence tier) used to brief the LLM controller.

Grounded in the 4e monster-role taxonomy and Keith Ammann's "The Monsters Know
What They're Doing" (tactical sophistication keyed to Intelligence).
"""
from __future__ import annotations

from . import spells
from .engine import _attacks_for_action
from .models import Ability, Combatant, MonsterDef, Option
from .rules import damage_multiplier


# -- immunity-aware option value (P0/P1) ----------------------------------

def _option_damages(actor: Combatant, opt: Option) -> list[tuple[float, str]]:
    """(average, damage_type) pairs an option would deal; [] for non-damage."""
    k = opt.kind
    if k in ("attack", "multiattack"):
        out = []
        for a in _attacks_for_action(actor.attacks, actor.multiattack, opt.name):
            out += [(d.average(), d.type) for d in a.damage]
        return out
    if k == "offhand":
        a = actor.attacks.get(opt.name)          # equipment-derived for PCs, else md.attacks
        return [(d.average(), d.type) for d in a.damage] if a else []
    if k == "area":
        area = next((a for a in actor.md.areas if a.name == opt.name), None)
        return [(d.average(), d.type) for d in area.damage] if area else []
    if k == "spell":
        try:
            sp = spells.get(opt.name)
        except KeyError:
            return []
        out = [(d.average(), d.type) for e in sp.effects if e.kind != "heal"
               for d in e.damage]
        if sp.target_mode == "multi":
            out = out * sp.count
        return out
    return []


def expected_damage(enc, actor: Combatant, opt: Option) -> float:
    """Expected damage of an option vs its target, after immunity/resist/vuln."""
    dmgs = _option_damages(actor, opt)
    tgt = enc.combatants.get(opt.target_id)
    if opt.kind == "area" and tgt is not None:
        area = next((a for a in actor.md.areas if a.name == opt.name), None)
        if area and area.rider and area.rider.zero_hp_on_fail:
            # save-or-drop-to-0 (Demilich Howl, Banshee Wail): typeless and worth
            # about half the target's remaining HP (rough failed-save odds)
            dmgs = dmgs + [(tgt.hp * 0.5, "unavoidable")]
    if not dmgs:
        return 0.0
    if tgt is None:
        return sum(a for a, _ in dmgs)
    return sum(a * damage_multiplier(tgt, d) for a, d in dmgs)


def effectiveness_tag(enc, actor: Combatant, opt: Option) -> str:
    """A short note for the LLM prompt: IMMUNE / resisted / vulnerable / ''."""
    dmgs = _option_damages(actor, opt)
    tgt = enc.combatants.get(opt.target_id)
    if not dmgs or tgt is None:
        return ""
    base = sum(a for a, _ in dmgs)
    eff = sum(a * damage_multiplier(tgt, d) for a, d in dmgs)
    if eff <= 0:
        return " (IMMUNE — 0 dmg)"
    if eff < base * 0.9:
        return " (resisted)"
    if eff > base * 1.1:
        return " (vulnerable!)"
    return ""


# -- greedy expected value (the ai=greedy controller) ----------------------
# One-ply option pricing from the engine's own probability math: hit chance vs
# AC, save-failure chance vs the target's save bonus, damage after resistances,
# and conditions priced as a fraction of the victim's REMAINING hp. Pure
# arithmetic — no RNG, no cloning — so it is deterministic and batch-fast.

# how much of the victim's remaining hp a (failed-save) condition is worth
COND_VALUE = {
    "petrified": 0.7, "paralyzed": 0.6, "unconscious": 0.6, "stunned": 0.5,
    "charmed": 0.4, "restrained": 0.3, "blinded": 0.25, "frightened": 0.2,
    "prone": 0.15, "poisoned": 0.15, "grappled": 0.1,
}
# flat values for buff/utility options the math can't price from the stat block
FLAT_VALUE = {
    "advance": 0.03, "dash": 0.02, "teleport": 0.025, "escape": 0.04,
    "hide": 0.01, "ready": 0.005, "action_surge": 6.0, "rage": 6.0,
    "second_wind": 0.0,          # priced by wounds below
    "vow": 4.0, "sacred_weapon": 4.0, "bardic_inspiration": 3.0,
    "turn_undead": 6.0, "wild_shape": 8.0, "frighten": 0.0,   # priced below
}
HEAL_KINDS = ("second_wind", "quaff", "lay_on_hands", "preserve_life", "moon_heal")


def _p_hit(bonus: int, ac: int) -> float:
    return min(0.95, max(0.05, (21 + bonus - ac) / 20))


def _p_fail(dc: int, save_bonus: int) -> float:
    return min(0.95, max(0.05, (dc - save_bonus - 1) / 20))


def _attack_ev(enc, actor: Combatant, t: Combatant, atks) -> float:
    cover = enc.cover_ac(actor, t)
    if cover is None:
        return 0.0
    total = 0.0
    for a in atks:
        p = _p_hit(a.attack_bonus, t.ac + cover)
        total += p * sum(d.average() * damage_multiplier(t, d.type) for d in a.damage)
        r = a.rider
        if r:
            pf = _p_fail(r.dc, t.md.save_bonus(r.ability))
            if r.extra_damage:
                total += p * pf * (r.extra_damage.average()
                                   * damage_multiplier(t, r.extra_damage.type))
            if r.on_fail_condition:
                total += p * pf * COND_VALUE.get(r.on_fail_condition, 0.1) * t.hp
    return total


def _area_ev(enc, actor: Combatant, area, center: Combatant) -> float:
    cells = enc._area_cells(actor.pos, center.pos, area)
    hit = [e for e in enc.enemies_of(actor)
           if any(s in cells for s in e.occupied_squares())
           and (not area.requires_condition or e.has(area.requires_condition))]
    if area.max_targets and len(hit) > area.max_targets:
        hit.sort(key=lambda e: (enc.dist(actor, e), e.id))
        hit = hit[:area.max_targets]
    total, dealt = 0.0, 0.0
    for e in hit:
        pf = _p_fail(area.dc, e.md.save_bonus(area.save))
        dmg = sum(d.average() * damage_multiplier(e, d.type) for d in area.damage)
        ev = pf * dmg + (0 if not area.half_on_save else (1 - pf) * dmg / 2)
        dealt += ev
        total += ev
        r = area.rider
        if r:
            if r.zero_hp_on_fail:
                total += pf * e.hp
            if r.on_fail_condition:
                total += pf * COND_VALUE.get(r.on_fail_condition, 0.1) * e.hp
    if area.heal_owner and actor.hp < actor.max_hp:
        total += 0.5 * min(dealt, actor.max_hp - actor.hp)
    return total


def _spell_ev(enc, actor: Combatant, sp, opt: Option) -> float:
    if sp.concentration and actor.concentration is not None:
        return 0.0                       # recasting would break what we hold
    t = enc.combatants.get(opt.target_id)
    if sp.affects in ("self", "allies"):
        total = 0.0
        for e in sp.effects:
            if e.kind == "heal" and t is not None:
                avg = sum(d.average() for d in e.damage)
                missing = t.max_hp - t.hp
                total += min(avg, missing) * (1.5 if t.hp <= t.max_hp * 0.4 else 0.4)
            elif e.kind == "summon":
                total += 12.0
            elif e.kind in ("modifier", "aura"):
                total += 4.0 + 2 * sum(d.average() for d in e.damage)
        return total
    # offensive: collect who it would catch
    if sp.target_mode in ("point", "self_area"):
        from .cast import area_targets
        targets = area_targets(enc, actor, sp, t)
    else:
        targets = [t] if t is not None else []
    total = 0.0
    for e in targets:
        if e is None:
            continue
        for eff in sp.effects:
            dmg = sum(d.average() * damage_multiplier(e, d.type) for d in eff.damage)
            if eff.kind == "spell_attack":
                shots = sp.count if sp.target_mode == "multi" else 1
                total += _p_hit(actor.spell_attack, e.ac) * dmg * shots
            elif eff.kind == "auto_damage":
                darts = sp.count if sp.target_mode == "multi" else 1
                total += dmg * darts
            elif eff.kind == "save" and eff.ability is not None:
                pf = _p_fail(actor.spell_dc, e.md.save_bonus(eff.ability))
                total += pf * dmg + ((1 - pf) * dmg / 2 if eff.half_on_save else 0)
                if eff.condition:
                    total += pf * COND_VALUE.get(eff.condition, 0.1) * e.hp
                if eff.modifier_on_fail:
                    total += pf * 3.0
            elif eff.kind == "banish":
                pf = _p_fail(actor.spell_dc, e.md.save_bonus(eff.ability or Ability.CHA))
                total += pf * 0.5 * e.hp
    return total


def expected_value(enc, actor: Combatant, opt: Option) -> float:
    """Probability-weighted value of an option in hp-equivalents (greedy's score)."""
    k = opt.kind
    t = enc.combatants.get(opt.target_id)
    if k in ("attack", "multiattack"):
        if t is None:
            return 0.0
        return _attack_ev(enc, actor, t,
                          _attacks_for_action(actor.attacks, actor.multiattack, opt.name))
    if k in ("offhand", "war_magic", "polearm", "war_priest", "flurry", "quicken"):
        a = actor.attacks.get(opt.name)
        if t is not None and a is not None:
            return _attack_ev(enc, actor, t, [a])
        return 0.6 * expected_damage(enc, actor, opt)
    if k == "area":
        area = next((a for a in actor.md.areas if a.name == opt.name), None)
        if area is None or t is None:
            return 0.0
        return _area_ev(enc, actor, area, t)
    if k == "spell":
        try:
            sp = spells.get(opt.name)
        except KeyError:
            return 0.0
        return _spell_ev(enc, actor, sp, opt)
    if k == "eye_rays":
        rays = actor.md.eye_rays
        in_range = [e for e in enc.enemies_of(actor)
                    if enc.dist(actor, e) <= actor.md.eye_ray_range
                    and enc.cover_ac(actor, e) is not None]
        if not rays or not in_range:
            return 0.0
        near = min(in_range, key=lambda e: (enc.dist(actor, e), e.id))
        per_ray = 0.0
        for ray in rays:
            pf = _p_fail(ray.dc, near.md.save_bonus(ray.ability))
            if ray.damage:
                d = ray.damage.average() * damage_multiplier(near, ray.damage.type)
                per_ray += pf * d + ((1 - pf) * d / 2 if ray.half_on_save else 0)
            if ray.condition:
                per_ray += pf * COND_VALUE.get(ray.condition, 0.1) * near.hp
        return per_ray / len(rays) * min(actor.md.eye_ray_count, len(rays))
    if k == "swallow":
        return 0.5 * t.hp if t is not None else 0.0
    if k == "frighten":
        fp = actor.md.frightful_presence
        if fp is None:
            return 0.0
        fresh = [e for e in enc.enemies_of(actor)
                 if not e.has("frightened") and enc.dist(actor, e) <= fp.size]
        return sum(_p_fail(fp.dc, e.md.save_bonus(fp.save)) * 0.2 * e.hp for e in fresh)
    if k in HEAL_KINDS:
        tgt = t or actor
        missing = tgt.max_hp - tgt.hp
        return 0.5 * missing if tgt.hp <= tgt.max_hp * 0.5 else 0.05 * missing
    if k == "lay_on_hands" and t is not None:
        missing = t.max_hp - t.hp
        return 0.5 * missing if t.hp <= t.max_hp * 0.4 else 0.0
    return FLAT_VALUE.get(k, 0.0)


# -- strategy taxonomy (P2a) ----------------------------------------------

def _has_heal_or_buff(md: MonsterDef) -> bool:
    for name in md.spells:
        try:
            sp = spells.get(name)
        except KeyError:
            continue
        if sp.affects == "allies":
            return True
    return False


def _has_control(md: MonsterDef) -> bool:
    if md.frightful_presence is not None or md.areas:
        return True
    for name in md.spells + tuple(md.innate):
        try:
            sp = spells.get(name)
        except KeyError:
            continue
        if sp.target_mode in ("point", "self_area") or any(e.condition for e in sp.effects):
            return True
    return False


def combat_role(md: MonsterDef) -> str:
    """Derive the 4e combat role from objective stat-block signals."""
    melee = [a for a in md.attacks.values() if a.kind == "melee"]
    ranged = [a for a in md.attacks.values() if a.kind == "ranged"]
    blasty = bool(md.spells) or bool(md.areas)
    if _has_control(md) and (blasty or md.frightful_presence):
        role = "controller"
    elif ranged and not melee:
        role = "artillery"
    elif (md.fly > 0 or md.speed >= 40) and (ranged or md.spells):
        role = "skirmisher"
    elif md.skills.get("Stealth", 0) >= 4:
        role = "lurker"
    elif md.ac >= 16 and melee:
        role = "soldier"
    else:
        role = "brute"
    if _has_heal_or_buff(md):
        role += "/leader"
    return role


def int_tier(md: MonsterDef) -> str:
    i = md.abilities.get(Ability.INT, 10)
    if i <= 2:
        return "mindless"
    if i <= 5:
        return "animal"
    if i <= 9:
        return "cunning"
    if i <= 13:
        return "smart"
    return "genius"


_ROLE_LINE = {
    "controller": "Lead with area attacks and conditions on clustered or dangerous foes.",
    "artillery": "Stay at maximum range; never enter melee; blast the deadliest foe.",
    "skirmisher": "Strike and reposition; kite at range/altitude; don't get pinned.",
    "lurker": "Attack from hiding for burst damage, then break line of sight.",
    "soldier": "Hold the front line; protect weaker allies; lock down threats.",
    "brute": "Close the distance and pour your strongest attacks into one foe.",
}
_LEADER_LINE = "As a leader, keep allies up — heal the badly wounded and buff before blasting."

_TIER_PRINCIPLES = {
    "mindless": ["Attack the nearest reachable foe. You do not retreat."],
    "animal": ["Go for wounded or weak prey.", "Use your pack/numbers.",
               "Flee if badly hurt."],
    "cunning": ["Focus all fire on ONE target.", "Target enemy spellcasters and healers.",
                "Avoid opportunity attacks (Disengage).",
                "Never attack a foe immune to your damage — switch target or attack."],
    "smart": ["Hit concentrating casters to break their concentration.",
              "Conserve high spell slots; don't break your own concentration.",
              "Kite if you out-range the enemy."],
    "genius": ["Exploit resistances and vulnerabilities.", "Bait enemy reactions.",
               "Sequence abilities optimally (e.g. frighten, then breath, then attacks)."],
}
_TIER_ORDER = ["mindless", "animal", "cunning", "smart", "genius"]


def strategy_brief(md: MonsterDef) -> str:
    """Role line + cumulative INT-gated principles + optional free-form override."""
    role = combat_role(md)
    tier = int_tier(md)
    lines = [f"Your combat role is {role} ({tier} tactician)."]
    lines.append(_ROLE_LINE[role.split("/")[0]])
    if "leader" in role:
        lines.append(_LEADER_LINE)
    principles: list[str] = []
    for t in _TIER_ORDER[:_TIER_ORDER.index(tier) + 1]:
        principles += _TIER_PRINCIPLES[t]
    lines += [f"- {p}" for p in principles]
    if md.strategy:
        lines.append(f"Specific tactics: {md.strategy}")
    return "\n".join(lines)
