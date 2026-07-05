"""Event-triggered monster abilities (SPEC §2.2 trigger layer, §15 monster features).

An ability subscribes a handler to a named trigger; the engine fires triggers at
interception points (`would_drop_to_0`, `on_kill`, ...). A stat block opts in via its
`abilities` list (ids registered here). This replaces hard-coding each reactive ability
in the engine: new triggered abilities register a handler instead of editing the core.

Trigger contract
- `would_drop_to_0(enc, owner, ctx)` — ctx {amount, dtype, crit}. Return True (and set
  `owner.hp`) to keep the creature alive; False to let it drop.
- `on_kill(enc, killer, ctx)` — ctx {victim, melee}. Side-effecting; no return.

Forward note: when the declarative ability schema (the next enabler) lands, it will
register handlers through this same registry, so the dispatch path never changes.
"""
from __future__ import annotations

from typing import Callable

from .models import Ability

_REGISTRY: dict[str, dict[str, Callable]] = {}


def on(ability_id: str, trigger: str):
    """Register a handler for an ability id + trigger name."""
    def deco(fn: Callable) -> Callable:
        _REGISTRY.setdefault(ability_id, {})[trigger] = fn
        return fn
    return deco


def handler_for(ability_id: str, trigger: str) -> Callable | None:
    return _REGISTRY.get(ability_id, {}).get(trigger)


# --------------------------------------------------------------------------
# Abilities
# --------------------------------------------------------------------------

@on("undead_fortitude", "would_drop_to_0")
def _undead_fortitude(enc, owner, ctx) -> bool:
    """Zombie: a CON save (DC 5 + damage) leaves it at 1 HP, unless the damage was
    radiant or a critical hit."""
    from .rules import saving_throw
    if ctx["dtype"] == "radiant" or ctx["crit"]:
        return False
    dc = 5 + ctx["amount"]
    if saving_throw(owner, Ability.CON, dc, enc.rng, log=enc.log):
        owner.hp = 1
        enc.log.append(f"  {owner.id} clings to 1 HP (Undead Fortitude, DC {dc})")
        enc.emit(kind="survive", actor=owner.id, hp=1, info="undead_fortitude")
        return True
    return False


@on("relentless_rage", "would_drop_to_0")
def _relentless_rage(enc, owner, ctx) -> bool:
    """Barbarian (L11): while raging, dropping to 0 HP (but not killed outright) lets you make
    a CON save to stay at 1 HP instead. RAW the DC starts at 10 and rises by 5 per use (resetting
    on a rest); we simplify to a flat DC 10 (the escalating DC needs per-rest state — a follow-on)."""
    from .rules import saving_throw
    if not owner.raging:
        return False
    dc = 10
    if saving_throw(owner, Ability.CON, dc, enc.rng, log=enc.log):
        owner.hp = 1
        enc.log.append(f"  {owner.id} refuses to fall (Relentless Rage, DC {dc}) — 1 HP!")
        enc.emit(kind="survive", actor=owner.id, hp=1, info="relentless_rage")
        return True
    return False


@on("misty_escape", "would_drop_to_0")
def _misty_escape(enc, owner, ctx) -> bool:
    """Vampire: on dropping to 0 HP (and not in sunlight or running water), it becomes a
    cloud of mist and drifts away instead of being destroyed. It can only do this once —
    caught at 0 HP already in mist form, it is destroyed."""
    if owner.misted:
        return False
    owner.misted = True
    owner.fled = True          # drifts out of the fight toward its resting place
    owner.hp = 1
    enc.log.append(f"  {owner.id} dissolves into a cloud of mist and escapes destruction!")
    enc.emit(kind="survive", actor=owner.id, hp=1, info="misty_escape")
    return True


@on("aggressive", "on_turn_start")
def _aggressive(enc, owner, ctx) -> None:
    """Orc Aggressive: as a bonus action at the start of its turn, move up to its speed
    toward the nearest foe (so it closes ~twice its speed before attacking)."""
    if not owner.can_move:
        return
    enemy = enc._nearest_living_enemy(owner)
    if enemy is None or enc.dist(owner, enemy) <= 5:
        return
    dest = enc._choose_destination(owner, enemy, "melee", 5)
    if dest != owner.pos:
        enc.log.append(f"  {owner.id} moves aggressively toward {enemy.id}")
        enc._do_move(owner, dest)


@on("rampage", "on_kill")
def _rampage(enc, killer, ctx) -> None:
    """Gnoll: dropping a creature with a melee attack grants a bonus-action bite at the
    nearest foe in reach (uses the turn's bonus action; fires at most once per turn)."""
    if not ctx.get("melee") or killer.bonus_used or not killer.alive:
        return
    bite = killer.md.attacks.get("Bite")
    if bite is None:
        return
    target = enc._nearest_living_enemy(killer)
    if target is None or enc.dist(killer, target) > bite.reach:
        return
    killer.bonus_used = True
    enc.log.append(f"  >> {killer.id} Rampages (bonus Bite)")
    from .rules import resolve_attack
    resolve_attack(killer, target, bite, enc.rng, enc.log,
                   flanking=enc._positional_advantage(killer, target, "melee"), enc=enc)


@on("temp_hp_on_kill", "on_kill")
def _temp_hp_on_kill(enc, killer, ctx) -> None:
    """Fiend/deity-blessed brutes (Imix's / Raxivort's / Sseth's Blessing): dropping an enemy
    to 0 HP grants a gout of temporary hit points. Temp HP is non-stacking — keep the higher
    pool (RAW: 'you gain', which never stacks with an existing temp-HP source)."""
    amt = killer.md.temp_hp_on_kill
    if not killer.alive or amt <= 0:
        return
    if amt > killer.temp_hp:
        killer.temp_hp = amt
        enc.log.append(f"  {killer.id} feeds on the kill (+{amt} temp HP)")


# --------------------------------------------------------------------------
# Built-in reactions (previously hard-coded in the engine). Declared by existing
# stat-block fields rather than the `triggered_abilities` list, but dispatched
# through this same registry so there is one mechanism for all reactive behavior.
# The engine's thin `try_*`/`offer_*` methods provide the iteration; the per-owner
# eligibility + effect lives here.
# --------------------------------------------------------------------------

@on("shield", "incoming_attack")
def _shield(enc, owner, ctx) -> bool:
    """Reaction: cast Shield (+5 AC until the start of the caster's next turn)."""
    from .conditions import can_react
    from .effects import add_effect
    from .models import ActiveEffect
    if not can_react(owner) or enc.is_silenced(owner) or enc.in_antimagic(owner):
        return False                            # Shield is a verbal spell
    if "Shield" not in owner.md.spells or any(e.name == "Shield" for e in owner.effects):
        return False
    slot = enc._lowest_slot(owner, 1)
    if slot is None:
        return False
    owner.slots[slot] -= 1
    owner.reaction_available = False
    add_effect(owner, ActiveEffect(name="Shield", source_id=owner.id, ac_bonus=5, duration=1))
    enc.log.append(f"  >> {owner.id} casts Shield (reaction, +5 AC)")
    return True


@on("parry", "incoming_attack")
def _parry(enc, owner, ctx) -> bool:
    """Reaction: a martial creature parries, adding AC to the triggering melee hit."""
    from .conditions import can_react
    if not can_react(owner) or owner.md.parry <= 0:
        return False
    owner.reaction_available = False
    enc.log.append(f"  >> {owner.id} parries (+{owner.md.parry} AC)")
    return True


@on("counterspell", "on_spell_cast")
def _counterspell(enc, reactor, ctx) -> bool:
    """Reaction: a hostile caster within 60 ft negates a spell of level >= 2."""
    from .conditions import can_react
    from .grid import feet_between
    caster, spell = ctx["caster"], ctx["spell"]
    if not can_react(reactor) or "Counterspell" not in reactor.md.spells:
        return False
    if enc.is_silenced(reactor) or enc.in_antimagic(reactor):
        return False                            # can't cast Counterspell here
    if feet_between(reactor.pos, caster.pos) > 60:
        return False
    slot = enc._lowest_slot(reactor, 3)
    if slot is None:
        return False
    reactor.slots[slot] -= 1
    reactor.reaction_available = False
    enc.log.append(f"  >> {reactor.id} casts Counterspell on {caster.id}'s {spell.name}")
    return True


@on("hellish_rebuke", "on_damaged")
def _hellish_rebuke(enc, reactor, ctx) -> None:
    """On-damage reaction: retaliate at the attacker (DEX save for half)."""
    from . import cast, spells
    from .conditions import can_react
    from .grid import feet_between
    from .models import Ability
    from .rules import apply_damage, saving_throw
    attacker = ctx["attacker"]
    if not (can_react(reactor) and attacker.alive):
        return
    if "Hellish Rebuke" not in reactor.md.spells:
        return
    if enc.is_silenced(reactor) or enc.in_antimagic(reactor):
        return                                  # a verbal spell — blocked here
    if feet_between(reactor.pos, attacker.pos) > 60:
        return
    slot = enc._lowest_slot(reactor, 1)
    if slot is not None:
        reactor.slots[slot] -= 1
    elif (reactor.md.innate.get("Hellish Rebuke", 0)          # Tiefling: innate X/day, no slot
          and reactor.innate_left.get("Hellish Rebuke", 0) > 0):
        reactor.innate_left["Hellish Rebuke"] -= 1
        slot = 1
    else:
        return                                                # no slot and no innate use left
    reactor.reaction_available = False
    sp = spells.get("Hellish Rebuke")
    dmgs = cast._scaled_damage(sp, sp.effects[0], slot, reactor)
    enc.log.append(f"  >> {reactor.id} casts Hellish Rebuke at {attacker.id} (slot {slot})")
    saved = saving_throw(attacker, Ability.DEX, reactor.md.spell_dc, enc.rng, log=enc.log)
    for d in dmgs:
        amt = d.roll(enc.rng)
        if saved:
            amt //= 2
        apply_damage(attacker, amt, d.type, enc.log, enc.rng, enc=enc)


@on("death_burst", "on_death")
def _death_burst(enc, owner, ctx) -> None:
    """On-death AoE (e.g. Magmin). The engine handles chaining across bursts."""
    from .rules import apply_damage, saving_throw
    area = owner.md.death_burst
    enc.log.append(f"  ** {owner.id} bursts: {area.name} **")
    cells = enc._area_cells(owner.pos, owner.pos, area)
    for v in list(enc.combatants.values()):
        if not v.alive or v.id == owner.id:
            continue
        if not any(s in cells for s in v.occupied_squares()):
            continue
        saved = saving_throw(v, area.save, area.dc, enc.rng, log=enc.log)
        for d in area.damage:
            amt = d.roll(enc.rng)
            if saved and area.half_on_save:
                amt //= 2
            apply_damage(v, amt, d.type, enc.log, enc.rng, enc=enc)


def effective_abilities(md) -> set:
    """A creature's triggered-ability ids: explicit ones plus those implied by its
    existing stat fields (so built-in reactions register without re-tagging content)."""
    a = set(md.triggered_abilities)
    if "Shield" in md.spells:
        a.add("shield")
    if "Counterspell" in md.spells:
        a.add("counterspell")
    if "Hellish Rebuke" in md.spells:
        a.add("hellish_rebuke")
    if md.parry:
        a.add("parry")
    if md.death_burst is not None:
        a.add("death_burst")
    return a
