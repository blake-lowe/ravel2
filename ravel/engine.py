"""The encounter engine: deterministic combat loop, legal-option enumeration,
movement/positioning, opportunity attacks, and win detection.

The engine computes positioning deterministically. A Controller makes only the
high-level choice (which option + which target) among options the engine
enumerated and validated. That is the single nondeterminism seam.
"""
from __future__ import annotations

from . import cast, skills, spells, triggers
from .events import Event
from .conditions import (can_sense, can_act, can_heal, can_react, cleanup_implied,
                         speed_multiplier)
from .dice import RNG, Damage, parse_dice
from .effects import (add_effect, break_concentration, tick_effects_end_of_turn,
                      total_speed_delta)
from .grid import (BOTTOMLESS, LIGHT_BRIGHT, LIGHT_DIM, Grid, chebyshev, cone_cells,
                   cube_cells, dist3d, feet_between, line_aoe_cells, sphere_cells)
from .models import (SIZE_ORDER, Ability, ActiveEffect, AreaDef, AttackDef, Combatant,
                     MonsterDef, Option, RulesConfig, Size)
from .rules import (apply_condition, apply_damage, area_damage_after_save, contest,
                    resolve_attack, saving_throw, tick_conditions_end_of_turn)

ROUND_CAP = 60
SAFE_ALT = 20.0   # altitude (ft) a flyer climbs to when it can attack at range — out of melee
_POLEARMS = frozenset({"Glaive", "Halberd", "Pike", "Quarterstaff", "Spear"})   # Polearm Master
MORALE_DC = 10    # WIS save when first bloodied; failure routs the creature
MAX_FALL_DICE = 20   # fall damage caps at 20d6 (a 200 ft fall), per the standard rules
ABSORB_TYPES = frozenset(  # Absorb Elements triggers on these damage types
    {"acid", "cold", "fire", "lightning", "thunder"})


# ---------------------------------------------------------------------------


def _roll_hit_points(hit_dice: str, rng: RNG) -> int | None:
    """Roll a creature's HP from its hit-dice formula (e.g. '18d10+90'). Returns None
    when there are no parseable hit dice, so the stat-block average stands."""
    if not hit_dice:
        return None
    try:
        count, sides, bonus = parse_dice(hit_dice)
    except (ValueError, KeyError):
        return None
    if count <= 0 or sides <= 0:
        return None
    return max(1, rng.roll(count, sides, bonus))


def content_cr(name: str) -> float:
    """CR of a registered creature (1e9 if unknown) — used to gate Wild Shape forms by CR cap."""
    from . import content
    try:
        return content.get(name).cr
    except KeyError:
        return 1e9


def default_smite_policy(attacker: Combatant, target: Combatant, crit: bool) -> bool:
    """Fallback Divine Smite spend policy (used by controllers without their own `should_smite`,
    e.g. Random/LLM, and by direct engine calls). Bounded so a paladin doesn't dump every slot:
    always smite a crit (the doubled dice are worth it); otherwise smite at most one worthwhile
    target (>= 15 HP) per turn. RAW imposes no per-turn cap — this is a heuristic, not a rule."""
    if crit:
        return True
    return target.hp >= 15 and attacker.smites_this_turn == 0


def best_melee_attack(attacks: dict) -> AttackDef | None:
    melee = [a for a in attacks.values() if a.kind == "melee"]
    if not melee:
        return None
    return max(melee, key=lambda a: sum(d.average() for d in a.damage))


def _attacks_for_action(attacks: dict, multiattack, name: str) -> list[AttackDef]:
    if name == "multiattack":
        out = []
        for atk_name, count in multiattack:
            if atk_name in attacks:
                out.extend([attacks[atk_name]] * count)
        return out
    return [attacks[name]] if name in attacks else []


def _action_range(attacks: list[AttackDef]) -> tuple[str, int, int]:
    """Return (mode, normal_ft, long_ft). mode in {'melee','ranged'}."""
    melee = [a for a in attacks if a.kind == "melee"]
    if melee:
        return "melee", max(a.reach for a in melee), max(a.reach for a in melee)
    normal = min(a.range_normal for a in attacks)
    long = min(a.range_long or a.range_normal for a in attacks)
    return "ranged", normal, long


class Encounter:
    def __init__(self, grid: Grid, combatants: list[Combatant], rng: RNG,
                 rules: RulesConfig | None = None, roll_hp: bool = True,
                 underwater: bool = False, weather: str = "clear",
                 lair_names: frozenset[str] | set[str] = frozenset()) -> None:
        self.grid = grid
        self._cond_seen: dict[str, str] = {}     # last conditions snapshot per id
        self._cond_syncing = False               # (must precede the first emit)
        self.combatants = {c.id: c for c in combatants}
        for c in combatants:
            c.enc = self                 # back-ref for position-based passive auras (Aura of Protection)
        self.order: list[str] = []
        self.rng = rng
        self.underwater = underwater
        self.weather = weather           # "clear" | "fog" | "rain" | "wind"
        # creature NAMES fighting in their lair (lair actions on; a 5e monster only
        # has lair actions at home, so the default arena bout grants none)
        self.lair_names = frozenset(lair_names)
        if roll_hp:                      # roll each creature's HP from its hit dice
            for c in combatants:
                rolled = _roll_hit_points(c.md.hit_dice, rng)
                if rolled is not None:
                    c.rolled_max_hp = c.hp = rolled
        if underwater:                   # air-breathers start a hold-breath countdown
            for c in combatants:
                if not c.md.water_breathing:
                    cm = c.md.mod(Ability.CON)
                    c.breath_rounds = max(5, (1 + cm) * 10) + max(1, cm)  # hold + choke
        for c in combatants:
            if c.md.false_appearance:    # looks like an object -> ambushes until it acts
                c.hidden = True
        self.rules = rules or RulesConfig()
        self.log: list[str] = []
        self.events: list = []          # typed event stream (SPEC §2.3); see events.py
        self.zones: list = []           # spell-created terrain patches (models.Zone)
        self.lights: list = []          # dynamic light sources (torches, Light spell)
        self.darkness: list = []        # magical-darkness zones: {cells, level} (Darkness)
        self.fog: set = set()           # heavily-obscured cells (Fog Cloud / weather)
        self.round = 0
        self._controllers: dict = {}     # team -> Controller (set by run(); drives the smite policy)
        for c in combatants:
            for area in c.md.areas:
                c.area_ready[area.name] = True
            if c.md.lair_action is not None:
                c.area_ready[c.md.lair_action.name] = True
            c.legendary_resistance_left = c.md.legendary_resistance
            c.legendary_actions_left = c.md.legendary_actions
            if c.md.fly == 0:               # grounded creatures start at terrain height
                c.alt = grid.elevation.get(c.pos, 0)

    # -- queries ----------------------------------------------------------
    def living(self) -> list[Combatant]:
        # "in the fight": alive and not fled off the map
        return [c for c in self.combatants.values() if c.in_combat]

    def teams_alive(self) -> set[str]:
        # untargetable summons (Spiritual Weapon) don't keep a team in the fight
        return {c.team for c in self.living() if not c.untargetable}

    def enemies_of(self, c: Combatant) -> list[Combatant]:
        return [o for o in self.living() if o.team != c.team and not o.untargetable]

    def over(self) -> bool:
        return len(self.teams_alive()) <= 1 or self.round > ROUND_CAP

    def winner(self) -> str | None:
        teams = self.teams_alive()
        if len(teams) == 1:
            return next(iter(teams))
        if len(teams) == 0:
            return None
        # round cap: side with most remaining HP
        totals: dict[str, int] = {}
        for c in self.living():
            totals[c.team] = totals.get(c.team, 0) + c.hp
        return max(totals, key=totals.get) if totals else None

    def _blocked(self, mover: Combatant) -> set[tuple[int, int]]:
        # A swarm can occupy another creature's space, and its own space doesn't block
        # others (they move through it). So swarms neither block nor are blocked by
        # creatures. Walls/chasms still block — those are enforced by the grid, not here.
        if mover.md.swarm:
            return set()
        blocked: set[tuple[int, int]] = set()
        for c in self.combatants.values():
            if c.id == mover.id or not c.in_combat or c.md.swarm:
                continue
            blocked.update(c.occupied_squares())
        return blocked

    # -- initiative -------------------------------------------------------
    def roll_initiative(self) -> None:
        from .models import Ability
        self._spawn_companions()             # Beast Master pets join before initiative is rolled
        tiebreak: dict[str, int] = {}
        for c in self.combatants.values():
            adv = 1 if c.md.feral_instinct else 0        # Barbarian Feral Instinct: advantage
            roll, _ = self.rng.d20(adv)
            # Jack of All Trades (Bard) / Remarkable Athlete (Champion): half proficiency to
            # initiative (a DEX check that isn't otherwise proficient)
            joat = c.md.prof_bonus // 2 if (c.md.jack_of_all_trades or c.md.remarkable_athlete) else 0
            c.initiative = roll + c.md.mod(Ability.DEX) + (5 if c.md.alert else 0) + joat
            if c.md.alert or c.md.feral_instinct:
                c.surprised = False                      # Alert / Feral Instinct: can't be surprised
            tiebreak[c.id] = self.rng.randint(0, 1_000_000)  # fair, seeded tie-break
            if c.md.portent:                             # Diviner: pre-roll the Portent dice
                c.portent_rolls = [self.rng.d20()[0] for _ in range(c.md.portent)]
            if c.md.relentless and c.resources.get("Superiority Dice", 0) == 0:   # Relentless
                c.resources["Superiority Dice"] = 1
        self.order = sorted(
            self.combatants,
            key=lambda i: (self.combatants[i].initiative,
                           self.combatants[i].md.mod(Ability.DEX), tiebreak[i]),
            reverse=True,
        )
        self.log.append("Initiative: " + ", ".join(
            f"{i}={self.combatants[i].initiative}" for i in self.order))
        for c in self.combatants.values():       # seed the event stream (reducer.py)
            self.emit(kind="spawn", actor=c.id, hp=c.hp, pos=c.pos, info=c.team,
                      alt=c.alt)
        for i in self.order:                     # canonical turn order, for the replay —
            self.emit(kind="initiative", actor=i,   # a creature slain before its first
                      amount=self.combatants[i].initiative)  # turn is still on the list

    # -- option enumeration ----------------------------------------------
    # -- 3D distance helpers (altitude-aware) ----------------------------
    def dist(self, a: Combatant, b: Combatant) -> float:
        # nearest squares of BOTH footprints (matters for Large+ creatures)
        return min(dist3d(asq, a.alt, bsq, b.alt)
                   for asq in a.occupied_squares() for bsq in b.occupied_squares())

    def _dist_pos(self, xy, alt: float, b: Combatant) -> float:
        return min(dist3d(xy, alt, s, b.alt) for s in b.occupied_squares())

    def _from_footprint(self, xy, n: int, tgt_squares) -> float:
        """Min horizontal feet between an n-square footprint placed at xy and a target.

        Mirrors `dist`'s footprint awareness so the movement/enumeration layer agrees
        with combat resolution (a Large creature reaches from any of its squares)."""
        return min(feet_between((xy[0] + dx, xy[1] + dy), ts)
                   for dx in range(n) for dy in range(n) for ts in tgt_squares)

    def _enemy_in_melee(self, actor: Combatant) -> bool:
        return any(self.dist(actor, e) <= 5 for e in self.enemies_of(actor))

    def _desired_alt(self, actor: Combatant, mode: str, target: Combatant) -> float:
        """A flyer descends to melee, climbs to a safe altitude to shoot/breathe."""
        if actor.md.fly <= 0 or self.weather == "wind":   # wind grounds nonmagical flyers
            return 0.0
        return target.alt if mode == "melee" else SAFE_ALT

    def reachable_within(self, actor: Combatant, target: Combatant,
                         max_ft: float) -> tuple[bool, float]:
        """Can actor get within max_ft of target this turn (3D)? Returns (ok, min_ft)."""
        tgt_squares = target.occupied_squares()
        # a non-flyer can't close the altitude gap to an airborne target
        alt_gap = 0.0 if actor.md.fly > 0 else abs(target.alt - actor.alt)
        n = actor.footprint

        def d3(horiz: float) -> float:
            return (horiz * horiz + alt_gap * alt_gap) ** 0.5

        cur = d3(self._from_footprint(actor.pos, n, tgt_squares))
        if cur <= max_ft:
            return True, cur
        if not actor.can_move:
            return False, cur
        budget = self._move_budget(actor)
        reach = self.grid.reachable(actor.pos, n, budget, self._blocked(actor),
                                    **self._reach_kwargs(actor))
        best = cur
        for sq in reach:
            d = d3(self._from_footprint(sq, n, tgt_squares))
            best = min(best, d)
            if d <= max_ft:
                return True, d
        return False, best

    def _move_budget(self, actor: Combatant) -> float:
        """Movement budget in FEET this turn."""
        if actor.movement_halted:        # Sentinel OA reduced this creature's speed to 0
            return 0.0
        mult = speed_multiplier(actor)   # exhaustion / immobilising conditions
        if mult == 0:
            return 0.0
        best_mode = max(actor.md.speed, actor.md.fly, actor.md.burrow, actor.md.climb,
                        actor.md.teleport)
        speed = max(0, best_mode + total_speed_delta(actor)) * mult
        budget = speed
        if actor.dashing:
            budget += speed          # Dash adds your speed (so prone+Dash ~ 1.5x)
        if actor.has("prone"):
            budget -= speed / 2      # standing costs half your speed
        return max(0.0, budget)

    def _cover_ac(self, attacker: Combatant, target: Combatant) -> int | None:
        """Cover AC bonus along the best sightline; None = total cover / no LoS."""
        blockers: set[tuple[int, int]] = set()
        for c in self.combatants.values():
            if c.id in (attacker.id, target.id) or not c.alive:
                continue
            blockers.update(c.occupied_squares())
        return self.grid.cover_bonus(attacker.pos, target.occupied_squares(), blockers)

    # public seam for the casting layer (avoids reaching into private methods) ---
    def cover_ac(self, attacker: Combatant, target: Combatant) -> int | None:
        return self._cover_ac(attacker, target)

    def choose_destination(self, actor, target, mode: str, normal: int):
        return self._choose_destination(actor, target, mode, normal)

    def move_to(self, actor: Combatant, dest: tuple[int, int]) -> None:
        self._do_move(actor, dest)

    def _reach_kwargs(self, actor: Combatant) -> dict:
        """The one cost model for this actor's movement — destination selection
        (`grid.reachable`) and route extraction (`grid.path_to`) must always agree."""
        return dict(
            ignore_difficult=actor.md.fly > 0 or actor.md.burrow > 0 or actor.md.teleport > 0,
            extra_difficult=self.dynamic_difficult(actor),
            can_fly=actor.md.fly > 0,
            can_climb=actor.md.climb > 0 or actor.md.fly > 0,
            can_burrow=actor.md.burrow > 0,
            can_phase=actor.md.incorporeal or actor.md.teleport > 0)

    def _move_path(self, actor: Combatant, dest: tuple[int, int]) -> list[tuple[int, int]]:
        """The route _do_move actually walks (same cost model that chose dest).
        Falls back to the straight hop when dest lies outside the budget surface
        (defensive: shove landings, scripted repositioning)."""
        path = self.grid.path_to(actor.pos, dest, actor.footprint,
                                 self._move_budget(actor), self._blocked(actor),
                                 **self._reach_kwargs(actor))
        return path if len(path) >= 2 else [actor.pos, dest]

    def blocked_squares(self, mover: Combatant) -> set[tuple[int, int]]:
        return self._blocked(mover)

    # -- reactions --------------------------------------------------------
    @staticmethod
    def _lowest_slot(c: Combatant, minimum: int) -> int | None:
        return next((lvl for lvl in range(minimum, 10) if c.slots.get(lvl, 0) > 0), None)

    # Built-in reactions now live as handlers in triggers.py; these methods are the
    # engine-side dispatch (iteration + reaction windows) into that one registry.
    def try_shield(self, target: Combatant) -> bool:
        """Reaction: cast Shield (+5 AC until start of next turn). Returns success."""
        if target.armor_penalty:
            return False                     # can't cast in armor you're not proficient with
        h = triggers.handler_for("shield", "incoming_attack")
        return bool(h and h(self, target, {}))

    def try_parry(self, target: Combatant) -> bool:
        """Reaction: a martial monster parries to add AC to the triggering attack."""
        h = triggers.handler_for("parry", "incoming_attack")
        return bool(h and h(self, target, {}))

    def battle_master_maneuver(self, attacker: Combatant, target: Combatant, crit: bool) -> int:
        """A Battle Master maneuver triggered on a weapon hit: spend a superiority die for
        bonus damage (returned, doubled on a crit) and a rider — Trip Attack (STR save or
        prone) on a standing Large-or-smaller foe, else Menacing Attack (WIS save or
        frightened). RAW allows one maneuver per *attack*; we cap it at one per *turn*
        (`maneuver_used`) as a deliberate AI policy so the dice last across the fight."""
        if (attacker.md.superiority_die == 0 or attacker.maneuver_used
                or attacker.resources.get("Superiority Dice", 0) <= 0):
            return 0
        attacker.maneuver_used = True
        attacker.resources["Superiority Dice"] -= 1
        die = self.rng.roll(2 if crit else 1, attacker.md.superiority_die)   # a crit doubles the die
        dc = attacker.md.maneuver_dc
        m = attacker.md.maneuvers or frozenset({"Trip", "Menacing"})
        # a second foe adjacent to the target -> Sweeping Attack (die damage to it, no roll)
        adj = [e for e in self.enemies_of(attacker)
               if e.id != target.id and self.dist(e, target) <= 5]
        can_trip = not target.has("prone") and SIZE_ORDER[target.md.size] <= SIZE_ORDER[Size.LARGE]
        if "Sweeping" in m and adj:               # Sweeping Attack
            other = adj[0]
            self.log.append(f"  >> {attacker.id} Sweeping Attack also hits {other.id} (+{die})")
            apply_damage(other, die, "slashing", self.log, self.rng, enc=self)
        elif "Pushing" in m and not can_trip and not adj:   # Pushing Attack (when Trip won't land)
            if not saving_throw(target, Ability.STR, dc, self.rng, log=self.log):
                from . import cast as _cast
                _cast._push(self, attacker, target, 15)
                self.log.append(f"  >> {attacker.id} Pushing Attack: shoves {target.id} (+{die})")
            else:
                self.log.append(f"  >> {attacker.id} Pushing Attack (+{die}, saved)")
        elif can_trip and "Trip" in m:            # Trip Attack
            if not saving_throw(target, Ability.STR, dc, self.rng, log=self.log):
                apply_condition(target, "prone", attacker.id, self.rng, self.log)
                self.log.append(f"  >> {attacker.id} Trip Attack: {target.id} prone (+{die})")
            else:
                self.log.append(f"  >> {attacker.id} Trip Attack (+{die}, saved)")
        else:                                     # Menacing Attack
            if not saving_throw(target, Ability.WIS, dc, self.rng, log=self.log):
                apply_condition(target, "frightened", attacker.id, self.rng, self.log, duration=1)
                self.log.append(f"  >> {attacker.id} Menacing Attack: {target.id} frightened (+{die})")
            else:
                self.log.append(f"  >> {attacker.id} Menacing Attack (+{die}, saved)")
        return die

    def battle_master_precision(self, attacker: Combatant, shortfall: int) -> int:
        """Precision Attack: on a near-miss, spend a die to add to the attack roll. Returns the
        bonus if it turns the miss into a hit (only spent when it would)."""
        if ("Precision" not in attacker.md.maneuvers or attacker.maneuver_used
                or attacker.resources.get("Superiority Dice", 0) <= 0):
            return 0
        if 1 <= shortfall <= attacker.md.superiority_die:      # a die could cover the gap
            attacker.maneuver_used = True
            attacker.resources["Superiority Dice"] -= 1
            bonus = self.rng.roll(1, attacker.md.superiority_die)
            self.log.append(f"  >> {attacker.id} Precision Attack (+{bonus} to the roll)")
            return bonus
        return 0

    def cleric_guided_strike(self, attacker: Combatant, shortfall: int) -> int:
        """War Domain Channel Divinity: Guided Strike — spend a Channel Divinity use to add +10
        to a would-miss attack. Returns 10 only when that turns the miss into a hit."""
        if (not attacker.md.guided_strike
                or attacker.resources.get("Channel Divinity", 0) <= 0):
            return 0
        if 1 <= shortfall <= 10:
            attacker.resources["Channel Divinity"] -= 1
            self.log.append(f"  >> {attacker.id} Guided Strike (+10 to the attack)")
            return 10
        return 0

    def paladin_divine_smite(self, attacker: Combatant, target: Combatant, crit: bool) -> int:
        """Paladin Divine Smite: on a melee hit, spend the highest available slot (capped at 5th)
        for 2d8 + 1d8 per slot level above 1st (max 5d8), +1d8 vs an undead or fiend; a crit
        doubles the dice. Returns the rolled radiant damage (0 if not spent).

        RAW (2014) places NO once-per-turn cap on Divine Smite. The *spend policy* (which hits are
        worth a slot, so a paladin doesn't dump every slot instantly) lives in the controller
        (`HeuristicController.should_smite`); the engine falls back to `default_smite_policy` for
        controllers that don't define one. The engine only enforces slot availability here."""
        if not attacker.md.divine_smite:
            return 0
        slot = next((lvl for lvl in range(5, 0, -1) if attacker.slots.get(lvl, 0) > 0), None)
        if slot is None:
            return 0
        ctrl = self._controllers.get(attacker.team)
        policy = getattr(ctrl, "should_smite", None) or default_smite_policy
        if not policy(attacker, target, crit):
            return 0
        if not crit:
            attacker.smites_this_turn += 1                # bounded: policy limits non-crit smites/turn
        attacker.slots[slot] -= 1
        dice = min(2 + (slot - 1), 5)                     # 2d8 at 1st, +1d8/level, capped at 5d8
        if target.md.mtype in ("undead", "fiend"):
            dice += 1                                     # +1d8 vs undead/fiend
        dice *= 2 if crit else 1
        dmg = self.rng.roll(dice, 8)
        self.log.append(f"  >> {attacker.id} Divine Smite (slot {slot}: {dice}d8 radiant) vs {target.id}")
        return dmg

    def cleric_war_gods_blessing(self, attacker: Combatant, shortfall: int) -> int:
        """War Domain L6 — War God's Blessing: when an ally within 30 ft would miss, a War Priest
        can spend a Channel Divinity use (as a reaction) to grant +10. Returns 10 if applied."""
        if not (1 <= shortfall <= 10):
            return 0
        for p in self.combatants.values():
            if (p.id != attacker.id and p.md.war_gods_blessing and p.team == attacker.team
                    and can_react(p) and p.resources.get("Channel Divinity", 0) > 0
                    and self.dist(p, attacker) <= 30 and self.can_see(p, attacker)):
                p.resources["Channel Divinity"] -= 1
                p.reaction_available = False
                self.log.append(f"  >> {p.id} War God's Blessing (+10 to {attacker.id}'s attack)")
                return 10
        return 0

    def try_illusory_self(self, target: Combatant) -> bool:
        """Illusionist Illusory Self reaction: interpose an illusion so an attack misses
        (once per short rest)."""
        if (not target.md.illusory_self or target.resources.get("Illusory Self", 0) <= 0
                or not can_react(target)):
            return False
        target.resources["Illusory Self"] -= 1
        target.reaction_available = False
        self.log.append(f"  >> {target.id} uses Illusory Self — the attack misses")
        return True

    def bard_cutting_words(self, attacker: Combatant, target: Combatant, margin: int) -> int:
        """College of Lore Cutting Words: when an enemy makes an attack roll, a Lore bard within
        60 ft (that can see it) may spend a Bardic Inspiration die + its reaction to subtract the
        die from the roll. `margin` is (attack total - AC); only spent when a die could turn the
        hit into a miss (deterministic, conservative). Returns the die subtracted (0 if none)."""
        for bard in self.living():
            if bard.team != target.team or bard.md.cutting_words <= 0:
                continue
            if not can_react(bard) or bard.resources.get("Bardic Inspiration", 0) <= 0:
                continue
            if self.dist(bard, attacker) > 60 or not self.can_see(bard, attacker):
                continue
            if not (0 <= margin < bard.md.cutting_words):    # a die could only just cover the gap
                continue
            bard.resources["Bardic Inspiration"] -= 1
            bard.reaction_available = False
            die = self.rng.roll(1, bard.md.cutting_words)
            self.log.append(f"  >> {bard.id} Cutting Words: -{die} to {attacker.id}'s attack")
            return die
        return 0

    def try_entropic_ward(self, target: Combatant) -> int:
        """Great Old One Entropic Ward: reaction (1/short rest) to impose disadvantage on an
        attack roll aimed at the warlock. Returns a second d20 (the disadvantage die) if spent,
        else 0 — the caller keeps the lower of the two rolls."""
        if (not target.md.entropic_ward or target.resources.get("Entropic Ward", 0) <= 0
                or not can_react(target)):
            return 0
        target.resources["Entropic Ward"] -= 1
        target.reaction_available = False
        return self.rng.d20()[0]

    def _do_hypnotic_gaze(self, actor: Combatant, target: Combatant) -> None:
        """Enchanter Hypnotic Gaze: an adjacent foe makes a WIS save or is charmed and
        incapacitated until the end of the enchanter's next turn."""
        if target is None:
            return
        if saving_throw(target, Ability.WIS, actor.md.spell_dc, self.rng, log=self.log,
                        vs_magic=True):
            self.log.append(f"  {actor.id} Hypnotic Gaze: {target.id} resists")
        else:
            apply_condition(target, "charmed", actor.id, self.rng, self.log, duration=1)
            apply_condition(target, "incapacitated", actor.id, self.rng, self.log, duration=1)
            self.log.append(f"  {actor.id} Hypnotic Gaze: {target.id} charmed & incapacitated")

    def sentinel_reaction(self, attacker: Combatant, target: Combatant) -> bool:
        """Sentinel: when a foe within 5 ft attacks one of your allies, you use your reaction to
        make a melee attack against that foe."""
        for ally in self.living():
            if ally.team != target.team or ally.id in (target.id, attacker.id):
                continue
            if not ally.md.sentinel or not can_react(ally) or self.dist(ally, attacker) > 5:
                continue
            atk = best_melee_attack(ally.attacks)
            if atk is None or self.dist(ally, attacker) > atk.reach:
                continue
            ally.reaction_available = False
            self.log.append(f"  >> {ally.id} (Sentinel) strikes {attacker.id}")
            resolve_attack(ally, attacker, atk, self.rng, self.log,
                           flanking=self._positional_advantage(ally, attacker, "melee"),
                           enc=self, reckless_ok=False, is_reaction=True)
            return True
        return False

    def protection_reaction(self, attacker: Combatant, target: Combatant) -> bool:
        """Fighting Style: Protection — an ally wielding a shield within 5 ft of the target
        spends its reaction to impose disadvantage on an attack it can see."""
        for ally in self.living():
            if ally.team != target.team or ally.id == target.id:
                continue
            eq = ally.equipment
            if eq is None or getattr(eq, "fighting_style", "") != "Protection" or not eq.shield:
                continue
            if not can_react(ally) or self.dist(ally, target) > 5 or not self.can_see(ally, attacker):
                continue
            ally.reaction_available = False
            self.log.append(f"  >> {ally.id} uses Protection to defend {target.id} (disadvantage)")
            return True
        return False

    def offer_counterspell(self, caster: Combatant, spell) -> bool:
        """Reaction: a hostile caster within 60 ft negates a spell of level >= 2."""
        if spell.level < 2:
            return False
        h = triggers.handler_for("counterspell", "on_spell_cast")
        for r in self.living():
            if r.team == caster.team or r.armor_penalty:   # can't cast in non-proficient armor
                continue
            if h and h(self, r, {"caster": caster, "spell": spell}):
                return True
        return False

    def offer_hellish_rebuke(self, reactor: Combatant, attacker: Combatant) -> None:
        """On-damage reaction: retaliate at the attacker (DEX save, half)."""
        if reactor.armor_penalty:
            return                           # can't cast in armor you're not proficient with
        h = triggers.handler_for("hellish_rebuke", "on_damaged")
        if h:
            h(self, reactor, {"attacker": attacker})

    # -- auras ------------------------------------------------------------
    def aura_cells(self, owner: Combatant) -> set[tuple[int, int]]:
        a = owner.aura
        origin = owner.pos if a.anchor == "caster" else a.point
        if a.shape == "cube":
            return cube_cells(origin, a.size, self.grid)
        return sphere_cells(origin, a.size, self.grid)

    def dynamic_difficult(self, mover: Combatant) -> set[tuple[int, int]]:
        cells: set[tuple[int, int]] = set()
        for owner in self.living():
            a = owner.aura
            if a is not None and a.difficult_terrain and owner.team != mover.team:
                cells |= self.aura_cells(owner)
        # water is difficult terrain unless the mover swims or flies (uses swim speed)
        if self.grid.water and not (mover.md.swim > 0 or mover.md.fly > 0):
            cells |= self.grid.water
        # fully underwater: a creature without a swim speed slogs (whole map is difficult)
        if self.underwater and mover.md.swim == 0:
            cells |= {(x, y) for x in range(self.grid.width)
                      for y in range(self.grid.height)}
        for z in self._terrain_zones():          # spell terrain + map hazards
            # difficult (grease/ice/spike) or a damaging hazard (lava/acid) the AI should
            # route around when it can — but it still takes damage if forced across
            if z.difficult or (z.on_enter and z.damage):
                cells |= z.cells
        return cells

    def _terrain_zones(self):
        """All active damaging/difficult terrain: static map hazards + spell zones."""
        return list(self.grid.hazards) + list(self.zones)

    def _douse_flames(self) -> None:
        """Rain/wind put out open flames — spell fires (Wall of Fire) and burning ground,
        but not lava (molten rock)."""
        for z in list(self.zones):
            if z.name != "lava" and any(d.type == "fire" for d in z.damage):
                self.zones.remove(z)
                self.log.append(f"  the {z.name} is extinguished by the {self.weather}")
        for z in self.grid.hazards:
            if z.name.startswith("burning"):
                z.damage, z.light, z.on_enter = (), 0, False

    def _spread_fire(self) -> None:
        """Flammable terrain (grease) that touches a fire source ignites into fire."""
        fire_cells = set()
        for z in self._terrain_zones():
            if z.light or any(d.type == "fire" for d in z.damage):
                fire_cells |= z.cells
        near_fire = {(c[0] + dx, c[1] + dy) for c in fire_cells   # fire spreads to touching cells
                     for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        from .dice import Damage
        for z in self._terrain_zones():
            if z.flammable and z.cells & near_fire:
                z.flammable = False
                z.name = f"burning {z.name}"
                z.damage = (Damage(1, 6, 0, "fire"),)
                z.on_enter = True
                z.light = 20
                self.log.append(f"  the {z.name} catches fire!")

    # -- lighting & vision (ENVIRONMENT.md §1) ----------------------------
    def _light_origin(self, lg):
        if lg.carrier_id is not None:
            c = self.combatants.get(lg.carrier_id)
            return c.pos if (c is not None and c.in_combat) else None
        return lg.origin

    def _light_reaches(self, origin, cell) -> bool:
        """A light illuminates a cell only with clear line of sight (walls cast shadows)."""
        return not any(c in self.grid.walls for c in self.grid.line_cells(origin, cell))

    def light_at(self, cell) -> float:
        """Raw light level at a cell: ambient + inverse-square from every source in sight."""
        for dk in self.darkness:                 # magical darkness clamps to dark
            if cell in dk["cells"]:
                return 0.0
        level = self.grid.ambient
        douse = self.weather in ("rain", "wind")     # weather blows out / soaks open flames
        for lg in list(self.grid.lights) + list(self.lights):
            if douse and not lg.magical:
                continue                             # torches/braziers are extinguished
            origin = self._light_origin(lg)
            if origin is None or not self._light_reaches(origin, cell):
                continue
            d = feet_between(cell, origin)
            level += (lg.bright_radius ** 2) / max(d, 2.5) ** 2
        for z in self._terrain_zones():          # lava/fire glow lights its own cells
            if z.light and cell in z.cells:
                level = max(level, LIGHT_BRIGHT)
        return level

    def light_level(self, cell) -> str:
        L = self.light_at(cell)
        return "bright" if L >= LIGHT_BRIGHT else "dim" if L >= LIGHT_DIM else "dark"

    def _magical_dark(self, cell) -> bool:
        return any(cell in dk["cells"] for dk in self.darkness)

    def in_sunlight(self, cell) -> bool:
        """Is this cell lit by natural sunlight (for Sunlight Sensitivity / vampires)?"""
        if self._magical_dark(cell):
            return False
        if self.grid.ambient_sunlight and self.grid.ambient >= LIGHT_BRIGHT:
            return True
        for lg in list(self.grid.lights) + list(self.lights):
            if not lg.sunlight:
                continue
            o = self._light_origin(lg)
            if o is not None and self._light_reaches(o, cell) and self.light_level(cell) == "bright":
                return True
        return False

    def can_see(self, observer: Combatant, target: Combatant) -> bool:
        """Can `observer` see `target`, given light, obscurement, senses and invisibility?
        (Wall line-of-sight is handled separately by cover.) Default-bright maps => always
        True for visible creatures, so existing battles are unaffected."""
        d = self.dist(observer, target)
        senses = observer.md.senses
        # blindsight / tremorsense / truesight perceive without sight (and see the invisible)
        if any(senses.get(s, 0) >= d for s in ("blindsight", "tremorsense", "truesight")):
            return True
        if target.has("invisible") or target.hidden:
            return False
        if self.weather == "fog" or any(s in self.fog for s in target.occupied_squares()):
            return False                     # heavily obscured (fog) — sight can't penetrate
        if self.light_level(target.pos) in ("bright", "dim"):
            return True
        # target is in darkness. Devil's Sight pierces magical & nonmagical darkness (120 ft);
        # darkvision sees only nonmagical darkness (as dim) within range.
        if observer.md.devils_sight and d <= 120:
            return True
        if self._magical_dark(target.pos):
            return False
        return senses.get("darkvision", 0) >= d

    def _apply_zones_start_of_turn(self, actor: Combatant) -> None:
        """A creature that starts its turn in a damaging zone/hazard is hit."""
        for z in self._terrain_zones():
            if not z.damage or not any(s in z.cells for s in actor.occupied_squares()):
                continue
            self._zone_damage(actor, z)
            if not actor.alive:
                return

    def _zone_damage(self, actor: Combatant, z) -> None:
        saved = z.save is not None and saving_throw(actor, z.save, z.dc, self.rng,
                                                    log=self.log)
        self.log.append(f"  {actor.id} is in {z.name}"
                        + (f" ({z.save.value} save)" if z.save else ""))
        for d in z.damage:
            amt = area_damage_after_save(actor, z.save, saved, z.half_on_save,
                                         d.roll(self.rng))          # Evasion-aware
            apply_damage(actor, amt, d.type, self.log, self.rng, enc=self)

    def _apply_hazards_along(self, actor: Combatant, path: list[tuple[int, int]]) -> None:
        """On-enter hazards for every square the walked route touches — crossing lava
        burns even when the move ends outside it. Each zone fires at most once per
        move. A creature flying above the ground clears ground hazards entirely."""
        if actor.md.fly > 0 and actor.alt > self.grid.elevation.get(actor.pos, 0):
            return
        stepped = {c for p in path[1:]
                   for c in self.grid.footprint_cells(p, actor.footprint)}
        for z in self._terrain_zones():
            if not (stepped & set(z.cells)):
                continue
            if z.prone_save and not actor.has("prone"):
                if not saving_throw(actor, Ability.DEX, z.prone_save, self.rng, log=self.log):
                    apply_condition(actor, "prone", actor.id, self.rng, self.log)
                    self.log.append(f"  {actor.id} slips in {z.name} and falls prone")
            if z.on_enter and z.damage:
                self._zone_damage(actor, z)
            if not actor.alive:
                return

    def _apply_hazard_on_enter(self, actor: Combatant) -> None:
        """A creature that ENTERS a hazard takes on-enter damage and/or a prone save."""
        for z in self._terrain_zones():
            if not any(s in z.cells for s in actor.occupied_squares()):
                continue
            if z.prone_save and not actor.has("prone"):
                if not saving_throw(actor, Ability.DEX, z.prone_save, self.rng, log=self.log):
                    apply_condition(actor, "prone", actor.id, self.rng, self.log)
                    self.log.append(f"  {actor.id} slips in {z.name} and falls prone")
            if z.on_enter and z.damage:
                self._zone_damage(actor, z)
            if not actor.alive:
                return

    def _apply_aura_to(self, owner: Combatant, victim: Combatant) -> None:
        """Apply one aura's save+damage to a victim, at most once per its turn."""
        if owner.id in victim.auras_taken_this_turn:
            return
        a = owner.aura
        if a.silence or a.antimagic or self.in_antimagic(victim):
            return                              # control zones deal no damage; antimagic suppresses
        victim.auras_taken_this_turn.add(owner.id)
        saved = saving_throw(victim, a.save, a.dc, self.rng, vs_magic=True)
        self.log.append(f"  {victim.id} in {owner.id}'s {a.spell}: "
                        f"{a.save.value} save {'success' if saved else 'FAIL'}")
        for d in a.damage:
            amt = area_damage_after_save(victim, a.save, saved, a.half_on_save,
                                         d.roll(self.rng))          # Evasion-aware
            apply_damage(victim, amt, d.type, self.log, self.rng, enc=self)

    def _aura_owners_covering(self, victim: Combatant):
        for owner in self.living():
            a = owner.aura
            if a is None or owner.team == victim.team or owner.id == victim.id:
                continue
            if any(s in self.aura_cells(owner) for s in victim.occupied_squares()):
                yield owner

    def _apply_auras_start_of_turn(self, actor: Combatant) -> None:
        for owner in self._aura_owners_covering(actor):
            self._apply_aura_to(owner, actor)
            if not actor.alive:
                return

    # -- magical zones: Silence & Antimagic Field -------------------------
    def _zone_covers(self, flag: str, c: Combatant) -> bool:
        """Is c inside any active zone aura flagged `flag` (silence/antimagic)?
        Zones are non-partisan — they affect friend and foe alike."""
        for owner in self.combatants.values():
            a = owner.aura
            if not (owner.in_combat and a is not None and getattr(a, flag, False)):
                continue
            if any(s in self.aura_cells(owner) for s in c.occupied_squares()):
                return True
        return False

    def is_silenced(self, c: Combatant) -> bool:
        """In a Silence zone: no spell with a verbal component can be cast."""
        return self._zone_covers("silence", c)

    def in_antimagic(self, c: Combatant) -> bool:
        """In an Antimagic Field: cannot cast, and spells have no effect here."""
        return self._zone_covers("antimagic", c)

    def cannot_cast(self, actor: Combatant, sp) -> bool:
        """Whether `actor` is barred from casting `sp` right now by a magical zone."""
        if self.in_antimagic(actor):
            return True
        return self.is_silenced(actor) and cast.requires_verbal(sp)

    # -- flight enforcement: a non-hovering flyer falls when it can't stay aloft
    def enforce_flight(self, c: Combatant) -> None:
        if c.md.fly == 0 or c.alt <= 0:
            return
        if self.weather == "wind":              # strong wind: nonmagical flyers must land
            c.alt = 0.0
            self.log.append(f"  {c.id} is forced to land by the wind")
            self.emit(kind="move", actor=c.id, pos=c.pos, alt=c.alt)  # replay: altitude drop
            return
        if c.md.hover:
            return
        # PHB flying movement: a non-hovering flyer falls if knocked prone, reduced to
        # speed 0, or otherwise deprived of movement (grappled/restrained/incapacitated).
        if c.alive and c.can_move and not c.has("prone"):
            return                              # still able to keep itself airborne
        fallen = int(c.alt)
        c.alt = 0.0
        self.emit(kind="move", actor=c.id, pos=c.pos, alt=c.alt)      # replay: altitude drop
        if c.alive and fallen >= 10:
            self.log.append(f"  {c.id} can't stay aloft and falls {fallen} ft!")
            dice = min(fallen // 10, MAX_FALL_DICE)
            apply_damage(c, self.rng.roll(dice, 6), "bludgeoning", self.log, self.rng, enc=self)
            if c.alive:
                apply_condition(c, "prone", c.id, self.rng, self.log)

    # -- Absorb Elements reaction -----------------------------------------
    def offer_absorb_elements(self, target: Combatant, dtype: str) -> bool:
        """Reaction: resist one instance of acid/cold/fire/lightning/thunder and store
        a +1d6 rider for the reactor's next melee hit. Returns True if cast."""
        if dtype not in ABSORB_TYPES or not can_react(target):
            return False
        if "Absorb Elements" not in target.md.spells or target.armor_penalty:
            return False                        # unknown, or can't cast in non-proficient armor
        if self.in_antimagic(target):
            return False                        # somatic-only, so Silence doesn't block it
        slot = self._lowest_slot(target, 1)
        if slot is None:
            return False
        target.slots[slot] -= 1
        target.reaction_available = False
        target.absorb_rider = Damage(1, 6, 0, dtype)
        self.log.append(f"  >> {target.id} casts Absorb Elements (reaction, resist {dtype})")
        return True

    # -- event stream & triggered abilities (SPEC §2.2/2.3) ---------------
    def emit(self, **kw) -> None:
        """Append a typed event to the stream (coexists with the prose log for now).

        Every event is stamped with the current round and the prose-log position at
        emit time, so a replay UI can scrub the grid and the combat log in sync."""
        kw.setdefault("round", self.round)
        kw.setdefault("log_index", len(self.log))
        self.events.append(Event(**kw))
        self._sync_condition_events()

    def _sync_condition_events(self) -> None:
        """Emit a `conditions` SNAPSHOT (comma-joined, sorted) for any combatant
        whose condition set changed since the last event. Conditions are mutated
        at a dozen scattered sites; sweeping at the emit choke point turns them
        into last-write-wins snapshot events the replay can fold at any prefix
        (at most one event of lag, which the dense stream makes invisible)."""
        if self._cond_syncing:
            return
        self._cond_syncing = True
        try:
            for c in self.combatants.values():
                cur = ",".join(sorted(c.conditions))
                if cur != self._cond_seen.get(c.id, ""):
                    self._cond_seen[c.id] = cur
                    self.events.append(Event(kind="conditions", actor=c.id, info=cur,
                                             round=self.round,
                                             log_index=len(self.log)))
        finally:
            self._cond_syncing = False

    def survive_check(self, target: Combatant, amount: int, dtype: str,
                      crit: bool) -> bool:
        """Fire `would_drop_to_0` abilities; return True if one kept the target alive
        (the handler sets its HP). Called from the damage path before a creature drops."""
        for aid in target.md.triggered_abilities:
            h = triggers.handler_for(aid, "would_drop_to_0")
            if h and h(self, target, {"amount": amount, "dtype": dtype, "crit": crit}):
                return True
        return False

    def fire_on_kill(self, killer: Combatant, victim: Combatant, melee: bool) -> None:
        """Fire the killer's `on_kill` abilities (e.g. Gnoll Rampage)."""
        for aid in killer.md.triggered_abilities:
            h = triggers.handler_for(aid, "on_kill")
            if h:
                h(self, killer, {"victim": victim.id, "melee": melee})

    def fire_turn(self, actor: Combatant, when: str) -> None:
        """Fire `on_turn_start` / `on_turn_end` abilities (e.g. Orc Aggressive)."""
        for aid in triggers.effective_abilities(actor.md):
            h = triggers.handler_for(aid, when)
            if h:
                h(self, actor, {})

    def absorb(self, target: Combatant, dtype: str, amount: int) -> int:
        """Offer Absorb Elements against an elemental instance; halve it if taken.
        Called once per Damage entry; the reaction guard prevents double-spend, so a
        spell with multiple same-type entries only halves the first (a conservative
        under-application — it never over-protects, and no current spell splits a type)."""
        if amount > 0 and self.offer_absorb_elements(target, dtype):
            amount = amount // 2        # Absorb Elements: take half
        if amount > 0 and target.md.spell_resistance:
            amount = amount // 2        # Abjurer Spell Resistance: resistance to spell damage
        return amount

    # -- summons ----------------------------------------------------------
    def _find_free_square(self, near: tuple[int, int], footprint: int) -> tuple[int, int]:
        blocked: set[tuple[int, int]] = set()
        for c in self.combatants.values():
            if c.in_combat:
                blocked.update(c.occupied_squares())
        for radius in range(1, 8):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    sq = (near[0] + dx, near[1] + dy)
                    if self.grid.footprint_fits(sq, footprint, blocked):
                        return sq
        return near

    def summon(self, caster: Combatant, creature: str, count: int, untargetable: bool,
               duration: int, concentration: bool, applied: list) -> None:
        from . import content
        for i in range(count):
            cid = f"{caster.id}~{creature[:3]}{i + 1}"
            s = content.make(creature, cid, caster.team, caster.pos)
            s.enc = self
            s.pos = self._find_free_square(caster.pos, s.footprint)
            s.summoner_id = caster.id
            s.untargetable = untargetable
            s.summon_duration = None if concentration else duration
            self.combatants[cid] = s
            self.order.append(cid)
            self.emit(kind="spawn", actor=cid, hp=s.hp, pos=s.pos, info=s.team,
                      alt=s.alt)   # enters the fight
            if concentration:
                applied.append((s, "summon", None))
            self.log.append(f"  {caster.id} summons {cid} ({creature})")

    def _spawn_companions(self) -> None:
        """Beast Master Ranger's Companion: a beast that fights alongside its ranger. It gets
        its own initiative (a documented simplification of 'acts on the ranger's turn') and
        persists for the whole battle. Spawned once, at the start of the encounter."""
        from . import content
        for owner in list(self.combatants.values()):
            if not owner.md.companion:
                continue
            cid = f"{owner.id}~pet"
            if cid in self.combatants:
                continue
            try:
                s = content.make(owner.md.companion, cid, owner.team, owner.pos)
            except KeyError:
                continue
            s.enc = self
            s.pos = self._find_free_square(owner.pos, s.footprint)
            s.summoner_id = owner.id
            self.combatants[cid] = s
            self.log.append(f"  {owner.id}'s companion ({s.name}) joins the fight")

    def enumerate_options(self, actor: Combatant) -> list[Option]:
        opts: list[Option] = []
        enemies = self.enemies_of(actor)
        # a swallowed creature can only strike its captor from the inside; foes swallowed
        # by someone else have total cover and can't be targeted
        if actor.swallowed_by:
            cap = self.combatants.get(actor.swallowed_by)
            enemies = [cap] if (cap and cap.alive) else []
        else:
            enemies = [e for e in enemies
                       if not (e.swallowed_by and e.swallowed_by != actor.id)]
        # Swallow: gulp down a foe this creature is already grappling
        if actor.md.swallow is not None and not any(
                c.swallowed_by == actor.id for c in self.combatants.values()):
            for e in enemies:
                g = e.conditions.get("grappled")
                if (g and g.source_id == actor.id and not e.swallowed_by
                        and SIZE_ORDER[e.md.size] <= SIZE_ORDER[actor.md.swallow.max_size]
                        and self.dist(actor, e) <= 5):
                    opts.append(Option(f"swallow->{e.id}", "swallow", "Swallow", e.id,
                                       f"Swallow the grappled {e.name} [{e.id}] whole"))
        action_names: list[str] = []
        if actor.multiattack:
            action_names.append("multiattack")
            # also offer standalone RANGED attacks not part of the multiattack
            # (e.g. Manticore Tail Spike, giants' Rock) so flyers can kite, etc.
            ma_names = {n for n, _ in actor.multiattack}
            action_names.extend(n for n, a in actor.attacks.items()
                                if n not in ma_names and a.kind == "ranged")
        else:
            action_names.extend(actor.attacks.keys())
        for name in action_names:
            attacks = _attacks_for_action(actor.attacks, actor.multiattack, name)
            mode, normal, long = _action_range(attacks)
            label = "Multiattack" if name == "multiattack" else name
            for e in enemies:
                ok, _ = self.reachable_within(actor, e, long if mode == "ranged" else normal)
                if ok:
                    kind = "multiattack" if name == "multiattack" else "attack"
                    opts.append(Option(
                        f"{name}->{e.id}", kind, name, e.id,
                        f"{label} ({mode}) the {e.name} [{e.id}] "
                        f"({e.hp}/{e.max_hp} HP)"))
        # area abilities
        for area in actor.md.areas:
            if not actor.area_ready.get(area.name, True):
                continue
            for e in enemies:
                if area.requires_condition and not e.has(area.requires_condition):
                    continue                 # e.g. Death Glare only works on the frightened
                # the area reaches a foe within (placement range + the template's own
                # size); a self-emanation has origin_range 0 but still reaches `size` ft
                ok, _ = self.reachable_within(actor, e, area.origin_range + area.size)
                if ok:
                    cells = self._area_cells(actor.pos, e.pos, area)
                    hits = sum(1 for f in enemies
                               if any(s in cells for s in f.occupied_squares()))
                    if area.max_targets:
                        hits = min(hits, area.max_targets)
                    opts.append(Option(
                        f"area:{area.name}->{e.id}", "area", area.name, e.id,
                        f"{area.name} (area, save DC {area.dc}) on the {e.name} "
                        f"[{e.id}] — hits ~{hits} foe(s)"))
        if actor.md.eye_rays:
            in_range = [e for e in enemies
                        if self.dist(actor, e) <= actor.md.eye_ray_range
                        and self.cover_ac(actor, e) is not None]
            if in_range:
                opts.append(Option("eye_rays", "eye_rays", "Eye Rays", in_range[0].id,
                                   f"Eye Rays: {actor.md.eye_ray_count} random rays "
                                   f"at {len(in_range)} foe(s)"))
        if actor.md.frightful_presence is not None and not actor.frightful_used and enemies:
            opts.append(Option("frighten", "frighten", "Frightful Presence", None,
                               "Frightful Presence: enemies save or be frightened"))
        # Divine action-phase options: Cleric Channel Divinity (Turn/Preserve) + Paladin Lay on Hands
        cd = actor.resources.get("Channel Divinity", 0)
        if cd > 0 and actor.md.turn_undead and any(
                e.md.mtype == "undead" and self.dist(actor, e) <= 30 for e in enemies):
            opts.append(Option("turn_undead", "turn_undead", "Turn Undead", None,
                               "Channel Divinity: Turn Undead (undead within 30 ft flee)"))
        if cd > 0 and actor.md.preserve_life and any(
                a.team == actor.team and not a.dead and (a.in_combat or a.dying)
                and a.md.mtype not in ("undead", "construct")
                and a.hp < a.max_hp // 2 and self.dist(actor, a) <= 30
                for a in self.combatants.values()):
            opts.append(Option("preserve_life", "preserve_life", "Preserve Life", actor.id,
                               "Channel Divinity: Preserve Life (heal wounded allies)"))
        if actor.resources.get("Lay on Hands", 0) > 0:
            if actor.hp < actor.max_hp:
                opts.append(Option("lay_on_hands", "lay_on_hands", "Lay on Hands", actor.id,
                                   "Lay on Hands: heal yourself from the pool by touch"))
            for a in self.combatants.values():           # ...or heal a wounded ally within reach
                if (a.team == actor.team and a.id != actor.id and not a.dead
                        and (a.in_combat or a.dying) and a.hp < a.max_hp
                        and self.dist(actor, a) <= 5):
                    opts.append(Option(f"lay_on_hands->{a.id}", "lay_on_hands", "Lay on Hands",
                                       a.id, f"Lay on Hands: heal {a.id} by touch"))
        # Druid Wild Shape (action; Circle of the Moon uses a bonus action instead — below)
        if (actor.md.wild_shape_forms and actor.base_md is None
                and not actor.md.wild_shape_bonus_action
                and actor.resources.get("Wild Shape", 0) > 0):
            for form in actor.md.wild_shape_forms:
                if content_cr(form) <= actor.md.wild_shape_max_cr:
                    opts.append(Option(f"wild_shape:{form}", "wild_shape", form, None,
                                       f"Wild Shape into a {form}"))
        opts.extend(cast.enumerate_spell_options(self, actor, "action"))
        if actor.equipment is not None and actor.hp < actor.max_hp:  # drink a healing potion
            for it in actor.equipment.inventory:
                if it.heal:
                    opts.append(Option(f"quaff:{it.name}", "quaff", it.name, actor.id,
                                       f"Drink {it.name} (heal {it.heal})"))
                    break
        if actor.resources.get("Action Surge", 0) > 0 and enemies:   # take an extra action
            opts.append(Option("action_surge", "action_surge", "Action Surge", actor.id,
                               "Action Surge (one additional action)"))
        if actor.md.hypnotic_gaze:                                    # Enchanter control action
            gaze = next((e for e in enemies if self.dist(actor, e) <= 5
                         and not e.has("charmed")), None)
            if gaze is not None:
                opts.append(Option(f"gaze->{gaze.id}", "hypnotic_gaze", "Hypnotic Gaze",
                                   gaze.id, f"Hypnotic Gaze on {gaze.id}"))
        if enemies and not any(o.kind in ("attack", "multiattack", "area", "spell",
                                          "eye_rays") for o in opts):
            tgt = self._nearest_living_enemy(actor)
            if tgt is not None and actor.can_move:
                opts.append(Option(f"advance->{tgt.id}", "advance", "Advance", tgt.id,
                                   f"Advance toward the {tgt.name} [{tgt.id}]"))
        opts.extend(self._minor_action_options(actor, enemies))
        best = best_melee_attack(actor.attacks) or next(iter(actor.attacks.values()), None)
        if enemies and best is not None:
            opts.append(Option(f"ready:{best.name}", "ready", best.name, None,
                               f"Ready {best.name} for the next foe to come into range"))
        opts.append(Option("dodge", "dodge", "Dodge", None,
                           "Dodge (attackers have disadvantage; adv on Dex saves)"))
        return opts

    def _minor_action_options(self, actor: Combatant, enemies) -> list[Option]:
        """Dash, Disengage, Grapple, Shove, Help, Hide (§7.3 action catalog)."""
        opts: list[Option] = []
        if not enemies:
            return opts
        if actor.can_move:
            nm = self._nearest_living_enemy(actor)
            if nm is not None:
                opts.append(Option(f"dash->{nm.id}", "dash", "Dash", nm.id,
                                   "Dash: move up to twice your speed toward a foe"))
            if self._enemy_in_melee(actor):
                opts.append(Option("disengage", "disengage", "Disengage", None,
                                   "Disengage: move without provoking opportunity attacks"))
        if actor.has("grappled"):
            opts.append(Option("escape", "escape", "Escape", None,
                               "Escape the grapple (contested check)"))
        for e in enemies:
            if self.dist(actor, e) <= 5:
                if ("grappled" not in e.conditions
                        and SIZE_ORDER[e.md.size] <= SIZE_ORDER[actor.md.size] + 1):
                    opts.append(Option(f"grapple->{e.id}", "grapple", "Grapple", e.id,
                                       f"Grapple the {e.name} [{e.id}] (speed 0)"))
                opts.append(Option(f"shove->{e.id}", "shove", "Shove", e.id,
                                   f"Shove the {e.name} [{e.id}] prone"))
        for ally in self.living():
            if (ally.team == actor.team and ally.id != actor.id and not ally.help_advantage
                    and any(self.dist(ally, e) <= 5 and self.dist(actor, e) <= 5
                            for e in enemies)):
                opts.append(Option(f"help->{ally.id}", "help", "Help", ally.id,
                                   f"Help {ally.id}: it gains advantage on its next attack"))
                break
        if not actor.hidden:
            opts.append(Option("hide", "hide", "Hide", None, "Hide: try to become unseen"))
        return opts

    def enumerate_bonus_options(self, actor: Combatant) -> list[Option]:
        """Bonus-action options: bonus-cast spells, an off-hand attack, or pass."""
        opts = cast.enumerate_spell_options(self, actor, "bonus")
        oh = actor.md.offhand_attack
        if oh and oh in actor.attacks:           # two-weapon fighting (resolved in place)
            atk = actor.attacks[oh]
            reach = atk.reach if atk.kind == "melee" else (atk.range_long or atk.range_normal)
            for e in self.enemies_of(actor):
                if self.dist(actor, e) <= reach:
                    opts.append(Option(f"{oh}->{e.id}", "offhand", oh, e.id,
                                       f"Off-hand {oh} vs the {e.name} [{e.id}]"))
        if actor.resources.get("Second Wind", 0) > 0 and actor.hp < actor.max_hp:
            opts.append(Option("second_wind", "second_wind", "Second Wind", actor.id,
                               "Second Wind (heal 1d10 + level)"))
        if actor.md.war_magic and actor.cast_cantrip_this_turn:   # Eldritch Knight War Magic
            atk = best_melee_attack(actor.attacks) or next(iter(actor.attacks.values()), None)
            if atk is not None:
                reach = atk.reach if atk.kind == "melee" else (atk.range_long or atk.range_normal)
                for e in self.enemies_of(actor):
                    if self.dist(actor, e) <= reach:
                        opts.append(Option(f"warmagic->{e.id}", "war_magic", atk.name, e.id,
                                           f"War Magic: {atk.name} vs {e.id}"))
                        break
        mh = actor.equipment.main_hand if actor.equipment else None   # Polearm Master bonus attack
        if actor.md.polearm_master and mh is not None and mh.name in _POLEARMS:
            reach = 10 if mh.reach else 5
            for e in self.enemies_of(actor):
                if self.dist(actor, e) <= reach:
                    opts.append(Option(f"pam->{e.id}", "polearm", "Polearm", e.id,
                                       f"Polearm butt-end vs {e.id}"))
                    break
        enemies = self.enemies_of(actor)
        # Barbarian Rage (bonus action): enter a rage while a rage use remains
        if (actor.md.rage_damage and not actor.raging and enemies
                and actor.resources.get("Rage", 0) > 0):
            opts.append(Option("rage", "rage", "Rage", actor.id, "Rage (bonus action)"))
        # Berserker Frenzy: an extra melee attack each turn while raging
        if actor.md.frenzy and actor.raging:
            atk = best_melee_attack(actor.attacks)
            if atk is not None:
                for e in enemies:
                    if self.dist(actor, e) <= atk.reach:
                        opts.append(Option(f"frenzy->{e.id}", "offhand", atk.name, e.id,
                                           f"Frenzy: bonus {atk.name} vs {e.id}"))
                        break
        # Great Weapon Master: a bonus-action melee attack pending from a crit or a kill this turn
        if actor.gwm_bonus_ready:
            atk = best_melee_attack(actor.attacks)
            if atk is not None:
                for e in enemies:
                    if self.dist(actor, e) <= atk.reach:
                        opts.append(Option(f"gwm->{e.id}", "offhand", atk.name, e.id,
                                           f"Great Weapon Master: bonus {atk.name} vs {e.id}"))
                        break
        # Monk Martial Arts bonus strike / Flurry of Blows / Patient Defense (Ki)
        if actor.md.martial_arts_die and actor.took_attack_action and "Unarmed Strike" in actor.attacks:
            reach = actor.attacks["Unarmed Strike"].reach
            in_reach = next((e for e in enemies if self.dist(actor, e) <= reach), None)
            if actor.resources.get("Ki", 0) > 0 and in_reach is not None:
                opts.append(Option(f"flurry->{in_reach.id}", "flurry", "Flurry of Blows",
                                   in_reach.id, "Flurry of Blows (1 Ki: two unarmed strikes)"))
            if in_reach is not None:
                opts.append(Option(f"marts->{in_reach.id}", "offhand", "Unarmed Strike",
                                   in_reach.id, "Martial Arts: bonus unarmed strike"))
            if actor.resources.get("Ki", 0) > 0:
                opts.append(Option("patient_defense", "patient_defense", "Patient Defense",
                                   actor.id, "Patient Defense (1 Ki: Dodge as a bonus action)"))
        # Rogue Cunning Action: bonus-action Dash / Disengage / Hide
        if actor.md.cunning_action and enemies:
            if actor.can_move and not self._enemy_in_melee(actor):
                nm = self._nearest_living_enemy(actor)
                if nm is not None:
                    opts.append(Option(f"dash->{nm.id}", "dash", "Dash", nm.id,
                                       "Cunning Action: Dash toward a foe"))
            if actor.can_move and self._enemy_in_melee(actor):
                opts.append(Option("disengage", "disengage", "Disengage", None,
                                   "Cunning Action: Disengage"))
            if not actor.hidden:
                opts.append(Option("hide", "hide", "Hide", None, "Cunning Action: Hide"))
        # Bonus-action self-teleport (Fey Step / Astral Step / Cloud Step): reposition toward
        # a foe that is out of melee reach (ignores terrain, provokes no opportunity attack).
        if actor.md.teleport_bonus > 0 and actor.can_move:
            nm = self._nearest_living_enemy(actor)
            if nm is not None and self.dist(actor, nm) > 5:
                opts.append(Option(f"teleport->{nm.id}", "teleport", "Teleport", nm.id,
                                   f"Teleport up to {actor.md.teleport_bonus} ft toward {nm.id}"))
        # Paladin bonus-action Channel Divinity (Oath of Devotion / Oath of Vengeance)
        if actor.resources.get("Channel Divinity", 0) > 0 and enemies:
            if actor.md.sacred_weapon and not any(e.name == "Sacred Weapon" for e in actor.effects):
                opts.append(Option("sacred_weapon", "sacred_weapon", "Sacred Weapon", actor.id,
                                   "Channel Divinity: Sacred Weapon (+CHA to attack rolls)"))
            vt = self.combatants.get(actor.vow_target_id) if actor.vow_target_id else None
            if actor.md.vow_of_enmity and (vt is None or not vt.alive):
                tgt = self._nearest_living_enemy(actor)
                if tgt is not None:
                    opts.append(Option(f"vow->{tgt.id}", "vow", "Vow of Enmity", tgt.id,
                                       f"Channel Divinity: Vow of Enmity vs {tgt.id} (advantage)"))
        # War Domain War Priest: a bonus weapon attack after taking the Attack action
        if (actor.md.war_priest and actor.took_attack_action
                and actor.resources.get("War Priest", 0) > 0):
            atk = best_melee_attack(actor.attacks) or next(iter(actor.attacks.values()), None)
            if atk is not None:
                reach = atk.reach if atk.kind == "melee" else (atk.range_long or atk.range_normal)
                for e in enemies:
                    if self.dist(actor, e) <= reach:
                        opts.append(Option(f"warpriest->{e.id}", "war_priest", atk.name, e.id,
                                           f"War Priest: bonus {atk.name} vs {e.id}"))
                        break
        # Bard Bardic Inspiration: bank a die on an ally that isn't already inspired
        if actor.md.bardic_inspiration_die and actor.resources.get("Bardic Inspiration", 0) > 0:
            for a in self.living():
                if (a.team == actor.team and a.id != actor.id and a.inspiration_die == 0
                        and a.attacks):
                    opts.append(Option(f"inspire->{a.id}", "bardic_inspiration",
                                       "Bardic Inspiration", a.id,
                                       f"Bardic Inspiration (d{actor.md.bardic_inspiration_die}) "
                                       f"to {a.id}"))
        # Circle of the Moon: Combat Wild Shape (bonus action) + spend-a-slot healing in form
        if (actor.md.wild_shape_forms and actor.base_md is None
                and actor.md.wild_shape_bonus_action
                and actor.resources.get("Wild Shape", 0) > 0 and enemies):
            for form in actor.md.wild_shape_forms:
                if content_cr(form) <= actor.md.wild_shape_max_cr:
                    opts.append(Option(f"wild_shape:{form}", "wild_shape", form, None,
                                       f"Combat Wild Shape into a {form}"))
        if (actor.base_md is not None and actor.base_md.combat_wild_shape
                and actor.hp < actor.max_hp):
            slot = next((lvl for lvl in range(1, 10) if actor.slots.get(lvl, 0) > 0), None)
            if slot is not None:
                opts.append(Option("moon_heal", "moon_heal", "Combat Wild Shape Heal", actor.id,
                                   f"Spend a level-{slot} slot to heal {slot}d8", slot_level=slot))
        # Sorcerer Metamagic — Quickened Spell: cast an action spell as a bonus action (2 points)
        if actor.md.quicken_spell and actor.resources.get("Sorcery Points", 0) >= 2:
            for o in cast.enumerate_spell_options(self, actor, "action"):
                if o.kind != "spell":
                    continue
                try:
                    sp = spells.get(o.name)
                except KeyError:
                    continue
                if sp.casting_time != "action":
                    continue
                if sp.level >= 1 and actor.cast_leveled_this_turn:
                    continue                    # only one leveled spell per turn (a cantrip is fine)
                opts.append(Option(f"q:{o.id}", "quicken", o.name, o.target_id,
                                   f"Quicken: {o.desc}", spell=o.name, slot_level=o.slot_level))
        opts.append(Option("pass", "pass", "Pass", None, "No bonus action"))
        return opts

    # -- movement & execution --------------------------------------------
    def _choose_destination(self, actor: Combatant, target: Combatant,
                            mode: str, normal: int) -> tuple[int, int]:
        tgt_squares = target.occupied_squares()
        n = actor.footprint
        cur = self._from_footprint(actor.pos, n, tgt_squares)
        if mode == "melee":
            if cur <= normal:
                return actor.pos
        else:
            # ranged/area: if already within normal range, kite away from enemies
            if cur <= normal and not self._adjacent_enemy(actor, actor.pos):
                return actor.pos
        if not actor.can_move:
            return actor.pos
        budget = self._move_budget(actor)
        reach = self.grid.reachable(actor.pos, actor.footprint, budget,
                                    self._blocked(actor), **self._reach_kwargs(actor))
        cands = []
        for sq, steps in reach.items():
            if not self._fear_ok(actor, sq):
                continue
            d = self._from_footprint(sq, n, tgt_squares)
            if mode == "melee" and d <= normal:
                cands.append((steps, sq))
            elif mode != "melee" and d <= normal:
                cands.append((sq, steps))
        if mode == "melee":
            if cands:
                cands.sort(key=lambda t: (t[0], t[1]))
                return cands[0][1]
            # can't reach: step as close as possible
            return min(reach, key=lambda s: self._from_footprint(s, n, tgt_squares))
        if cands:
            # maximize distance to nearest enemy (kite), then fewest steps
            cands.sort(key=lambda t: (-self._dist_nearest_enemy(actor, t[0]), t[1]))
            return cands[0][0]
        return min(reach, key=lambda s: self._from_footprint(s, n, tgt_squares))

    def _teleport_destination(self, actor: Combatant,
                              target: Combatant) -> tuple[int, int]:
        """Best cell within `teleport_bonus` ft to teleport to — closest to the target
        (phases past terrain and creatures; the landing cell itself must be free)."""
        if not actor.can_move or target is None:
            return actor.pos
        n = actor.footprint
        tgt = target.occupied_squares()
        reach = self.grid.reachable(actor.pos, n, actor.md.teleport_bonus,
                                    self._blocked(actor), ignore_difficult=True,
                                    can_phase=True)
        cells = [s for s in reach if self._fear_ok(actor, s)]
        if not cells:
            return actor.pos
        return min(cells, key=lambda s: self._from_footprint(s, n, tgt))

    def _fear_ok(self, actor: Combatant, sq: tuple[int, int]) -> bool:
        """Frightened creatures can't move closer to the source of their fear."""
        cond = actor.conditions.get("frightened")
        if cond is None:
            return True
        src = self.combatants.get(cond.source_id)
        if src is None or not src.alive:
            return True
        n = actor.footprint
        cur = self._from_footprint(actor.pos, n, src.occupied_squares())
        new = self._from_footprint(sq, n, src.occupied_squares())
        return new >= cur

    def _is_flanking(self, attacker: Combatant, target: Combatant) -> bool:
        """DMG optional rule: advantage when a non-incapacitated ally is on the
        opposite side of the target. Both flankers must be adjacent (within 5 ft,
        so reach weapons don't flank); the target must lie between them."""
        if not self.rules.flanking:
            return False
        tsq = set(target.occupied_squares())
        if min(feet_between(attacker.pos, s) for s in tsq) > 5:
            return False                            # attacker must be within 5 ft
        for ally in self.combatants.values():
            if (not ally.in_combat or ally.incapacitated or ally.team != attacker.team
                    or ally.id == attacker.id):
                continue
            if min(feet_between(ally.pos, s) for s in tsq) > 5:
                continue                            # ally must also be within 5 ft
            # the target lies between attacker and ally -> opposite sides
            if set(self.grid.line_cells(attacker.pos, ally.pos)) & tsq:
                return True
        return False

    def _positional_advantage(self, attacker: Combatant, target: Combatant,
                              kind: str) -> bool:
        """Advantage from Pack Tactics, high ground, or flanking (melee only)."""
        # High ground: standing on raised TERRAIN (not flight) above your foe. Flyers are
        # excluded — their altitude is already an advantage, and SAFE_ALT would otherwise
        # grant them permanent advantage on every ranged attack against grounded targets.
        if (self.rules.high_ground and attacker.md.fly == 0
                and attacker.alt >= target.alt + 5):
            return True
        if attacker.md.pack_tactics:
            tsq = target.occupied_squares()
            for ally in self.combatants.values():
                if (ally.in_combat and ally.team == attacker.team and ally.id != attacker.id
                        and not ally.incapacitated
                        and min(feet_between(ally.pos, s) for s in tsq) <= 5):
                    return True
        return kind == "melee" and self._is_flanking(attacker, target)

    def _adjacent_enemy(self, actor: Combatant, pos: tuple[int, int]) -> bool:
        n = actor.footprint
        return any(self._from_footprint(pos, n, e.occupied_squares()) <= 5
                   for e in self.enemies_of(actor))

    def _dist_nearest_enemy(self, actor: Combatant, pos: tuple[int, int]) -> float:
        n = actor.footprint
        ds = [self._from_footprint(pos, n, e.occupied_squares())
              for e in self.enemies_of(actor)]
        return min(ds) if ds else 1e9

    def _do_move(self, actor: Combatant, dest: tuple[int, int],
                 alt: float | None = None) -> None:
        if alt is None:
            alt = actor.alt
        if dest == actor.pos and alt == actor.alt:
            return
        start, start_alt = actor.pos, actor.alt
        # the actual route (same Dijkstra cost surface that chose dest) — consequences
        # below are evaluated along it, and the replay animates it
        path = self._move_path(actor, dest) if dest != start else [start, start]
        step_alt = [start_alt] * (len(path) - 1) + [alt]   # level flight until the last square
        # opportunity attacks: enemies whose (3D) reach the route LEAVES at any step —
        # including running PAST a foe (entering its reach and out the other side)
        provokers = []
        for e in self.enemies_of(actor):
            if not can_react(e) or e.swallowed_by == actor.id:
                continue                        # a creature inside us can't take an OA on us
            if actor.md.mobile and e.id in actor.attacked_this_turn:
                continue                        # Mobile: no OA from a foe you melee'd this turn
            atk = best_melee_attack(e.attacks)
            if atk is None:
                continue
            within = [self._dist_pos(p, a, e) <= atk.reach
                      for p, a in zip(path, step_alt)]
            if any(within[i] and not within[i + 1] for i in range(len(within) - 1)):
                provokers.append((e, atk))
            elif e.md.polearm_master and any(                     # PAM: OA on entering reach
                    not within[i] and within[i + 1] for i in range(len(within) - 1)):
                provokers.append((e, atk))
        if actor.has("prone"):
            actor.conditions.pop("prone", None)
            self.log.append(f"    {actor.id} stands up")
        actor.moved_this_turn += feet_between(start, dest)   # for Pounce
        actor.pos, actor.alt = dest, alt
        if actor.md.fly == 0:                # grounded creatures stand at terrain height
            actor.alt = self.grid.elevation.get(dest, 0)
        actor.squeezing = not self.grid.footprint_fits(dest, actor.footprint,
                                                       self._blocked(actor))
        self.log.append(f"    {actor.id} moves to {dest}"
                        + (f" @{int(alt)}ft" if alt else "")
                        + (" (squeezing)" if actor.squeezing else ""))
        self.emit(kind="move", actor=actor.id, pos=dest,   # after its prose, before consequences
                  alt=actor.alt, cells=tuple(path))        # cells = the walked route
        for owner in list(self._aura_owners_covering(actor)):   # auras trigger on entering
            self._apply_aura_to(owner, actor)
            if not actor.alive:
                return
        self._apply_hazards_along(actor, path)  # lava/fire/grease/ice anywhere on the route
        if not actor.alive:
            return
        # Flyby / teleport provoke no OAs; Disengage avoids them except from a Sentinel
        if not actor.md.flyby and actor.md.teleport == 0:
            for e, atk in provokers:
                if actor.disengaging and not e.md.sentinel:
                    continue
                e.reaction_available = False
                self.log.append(f"    >> opportunity attack from {e.id}")
                hit = resolve_attack(e, actor, atk, self.rng, self.log,
                                     flanking=self._positional_advantage(e, actor, "melee"),
                                     enc=self, reckless_ok=False, is_reaction=True)
                if not actor.alive:
                    return
                if hit and e.md.sentinel:       # Sentinel: the OA stops the target's movement
                    actor.movement_halted = True
        self._trigger_readied(actor, path)

    def _trigger_readied(self, mover: Combatant, path: list[tuple[int, int]]) -> None:
        """A foe who readied an attack fires it when the mover ENTERS its range at
        any step of the walked route (not just the endpoint)."""
        for e in self.enemies_of(mover):
            if e.readied_attack is None or not can_react(e):
                continue
            atk = e.md.attacks.get(e.readied_attack)
            if atk is None:
                continue
            reach = atk.reach if atk.kind == "melee" else (atk.range_long or atk.range_normal)
            e_sq = e.occupied_squares()
            within = [min(feet_between(p, s) for s in e_sq) <= reach for p in path]
            if not any(not within[i] and within[i + 1] for i in range(len(within) - 1)):
                continue
            cover = 0
            if atk.kind != "melee":
                cover = self._cover_ac(e, mover)
                if cover is None:
                    continue          # no line of sight; hold the readied action
            e.reaction_available = False
            e.readied_attack = None
            self.log.append(f"    >> {e.id} looses a readied {atk.name} at {mover.id}")
            if atk.kind == "melee":
                resolve_attack(e, mover, atk, self.rng, self.log,
                               flanking=self._positional_advantage(e, mover, "melee"),
                               enc=self, reckless_ok=False)   # readied reaction
            else:
                d = self.dist(e, mover)
                resolve_attack(e, mover, atk, self.rng, self.log, cover_ac=cover,
                               ranged_in_melee=self._enemy_in_melee(e),
                               long_range=d > atk.range_normal, enc=self, reckless_ok=False)
            if not mover.alive:
                return

    def _do_second_wind(self, actor: Combatant) -> None:
        """Fighter Second Wind: a bonus action to regain 1d10 + fighter level HP."""
        actor.resources["Second Wind"] -= 1
        level = int(actor.md.hit_dice.split("d")[0]) if "d" in actor.md.hit_dice else 1
        amt = self.rng.roll(1, 10, level)
        actor.hp = min(actor.max_hp, actor.hp + amt)
        self.log.append(f"  {actor.id} uses Second Wind, regaining {amt} -> "
                        f"{actor.hp}/{actor.max_hp} HP")
        self.emit(kind="heal", actor=actor.id, amount=amt, hp=actor.hp)

    def _do_rage(self, actor: Combatant) -> None:
        """Barbarian Rage: a bonus action to enter a rage (melee damage bonus + B/P/S resistance).
        PHB simplification — it lasts the rest of the fight (or until the barbarian is
        incapacitated); the attack/damage-each-turn upkeep is not tracked."""
        if actor.resources.get("Rage", 0) <= 0 or actor.raging:
            return
        actor.resources["Rage"] -= 1
        actor.raging = True
        self.log.append(f"  {actor.id} flies into a RAGE "
                        f"(+{actor.md.rage_damage} melee dmg, resist B/P/S)")

    def _do_turn_undead(self, actor: Combatant) -> None:
        """Cleric Channel Divinity: Turn Undead — undead within 30 ft make a WIS save or are
        turned (frightened + routed, so they flee for a minute). Destroy Undead instantly slays
        turned undead whose CR is at or below the cleric's threshold."""
        actor.resources["Channel Divinity"] = actor.resources.get("Channel Divinity", 0) - 1
        self.log.append(f"  {actor.id} presents a holy symbol — Turn Undead! (DC {actor.md.spell_dc})")
        for e in self.enemies_of(actor):
            if e.md.mtype != "undead" or self.dist(actor, e) > 30:
                continue
            if saving_throw(e, Ability.WIS, actor.md.spell_dc, self.rng, log=self.log):
                self.log.append(f"    {e.id} resists the turning")
                continue
            if actor.md.destroy_undead_cr >= 0 and e.md.cr <= actor.md.destroy_undead_cr:
                self.log.append(f"    ** {e.id} is destroyed (Destroy Undead) **")
                apply_damage(e, e.hp + e.max_hp, "radiant", self.log, self.rng, enc=self)
            else:
                apply_condition(e, "frightened", actor.id, self.rng, self.log, duration=10)
                e.routed = True                          # turned undead must flee (rout machinery)
                e.turned_by = actor.id                   # the turn ends the instant it takes damage
                self.log.append(f"    {e.id} is turned and flees")

    def _do_preserve_life(self, actor: Combatant) -> None:
        """Life Domain Channel Divinity: Preserve Life — restore 5 x cleric level HP, divided
        among wounded allies within 30 ft, but none above half its HP maximum. Not undead/constructs."""
        actor.resources["Channel Divinity"] = actor.resources.get("Channel Divinity", 0) - 1
        pool = actor.md.preserve_life
        self.log.append(f"  {actor.id} channels Preserve Life ({pool} HP to share)")
        allies = sorted((a for a in self.combatants.values()
                         if a.team == actor.team and not a.dead and (a.in_combat or a.dying)
                         and a.md.mtype not in ("undead", "construct")
                         and a.hp < a.max_hp // 2 and self.dist(actor, a) <= 30),
                        key=lambda a: a.hp)
        for a in allies:
            if pool <= 0:
                break
            give = min(a.max_hp // 2 - a.hp, pool)
            if give <= 0:
                continue
            a.hp += give
            pool -= give
            a.wake_from_dying()
            self.emit(kind="heal", actor=a.id, amount=give, hp=a.hp)
            self.log.append(f"    {a.id} restored {give} -> {a.hp}/{a.max_hp} HP")

    def _do_sacred_weapon(self, actor: Combatant) -> None:
        """Oath of Devotion Channel Divinity: Sacred Weapon — add CHA to attack rolls for 1
        minute (modelled as a 10-round buff)."""
        actor.resources["Channel Divinity"] = actor.resources.get("Channel Divinity", 0) - 1
        add_effect(actor, ActiveEffect(name="Sacred Weapon", source_id=actor.id,
                                       attack_bonus=Damage(0, 0, actor.md.sacred_weapon, ""),
                                       duration=10))
        self.log.append(f"  {actor.id} imbues its weapon (Sacred Weapon, +{actor.md.sacred_weapon} to hit)")

    def _do_vow(self, actor: Combatant, target: Combatant) -> None:
        """Oath of Vengeance Channel Divinity: Vow of Enmity — gain advantage on attacks against
        one foe for 1 minute (modelled as until the fight ends)."""
        if target is None:
            return
        actor.resources["Channel Divinity"] = actor.resources.get("Channel Divinity", 0) - 1
        actor.vow_target_id = target.id
        self.log.append(f"  {actor.id} swears a Vow of Enmity against {target.id} (advantage)")

    def _do_lay_on_hands(self, actor: Combatant, target: Combatant | None) -> None:
        """Paladin Lay on Hands: spend HP from a pool (5 x paladin level) to heal by touch.
        Restores the touched creature (self by default) by the missing amount, capped at the
        remaining pool. (The pool's disease/poison-cure use is a non-combat follow-on.)"""
        tgt = target or actor
        pool = actor.resources.get("Lay on Hands", 0)
        give = min(pool, tgt.max_hp - tgt.hp)
        if give <= 0:
            return
        actor.resources["Lay on Hands"] = pool - give
        tgt.hp += give
        tgt.wake_from_dying()
        self.emit(kind="heal", actor=tgt.id, amount=give, hp=tgt.hp)
        self.log.append(f"  {actor.id} lays on hands: {tgt.id} +{give} -> "
                        f"{tgt.hp}/{tgt.max_hp} HP (pool {actor.resources['Lay on Hands']})")

    def apply_wild_shape(self, actor: Combatant, form: str) -> None:
        """Druid Wild Shape: swap in a beast's stat block (physical stats, AC, speeds, attacks)
        while keeping the druid's mental scores, save proficiencies and proficiency bonus. The
        beast HP is a separate pool held on the Combatant; dropping to 0 reverts (rules.handle_drop).
        Approximations: the druid can't cast in form (except Circle of the Moon's Combat Wild Shape
        heal); its own class features/senses beyond stats are not re-derived onto the beast."""
        import dataclasses
        from . import content
        try:
            beast = content.get(form)
        except KeyError:
            return
        actor.resources["Wild Shape"] = actor.resources.get("Wild Shape", 0) - 1
        druid = actor.md
        ab = dict(beast.abilities)
        for k in (Ability.INT, Ability.WIS, Ability.CHA):
            ab[k] = druid.abilities[k]
        merged = dataclasses.replace(beast, abilities=ab, save_profs=druid.save_profs,
                                     prof_bonus=druid.prof_bonus)
        actor.base_md, actor.base_hp = druid, actor.hp
        actor.base_rolled, actor.base_temp_hp = actor.rolled_max_hp, actor.temp_hp
        actor.base_equipment = actor.equipment
        actor.md, actor.equipment = merged, None
        actor.rolled_max_hp, actor.hp, actor.temp_hp = beast.hp, beast.hp, 0
        for area in merged.areas:
            actor.area_ready.setdefault(area.name, True)
        self.log.append(f"  {actor.id} takes Wild Shape -> {beast.name} "
                        f"({beast.hp} HP, AC {merged.ac})")
        self.emit(kind="condition", actor=actor.id, info=f"wild_shape:{beast.name}")

    def _do_wild_shape(self, actor: Combatant, form: str) -> None:
        if actor.base_md is not None or actor.resources.get("Wild Shape", 0) <= 0:
            return
        self.apply_wild_shape(actor, form)

    def _do_bardic_inspiration(self, actor: Combatant, target: Combatant) -> None:
        """Bard: a bonus action to bank an inspiration die on an ally (consumed on its next
        attack roll — see rules.resolve_attack)."""
        if target is None or actor.resources.get("Bardic Inspiration", 0) <= 0:
            return
        actor.resources["Bardic Inspiration"] -= 1
        target.inspiration_die = actor.md.bardic_inspiration_die
        self.log.append(f"  {actor.id} inspires {target.id} "
                        f"(Bardic Inspiration d{target.inspiration_die})")

    def _do_moon_heal(self, actor: Combatant, slot: int) -> None:
        """Circle of the Moon Combat Wild Shape: while in beast form, spend a spell slot as a
        bonus action to regain 1d8 HP per level of the slot."""
        if actor.base_md is None or actor.slots.get(slot, 0) <= 0:
            return
        actor.slots[slot] -= 1
        amt = self.rng.roll(slot, 8)
        actor.hp = min(actor.max_hp, actor.hp + amt)
        self.log.append(f"  {actor.id} channels a slot (Combat Wild Shape): +{amt} -> "
                        f"{actor.hp}/{actor.max_hp} HP")
        self.emit(kind="heal", actor=actor.id, amount=amt, hp=actor.hp)

    def monk_stunning_strike(self, attacker: Combatant, target: Combatant) -> None:
        """Monk (L5): on a melee hit, spend 1 Ki to force a CON save or the target is stunned
        until the end of the monk's next turn. Policy: at most once per turn, on the first hit
        against a not-yet-stunned foe (so the Ki lasts across the fight)."""
        if (attacker.stunning_used or attacker.resources.get("Ki", 0) <= 0
                or target.has("stunned") or not target.alive):
            return
        attacker.stunning_used = True
        attacker.resources["Ki"] -= 1
        self.log.append(f"  >> {attacker.id} Stunning Strike (1 Ki) vs {target.id}")
        if not saving_throw(target, Ability.CON, attacker.md.ki_dc, self.rng, log=self.log):
            apply_condition(target, "stunned", attacker.id, self.rng, self.log, duration=1)

    def _do_flurry(self, actor: Combatant, target: Combatant) -> None:
        """Monk Flurry of Blows: spend 1 Ki for two bonus unarmed strikes. Way of the Open Hand
        riders each strike: a hit forces a DEX save or the target is knocked prone."""
        if actor.resources.get("Ki", 0) <= 0:
            return
        atk = actor.attacks.get("Unarmed Strike")
        if atk is None:
            return
        actor.resources["Ki"] -= 1
        self.log.append(f"  >> {actor.id} unleashes a Flurry of Blows (1 Ki)")
        for _ in range(2):
            tgt = target if (target and target.alive) else self._lowest_hp_enemy(actor)
            if tgt is None or self.dist(actor, tgt) > atk.reach:
                return
            cover = self._cover_ac(actor, tgt)
            if cover is None:
                continue
            hit = resolve_attack(actor, tgt, atk, self.rng, self.log, cover_ac=cover,
                                 flanking=self._positional_advantage(actor, tgt, "melee"),
                                 enc=self)
            if hit and actor.md.open_hand and tgt.alive:      # Open Hand Technique: save or prone
                if not saving_throw(tgt, Ability.DEX, actor.md.ki_dc, self.rng, log=self.log):
                    apply_condition(tgt, "prone", actor.id, self.rng, self.log)

    def _do_patient_defense(self, actor: Combatant) -> None:
        """Monk Patient Defense: spend 1 Ki to take the Dodge action as a bonus action."""
        if actor.resources.get("Ki", 0) <= 0:
            return
        actor.resources["Ki"] -= 1
        actor.dodging = True
        self.log.append(f"  {actor.id} takes Patient Defense (Dodge, 1 Ki)")

    def _do_quaff(self, actor: Combatant, name: str) -> None:
        """Drink a healing potion from the inventory."""
        from .dice import parse_dice
        eqp = actor.equipment
        it = next((i for i in eqp.inventory if i.name == name), None)
        if it is None or not it.heal:
            return
        eqp.inventory.remove(it)
        c, s, b = parse_dice(it.heal)
        amt = self.rng.roll(c, s, b)
        actor.hp = min(actor.max_hp, actor.hp + amt)
        self.log.append(f"  {actor.id} drinks {name}, healing {amt} -> "
                        f"{actor.hp}/{actor.max_hp} HP")
        self.emit(kind="heal", actor=actor.id, amount=amt, hp=actor.hp)

    def _do_polearm(self, actor: Combatant, target: Combatant) -> None:
        """Polearm Master bonus action: a butt-end strike (1d4 bludgeoning)."""
        from .dice import Damage
        mh = actor.equipment.main_hand if actor.equipment else None
        if mh is None or target is None:
            return
        smod = actor.md.mod(Ability.STR)
        atk = AttackDef(name="Polearm (butt)", kind="melee",
                        attack_bonus=smod + actor.md.prof_bonus,
                        damage=(Damage(1, 4, smod, "bludgeoning"),), reach=10 if mh.reach else 5)
        if self.dist(actor, target) > atk.reach:
            return
        cover = self._cover_ac(actor, target)
        if cover is None:
            return
        resolve_attack(actor, target, atk, self.rng, self.log, cover_ac=cover,
                       flanking=self._positional_advantage(actor, target, "melee"), enc=self)

    def _do_attack_action(self, actor: Combatant, target: Combatant,
                          name: str) -> None:
        actor.took_attack_action = True             # Monk Martial Arts / Flurry bonus-strike gate
        if target is not None and target.team != actor.team:
            actor.last_target_id = target.id        # for ally focus-fire coordination
        attacks = _attacks_for_action(actor.attacks, actor.multiattack, name)
        mode, normal, long = _action_range(attacks)
        dest = self._choose_destination(actor, target, mode, normal)
        desired_alt = self._desired_alt(actor, mode, target)
        if actor.md.fly > 0 and mode != "melee" and long:
            # don't climb so high the target leaves attack range
            horiz = self._from_footprint(dest, actor.footprint, target.occupied_squares())
            max_alt = (max(0.0, long * long - horiz * horiz)) ** 0.5
            desired_alt = min(desired_alt, max_alt)
        self._do_move(actor, dest, desired_alt)
        if not actor.alive:
            return
        for atk in attacks:
            if not actor.alive:        # a reaction (e.g. Hellish Rebuke) may have killed us
                return
            tgt = target if target.alive else self._lowest_hp_enemy(actor)
            if tgt is None:
                return
            d = self.dist(actor, tgt)        # true 3D distance
            cover = self._cover_ac(actor, tgt)
            if cover is None:
                self.log.append(f"  {actor.id} has no line of sight to {tgt.id}")
                continue
            if atk.kind == "melee":
                if d > atk.reach:
                    continue
                hit = resolve_attack(actor, tgt, atk, self.rng, self.log, cover_ac=cover,
                                     flanking=self._positional_advantage(actor, tgt, "melee"),
                                     enc=self)
                if hit:
                    self._try_pounce(actor, tgt)
            else:
                if d > (atk.range_long or atk.range_normal):
                    continue
                eqp = actor.equipment
                if eqp is not None and eqp.out_of_ammo():
                    self.log.append(f"  {actor.id} is out of ammunition")
                    continue
                resolve_attack(actor, tgt, atk, self.rng, self.log, cover_ac=cover,
                               flanking=self._positional_advantage(actor, tgt, "ranged"),
                               ranged_in_melee=self._enemy_in_melee(actor),
                               long_range=d > atk.range_normal, enc=self)
                if eqp is not None and eqp.main_hand and eqp.main_hand.ammunition:
                    eqp.ammo -= 1               # one shot consumed

    def _try_pounce(self, actor: Combatant, target: Combatant) -> None:
        """If the actor charged >= pounce_distance and hit, knock prone + bonus attack."""
        if (actor.md.pounce_distance <= 0 or not target.alive
                or actor.moved_this_turn < actor.md.pounce_distance):
            return
        actor.moved_this_turn = 0.0   # pounce triggers once per turn
        if not saving_throw(target, Ability.STR, actor.md.pounce_save_dc, self.rng,
                            log=self.log):
            apply_condition(target, "prone", actor.id, self.rng, self.log, duration=1)
        bonus = actor.attacks.get(actor.md.pounce_bonus_attack)
        if bonus is not None and target.alive and self.dist(actor, target) <= bonus.reach:
            self.log.append(f"  {actor.id} pounces with a bonus {bonus.name}")
            resolve_attack(actor, target, bonus, self.rng, self.log,
                           flanking=self._positional_advantage(actor, target, "melee"),
                           enc=self)

    def _nearest_living_enemy(self, actor: Combatant) -> Combatant | None:
        es = self.enemies_of(actor)
        return min(es, key=lambda e: self.dist(actor, e)) if es else None

    def _lowest_hp_enemy(self, actor: Combatant) -> Combatant | None:
        """Redirect target for spare multiattacks: focus-fire the weakest in reach."""
        es = self.enemies_of(actor)
        return min(es, key=lambda e: (e.hp, self.dist(actor, e))) if es else None

    def _area_cells(self, owner_pos, origin, area: AreaDef) -> set[tuple[int, int]]:
        direction = (origin[0] - owner_pos[0], origin[1] - owner_pos[1])
        if direction == (0, 0):
            direction = (1, 0)          # only substitute when the vector is fully zero
        if area.shape == "cone":
            return cone_cells(owner_pos, direction, area.size, self.grid)
        if area.shape == "line":
            return line_aoe_cells(owner_pos, direction, area.size, self.grid)
        if area.shape == "cube":
            return cube_cells(origin, area.size, self.grid)
        return sphere_cells(origin, area.size, self.grid)

    def _apply_area(self, owner: Combatant, area: AreaDef,
                    cells: set[tuple[int, int]]) -> None:
        hit = [e for e in self.enemies_of(owner)
               if any(s in cells for s in e.occupied_squares())
               and (not area.requires_condition or e.has(area.requires_condition))]
        if area.max_targets and len(hit) > area.max_targets:
            # "up to N creatures" abilities: take the nearest N (deterministic tiebreak)
            hit.sort(key=lambda e: (self.dist(owner, e), e.id))
            hit = hit[:area.max_targets]
        # only burn Legendary Resistance on high-stakes areas, like cast.py
        important = (sum(d.average() for d in area.damage) >= 20
                     or bool(area.rider and area.rider.on_fail_condition))
        self.log.append(f"  {owner.id}'s {area.name} hits {len(hit)} foe(s): "
                        f"{[c.id for c in hit]}")
        self.emit(kind="area", actor=owner.id, info=area.name,   # replay shades the burst
                  cells=tuple(sorted(cells)))
        dealt_total = 0
        for e in hit:
            # a creature with advantage on saves vs the rider's condition (Fey Ancestry,
            # etc.) rolls the area save with advantage
            saved = saving_throw(e, area.save, area.dc, self.rng, important=important,
                                 log=self.log,
                                 vs=area.rider.on_fail_condition if area.rider else None)
            self.log.append(f"    {e.id} {area.save.value} save DC {area.dc}: "
                            f"{'success' if saved else 'FAIL'}")
            for dmg in area.damage:
                amt = area_damage_after_save(e, area.save, saved, area.half_on_save,
                                             dmg.roll(self.rng))     # Evasion-aware
                dealt_total += apply_damage(e, amt, dmg.type, self.log, self.rng, enc=self)
            r = area.rider
            # "or drop to 0 hit points" (Demilich Howl, Banshee Wail): typeless and
            # unavoidable, so no resistance applies; routed through apply_damage to keep
            # the drop/death processing and the event stream canonical
            if not saved and r and r.zero_hp_on_fail and e.alive and e.hp > 0:
                self.log.append(f"    {e.id} drops to 0 hit points!")
                apply_damage(e, e.hp, "unavoidable", self.log, self.rng, enc=self)
            # skip if the foe already holds the worsened condition (e.g. re-gazing a
            # creature that is already petrified)
            already = bool(r and r.escalates_to and e.has(r.escalates_to))
            if not saved and r and r.on_fail_condition and e.alive and not already:
                se = r.condition_save_ends
                apply_condition(e, r.on_fail_condition, owner.id, self.rng, self.log,
                                duration=r.condition_duration,
                                save_ability=r.ability if se else None,
                                save_dc=r.dc if se else 0,
                                escalates_to=r.escalates_to)
            if not saved and r and r.push and e.alive:
                self.force_move(owner, e, abs(r.push), toward=r.push < 0)
        if area.heal_owner and dealt_total > 0 and owner.alive and owner.hp < owner.max_hp:
            gained = min(owner.max_hp - owner.hp, dealt_total)
            owner.hp += gained
            self.emit(kind="heal", actor=owner.id, amount=gained, hp=owner.hp)
            self.log.append(f"    {owner.id} drains {gained} -> "
                            f"{owner.hp}/{owner.max_hp} HP")

    def fire_eye_rays(self, actor: Combatant) -> None:
        """Fire `eye_ray_count` distinct random rays (seeded) at visible foes in range."""
        rays = list(actor.md.eye_rays)
        enemies = [e for e in self.enemies_of(actor)
                   if self.dist(actor, e) <= actor.md.eye_ray_range
                   and self.cover_ac(actor, e) is not None]
        if not rays or not enemies:
            return
        pool = rays[:]
        chosen = []
        for _ in range(min(actor.md.eye_ray_count, len(pool))):
            chosen.append(pool.pop(self.rng.randint(0, len(pool) - 1)))
        self.log.append(f"  {actor.id} fires {len(chosen)} eye rays!")
        for i, ray in enumerate(chosen):
            target = enemies[i % len(enemies)]
            if not target.alive:
                continue
            self.emit(kind="attack", actor=actor.id, info=target.id,
                      dtype="ranged", amount=1)      # replay draws the ray
            important = (ray.condition in ("paralyzed", "petrified")
                         or (ray.damage is not None and ray.damage.average() >= 20))
            saved = saving_throw(target, ray.ability, ray.dc, self.rng,
                                 important=important, log=self.log,
                                 vs=ray.condition or None)
            self.log.append(f"    {ray.name} vs {target.id}: "
                            f"{'save' if saved else 'FAIL'}")
            if ray.damage is not None:
                amt = ray.damage.roll(self.rng)
                if saved and ray.half_on_save:
                    amt //= 2
                apply_damage(target, amt, ray.damage.type, self.log, self.rng, enc=self)
            already = bool(ray.escalates_to and target.has(ray.escalates_to))
            if not saved and ray.condition and target.alive and not already:
                apply_condition(target, ray.condition, actor.id, self.rng, self.log,
                                save_ability=ray.ability if ray.save_ends else None,
                                save_dc=ray.dc if ray.save_ends else 0,
                                escalates_to=ray.escalates_to or None)

    def sweep_death_bursts(self) -> None:
        """Trigger any pending on-death AoEs (chains until none remain). The burst
        effect itself is the `death_burst` handler in triggers.py."""
        h = triggers.handler_for("death_burst", "on_death")
        again = True
        while again:
            again = False
            for c in list(self.combatants.values()):
                if c.hp <= 0 and not c.burst_done and c.md.death_burst is not None:
                    c.burst_done = True
                    again = True
                    if h:
                        h(self, c, {})

    def _do_frightful_presence(self, actor: Combatant) -> None:
        fp = actor.md.frightful_presence
        actor.frightful_used = True
        self.log.append(f"  {actor.id} unleashes Frightful Presence (DC {fp.dc})")
        for e in self.enemies_of(actor):
            if self.dist(actor, e) > fp.size:
                continue
            if saving_throw(e, fp.save, fp.dc, self.rng, log=self.log, vs="frightened"):
                continue
            apply_condition(e, "frightened", actor.id, self.rng, self.log,
                            save_ability=fp.save, save_dc=fp.dc)

    def apply_fall(self, c: Combatant) -> None:
        """A creature shoved into a chasm falls. Standard rules: 1d6 bludgeoning per 10 ft
        fallen, capped at 20d6 (a 200 ft fall); falls under 10 ft deal no damage and don't
        knock prone; an endless (bottomless) drop simply removes the creature."""
        if c.md.fly > 0:
            return                          # a flyer over a chasm doesn't fall
        depth = max((self.grid.chasm.get(s, 0) for s in c.occupied_squares()), default=0)
        if depth >= BOTTOMLESS:
            c.hp = 0
            self.emit(kind="death", actor=c.id, dtype="fall")
            self.log.append(f"  {c.id} falls into the bottomless chasm and is lost!")
            return
        if depth < 10:
            return                          # too short a drop to hurt or knock prone
        dice = min(depth // 10, MAX_FALL_DICE)   # 1d6 per 10 ft, capped at 20d6
        self.log.append(f"  {c.id} falls {depth} ft into the pit!")
        apply_damage(c, self.rng.roll(dice, 6), "bludgeoning", self.log, self.rng, enc=self)
        if c.alive:
            apply_condition(c, "prone", c.id, self.rng, self.log)
            c.alt = -float(depth)           # now at the bottom of the pit

    def _do_grapple(self, actor: Combatant, target: Combatant) -> None:
        if contest(self.rng, actor, Ability.STR, target, (Ability.STR, Ability.DEX)):
            apply_condition(target, "grappled", actor.id, self.rng, self.log)
        else:
            self.log.append(f"  {actor.id} fails to grapple {target.id}")

    def _do_swallow(self, actor: Combatant, target: Combatant) -> None:
        """Gulp a grappled foe whole: it is blinded + restrained inside, takes acid each
        of its turns, and has total cover (see enumerate_options)."""
        target.swallowed_by = actor.id
        target.pos = actor.pos                          # it rides along inside
        apply_condition(target, "blinded", actor.id, self.rng, self.log)
        apply_condition(target, "restrained", actor.id, self.rng, self.log)
        self.log.append(f"  ** {actor.id} SWALLOWS {target.id} whole! **")
        self.emit(kind="condition", actor=target.id, source=actor.id, info="swallowed")

    def _release_swallowed(self, captor: Combatant) -> None:
        """Free everyone a creature has swallowed (it died or regurgitated)."""
        if captor is None:
            return
        for c in self.combatants.values():
            if c.swallowed_by == captor.id and c.alive:
                c.swallowed_by = None
                c.conditions.pop("blinded", None)
                c.conditions.pop("restrained", None)
                cleanup_implied(c)
                apply_condition(c, "prone", captor.id, self.rng, self.log, duration=1)
                self.log.append(f"  {c.id} is expelled from {captor.id}, prone")

    def _do_shove(self, actor: Combatant, target: Combatant) -> None:
        if contest(self.rng, actor, Ability.STR, target, (Ability.STR, Ability.DEX)):
            apply_condition(target, "prone", actor.id, self.rng, self.log, duration=1)
        else:
            self.log.append(f"  {actor.id} fails to shove {target.id}")

    def force_move(self, actor: Combatant, target: Combatant, ft: int,
                   toward: bool = False) -> None:
        """Forced movement from a rider/area (push away or pull toward `actor`), along a clear
        path; walls/creatures stop it and a chasm makes it fall. Reuses the spell push primitive."""
        cast._push(self, actor, target, ft, toward=toward)

    def _do_escape(self, actor: Combatant) -> None:
        g = actor.conditions.get("grappled")
        grappler = self.combatants.get(g.source_id) if g else None
        if grappler is None:
            actor.conditions.pop("grappled", None)
            return
        best = (Ability.STR if actor.md.mod(Ability.STR) >= actor.md.mod(Ability.DEX)
                else Ability.DEX)
        if contest(self.rng, actor, best, grappler, (Ability.STR,)):
            actor.conditions.pop("grappled", None)
            self.log.append(f"  {actor.id} escapes the grapple")
        else:
            self.log.append(f"  {actor.id} fails to escape the grapple")

    def _do_offhand(self, actor: Combatant, target: Combatant, name: str) -> None:
        """Bonus-action off-hand attack — resolved in place (no extra movement)."""
        atk = actor.attacks.get(name)
        if atk is None or target is None or not target.alive:
            return
        reach = atk.reach if atk.kind == "melee" else (atk.range_long or atk.range_normal)
        if self.dist(actor, target) > reach:
            return
        cover = self._cover_ac(actor, target)
        if cover is None:
            return
        resolve_attack(actor, target, atk, self.rng, self.log, cover_ac=cover,
                       flanking=self._positional_advantage(actor, target, atk.kind),
                       enc=self)

    def _passive_perception(self, c: Combatant) -> int:
        return skills.passive_score(c, "Perception")

    def _do_hide(self, actor: Combatant) -> None:
        enemies = self.enemies_of(actor)
        if any(can_sense(e) for e in enemies):     # blindsight/truesight see through it
            self.log.append(f"  {actor.id} can't hide (a foe perceives it)")
            return
        roll = (skills.reliable_roll(actor, "Stealth", self.rng.d20()[0])
                + skills.skill_modifier(actor, "Stealth"))
        if all(roll >= self._passive_perception(e) for e in enemies):
            actor.hidden = True
            self.log.append(f"  {actor.id} hides (Stealth {roll})")
        else:
            self.log.append(f"  {actor.id} fails to hide (Stealth {roll})")

    def _do_area(self, actor: Combatant, target: Combatant, area: AreaDef) -> None:
        dest = self._choose_destination(actor, target, "ranged", area.origin_range)
        self._do_move(actor, dest, SAFE_ALT if actor.md.fly > 0 else actor.alt)
        if not actor.alive:
            return
        actor.area_ready[area.name] = area.recharge_min == 0
        cells = self._area_cells(actor.pos, target.pos, area)
        self._apply_area(actor, area, cells)

    # -- legendary & lair actions ----------------------------------------
    def lair_actions(self) -> None:
        """Initiative-count-20 lair actions, once at the top of each round."""
        for owner in list(self.combatants.values()):
            if not owner.alive or owner.incapacitated or owner.md.lair_action is None:
                continue   # can't take lair actions while incapacitated (5e)
            if owner.name not in self.lair_names:
                continue   # not fighting in its lair (per-creature scenario toggle)
            area = owner.md.lair_action
            if area.recharge_min and not owner.area_ready.get(area.name, True):
                continue
            enemies = self.enemies_of(owner)
            if not enemies:
                continue
            center = max(enemies, key=lambda e: self._cluster_size(owner, e.pos))
            self.log.append(f"  ~~ Lair action ({area.name}) ~~")
            self._apply_area(owner, area, self._area_cells(owner.pos, center.pos, area))
            owner.area_ready[area.name] = area.recharge_min == 0

    def _cluster_size(self, owner: Combatant, pos: tuple[int, int],
                      radius: int = 2) -> int:
        return sum(1 for e in self.enemies_of(owner)
                   if min(chebyshev(pos, s) for s in e.occupied_squares()) <= radius)

    def legendary_actions_after(self, just_acted: Combatant) -> None:
        """After another creature's turn, legendary creatures may spend an action."""
        for legend in list(self.combatants.values()):
            if (not legend.alive or legend.incapacitated or legend.id == just_acted.id
                    or legend.legendary_actions_left <= 0):
                continue   # incapacitated creatures can't take legendary actions (5e)
            tgt = self._nearest_living_enemy(legend)
            if tgt is None:
                continue
            wing = legend.md.legendary_wing
            # 2-cost Wing Attack: clears clustered foes and lifts the dragon aloft
            wing_targets = (sum(1 for e in self.enemies_of(legend)
                                if self.dist(legend, e) <= wing.size) if wing else 0)
            if (wing is not None and legend.legendary_actions_left >= 2
                    and wing_targets >= 2):
                legend.legendary_actions_left -= 2
                self.log.append(f"  ~ {legend.id} legendary action: {wing.name} "
                                f"({legend.legendary_actions_left} left)")
                self._apply_area(legend, wing, self._area_cells(legend.pos, legend.pos, wing))
                if legend.md.fly > 0:
                    legend.alt = SAFE_ALT      # the dragon flies up to half its speed
                continue
            atk = legend.md.attacks.get(legend.md.legendary_attack)
            if atk is None or self.dist(legend, tgt) > atk.reach:
                continue   # save the action rather than waste it out of reach
            legend.legendary_actions_left -= 1
            self.log.append(f"  ~ {legend.id} legendary action: {atk.name} vs {tgt.id} "
                            f"({legend.legendary_actions_left} left)")
            resolve_attack(legend, tgt, atk, self.rng, self.log,
                           flanking=self._positional_advantage(legend, tgt, "melee"),
                           enc=self, reckless_ok=False)   # legendary action, not its Attack action

    def apply(self, actor: Combatant, opt: Option) -> None:
        if opt.kind == "dodge":
            actor.dodging = True
            self.log.append(f"  {actor.id} Dodges")
            return
        target = self.combatants.get(opt.target_id) if opt.target_id else None
        if opt.kind == "swallow":
            self._do_swallow(actor, target)
            return
        if opt.kind == "advance":
            self._do_move(actor, self._choose_destination(actor, target, "melee", 5))
            return
        if opt.kind == "dash":
            actor.dashing = True
            self._do_move(actor, self._choose_destination(actor, target, "melee", 5))
            actor.dashing = False
            return
        if opt.kind == "teleport":
            dest = self._teleport_destination(actor, target)
            if dest != actor.pos:
                self.log.append(f"  {actor.id} teleports {actor.pos} -> {dest}")
                actor.pos = dest                     # teleport: no path, no OA
                self.emit(kind="move", actor=actor.id, pos=dest, alt=actor.alt)
            return
        if opt.kind == "disengage":
            actor.disengaging = True
            if actor.can_move:
                reach = self.grid.reachable(actor.pos, actor.footprint,
                                            self._move_budget(actor), self._blocked(actor),
                                            **self._reach_kwargs(actor))
                self._do_move(actor, max(reach, key=lambda s:
                                         self._dist_nearest_enemy(actor, s)))
            return
        if opt.kind == "grapple":
            self._do_grapple(actor, target)
            return
        if opt.kind == "shove":
            self._do_shove(actor, target)
            return
        if opt.kind == "escape":
            self._do_escape(actor)
            return
        if opt.kind == "offhand":
            self._do_offhand(actor, target, opt.name)
            return
        if opt.kind == "help":
            target.help_advantage = True
            self.log.append(f"  {actor.id} Helps {target.id} (advantage on its next attack)")
            return
        if opt.kind == "hide":
            self._do_hide(actor)
            return
        if opt.kind == "ready":
            actor.readied_attack = opt.name
            self.log.append(f"  {actor.id} readies {opt.name}")
            return
        if opt.kind == "eye_rays":
            self.fire_eye_rays(actor)
            return
        if opt.kind == "quaff":
            self._do_quaff(actor, opt.name)
            return
        if opt.kind == "second_wind":
            self._do_second_wind(actor)
            return
        if opt.kind == "rage":                       # Barbarian Rage (bonus action)
            self._do_rage(actor)
            return
        if opt.kind == "flurry":                     # Monk Flurry of Blows (1 Ki, two strikes)
            self._do_flurry(actor, target)
            return
        if opt.kind == "patient_defense":            # Monk Patient Defense (1 Ki, Dodge)
            self._do_patient_defense(actor)
            return
        if opt.kind == "war_magic":                  # Eldritch Knight: bonus weapon attack
            self._do_offhand(actor, target, opt.name)
            return
        if opt.kind == "polearm":                    # Polearm Master: bonus butt-end (1d4)
            self._do_polearm(actor, target)
            return
        if opt.kind == "hypnotic_gaze":
            self._do_hypnotic_gaze(actor, target)
            return
        if opt.kind == "turn_undead":                # Cleric Channel Divinity: Turn Undead
            self._do_turn_undead(actor)
            return
        if opt.kind == "preserve_life":              # Life Domain Channel Divinity: Preserve Life
            self._do_preserve_life(actor)
            return
        if opt.kind == "lay_on_hands":               # Paladin Lay on Hands (pool heal)
            self._do_lay_on_hands(actor, target)
            return
        if opt.kind == "sacred_weapon":              # Oath of Devotion Channel Divinity
            self._do_sacred_weapon(actor)
            return
        if opt.kind == "vow":                        # Oath of Vengeance Channel Divinity
            self._do_vow(actor, target)
            return
        if opt.kind == "war_priest":                 # War Domain: bonus weapon attack
            actor.resources["War Priest"] = actor.resources.get("War Priest", 0) - 1
            self._do_offhand(actor, target, opt.name)
            return
        if opt.kind == "bardic_inspiration":         # Bard: bank an inspiration die on an ally
            self._do_bardic_inspiration(actor, target)
            return
        if opt.kind == "wild_shape":                 # Druid: assume a beast form
            self._do_wild_shape(actor, opt.name)
            return
        if opt.kind == "moon_heal":                  # Circle of the Moon: slot -> HP in form
            self._do_moon_heal(actor, opt.slot_level)
            return
        if opt.kind == "quicken":                    # Sorcerer Metamagic: Quickened Spell (2 pts)
            actor.resources["Sorcery Points"] = actor.resources.get("Sorcery Points", 0) - 2
            self.log.append(f"  {actor.id} quickens {opt.name} (2 sorcery points)")
            cast.cast(self, actor, opt)
            return
        if opt.kind == "action_surge":
            actor.resources["Action Surge"] -= 1
            self.log.append(f"  {actor.id} uses Action Surge (extra action)")
            return
        if opt.kind == "frighten":
            self._do_frightful_presence(actor)
            return
        if opt.kind == "spell":
            cast.cast(self, actor, opt)
            return
        if opt.kind == "area":
            area = next(a for a in actor.md.areas if a.name == opt.name)
            self._do_area(actor, target, area)
        else:
            self._do_attack_action(actor, target, opt.name)

    # -- turn / round loop -----------------------------------------------
    def roll_death_save(self, c: Combatant) -> None:
        """A dying creature's turn: a raw d20 death saving throw (no modifiers). 10+ succeeds,
        nat 20 revives at 1 HP, nat 1 is two failures; 3 successes stabilize, 3 failures die."""
        if c.stable or not c.dying:
            return
        roll = self.rng.d20()[0]
        if roll == 20:
            c.wake_from_dying()
            c.hp = 1
            self.log.append(f"  {c.id} death save: NAT 20 — regains 1 HP!")
            return
        if roll == 1:
            c.death_failures += 2
        elif roll >= 10:
            c.death_successes += 1
        else:
            c.death_failures += 1
        self.log.append(f"  {c.id} death save: {roll} "
                        f"({c.death_successes} successes / {c.death_failures} failures)")
        if c.death_failures >= 3:
            c.dying = False
            c.dead = True
            self.emit(kind="death", actor=c.id)
            self._release_swallowed(c)
            self.log.append(f"  *** {c.id} dies (3 death-save failures) ***")
        elif c.death_successes >= 3:
            c.dying = False
            c.stable = True
            self.log.append(f"  {c.id} is stable (unconscious)")

    def start_of_turn(self, actor: Combatant) -> None:
        self.emit(kind="turn_start", actor=actor.id)
        actor.dodging = False
        if actor.md.survivor and 0 < actor.hp <= actor.max_hp // 2:   # Champion Survivor
            heal = 5 + actor.md.mod(Ability.CON)
            actor.hp = min(actor.max_hp, actor.hp + heal)
            self.log.append(f"  {actor.id} regains {heal} HP (Survivor)")
        # drowning: an air-breather underwater runs out of held breath and drops to 0
        if self.underwater and actor.breath_rounds is not None and actor.alive:
            actor.breath_rounds -= 1
            if actor.breath_rounds <= 0:
                actor.hp = 0
                self.emit(kind="death", actor=actor.id, dtype="suffocation")
                self.log.append(f"  {actor.id} runs out of air and drowns!")
                if actor.concentration is not None:
                    break_concentration(actor, self.log, "drowned", enc=self)
                return
        # swallowed: ride along inside the captor, take acid, reset the escape counter
        if actor.swallowed_by:
            cap = self.combatants.get(actor.swallowed_by)
            if cap and cap.alive:
                actor.pos = cap.pos
                actor.captor_damage = 0
                sw = cap.md.swallow
                if sw is not None and actor.alive:
                    self.log.append(f"  {actor.id} is digested inside {cap.id}")
                    apply_damage(actor, sw.acid.roll(self.rng), sw.acid.type,
                                 self.log, self.rng, enc=self)
        self.enforce_flight(actor)                  # a downed/stunned flyer falls now
        actor.reaction_available = not actor.surprised   # no reactions until surprise ends
        actor.readied_attack = None                 # readied action lapses on your turn
        actor.auras_taken_this_turn = set()         # reset per-turn aura tracking
        actor.moved_this_turn = 0.0                  # reset distance moved (Pounce/Charge)
        actor.maneuver_used = False                  # Battle Master: one maneuver per turn
        actor.savage_used = False                    # Savage Attacker: one reroll per turn
        actor.movement_halted = False                # Sentinel speed-0 lasts one turn
        actor.attacked_this_turn = set()             # Mobile: reset melee'd-foe tracking
        actor.reckless_active = False                # Reckless lasts until your next turn
        actor.took_attack_action = False             # Monk bonus-strike gate (took the Attack action)
        actor.stunning_used = False                  # Monk Stunning Strike: one per turn
        actor.smites_this_turn = 0                    # Paladin Divine Smite: reset the per-turn spend budget
        actor.gwm_bonus_ready = False                # Great Weapon Master bonus attack: fresh each turn
        if actor.raging and actor.incapacitated:     # Rage ends if the barbarian is incapacitated
            actor.raging = False
            self.log.append(f"  {actor.id}'s rage ends (incapacitated)")
        # refresh once-per-turn conditional riders (Sneak Attack, Martial Advantage). Reset
        # on the owner's own turn only — a reaction-attack proc between its turns is a rare
        # legal extra we intentionally forgo (conservative; never over-applies).
        actor.bonus_damage_used = set()
        actor.dashing = actor.disengaging = False   # per-action movement flags
        actor.cast_leveled_this_turn = False         # bonus-action spell rule
        actor.cast_cantrip_this_turn = False         # Eldritch Knight War Magic
        actor.action_used = actor.bonus_used = False
        # refresh squeezing in case the blocking space opened/closed since last move
        actor.squeezing = (actor.footprint > 1 and not self.grid.footprint_fits(
            actor.pos, actor.footprint, self._blocked(actor)))
        # release a grapple whose grappler is gone, incapacitated, or out of reach
        g = actor.conditions.get("grappled")
        if g is not None:
            gr = self.combatants.get(g.source_id)
            if gr is None or not gr.alive or gr.incapacitated or self.dist(actor, gr) > 5:
                actor.conditions.pop("grappled", None)
                self.log.append(f"  {actor.id} is no longer grappled")
        actor.legendary_actions_left = actor.md.legendary_actions   # refresh the pool
        # re-aim a movable aura (Moonbeam) toward the densest enemy cluster,
        # limited to a 60 ft (12-square) move and scored at the aura's own radius.
        # Moving it costs an action, so not while surprised/incapacitated.
        if (actor.aura is not None and actor.aura.anchor == "point"
                and not (actor.aura.silence or actor.aura.antimagic)  # fixed-point zones don't move
                and not actor.surprised and can_act(actor)):
            enemies = self.enemies_of(actor)
            if enemies:
                radius = max(1, actor.aura.size // 5)
                target = max(enemies, key=lambda e: self._cluster_size(actor, e.pos, radius))
                px, py = actor.aura.point
                dx = max(-12, min(12, target.pos[0] - px))
                dy = max(-12, min(12, target.pos[1] - py))
                actor.aura.point = (px + dx, py + dy)
        # regeneration
        if actor.md.regen > 0 and actor.alive and actor.hp < actor.max_hp \
                and not actor.regen_disabled and can_heal(actor):
            actor.hp = min(actor.max_hp, actor.hp + actor.md.regen)
            self.emit(kind="heal", actor=actor.id, amount=actor.md.regen, hp=actor.hp)
            self.log.append(f"  {actor.id} regenerates -> {actor.hp}/{actor.max_hp}")
        actor.regen_disabled = False
        # recharge area abilities (incl. a recharge-tagged lair action)
        rechargeable = list(actor.md.areas)
        if actor.md.lair_action is not None:
            rechargeable.append(actor.md.lair_action)
        for area in rechargeable:
            if area.recharge_min and not actor.area_ready.get(area.name, False):
                if self.rng.d(6) >= area.recharge_min:
                    actor.area_ready[area.name] = True
                    self.log.append(f"  {actor.id}'s {area.name} recharges")

    def _fearless(self, c: Combatant) -> bool:
        return (c.md.fearless or c.md.abilities.get(Ability.INT, 10) <= 2
                or c.md.mtype in ("undead", "construct", "ooze", "plant"))

    def _at_edge(self, pos: tuple[int, int]) -> bool:
        return (pos[0] <= 0 or pos[1] <= 0
                or pos[0] >= self.grid.width - 1 or pos[1] >= self.grid.height - 1)

    def _flee(self, actor: Combatant) -> None:
        """A routed creature runs for the nearest edge and escapes off the map."""
        if self._at_edge(actor.pos):
            actor.fled = True
            self.log.append(f"  {actor.id} escapes the battle!")
            self.emit(kind="flee", actor=actor.id, pos=actor.pos)
            return
        if not actor.can_move:
            self.log.append(f"  {actor.id} is routed but cannot move")
            return
        actor.disengaging = actor.dashing = True   # flee without provoking, at double speed
        reach = self.grid.reachable(actor.pos, actor.footprint, self._move_budget(actor),
                                    self._blocked(actor), **self._reach_kwargs(actor))
        actor.dashing = False

        def border_dist(s):
            return min(s[0], s[1], self.grid.width - 1 - s[0], self.grid.height - 1 - s[1])

        self._do_move(actor, min(reach, key=border_dist))
        if self._at_edge(actor.pos):
            actor.fled = True
            self.log.append(f"  {actor.id} escapes the battle!")
            self.emit(kind="flee", actor=actor.id, pos=actor.pos)
        else:
            self.log.append(f"  {actor.id} flees toward the edge")

    def take_turn(self, actor: Combatant, controller) -> None:
        if not actor.in_combat:
            return
        self.start_of_turn(actor)
        self._apply_auras_start_of_turn(actor)
        if actor.alive:
            self._apply_zones_start_of_turn(actor)   # spell terrain (Wall of Fire, ...)
        if not actor.alive:                     # an aura/zone may have dropped it
            return
        self.log.append(f"-- {actor.id} ({actor.name}) turn "
                        f"[{actor.hp}/{actor.max_hp} HP @ {actor.pos}]"
                        + (f" {list(actor.conditions)}" if actor.conditions else ""))
        # morale: one check the first time it is bloodied (unless fearless)
        if (not actor.routed and not actor.morale_checked and actor.bloodied
                and not self._fearless(actor)):
            actor.morale_checked = True
            if not saving_throw(actor, Ability.WIS, MORALE_DC, self.rng, log=self.log):
                actor.routed = True
                self.log.append(f"  {actor.id}'s morale breaks — it flees!")
        if actor.routed:
            self._flee(actor)
        elif actor.surprised:
            self.log.append(f"  {actor.id} is surprised, no action")
            actor.surprised = False             # surprise ends after this (skipped) turn
            actor.reaction_available = True     # ...and reactions are restored once it ends
        elif actor.incapacitated:
            self.log.append(f"  {actor.id} is incapacitated, no action")
        else:
            self.fire_turn(actor, "on_turn_start")   # e.g. Orc Aggressive (bonus move)
            # action phase — Fighter Action Surge can grant one (or more) extra actions
            extra = 0
            for _ in range(3):                        # 1 action + up to 2 surges (safety cap)
                if not actor.in_combat or actor.incapacitated:
                    break
                choice = controller.decide(self, actor, self.enumerate_options(actor))
                if choice.kind == "action_surge":     # free: grants an action, doesn't spend one
                    self.apply(actor, choice)
                    extra += 1
                    continue
                self.apply(actor, choice)
                actor.action_used = True
                if extra <= 0:
                    break
                extra -= 1
            # bonus-action phase (bonus-cast spells, off-hand attack, or pass)
            if actor.alive and not actor.incapacitated:
                bopts = self.enumerate_bonus_options(actor)
                if len(bopts) > 1:                  # something beyond "pass"
                    bchoice = controller.decide(self, actor, bopts)
                    if bchoice.kind != "pass":
                        self.apply(actor, bchoice)
                        actor.bonus_used = True
        # regurgitation: enough damage from inside forces the captor to spit it out
        if actor.swallowed_by:
            cap = self.combatants.get(actor.swallowed_by)
            sw = cap.md.swallow if (cap and cap.alive) else None
            if sw is not None and actor.captor_damage >= sw.escape_threshold:
                if not saving_throw(cap, Ability.CON, sw.escape_dc, self.rng, log=self.log):
                    self.log.append(f"  {cap.id} retches and regurgitates!")
                    self._release_swallowed(cap)
        self.fire_turn(actor, "on_turn_end")
        # Incorporeal Movement: 1d10 force if it ends its turn inside an object (a wall)
        if actor.md.incorporeal and actor.alive and any(
                s in self.grid.walls for s in actor.occupied_squares()):
            apply_damage(actor, self.rng.roll(1, 10), "force", self.log, self.rng, enc=self)
            self.log.append(f"  {actor.id} takes force damage for ending inside an object")
        tick_conditions_end_of_turn(actor, self.rng, self.log)
        tick_effects_end_of_turn(actor)
        actor.absorb_rider = None       # Absorb Elements lasts only through this, your next turn
        if actor.concentration is not None:
            actor.concentration.duration -= 1
            if actor.concentration.duration <= 0:
                break_concentration(actor, self.log, "duration ended", enc=self)
        if actor.summon_duration is not None:
            actor.summon_duration -= 1
            if actor.summon_duration <= 0:
                actor.hp = 0
                self.emit(kind="death", actor=actor.id, dtype="expired")
                self.log.append(f"  {actor.id} vanishes (summon duration ended)")

    def run(self, controllers: dict) -> str | None:
        """controllers: maps team name -> Controller. Returns winning team."""
        self._controllers = controllers      # exposes each team's controller to policy hooks (smite)
        self.roll_initiative()
        while not self.over():
            self.round += 1
            self.log.append(f"\n=== Round {self.round} ===")
            for z in list(self.zones):          # expire spell terrain
                z.duration -= 1
                if z.duration <= 0:
                    self.zones.remove(z)
                    self.log.append(f"  {z.name} fades")
            if self.weather in ("rain", "wind"):
                self._douse_flames()            # rain/wind extinguish open flames
            else:
                self._spread_fire()             # flammable terrain (grease) ignites
            self.lair_actions()                 # initiative count 20
            self.sweep_death_bursts()
            if self.over():
                break
            for cid in list(self.order):        # snapshot: summons created mid-round act next round
                actor = self.combatants.get(cid)
                if actor is None or not actor.in_combat:
                    if actor is not None and actor.dying:
                        self.roll_death_save(actor)     # a downed creature's turn = a death save
                    continue
                self.take_turn(actor, controllers[actor.team])
                self.sweep_death_bursts()
                if self.over():
                    break
                self.legendary_actions_after(actor)
                self.sweep_death_bursts()
                if self.over():
                    break
        w = self.winner()
        self.log.append(f"\n### Winner: {w or 'draw'} (round {self.round}) ###")
        return w
