"""Controllers — the decision seam. Each picks one Option among the engine's
enumerated, pre-validated options. Random and Heuristic are fully deterministic
given their seed; the LLM controller (llm.py) is the only nondeterministic one.
"""
from __future__ import annotations

from . import content, spells, tactics
from .dice import RNG
from .engine import Encounter, default_smite_policy
from .grid import chebyshev
from .models import Option
from .rules import damage_multiplier


class RandomController:
    name = "random"

    def __init__(self, seed: int = 0) -> None:
        self.rng = RNG(seed)

    def decide(self, enc: Encounter, actor, options: list[Option]) -> Option:
        active = [o for o in options
                  if o.kind in ("attack", "multiattack", "area", "spell", "advance")]
        pool = active or options
        return pool[self.rng.randint(0, len(pool) - 1)]


class GreedyController:
    """One-ply expected-value argmax: every option is priced with the engine's own
    probability math (tactics.expected_value) and the best is taken, deterministic
    tiebreak toward the weakest target. No hand-written rule ladder — a new ability
    with a rider is valued automatically the day it is imported."""
    name = "greedy"

    def should_smite(self, attacker, target, crit: bool) -> bool:
        return default_smite_policy(attacker, target, crit)

    def decide(self, enc: Encounter, actor, options: list[Option]) -> Option:
        def key(opt: Option):
            t = enc.combatants.get(opt.target_id)
            hp = t.hp if t is not None and t.team != actor.team else 1 << 30
            return (-tactics.expected_value(enc, actor, opt), hp, opt.id)
        return min(options, key=key)


def _target(enc: Encounter, opt: Option):
    return enc.combatants.get(opt.target_id)


def _cluster_score(enc: Encounter, actor, opt: Option) -> int:
    """How many of actor's enemies sit within 10 ft of the option's center."""
    center = _target(enc, opt)
    if center is None:
        return 0
    return sum(1 for e in enc.enemies_of(actor)
               if min(chebyshev(center.pos, s) for s in e.occupied_squares()) <= 2)


def _spell(opt: Option):
    try:
        return spells.get(opt.name)
    except KeyError:
        return None


def _is_ranged_option(actor, opt: Option) -> bool:
    if opt.kind not in ("attack", "multiattack"):
        return False
    from .engine import _action_range, _attacks_for_action
    return _action_range(_attacks_for_action(actor.attacks, actor.multiattack, opt.name))[0] == "ranged"


class HeuristicController:
    """Utility AI. Casters favour AoE on clusters, then best damage spell, then
    healing/buff/control; martials focus-fire the weakest reachable foe."""
    name = "heuristic"

    def should_smite(self, attacker, target, crit: bool) -> bool:
        """Divine Smite spend policy (RAW has no per-turn cap; this is the heuristic's slot
        conservation). Always smite a crit; otherwise smite at most one worthwhile foe (>= 15 HP)
        per turn so slots aren't dumped on a full multiattack of mooks."""
        return default_smite_policy(attacker, target, crit)

    def decide(self, enc: Encounter, actor, options: list[Option]) -> Option:
        spell_opts = [o for o in options if o.kind == "spell"]
        attacks = [o for o in options if o.kind in ("attack", "multiattack")]
        areas = [o for o in options if o.kind == "area"]

        # 0. Swallow a grappled foe whole — strong lockdown + damage over time
        swallow = [o for o in options if o.kind == "swallow"]
        if swallow:
            return swallow[0]

        # 0. Eye Rays — multi-target control + damage, the creature's best action
        eye = [o for o in options if o.kind == "eye_rays"]
        if eye:
            return eye[0]

        # 0. Frightful Presence when it would frighten 2+ not-yet-frightened foes
        frighten = [o for o in options if o.kind == "frighten"]
        if frighten and sum(1 for e in enc.enemies_of(actor)
                            if not e.has("frightened")) >= 2:
            return frighten[0]

        # 0. Turn Undead — rout (or destroy) undead foes; always worth the Channel use
        turn = [o for o in options if o.kind == "turn_undead"]
        if turn:
            return turn[0]

        # 1. emergency heal a badly-wounded ally
        for o in spell_opts:
            sp = _spell(o)
            if sp and any(e.kind == "heal" for e in sp.effects):
                ally = _target(enc, o)
                if ally and ally.hp <= ally.max_hp * 0.4:
                    return o

        # 1a. Life Domain Preserve Life: emergency channel heal for a badly-wounded ally
        preserve = [o for o in options if o.kind == "preserve_life"]
        if preserve and any(a.team == actor.team and a.alive and a.hp <= a.max_hp * 0.4
                            for a in enc.combatants.values()):
            return preserve[0]

        # 1a2. Paladin Lay on Hands: heal a badly-wounded ally in reach (self-heal handled below)
        loh_ally = [o for o in options if o.kind == "lay_on_hands" and o.target_id != actor.id]
        if loh_ally:
            wounded = [o for o in loh_ally
                       if (t := _target(enc, o)) and t.hp <= t.max_hp * 0.4]
            if wounded:
                return min(wounded, key=lambda o: (_target(enc, o).hp, o.target_id or ""))

        # 1b. patch yourself up when badly wounded (Second Wind is a bonus action; a potion
        #     is the action) — prefer the free Second Wind
        if actor.hp <= actor.max_hp * 0.5:
            sw = [o for o in options if o.kind == "second_wind"]
            if sw:
                return sw[0]
        if actor.hp <= actor.max_hp * 0.4:
            quaff = [o for o in options if o.kind == "quaff"]
            if quaff:
                return quaff[0]
            loh = [o for o in options if o.kind == "lay_on_hands"]   # Paladin: spend the pool
            if loh:
                return loh[0]

        # 1b2. Barbarian Rage (bonus action): rage the moment a foe is within striking distance
        rage = [o for o in options if o.kind == "rage"]
        if rage and any(enc.dist(actor, e) <= 10 for e in enc.enemies_of(actor)):
            return rage[0]

        # 1b2b. Druid Wild Shape: a Moon druid shapes up (bear form = HP + attacks) when a foe
        #       is near; pick the beefiest legal form. Non-Moon shaping is left to a direct build.
        ws = [o for o in options if o.kind == "wild_shape"]
        if (ws and actor.base_md is None and actor.md.wild_shape_bonus_action
                and any(enc.dist(actor, e) <= 30 for e in enc.enemies_of(actor))):
            def _form_hp(o: Option) -> int:
                try:
                    return content.get(o.name).hp
                except KeyError:
                    return 0
            return max(ws, key=_form_hp)

        # 1b2c. Circle of the Moon: spend a slot to heal while in beast form when badly hurt
        moon_heal = [o for o in options if o.kind == "moon_heal"]
        if moon_heal and actor.hp <= actor.max_hp * 0.4:
            return moon_heal[0]

        # 1b2d. Bardic Inspiration (bonus action): bank a die on the strongest ally
        inspire = [o for o in options if o.kind == "bardic_inspiration"]
        if inspire:
            return max(inspire, key=lambda o: (getattr(_target(enc, o), "max_hp", 0),
                                               o.target_id or ""))

        # 1b3. Monk Ki: Patient Defense when badly hurt, else Flurry of Blows for extra damage
        if actor.hp <= actor.max_hp * 0.4:
            pd = [o for o in options if o.kind == "patient_defense"]
            if pd:
                return pd[0]
        flurry = [o for o in options if o.kind == "flurry"]
        if flurry:
            return flurry[0]

        # 1b4. Paladin bonus-action Channel Divinity: buff before wading in (Devotion/Vengeance)
        vow = [o for o in options if o.kind == "vow"]
        if vow:
            return max(vow, key=lambda o: (getattr(_target(enc, o), "max_hp", 0),
                                           o.target_id or ""))
        sacred = [o for o in options if o.kind == "sacred_weapon"]
        if sacred:
            return sacred[0]

        # 1b5. Ranger Hunter's Mark: mark a foe (once) if not already concentrating
        if actor.concentration is None:
            hmark = [o for o in options if o.kind == "spell" and o.name == "Hunter's Mark"]
            if hmark:
                return max(hmark, key=lambda o: (getattr(_target(enc, o), "hp", 0),
                                                 o.target_id or ""))

        # 1c. bonus-action extra weapon attack (two-weapon fighting, Eldritch Knight War
        #     Magic, or War Priest): appears in the bonus phase, and striking is almost always right
        offhand = [o for o in options if o.kind in ("offhand", "war_magic", "polearm", "war_priest")]
        if offhand:
            eff = [o for o in offhand if tactics.expected_damage(enc, actor, o) > 0]
            if eff:
                return min(eff, key=lambda o: (_target(enc, o).hp, o.target_id or ""))

        # 1c2. Sorcerer Quickened Spell: spend points to squeeze a damaging cantrip into the bonus
        #      phase (an extra blast after the action). Focus the weakest reachable foe.
        quick = [o for o in options if o.kind == "quicken"
                 and enc.combatants.get(o.target_id) in enc.enemies_of(actor)]
        if quick:
            return min(quick, key=lambda o: (_target(enc, o).hp, o.target_id or ""))

        # 2. best area effect (monster area ability or AoE spell) on a cluster,
        #    scored by total expected damage = foes hit x per-target damage
        best_aoe, best_score = None, 0.0
        for o in areas + spell_opts:
            sp = _spell(o) if o.kind == "spell" else None
            if o.kind == "spell" and (sp is None or sp.target_mode not in
                                      ("point", "self_area")):
                continue
            per = tactics.expected_damage(enc, actor, o)   # immunity-aware
            n = _cluster_score(enc, actor, o)
            if n >= 2 and per > 0 and n * per > best_score:
                best_aoe, best_score = o, n * per
        if best_aoe is not None:
            return best_aoe

        # 2b. a monster area that hard-controls a foe (restrain/paralyze/stun/petrify)
        #     even with no damage — e.g. a basilisk's petrifying gaze. A save-or-drop
        #     rider (Demilich Howl, Banshee Wail) is the hardest control there is.
        hard = {"restrained", "paralyzed", "stunned", "petrified"}
        for o in areas:
            area = next((a for a in actor.md.areas if a.name == o.name), None)
            if area is None or area.rider is None:
                continue
            if area.rider.zero_hp_on_fail:
                return o
            if area.rider.on_fail_condition in hard:
                t = _target(enc, o)
                if t and not any(t.has(c) for c in hard):
                    return o

        # 2c. outline a cluster of foes so the whole team hits them at advantage
        #     (Faerie Fire and similar attackers-have-advantage reveals)
        if actor.concentration is None:
            for o in spell_opts:
                sp = _spell(o)
                if sp and sp.affects == "enemies" and any(
                        (e.modifier_on_fail or {}).get("attackers_have_advantage")
                        or (e.modifier or {}).get("attackers_have_advantage")
                        for e in sp.effects):
                    if _cluster_score(enc, actor, o) >= 2:
                        return o

        # 3. summon allies (if none active yet), then drop a damaging aura
        have_summon = any(c.summoner_id == actor.id and c.alive
                          for c in enc.combatants.values())
        for o in spell_opts:
            sp = _spell(o)
            if sp and any(e.kind == "summon" for e in sp.effects) and not have_summon:
                if not (sp.concentration and actor.concentration is not None):
                    return o
        if actor.concentration is None:
            for o in spell_opts:
                sp = _spell(o)
                if sp and any(e.kind == "aura" for e in sp.effects):
                    dtypes = {d.type for e in sp.effects if e.kind == "aura"
                              for d in e.damage}
                    if dtypes and all(all(damage_multiplier(en, dt) == 0 for dt in dtypes)
                                      for en in enc.enemies_of(actor)):
                        continue          # every foe is immune to this aura's damage
                    return o

        # 3b. blur/mirror-image self-defense when a foe is in melee and not yet up
        if not any(e.name in ("Blur", "Mirror Image") for e in actor.effects):
            for o in spell_opts:
                sp = _spell(o)
                if (sp and sp.affects == "self"
                        and any(e.kind == "modifier"
                                and (e.modifier or {}).get("attackers_have_disadvantage")
                                for e in sp.effects)
                        and any(enc.dist(actor, en) <= 10 for en in enc.enemies_of(actor))):
                    if not (sp.concentration and actor.concentration is not None):
                        return o

        # 4. control a dangerous foe, or buff the party (each uses concentration)
        if actor.concentration is None:
            control = []
            for o in spell_opts:
                sp = _spell(o)
                if sp and sp.concentration and sp.affects == "enemies" \
                        and any(e.condition or e.kind == "banish" for e in sp.effects):
                    t = _target(enc, o)
                    if t and t.max_hp >= 40 and not t.has("paralyzed") and not t.banished:
                        control.append((t.max_hp, o))
            if control:
                control.sort(key=lambda x: (-x[0], x[1].target_id or ""))
                return control[0][1]
            for o in spell_opts:
                sp = _spell(o)
                if sp and sp.concentration and sp.affects == "allies" \
                        and any(e.kind == "modifier" for e in sp.effects):
                    return o

        # 5. highest-damage offensive spell, focused on the weakest foe
        dmg_opts = [(tactics.expected_damage(enc, actor, o), o) for o in spell_opts
                    if (sp := _spell(o)) and sp.affects == "enemies"
                    and sp.target_mode not in ("point", "self_area")]
        dmg_opts = [(d, o) for d, o in dmg_opts if d > 0]   # skip immune targets
        if dmg_opts:
            top = max(d for d, _ in dmg_opts)
            best = [o for d, o in dmg_opts if d == top]
            best.sort(key=lambda o: (getattr(_target(enc, o), "hp", 1 << 30),
                                     o.target_id or ""))
            return best[0]

        # 6. unused AoE damage spell even on a single (non-immune) target
        for o in spell_opts:
            sp = _spell(o)
            if (sp and sp.target_mode in ("point", "self_area")
                    and tactics.expected_damage(enc, actor, o) > 0):
                return o

        # 6a. Enchanter Hypnotic Gaze: incapacitate an adjacent foe (free, no slot)
        gaze = [o for o in options if o.kind == "hypnotic_gaze"]
        if gaze:
            return gaze[0]

        # 6b. Action Surge: spend the extra action to nova when we have a foe we can hurt
        surge = [o for o in options if o.kind == "action_surge"]
        if surge and any(tactics.expected_damage(enc, actor, o) > 0 for o in attacks):
            return surge[0]

        # 6c. lock down a foe with a Web-style restrain attack it isn't already suffering —
        #     restrained is a strong debuff (attackers get advantage; it can't move) and these
        #     attacks are recharge-limited, so this fires as a high-value opener, not every turn
        for o in attacks:
            if o.kind != "attack":
                continue
            atk = actor.md.attacks.get(o.name)
            if atk and atk.rider and atk.rider.on_fail_condition == "restrained":
                t = _target(enc, o)
                if t and not t.has("restrained") and not t.has("grappled"):
                    return o

        # 7. martial: focus-fire the weakest reachable foe we can actually hurt.
        # Flyers prefer a ranged attack so they can strike from altitude (kiting).
        if attacks:
            pool = attacks
            if actor.md.fly > 0:
                ranged = [o for o in attacks if _is_ranged_option(actor, o)]
                if ranged:
                    pool = ranged
            effective = [o for o in pool if tactics.expected_damage(enc, actor, o) > 0]
            if effective:                      # don't swing at foes immune to our damage
                return min(effective, key=lambda o: (_target(enc, o).hp, o.target_id))
        # 7b. an at-will area even on a SINGLE foe: creatures whose whole kit is
        #     area abilities (Hellfire Engine, Eidolon) otherwise stand idle in
        #     one-on-ones — the cluster gate in step 2 never opens for them.
        #     Recharge areas stay held for clusters (step 2's conservatism).
        aoe1 = [(tactics.expected_damage(enc, actor, o), o) for o in areas
                if any(a.name == o.name and a.recharge_min == 0
                       for a in actor.md.areas)]
        aoe1 = [(d, o) for d, o in aoe1 if d > 0]
        if aoe1:
            top = max(d for d, _ in aoe1)
            best = [o for d, o in aoe1 if d == top]
            best.sort(key=lambda o: (getattr(_target(enc, o), "hp", 1 << 30),
                                     o.target_id or ""))
            return best[0]
        # can't attack this turn: escape a grapple, else close the gap (Dash > Advance)
        escape = [o for o in options if o.kind == "escape"]
        if escape:
            return escape[0]
        mover = ([o for o in options if o.kind == "dash"]
                 or [o for o in options if o.kind == "advance"])
        if mover:
            return mover[0]
        ready = [o for o in options if o.kind == "ready"]
        if ready:                          # nowhere to go -> hold an attack
            return ready[0]
        # bonus-action self-teleport: only offered when a foe is out of reach — close in
        teleport = [o for o in options if o.kind == "teleport"]
        if teleport:
            return teleport[0]
        return options[-1]  # dodge in the action phase, or pass in the bonus phase
