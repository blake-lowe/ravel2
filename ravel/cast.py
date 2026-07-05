"""Spell casting resolution: enumeration, targeting, scaling, effect application,
and concentration. The high-level choice (which spell, which target) is the
controller's; everything mechanical here is deterministic.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import spells
from .conditions import attack_mods
from .dice import Damage, parse_dice
from .effects import (add_effect, attackers_have_advantage, attackers_have_disadvantage,
                      break_concentration, has_attack_disadvantage, remove_effect,
                      start_concentration, total_ac_bonus, total_attack_bonus)
from .grid import (cone_cells, cube_cells, cylinder_cells, dist3d, feet_between,
                   line_aoe_cells, sphere_cells)
from .models import Ability, ActiveEffect, Combatant, Option
from .rules import apply_condition, apply_damage, area_damage_after_save, saving_throw
from .conditions import cleanup_implied
from .spells import Spell

if TYPE_CHECKING:
    from .engine import Encounter


def _sign(n: int) -> int:
    return (n > 0) - (n < 0)


def castable_slot(actor: Combatant, sp: Spell) -> int | None:
    """Lowest usable slot level (0 for a cantrip), or None if it can't be cast."""
    if sp.level == 0:
        return 0
    for lvl in range(sp.level, 10):
        if actor.slots.get(lvl, 0) > 0:
            return lvl
    return None


def eff_range(sp: Spell) -> int:
    if sp.range_type == "self":
        return sp.size if sp.target_mode == "self_area" else 0
    if sp.range_type == "touch":
        return 5
    return sp.range_ft


def _is_projectile(sp: Spell) -> bool:
    return any(e.kind in ("spell_attack", "auto_damage") for e in sp.effects)


def requires_verbal(sp: Spell) -> bool:
    """Does the spell have a verbal component (so Silence blocks it)? If a spell's
    components aren't recorded, assume verbal — nearly every 5e spell has one."""
    return ("V" in sp.components) if sp.components else True


def area_targets(enc: "Encounter", actor: Combatant, sp: Spell, primary,
                 origin=None) -> list[Combatant]:
    """Enemies an area spell catches. A sphere is a true 3D ball (it respects
    altitude — a flyer above the blast escapes); a cylinder is a vertical column
    (any altitude within its radius); cube/cone/line use the horizontal template."""
    if primary is None:
        return []
    enemies = enc.enemies_of(actor)
    r = sp.size
    if sp.shape == "sphere":
        return [e for e in enemies
                if any(dist3d(primary.pos, primary.alt, s, e.alt) <= r + 1e-9
                       for s in e.occupied_squares())]
    if sp.shape == "cylinder":
        return [e for e in enemies
                if any(feet_between(primary.pos, s) <= r + 1e-9
                       for s in e.occupied_squares())]
    cells = _area_cells(enc, actor, sp, primary, origin)
    return [e for e in enemies if any(s in cells for s in e.occupied_squares())]


def _portent_die(actor: Combatant, target: Combatant, ability, dc: int) -> "int | None":
    """Diviner Portent: spend the lowest pre-rolled die to force an enemy's save, but only if
    that die would actually make them fail (don't waste it)."""
    if not (actor.md.portent and actor.portent_rolls) or target.team == actor.team:
        return None
    low = min(actor.portent_rolls)
    if low + target.md.save_bonus(ability) < dc:
        actor.portent_rolls.remove(low)
        return low
    return None


def _wounded_ally(enc: "Encounter", actor: Combatant) -> Combatant:
    # includes downed-but-not-dead allies so healing can pick them back up (lowest HP first)
    allies = [c for c in enc.combatants.values()
              if c.team == actor.team and not c.dead and not c.fled and not c.banished
              and (c.in_combat or c.dying) and c.hp < c.max_hp]
    return min(allies, key=lambda a: a.hp) if allies else actor


def enumerate_spell_options(enc: "Encounter", actor: Combatant,
                            phase: str = "action") -> list[Option]:
    opts: list[Option] = []
    if enc.in_antimagic(actor):
        return opts                       # no spellcasting inside an antimagic field
    if actor.armor_penalty:
        return opts                       # can't cast in armor you're not proficient with
    silenced = enc.is_silenced(actor)
    for name in actor.md.spells:
        try:
            sp = spells.get(name)
        except KeyError:
            continue
        if sp.casting_time == "reaction":
            continue  # reaction spells fire via reaction hooks, not as actions
        if sp.casting_time not in ("action", "bonus"):
            continue  # ritual / minute / hour casts aren't offered in the combat loop
        if silenced and requires_verbal(sp):
            continue  # a Silence zone blocks verbal-component spells
        if phase == "bonus" and sp.casting_time != "bonus":
            continue
        if phase == "action" and sp.casting_time == "bonus":
            continue  # bonus-action spells are offered in the bonus phase
        # bonus-action spell rule: no leveled bonus spell after a leveled action spell
        if phase == "bonus" and sp.level >= 1 and actor.cast_leveled_this_turn:
            continue
        slot = castable_slot(actor, sp)
        if slot is None:
            continue
        lvl_note = "cantrip" if sp.level == 0 else f"lvl {slot}"
        if sp.affects == "self":
            opts.append(Option(f"spell:{name}", "spell", name, actor.id,
                               f"Cast {name} ({lvl_note}, self)", spell=name, slot_level=slot))
        elif sp.affects == "allies":
            heal = any(e.kind == "heal" for e in sp.effects)
            tgt = _wounded_ally(enc, actor) if heal else actor
            verb = "heal" if heal else "buff"
            opts.append(Option(f"spell:{name}", "spell", name, tgt.id,
                               f"Cast {name} ({lvl_note}) to {verb} allies",
                               spell=name, slot_level=slot))
        else:  # enemies
            aoe = sp.target_mode in ("point", "self_area")
            for e in enc.enemies_of(actor):
                ok, _ = enc.reachable_within(actor, e, eff_range(sp) or 5)
                if not ok:
                    continue
                note = ""
                if aoe:
                    # for self-area spells, estimate from where the caster will move to
                    org = None
                    if sp.target_mode == "self_area" and actor.can_move:
                        org = enc.choose_destination(actor, e, "melee", 5)
                    hits = len(area_targets(enc, actor, sp, e, org))
                    note = f" — hits ~{hits} foe(s)"
                opts.append(Option(f"spell:{name}->{e.id}", "spell", name, e.id,
                                   f"Cast {name} ({lvl_note}) at the {e.name} "
                                   f"[{e.id}] ({e.hp}/{e.max_hp} HP){note}",
                                   spell=name, slot_level=slot))
    if phase == "action":
        opts.extend(_innate_options(enc, actor))
    return opts


def _innate_options(enc: "Encounter", actor: Combatant) -> list[Option]:
    """Innate (X/day or at-will) spells — cast without a slot (slot_level = -1)."""
    out: list[Option] = []
    silenced = enc.is_silenced(actor)
    for name, per_day in actor.md.innate.items():
        if per_day != 0 and actor.innate_left.get(name, 0) <= 0:
            continue                      # out of daily uses
        try:
            sp = spells.get(name)
        except KeyError:
            continue
        if silenced and requires_verbal(sp):
            continue
        note = "at-will" if per_day == 0 else f"{actor.innate_left.get(name, 0)}/day left"
        if sp.affects in ("self", "allies"):
            tgt = (_wounded_ally(enc, actor) if any(e.kind == "heal" for e in sp.effects)
                   else actor)
            out.append(Option(f"innate:{name}", "spell", name, tgt.id,
                              f"Cast {name} (innate, {note})", spell=name, slot_level=-1))
        else:
            for e in enc.enemies_of(actor):
                if enc.reachable_within(actor, e, eff_range(sp) or 5)[0]:
                    out.append(Option(f"innate:{name}->{e.id}", "spell", name, e.id,
                                      f"Cast {name} (innate, {note}) at {e.id}",
                                      spell=name, slot_level=-1))
    return out


def _spend_cast(actor: Combatant, sp: Spell, slot: int) -> None:
    """Spend the resource for a cast: an innate use (slot<0) or a spell slot."""
    if slot < 0:                                   # innate
        if actor.md.innate.get(sp.name, 0) != 0:   # 0 = at-will
            actor.innate_left[sp.name] = actor.innate_left.get(sp.name, 0) - 1
        if sp.level >= 1:
            actor.cast_leveled_this_turn = True    # innate leveled spell also gates bonus
    elif slot > 0:
        actor.slots[slot] -= 1
        actor.cast_leveled_this_turn = True        # for the bonus-action spell rule


def cast(enc: "Encounter", actor: Combatant, opt: Option) -> None:
    sp = spells.get(opt.spell)
    slot = opt.slot_level
    innate = slot < 0
    if not innate and slot > 0 and actor.slots.get(slot, 0) <= 0:
        enc.log.append(f"  {actor.id} has no level {slot} slot for {sp.name}")
        return
    if innate and sp.name not in actor.md.innate:
        return
    # magical zones can bar the cast outright
    if enc.in_antimagic(actor):
        enc.log.append(f"  {actor.id}'s {sp.name} fizzles in the antimagic field")
        return
    if enc.is_silenced(actor) and requires_verbal(sp):
        enc.log.append(f"  {actor.id} can't cast {sp.name} (silenced)")
        return

    # Counterspell reaction window: the resource is still expended if countered
    if sp.level >= 1 and enc.offer_counterspell(actor, sp):
        _spend_cast(actor, sp, slot)
        enc.log.append(f"  {actor.id}'s {sp.name} is COUNTERSPELLED")
        return

    if sp.affects == "enemies":
        actor.hidden = False      # casting an offensive spell reveals a hidden caster

    # casting a new concentration spell ends the prior one, even if the new one
    # ends up establishing nothing (e.g. its only target saves).
    if sp.concentration and actor.concentration is not None:
        break_concentration(actor, enc.log, f"casting {sp.name}", enc=enc)

    primary = enc.combatants.get(opt.target_id)
    # reposition to bring the primary target into range + line of effect
    if sp.range_type == "self":
        if sp.target_mode == "self_area" and primary is not None and actor.can_move:
            enc.move_to(actor, enc.choose_destination(actor, primary, "melee", 5))
    elif primary is not None:
        enc.move_to(actor, enc.choose_destination(actor, primary, "ranged", eff_range(sp)))
    if not actor.alive:
        return

    targets = _gather_targets(enc, actor, sp, primary, slot)
    # a creature inside an antimagic field can't be affected by a spell
    targets = [t for t in targets if not enc.in_antimagic(t)]
    establishes_area = any(e.kind in ("aura", "summon", "silence", "antimagic", "terrain",
                                      "darkness", "fog", "light", "daylight")
                           for e in sp.effects)
    if not targets and sp.affects == "enemies" and not establishes_area:
        enc.log.append(f"  {actor.id}'s {sp.name} finds no valid target (no slot spent)")
        return

    _spend_cast(actor, sp, slot)   # spend only now that the spell takes effect
    enc.log.append(f"  {actor.id} casts {sp.name}"
                   + (" (innate)" if innate else
                      f" (slot {slot})" if slot > sp.level else "")
                   + (" [concentration]" if sp.concentration else ""))
    if targets:
        enc.log.append(f"    -> targets: {[t.id for t in targets]}")
    if sp.target_mode in ("point", "self_area") and sp.affects == "enemies":
        cells = _area_cells(enc, actor, sp, primary)
        if cells:                        # display-only: the replay shades the template
            enc.emit(kind="area", actor=actor.id, info=sp.name,
                     cells=tuple(sorted(cells)))
    # Sorcerer Metamagic — Empowered Spell: spend 1 sorcery point to reroll low damage dice.
    # Applied to leveled damage spells (cantrips are left cheap so points fuel other metamagic).
    empowered = (actor.md.empowered_spell and sp.level >= 1
                 and actor.resources.get("Sorcery Points", 0) >= 1
                 and any(e.damage for e in sp.effects
                         if e.kind in ("spell_attack", "auto_damage", "save")))
    if empowered:
        actor.resources["Sorcery Points"] -= 1
        enc.log.append(f"    {actor.id} empowers {sp.name} (rerolling low damage dice)")
    applied: list = []
    for eff in sp.effects:
        _apply_effect(enc, actor, sp, eff, targets, slot, applied, primary, empowered)
    # -- Arcane Tradition / Martial Archetype on-cast effects --
    if actor.md.grim_harvest and sp.level >= 1 and any(   # Necromancer: reap HP on a spell kill
            not t.alive and (t.dead or not t.uses_death_saves)   # a real kill, not a downed PC
            and t.team != actor.team and t.md.mtype not in ("construct", "undead")
            for t in targets):
        gain = sp.level * (3 if sp.school == "necromancy" else 2)
        actor.hp = min(actor.max_hp, actor.hp + gain)
        enc.log.append(f"    {actor.id} reaps {gain} HP (Grim Harvest)")
    if actor.arcane_ward_max and sp.school == "abjuration" and slot >= 1:   # Abjurer: recharge ward
        actor.arcane_ward = min(actor.arcane_ward_max, actor.arcane_ward + 2 * slot)
        enc.log.append(f"    {actor.id}'s Arcane Ward recharges ({actor.arcane_ward})")
    if actor.md.war_magic and (sp.level == 0 or actor.md.improved_war_magic):   # War Magic
        actor.cast_cantrip_this_turn = True                # (Improved War Magic: any spell)
    # concentrate only if the spell actually established an ongoing effect
    if sp.concentration and applied:
        start_concentration(actor, sp.name, sp.duration_rounds or 10, applied, enc.log,
                            level=max(sp.level, slot), enc=enc)


def _gather_targets(enc: "Encounter", actor: Combatant, sp: Spell,
                    primary: Combatant | None, slot: int) -> list[Combatant]:
    mode = sp.target_mode
    if mode == "self":
        return [actor]
    if sp.affects == "allies":
        allies = [c for c in enc.living() if c.team == actor.team]
        if any(e.kind == "heal" for e in sp.effects):
            wounded = sorted((a for a in allies if a.hp < a.max_hp), key=lambda a: a.hp)
            return wounded[:max(1, sp.count)] or [actor]
        allies.sort(key=lambda a: (a.id != actor.id, feet_between(actor.pos, a.pos)))
        return allies[:max(1, sp.count)]
    # enemies
    enemies = enc.enemies_of(actor)
    if mode in ("single", "multi"):
        if _is_projectile(sp):
            return [primary] if primary else []
        # save/modifier spread across nearest N enemies (e.g. Bane)
        n = _scaled_count(sp, slot)
        enemies.sort(key=lambda e: feet_between(actor.pos, e.pos))
        picked = [primary] if primary else []
        for e in enemies:
            if e not in picked and len(picked) < n:
                picked.append(e)
        return picked
    return area_targets(enc, actor, sp, primary)


def _area_cells(enc: "Encounter", actor: Combatant, sp: Spell, primary, origin=None):
    """Cells a spell's AoE covers. For self-area spells `origin` is the caster's
    position the template fires from (defaults to its current square — pass the
    post-move square when estimating coverage at enumeration time)."""
    if primary is None:
        return set()
    if sp.target_mode == "point":
        if sp.shape == "cube":
            return cube_cells(primary.pos, sp.size, enc.grid)
        if sp.shape == "cylinder":
            return cylinder_cells(primary.pos, sp.size, enc.grid)
        if sp.shape in ("cone", "line"):
            # a point-placed cone/line is aimed from the caster through the point
            d = (primary.pos[0] - actor.pos[0], primary.pos[1] - actor.pos[1])
            if d == (0, 0):
                d = (1, 0)
            fn = cone_cells if sp.shape == "cone" else line_aoe_cells
            return fn(primary.pos, d, sp.size, enc.grid)
        return sphere_cells(primary.pos, sp.size, enc.grid)
    # self_area: template emanates from the caster toward the primary target
    o = origin or actor.pos
    direction = (primary.pos[0] - o[0], primary.pos[1] - o[1])
    if direction == (0, 0):
        direction = (1, 0)              # only substitute when the vector is fully zero
    if sp.shape == "cone":
        return cone_cells(o, direction, sp.size, enc.grid)
    if sp.shape == "line":
        return line_aoe_cells(o, direction, sp.size, enc.grid)
    return cube_cells(o, sp.size, enc.grid)


def _apply_effect(enc: "Encounter", actor: Combatant, sp: Spell, eff, targets,
                  slot: int, applied: list, primary: Combatant | None = None,
                  empowered: bool = False) -> None:
    rng, log = enc.rng, enc.log
    dc = actor.spell_dc
    # Evocation subclass: Empowered Evocation adds INT to ONE damage roll of an evocation
    # spell (>= 1st level); Potent Cantrip makes a save vs your cantrip still deal half.
    emp = [actor.md.empowered_evocation
           if (sp.school == "evocation" and sp.level >= 1) else 0]

    def empower(amt: int) -> int:
        if emp[0] and amt > 0:
            amt += emp[0]
            emp[0] = 0
        return amt

    def prep(dmgs: list, is_eb: bool = False) -> list:
        """Apply the sorcerer/warlock damage metamagic & invocations: Empowered Spell rerolls
        low dice; Agonizing Blast adds CHA to each Eldritch Blast beam; Draconic Elemental
        Affinity adds CHA to the first matching-element die."""
        cha = actor.md.mod(Ability.CHA)
        out = []
        for i, d in enumerate(dmgs):
            bonus, rb = d.bonus, d.reroll_below
            if empowered and d.count:
                rb = max(rb, 2)                       # reroll 1s and 2s (approximates CHA dice)
            if is_eb and actor.md.agonizing_blast:
                bonus += cha                          # Agonizing Blast: +CHA per beam
            elif (i == 0 and actor.md.elemental_affinity
                  and d.type == actor.md.elemental_affinity_dtype
                  and sp.target_mode != "multi"):
                bonus += actor.md.elemental_affinity  # Elemental Affinity: +CHA to one roll
            out.append(Damage(d.count, d.sides, bonus, d.type, reroll_below=rb,
                              min_die=d.min_die, exploding=d.exploding))
        return out
    potent = actor.md.potent_cantrip and sp.level == 0
    if eff.kind == "spell_attack":
        dmgs = prep(_scaled_damage(sp, eff, slot, actor), is_eb=sp.name == "Eldritch Blast")
        shots = _scaled_count(sp, slot, actor) if sp.target_mode == "multi" else 1
        for t in targets:
            for _ in range(shots):
                if not t.alive:
                    break
                _spell_attack(enc, actor, t, dmgs, eff.melee, empower=empower)
    elif eff.kind == "auto_damage":
        dmgs = prep(_scaled_damage(sp, eff, slot, actor))
        darts = _scaled_count(sp, slot, actor) if sp.target_mode == "multi" else 1
        for t in targets:
            if sp.name == "Magic Missile" and enc.try_shield(t):
                log.append(f"    {t.id}'s Shield negates Magic Missile")
                continue
            enc.emit(kind="attack", actor=actor.id, info=t.id,   # replay draws the darts
                     dtype="ranged", amount=1)
            for _ in range(darts):
                if not t.alive:
                    break
                for d in dmgs:
                    apply_damage(t, enc.absorb(t, d.type, empower(d.roll(rng))), d.type,
                                 log, rng, enc=enc)
    elif eff.kind == "save":
        dmgs = prep(_scaled_damage(sp, eff, slot, actor))
        important = bool(eff.condition) or sum(d.average() for d in dmgs) >= 20
        # An area save spell is one shared damage roll every target takes, so Empowered
        # Evocation's +INT (added before the save halves it) benefits ALL of them.
        emp0 = emp[0]
        for t in targets:
            pd = _portent_die(actor, t, eff.ability, dc)
            if pd is not None:                           # Portent forces the roll
                saved = pd + t.md.save_bonus(eff.ability) >= dc
                if not saved and important and t.legendary_resistance_left > 0:
                    t.legendary_resistance_left -= 1     # a boss can still spend Legendary Resistance
                    saved = True
                    log.append(f"    {t.id} uses Legendary Resistance")
                log.append(f"    {actor.id} uses Portent ({pd}) on {t.id}")
            else:
                es = t.eldritch_strike_by == actor.id     # Eldritch Strike: disadvantage on this save
                if es:
                    t.eldritch_strike_by = None
                saved = saving_throw(t, eff.ability, dc, rng, important=important, log=log,
                                     vs_magic=True, disadvantage=es)
            log.append(f"    {t.id} {eff.ability.value} save vs DC {dc}: "
                       f"{'success' if saved else 'FAIL'}")
            bonus = emp0
            for d in dmgs:
                amt = d.roll(rng)
                if bonus:                        # +INT to one die, before the save halves it
                    amt += bonus
                    bonus = 0
                # Evasion-aware (Monk/Rogue): a DEX save-for-half success takes none, a fail half
                amt = area_damage_after_save(t, eff.ability, saved,
                                             eff.half_on_save or potent, amt,
                                             negate_on_save=True)
                if amt:
                    apply_damage(t, enc.absorb(t, d.type, amt), d.type, log, rng, enc=enc)
            if not saved and t.alive:
                _apply_save_failure(enc, actor, sp, eff, t, dc, applied, slot)
    elif eff.kind == "heal":
        from .conditions import can_heal
        mod = actor.spell_mod if (eff.add_mod and actor.spell_ability) else 0
        for t in targets:
            if not can_heal(t):
                log.append(f"    {t.id} can't regain HP (cursed)")
                continue
            amt = sum(d.roll(rng) for d in _scaled_damage(sp, eff, slot, actor)) + mod
            t.hp = min(t.max_hp, t.hp + amt)
            if t.hp > 0:
                t.wake_from_dying()          # Healing Word / Cure Wounds picks up a downed ally
            enc.emit(kind="heal", actor=t.id, amount=amt, hp=t.hp)
            log.append(f"    {t.id} healed {amt} -> {t.hp}/{t.max_hp} HP")
    elif eff.kind == "modifier":
        for t in targets:
            add_effect(t, _build_effect(sp, actor.id, eff.modifier, slot))
            log.append(f"    {t.id} gains {sp.name}")
            if sp.concentration:
                applied.append((t, "effect", sp.name))
    elif eff.kind == "mark":
        # Hunter's Mark: a concentration rider that rides on the CASTER but only fires when
        # the caster hits the *marked* enemy (rider_target_id). Reuses the damage_rider
        # machinery (effects.damage_riders_vs) — the same one Hex would use.
        mark = primary if primary is not None else (targets[0] if targets else None)
        if mark is not None:
            e = _build_effect(sp, actor.id, eff.modifier or {}, slot)
            e.rider_target_id = mark.id
            add_effect(actor, e)
            log.append(f"    {actor.id} marks {mark.id} ({sp.name}: extra damage per hit)")
            if sp.concentration:
                applied.append((actor, "effect", sp.name))
    elif eff.kind == "dispel":
        for t in targets:
            _dispel_magic(enc, actor, t, slot)
    elif eff.kind == "silence":
        from .models import AuraState
        point = primary.pos if primary is not None else actor.pos
        actor.aura = AuraState(spell=sp.name, source_id=actor.id, shape="sphere",
                               size=eff.size or sp.size, save=Ability.WIS, dc=0,
                               anchor="point", point=point, silence=True)
        log.append(f"    {actor.id}'s Silence zone forms ({eff.size or sp.size} ft at {point})")
        if sp.concentration:
            applied.append((actor, "aura", None))
    elif eff.kind == "antimagic":
        from .models import AuraState
        actor.aura = AuraState(spell=sp.name, source_id=actor.id, shape="sphere",
                               size=eff.size or sp.size, save=Ability.WIS, dc=0,
                               anchor="caster", antimagic=True)
        log.append(f"    {actor.id} is surrounded by an antimagic field "
                   f"({eff.size or sp.size} ft)")
        if sp.concentration:
            applied.append((actor, "aura", None))
    elif eff.kind == "darkness":
        center = actor.pos if sp.affects == "self" else (primary.pos if primary else actor.pos)
        cells = set(sphere_cells(center, eff.size or sp.size, enc.grid))
        entry = {"cells": cells, "level": sp.level}
        enc.darkness.append(entry)
        log.append(f"    {actor.id} conjures magical darkness ({len(cells)} cells)")
        if sp.concentration:
            applied.append((entry, "darkness", None))
    elif eff.kind == "fog":
        center = actor.pos if sp.affects == "self" else (primary.pos if primary else actor.pos)
        cells = set(sphere_cells(center, eff.size or sp.size, enc.grid))
        enc.fog |= cells
        log.append(f"    {actor.id} fills the area with fog ({len(cells)} cells)")
        if sp.concentration:
            applied.append((cells, "fog", None))
    elif eff.kind == "light":
        from .models import Light
        tgt = primary or actor
        enc.lights.append(Light(bright_radius=eff.size or 20, carrier_id=tgt.id,
                                magical=True))
        log.append(f"    {tgt.id} sheds bright light")
    elif eff.kind == "daylight":
        from .grid import LIGHT_BRIGHT
        from .models import Light
        center = actor.pos if sp.affects == "self" else (primary.pos if primary else actor.pos)
        enc.lights.append(Light(bright_radius=eff.size or 60, origin=center, magical=True))
        lit = set(sphere_cells(center, eff.size or 60, enc.grid))
        enc.darkness = [dk for dk in enc.darkness            # dispels <= 3rd-level Darkness
                        if not (dk["cells"] & lit and dk.get("level", 9) <= 3)]
        log.append(f"    {actor.id} floods the area with daylight")
    elif eff.kind == "banish":
        for t in targets:
            saved = saving_throw(t, eff.ability, dc, rng, important=True, log=log,
                                 vs_magic=True)
            log.append(f"    {t.id} {eff.ability.value} save vs DC {dc}: "
                       f"{'success' if saved else 'FAIL'}")
            if not saved:
                t.banished = True
                log.append(f"    ** {t.id} is BANISHED from the fight! **")
                enc.emit(kind="condition", actor=t.id, source=actor.id, info="banished")
                if sp.concentration:
                    applied.append((t, "banish", None))
    elif eff.kind == "terrain":
        from .models import Zone
        if primary is not None:
            size = eff.size or sp.size
            if sp.shape == "line":
                direction = (primary.pos[0] - actor.pos[0], primary.pos[1] - actor.pos[1])
                if direction == (0, 0):
                    direction = (1, 0)
                cells = line_aoe_cells(actor.pos, direction, size, enc.grid)
            elif sp.shape == "cube":
                cells = cube_cells(primary.pos, size, enc.grid)
            else:
                cells = sphere_cells(primary.pos, size, enc.grid)
            z = Zone(name=sp.name, cells=set(cells), difficult=eff.difficult_terrain,
                     damage=tuple(_scaled_damage(sp, eff, slot, actor)), save=eff.ability,
                     dc=dc, half_on_save=eff.half_on_save, duration=sp.duration_rounds or 10)
            enc.zones.append(z)
            log.append(f"    {sp.name} covers {len(z.cells)} cells for {z.duration} rounds")
    elif eff.kind == "aura":
        from .models import AuraState
        point = primary.pos if (eff.anchor == "point" and primary is not None) else actor.pos
        actor.aura = AuraState(
            spell=sp.name, source_id=actor.id, shape=eff.shape or "sphere",
            size=eff.size, save=eff.ability, dc=dc, damage=_scaled_damage(sp, eff, slot, actor),
            half_on_save=eff.half_on_save, difficult_terrain=eff.difficult_terrain,
            anchor=eff.anchor, point=point)
        where = f"at {point}" if eff.anchor == "point" else "around the caster"
        log.append(f"    {actor.id}'s {sp.name} aura forms ({eff.size} ft {where})")
        if sp.concentration:
            applied.append((actor, "aura", None))
    elif eff.kind == "summon":
        enc.summon(actor, eff.creature, eff.summon_count, eff.untargetable,
                   eff.summon_duration or sp.duration_rounds or 10, sp.concentration, applied)


def _apply_save_failure(enc, actor, sp, eff, t, dc, applied, slot: int = 0) -> None:
    if eff.condition:
        apply_condition(t, eff.condition, actor.id, enc.rng, enc.log,
                        duration=(None if eff.save_ends else eff.condition_duration),
                        save_ability=(eff.ability if eff.save_ends else None), save_dc=dc,
                        spell_level=max(sp.level, slot))
        if sp.concentration:
            applied.append((t, "condition", eff.condition))
    if eff.forced_move:
        _push(enc, actor, t, eff.forced_move)
    if eff.modifier_on_fail:
        add_effect(t, _build_effect(sp, actor.id, eff.modifier_on_fail, slot))
        if sp.concentration:
            applied.append((t, "effect", sp.name))


def _spell_attack(enc, actor, t, dmgs, melee: bool, empower=None) -> None:
    rng, log = enc.rng, enc.log
    cover = enc.cover_ac(actor, t)
    if cover is None:
        log.append(f"  {actor.id} has no line of sight to {t.id}")
        return
    dist = min(feet_between(actor.pos, s) for s in t.occupied_squares())
    adv, dis, _, _ = attack_mods(actor, t, "melee" if melee else "ranged", dist)
    if attackers_have_advantage(t):
        adv = True
    if has_attack_disadvantage(actor) or attackers_have_disadvantage(t):  # Blur, etc.
        dis = True
    if not enc.can_see(t, actor):
        adv = True                       # unseen caster (darkness/invisible)
    if not enc.can_see(actor, t):
        dis = True                       # can't clearly see the target
    if actor.md.sunlight_sensitivity and enc.in_sunlight(actor.pos):
        dis = True
    net = 1 if adv and not dis else -1 if dis and not adv else 0
    roll, _ = rng.d20(net)
    total = roll + actor.spell_attack + total_attack_bonus(actor, rng)
    ac = t.ac + cover + total_ac_bonus(t)
    crit = roll == 20
    hit = roll == 20 or (roll != 1 and total >= ac)
    if hit and roll != 20 and total < ac + 5 and enc.try_shield(t):
        hit = False
        ac += 5
    log.append(f"  {actor.id} spell attack vs {t.id}: d20={roll}+{actor.spell_attack}"
               f"={total} vs AC {ac} -> {'HIT' if hit else 'miss'}"
               f"{' CRIT!' if crit and hit else ''}")
    enc.emit(kind="attack", actor=actor.id, info=t.id,   # replay animates the bolt/touch
             dtype="melee" if melee else "ranged", amount=int(hit))
    if hit:
        for d in dmgs:
            amt = d.roll(rng, crit=crit)
            if empower is not None:
                amt = empower(amt)               # Empowered Evocation (+INT to one roll)
            apply_damage(t, enc.absorb(t, d.type, amt), d.type, log, rng, enc=enc, crit=crit)


def _dispel_check(enc, slot: int, spell_level: int, mod: int) -> bool:
    """Dispel Magic auto-succeeds vs spells of level <= the slot used; otherwise the
    caster makes a spellcasting-ability check against DC 10 + the spell's level."""
    if spell_level <= slot:
        return True
    roll, _ = enc.rng.d20(0)
    return roll + mod >= 10 + spell_level


def _dispel_magic(enc, caster: Combatant, t: Combatant, slot: int) -> None:
    """End spell effects on a target: its concentration, spell buffs/debuffs, and
    spell-applied conditions (each subject to the level check)."""
    mod = 0
    if caster.spell_ability is not None:
        mod = caster.spell_mod + caster.prof_bonus
    removed: list[str] = []
    if t.concentration is not None and _dispel_check(enc, slot, t.concentration.level or 1, mod):
        removed.append(t.concentration.spell)
        break_concentration(t, enc.log, "dispelled", enc=enc)
    for e in list(t.effects):
        if e.slot_level > 0 and _dispel_check(enc, slot, e.slot_level, mod):
            removed.append(e.name)
            remove_effect(t, e.name, e.source_id)
    for name, cond in list(t.conditions.items()):
        if cond.spell_level > 0 and _dispel_check(enc, slot, cond.spell_level, mod):
            removed.append(name)
            t.conditions.pop(name, None)
            cleanup_implied(t)
    if removed:
        enc.log.append(f"    Dispel Magic ends on {t.id}: {', '.join(removed)}")
    else:
        enc.log.append(f"    {t.id} has no magic to dispel")


def _push(enc, actor, t, ft: int, toward: bool = False) -> None:
    # away from the actor by default; `toward` pulls the target in (Grasping Spout, Tongue)
    dx, dy = t.pos[0] - actor.pos[0], t.pos[1] - actor.pos[1]
    if toward:
        dx, dy = -dx, -dy
    sx, sy = _sign(dx), _sign(dy)
    if sx == 0 and sy == 0:
        sx = 1
    blocked = enc.blocked_squares(t)
    pos = t.pos
    fell = False
    for _ in range(ft // 5):
        nxt = (pos[0] + sx, pos[1] + sy)
        if not enc.grid.footprint_fits(nxt, t.footprint, blocked):
            break
        pos = nxt
        # shoved over the lip of a chasm: stop here and plummet
        if any(c in enc.grid.chasm for c in enc.grid.footprint_cells(nxt, t.footprint)):
            fell = True
            break
    if pos != t.pos:
        t.pos = pos
        if t.md.fly == 0 and not fell:        # grounded: settle to terrain height
            t.alt = enc.grid.elevation.get(pos, 0)
        enc.log.append(f"    {t.id} is pushed to {pos}")
        if fell:
            enc.apply_fall(t)
        elif t.alive:
            enc._apply_hazard_on_enter(t)     # shoved into lava/grease/acid


def _scaled_damage(sp: Spell, eff, slot: int, actor: Combatant) -> list[Damage]:
    dmgs = list(eff.damage)
    if not dmgs:
        return dmgs
    if sp.level == 0:  # cantrip scaling by CHARACTER level (RAW: 5/11/17 total level, not class level)
        if sp.scaling_mode == "beams":     # Eldritch Blast: scale the beam COUNT, not the dice
            return dmgs
        lvl = actor.md.cantrip_level or actor.caster_level or 1
        tier = 1 + (lvl >= 5) + (lvl >= 11) + (lvl >= 17)
        return [Damage(d.count * tier, d.sides, d.bonus, d.type) for d in dmgs]
    if sp.scaling_mode == "damage" and slot > sp.level:
        extra = slot - sp.level
        c, s, _ = parse_dice(sp.scaling_amount)
        out, merged = [], False
        for d in dmgs:
            if d.sides == s and not merged:           # fold into a matching die
                out.append(Damage(d.count + extra * c, d.sides, d.bonus, d.type))
                merged = True
            else:
                out.append(d)
        if not merged:                                # mismatched die -> add a term
            out.append(Damage(extra * c, s, 0, dmgs[0].type))
        return out
    return dmgs


def _scaled_count(sp: Spell, slot: int, actor: "Combatant | None" = None) -> int:
    base = sp.count
    if sp.level == 0 and sp.scaling_mode == "beams":     # Eldritch Blast: 1/2/3/4 beams by CHARACTER level
        lvl = (actor.md.cantrip_level or actor.caster_level if actor else 0) or 1
        return 1 + (lvl >= 5) + (lvl >= 11) + (lvl >= 17)
    if slot > sp.level and sp.scaling_mode in ("missiles", "rays", "targets"):
        base += (slot - sp.level) * int(sp.scaling_amount)
    return base


def _build_effect(sp: Spell, source_id: str, spec: dict, slot: int = 0) -> ActiveEffect:
    def dice(key):
        if key in spec:
            c, s, b = parse_dice(spec[key])
            return Damage(c, s, b, "")
        return None

    rider = None
    if "damage_rider" in spec:
        e = spec["damage_rider"]
        c, s, b = parse_dice(e["dice"])
        rider = Damage(c, s, b, e["type"])
    return ActiveEffect(
        name=sp.name, source_id=source_id,
        attack_bonus=dice("attack_bonus"), attack_penalty=dice("attack_penalty"),
        save_bonus=dice("save_bonus"), save_penalty=dice("save_penalty"),
        ac_bonus=spec.get("ac_bonus", 0), speed_delta=spec.get("speed_delta", 0),
        attackers_have_advantage=spec.get("attackers_have_advantage", False),
        attackers_have_disadvantage=spec.get("attackers_have_disadvantage", False),
        disadvantage_on_attacks=spec.get("disadvantage_on_attacks", False),
        damage_rider=rider, rider_target_id=spec.get("rider_target_id"),
        duration=None if sp.concentration else (sp.duration_rounds or 1),
        concentration=sp.concentration, slot_level=max(sp.level, slot))
