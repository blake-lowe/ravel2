"""The Supertemporal Arena run-state machine (SPEC 18.8, ROADMAP Slice 12e).

A roguelite auto-battler run — shop, deploy, battle, wheel — as a pure, seeded
state machine: state + action in, state + result out. Every random draw comes
from a counter-derived `RNG`, so the whole state (RNG included) serializes to a
plain dict and a fixed seed + action script reproduces a run exactly. Battles
resolve through `ravel.sim` with the heuristic controller on both sides; the
web layer (`web/fortune.py`) is a thin wrapper and owns all IO.

Fortune's Wheel flavor: Shemeshka presides; each battle won earns one spin of
the three-ring wheel (SPEC 18.8.8). Time runs fast here — the presentation
counts a round of combat as ten years.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .calib import XP_BY_CR
from .dice import RNG
from .maps import MAPS
from .models import MonsterDef
from .sim import BattleResult, run_battle

# --- Tuning constants (the numbers in SPEC 18.8) ----------------------------

TEAM_CAP = 5                   # creatures that take the field
STANDBY_SLOTS = 1              # one stall sits out the battle
STABLE_CAP = TEAM_CAP + STANDBY_SLOTS
LIVES_START = 3
START_PURSE_CP = 1000          # 10 gp
INCOME_CP = 1000               # +10 gp per shop phase
REROLL_CP = 50                 # 5 sp
SCOUT_CP = 50                  # 5 sp divines tonight's opposition
MONSTER_SLOTS = 5
ITEM_SLOTS = 2
ITEM_CAP = 3                   # items a single monster can carry
BASE_PRICE_CP = 300            # 3 gp x playtested CR / shop tier (SPEC 18.8.4)
PRICE_FLOOR_CP = 5             # even a commoner costs pocket change
TRAIN_AC, TRAIN_HP = 1, 1      # per elite level
ITEM_PRICE_CP = {"common": 200, "uncommon": 400, "rare": 600}
ENEMY_BUDGET_FRAC = 0.75
BOSS_BUDGET_MULT = 1.5         # a lone boss buys action economy with bulk
WEATHERS = ("clear", "clear", "clear", "clear", "fog", "rain", "wind")
YEARS_PER_COMBAT_ROUND = 10    # the Supertemporal conceit

# The wheel's ring layouts, sector 1..10 (SPEC 18.8.8). Odds: outer 3 none /
# 6 common / 1 advance; middle 1 none / 8 uncommon / 1 advance; center all rare.
# No-prize sectors are spread to opposite sides of the wheel, never bunched.
OUTER_RING = ("none", "common", "common", "none", "common", "common",
              "none", "common", "common", "advance")
MIDDLE_RING = ("uncommon", "uncommon", "uncommon", "uncommon", "none",
               "uncommon", "uncommon", "uncommon", "uncommon", "advance")


def cr_cap(round_no: int) -> int:
    """The shop/enemy CR ceiling before battle `round_no`: +1 every 2 battles."""
    return 1 + (round_no - 1) // 2


def enemy_size(round_no: int) -> int:
    return min(TEAM_CAP, 2 + (round_no + 1) // 2)


def is_boss_round(round_no: int) -> bool:
    """Every other stock-tier increase is a boss night: the cap rises on rounds
    3, 5, 7, ... and every second rise (3, 7, 11, ...) sends a single huge
    monster, XP-matched to the round's whole team budget (SPEC 18.8.9)."""
    return round_no >= 3 and (round_no - 3) % 4 == 0


def _xp_of_cr(cr: float) -> float:
    if cr in XP_BY_CR:
        return float(XP_BY_CR[cr])
    below = max((c for c in XP_BY_CR if c <= cr), default=0)
    return float(XP_BY_CR[below])


# --- Items (kit boons): pure stat-block deltas -------------------------------

@dataclass(frozen=True)
class ArenaItem:
    name: str
    rarity: str                # common | uncommon | rare
    ac: int = 0
    hp: int = 0
    hit: int = 0
    dmg: int = 0
    speed: int = 0
    effect: str = ""           # the mechanics, plainly stated
    blurb: str = ""            # the flavor, italicized on the shelf


ITEMS: dict[str, ArenaItem] = {i.name: i for i in [
    # common — 2 gp on the shelf
    ArenaItem("Whetstone of the Great Foundry", "common", dmg=1,
              effect="+1 damage",
              blurb="Sparks from Sigil's foundry never quite go out."),
    ArenaItem("Rust-Ward Talisman", "common", ac=1,
              effect="+1 AC",
              blurb="Proof against rust dragons and worse."),
    ArenaItem("Flask of Elemental Vigor", "common", hp=5,
              effect="+5 HP",
              blurb="Bottled at the edge of the Chaos."),
    ArenaItem("Quicksilver Anklet", "common", speed=10,
              effect="+10 ft. speed",
              blurb="It remembers being a modron's gear."),
    # uncommon — 4 gp on the shelf
    ArenaItem("Oil of Keen Edges", "uncommon", hit=1, dmg=1,
              effect="+1 to hit, +1 damage",
              blurb="Bladelings swear by it."),
    ArenaItem("Bytopian Shield-Charm", "uncommon", ac=1, hp=5,
              effect="+1 AC, +5 HP",
              blurb="Honest gnomish work."),
    ArenaItem("Heart of the Gray Waste", "uncommon", hp=15,
              effect="+15 HP",
              blurb="It beats, slowly, joylessly."),
    ArenaItem("Githzerai Focus Bead", "uncommon", hit=2,
              effect="+2 to hit",
              blurb="Stillness, then the strike."),
    # rare — the wheel's center ring only
    ArenaItem("Razorvine Edge", "rare", hit=2, dmg=2,
              effect="+2 to hit, +2 damage",
              blurb="Pruned from the Lady's own ward."),
    ArenaItem("Modron Chassis Plating", "rare", ac=2, hp=10,
              effect="+2 AC, +10 HP",
              blurb="Salvage from the Great March."),
    ArenaItem("Planar Heartstone", "rare", hp=30,
              effect="+30 HP",
              blurb="A gate-key that chose flesh instead."),
    ArenaItem("Shemeshka's Favor", "rare", hit=1, dmg=1, ac=1, hp=10,
              effect="+1 to hit, +1 damage, +1 AC, +10 HP",
              blurb="The King of the Cross-Trade smiles. Worry later."),
]}

COMMON_ITEMS = tuple(sorted(n for n, i in ITEMS.items() if i.rarity == "common"))
UNCOMMON_ITEMS = tuple(sorted(n for n, i in ITEMS.items() if i.rarity == "uncommon"))
RARE_ITEMS = tuple(sorted(n for n, i in ITEMS.items() if i.rarity == "rare"))


def apply_kit(md: MonsterDef, elite: int = 0, items: tuple[str, ...] = ()) -> MonsterDef:
    """Return a MonsterDef with training (+1 AC/+1 HP per elite level, SPEC 18.8.7)
    and item deltas applied. +dmg lands on the first damage component of each attack
    so multi-rider attacks don't multiply the boon. Name gains one ★ per level."""
    ac = elite * TRAIN_AC + sum(ITEMS[n].ac for n in items)
    hp = elite * TRAIN_HP + sum(ITEMS[n].hp for n in items)
    hit = sum(ITEMS[n].hit for n in items)
    dmg = sum(ITEMS[n].dmg for n in items)
    speed = sum(ITEMS[n].speed for n in items)
    if not (ac or hp or hit or dmg or speed):
        return md
    attacks = md.attacks
    if hit or dmg:
        attacks = {}
        for name, atk in md.attacks.items():
            damage = atk.damage
            if dmg and damage:
                first = replace(damage[0], bonus=damage[0].bonus + dmg)
                damage = (first,) + tuple(damage[1:])
            attacks[name] = replace(atk, attack_bonus=atk.attack_bonus + hit,
                                    damage=damage)
    stars = " " + "★" * elite if elite else ""
    return replace(md, name=md.name + stars, ac=md.ac + ac, hp=md.hp + hp,
                   speed=md.speed + speed, attacks=attacks)


# --- Currency ----------------------------------------------------------------

def coins(cp: int) -> str:
    """Render copper as gp/sp/cp change: 460 -> '4 gp 6 sp'."""
    gp, rest = divmod(max(0, cp), 100)
    sp, c = divmod(rest, 10)
    parts = ([f"{gp} gp"] if gp else []) + ([f"{sp} sp"] if sp else []) \
        + ([f"{c} cp"] if c else [])
    return " ".join(parts) or "0 cp"


# --- Injected catalog ----------------------------------------------------------

@dataclass(frozen=True)
class CatalogEntry:
    """One shoppable monster — plain data injected by the outer layer (the pure
    machine never reads the ratings DB itself)."""
    name: str
    cr: float
    source: str                       # book label: "MM" | "MPMM" | "Ravel" | ...
    best_cr: float | None = None      # refined/adjusted CR when playtested
    adjusted_xp: float | None = None


def price_cp(e: CatalogEntry, tier: int) -> int:
    """3 gp x the creature's playtested CR, divided by the shop tier — weaker
    stock gets cheaper as the nights wear on (SPEC 18.8.4)."""
    best = e.best_cr if e.best_cr is not None else e.cr
    return max(PRICE_FLOOR_CP, round(BASE_PRICE_CP * best / max(1, tier)))


# --- Run state -----------------------------------------------------------------

@dataclass
class ShopSlot:
    name: str                 # monster or item name
    price_cp: int
    frozen: bool = False


@dataclass
class StableMember:
    name: str
    elite: int = 0
    items: list[str] = field(default_factory=list)
    invested_cp: int = 0
    standby: bool = False          # in the standby stall: sits out the battle


class FortuneError(ValueError):
    """An illegal player action (not enough coin, full stable, wrong phase...)."""


PHASES = ("shop", "wheel", "over")


@dataclass
class FortuneRun:
    seed: int
    books: tuple[str, ...]
    catalog: dict[str, CatalogEntry]          # already filtered to `books`
    draws: int = 0                            # counter feeding every RNG draw
    round: int = 1                            # the upcoming battle's number
    wins: int = 0
    lives: int = LIVES_START
    purse_cp: int = START_PURSE_CP
    phase: str = "shop"
    stable: list[StableMember] = field(default_factory=list)
    shop_monsters: list[ShopSlot | None] = field(default_factory=list)
    shop_items: list[ShopSlot | None] = field(default_factory=list)
    bank: list[str] = field(default_factory=list)   # unattached wheel-won items
    history: list[dict] = field(default_factory=list)
    scouted: bool = False          # paid this round to see the opposing composition

    # -- randomness: one fresh RNG per draw, keyed by (seed, draws) --------------
    def _draw(self) -> RNG:
        rng = RNG((self.seed * 1_000_003 + self.draws * 7919 + 12345) & 0x7FFFFFFF)
        self.draws += 1
        return rng

    # -- pure per-round environment (previewable without touching state) --------
    def round_env(self, round_no: int) -> tuple[str | None, str]:
        """(map_name | None, weather) for a battle — a pure function of the seed,
        so the foresight queue (SPEC 18.8.12) costs nothing."""
        rng = RNG((self.seed * 104_729 + round_no * 15_485_863 + 7) & 0x7FFFFFFF)
        arenas = [None] + sorted(MAPS)
        return rng.choice(arenas), rng.choice(list(WEATHERS))

    def foresight(self, k: int = 3) -> list[dict]:
        return [{"round": r, "map": self.round_env(r)[0],
                 "weather": self.round_env(r)[1], "boss": is_boss_round(r)}
                for r in range(self.round, self.round + k)]

    def battle_seed(self, round_no: int) -> int:
        return (self.seed * 32_452_843 + round_no * 104_729 + 3) & 0x7FFFFFFF

    # -- shop ---------------------------------------------------------------------
    def cap(self) -> int:
        return cr_cap(self.round)

    def _band(self, cap: float) -> list[CatalogEntry]:
        """Entries at or under the cap — falling back to the cheapest CR band the
        selected books offer, so a pool never comes up empty mid-run."""
        ordered = [self.catalog[n] for n in sorted(self.catalog)]
        pool = [e for e in ordered if e.cr <= cap]
        if not pool and ordered:
            floor = min(e.cr for e in ordered)
            pool = [e for e in ordered if e.cr <= floor]
        return pool

    def _pool(self) -> list[CatalogEntry]:
        return self._band(self.cap())

    def _weighted_pick(self, rng: RNG, pool: list[CatalogEntry]) -> CatalogEntry:
        cap = self.cap()
        weights = []
        for e in pool:
            w = 1.0 / (1.0 + max(0.0, cap - e.cr))
            weights.append(max(1, int(w * 1000)))
        total = sum(weights)
        roll = rng.randint(1, total)
        acc = 0
        for e, w in zip(pool, weights):
            acc += w
            if roll <= acc:
                return e
        return pool[-1]

    def _roll_shop(self, keep_frozen: bool = True) -> None:
        pool = self._pool()
        if not pool:
            raise FortuneError("no monsters in the selected books at this CR")
        old_m = self.shop_monsters if keep_frozen else []
        old_i = self.shop_items if keep_frozen else []
        self.shop_monsters = []
        for i in range(MONSTER_SLOTS):
            prev = old_m[i] if i < len(old_m) else None
            if prev is not None and prev.frozen:
                self.shop_monsters.append(prev)
                continue
            e = self._weighted_pick(self._draw(), pool)
            self.shop_monsters.append(ShopSlot(e.name, price_cp(e, self.cap())))
        self.shop_items = []
        for i in range(ITEM_SLOTS):
            prev = old_i[i] if i < len(old_i) else None
            if prev is not None and prev.frozen:
                self.shop_items.append(prev)
                continue
            rng = self._draw()
            rarity = "uncommon" if rng.randint(1, 4) == 4 else "common"
            name = rng.choice(list(UNCOMMON_ITEMS if rarity == "uncommon"
                                   else COMMON_ITEMS))
            self.shop_items.append(ShopSlot(name, ITEM_PRICE_CP[rarity]))

    def _require(self, phase: str) -> None:
        if self.phase != phase:
            raise FortuneError(f"not in the {phase} phase (currently: {self.phase})")

    def _spend(self, cp: int) -> None:
        if cp > self.purse_cp:
            raise FortuneError(f"not enough coin: need {coins(cp)}, "
                               f"have {coins(self.purse_cp)}")
        self.purse_cp -= cp

    def reroll(self) -> None:
        self._require("shop")
        self._spend(REROLL_CP)
        self._roll_shop()

    def scout(self) -> None:
        """Divine the future (5 sp): the round's opposing composition is revealed
        until the battle is fought. The house sells everything, even secrets."""
        self._require("shop")
        if self.scouted:
            raise FortuneError("the pit hand already talked")
        self._spend(SCOUT_CP)
        self.scouted = True

    def toggle_freeze(self, kind: str, slot: int) -> None:
        self._require("shop")
        slots = self.shop_monsters if kind == "monster" else self.shop_items
        if not (0 <= slot < len(slots)) or slots[slot] is None:
            raise FortuneError("nothing in that slot")
        slots[slot].frozen = not slots[slot].frozen

    def buy(self, slot: int, train_into: int | None = None) -> None:
        """Buy the monster in shop slot `slot` — into a free stable slot, or merged
        straight onto owned copy `train_into` (dragging a dupe onto its twin)."""
        self._require("shop")
        if not (0 <= slot < len(self.shop_monsters)) or self.shop_monsters[slot] is None:
            raise FortuneError("nothing in that slot")
        s = self.shop_monsters[slot]
        if train_into is not None:
            if not (0 <= train_into < len(self.stable)):
                raise FortuneError("no such stable member")
            tgt = self.stable[train_into]
            if tgt.name != s.name:
                raise FortuneError(f"{s.name} can only train a {s.name}")
            self._spend(s.price_cp)
            tgt.elite += 1
            tgt.invested_cp += s.price_cp
        else:
            if len(self.stable) >= STABLE_CAP:
                raise FortuneError(
                    f"the stable is full ({TEAM_CAP} fighting + {STANDBY_SLOTS} standby)")
            self._spend(s.price_cp)
            self.stable.append(StableMember(
                s.name, invested_cp=s.price_cp,
                standby=len(self.fielded()) >= TEAM_CAP))   # a 6th waits in the stall
        self.shop_monsters[slot] = None

    def buy_item(self, slot: int, target: int) -> None:
        self._require("shop")
        if not (0 <= slot < len(self.shop_items)) or self.shop_items[slot] is None:
            raise FortuneError("nothing in that slot")
        if not (0 <= target < len(self.stable)):
            raise FortuneError("no such stable member")
        member = self.stable[target]
        if len(member.items) >= ITEM_CAP:
            raise FortuneError(f"{member.name} already carries {ITEM_CAP} items")
        s = self.shop_items[slot]
        self._spend(s.price_cp)
        member.items.append(s.name)
        self.shop_items[slot] = None

    def attach_bank_item(self, bank_idx: int, target: int) -> None:
        """Attach an item won on the wheel (held in the bank) to a stable member."""
        self._require("shop")
        if not (0 <= bank_idx < len(self.bank)):
            raise FortuneError("no such banked item")
        if not (0 <= target < len(self.stable)):
            raise FortuneError("no such stable member")
        member = self.stable[target]
        if len(member.items) >= ITEM_CAP:
            raise FortuneError(f"{member.name} already carries {ITEM_CAP} items")
        member.items.append(self.bank.pop(bank_idx))

    def sell(self, idx: int) -> int:
        """Sell a stable member for half of everything invested (items lost)."""
        self._require("shop")
        if not (0 <= idx < len(self.stable)):
            raise FortuneError("no such stable member")
        refund = self.stable[idx].invested_cp // 2
        del self.stable[idx]
        self.purse_cp += refund
        return refund

    def train(self, i: int, j: int) -> None:
        """Merge owned copy `j` into `i`: elite levels sum +1; items transfer up to
        the cap (excess lost); invested gold accumulates (SPEC 18.8.7)."""
        self._require("shop")
        if i == j or not (0 <= i < len(self.stable)) or not (0 <= j < len(self.stable)):
            raise FortuneError("pick two different stable members")
        a, b = self.stable[i], self.stable[j]
        if a.name != b.name:
            raise FortuneError(f"{a.name} and {b.name} refuse to train together")
        a.elite += b.elite + 1
        for it in b.items:
            if len(a.items) < ITEM_CAP:
                a.items.append(it)
        a.invested_cp += b.invested_cp
        del self.stable[j]

    def fielded(self) -> list[StableMember]:
        return [m for m in self.stable if not m.standby]

    def bench(self, i: int) -> None:
        """Toggle a creature through the standby stall. Benching a fielded
        creature trades places with the stall's occupant (if any); fielding the
        standby needs an open spot on the field."""
        self._require("shop")
        if not (0 <= i < len(self.stable)):
            raise FortuneError("no such stall")
        m = self.stable[i]
        if m.standby:
            if len(self.fielded()) >= TEAM_CAP:
                raise FortuneError("the field is full — bench a fielded creature "
                                   "to trade places")
            m.standby = False
        else:
            for other in self.stable:
                if other.standby:
                    other.standby = False       # the stall's occupant takes the field
                    break
            m.standby = True

    # -- battle ---------------------------------------------------------------------
    def enemy_team(self, round_no: int | None = None) -> list[str]:
        """The opposing composition — a pure function of (seed, round), SPEC 18.8.9."""
        r = self.round if round_no is None else round_no
        rng = RNG((self.seed * 49_979_687 + r * 104_729 + 11) & 0x7FFFFFFF)
        cap = cr_cap(r)
        pool = self._band(cap)
        if not pool:
            return []
        size = enemy_size(r)
        budget = size * _xp_of_cr(cap) * ENEMY_BUDGET_FRAC \
            * (0.85 + rng.randint(0, 30) / 100)
        team: list[str] = []
        spent = 0.0

        def xp(e: CatalogEntry) -> float:
            return e.adjusted_xp if e.adjusted_xp else _xp_of_cr(e.cr)

        if is_boss_round(r):
            # one huge monster carrying the whole budget (x1.5: five creatures
            # focus-firing one initiative slot is worth a premium) — the CR cap
            # does not apply; the wheel of fortune turns for the house too
            budget *= BOSS_BUDGET_MULT
            everyone = [self.catalog[n] for n in sorted(self.catalog)]
            window = [e for e in everyone
                      if budget * 0.65 <= xp(e) <= budget * 1.15]
            if window:
                return [window[rng.randint(0, len(window) - 1)].name]
            return [min(everyone, key=lambda e: abs(xp(e) - budget)).name]

        for _ in range(size):
            affordable = [e for e in pool if spent + xp(e) <= budget * 1.15]
            if not affordable:
                break
            weights = [max(1, int(1000 / (1.0 + max(0.0, cap - e.cr))))
                       for e in affordable]
            roll = rng.randint(1, sum(weights))
            acc = 0
            pick = affordable[-1]
            for e, w in zip(affordable, weights):
                acc += w
                if roll <= acc:
                    pick = e
                    break
            team.append(pick.name)
            spent += xp(pick)
        if not team:                       # budget too tight for anything: send the
            cheapest = min(pool, key=xp)   # cheapest head the pit can find
            team.append(cheapest.name)
        return team

    def player_defs(self):
        """The fielded stable (the standby stall sits out) as kitted MonsterDefs,
        ready for `ravel.sim` (SPEC 18.8.11)."""
        from .content import get
        return [apply_kit(get(m.name), m.elite, tuple(m.items))
                for m in self.fielded()[:TEAM_CAP]]

    def fight(self, placements: list | None = None) -> BattleResult:
        """Resolve the round's battle. Placements are per-stable-member origin cells
        (None entries auto-place). Win -> a wheel spin is owed; loss (draws count —
        the house always wins) -> a life. The 3rd loss ends the run."""
        self._require("shop")
        if not self.player_defs():
            raise FortuneError("no creature stands on the field — buy or field one")
        map_name, weather = self.round_env(self.round)
        result = run_battle(self.player_defs(), self.enemy_team(),
                            seed=self.battle_seed(self.round), ai="heuristic",
                            map_name=map_name, weather=weather, roll_hp=False,
                            placements_a=placements)
        won = result.winner == "A"
        self.history.append({
            "round": self.round, "won": won, "map": map_name, "weather": weather,
            "enemy": self.enemy_team(), "rounds": result.rounds,
            "years": result.rounds * YEARS_PER_COMBAT_ROUND,
        })
        self.round += 1
        self.scouted = False           # next round's opposition is a fresh secret
        if won:
            self.wins += 1
            self.phase = "wheel"
        else:
            self.lives -= 1
            if self.lives <= 0:
                self.phase = "over"
            else:
                self._next_shop()
        return result

    def _next_shop(self) -> None:
        self.phase = "shop"
        self.purse_cp += INCOME_CP
        self._roll_shop()

    # -- the wheel -------------------------------------------------------------------
    def spin(self) -> dict:
        """One spin of the three-ring wheel (SPEC 18.8.8). Returns the ring stops and
        the prize; the client only animates to these numbers. The ring layouts are
        the mechanics AND the picture — the no-prize sectors sit spread across the
        wheel, not bunched — so what the player sees is what was rolled."""
        self._require("wheel")
        rng = self._draw()
        outer = rng.randint(1, 10)
        middle = center = None
        o = OUTER_RING[outer - 1]
        if o in ("none", "common"):
            tier = o
        else:                                   # the outer ★ advances inward
            middle = rng.randint(1, 10)
            m = MIDDLE_RING[middle - 1]
            if m in ("none", "uncommon"):
                tier = m
            else:                               # the middle ★: the center pays rare
                center = rng.randint(1, 10)
                tier = "rare"
        prize = self._award(tier, rng)
        self._next_shop()
        return {"outer": outer, "middle": middle, "center": center,
                "tier": tier, "prize": prize}

    def _award(self, tier: str, rng: RNG) -> dict:
        if tier == "none":
            return {"kind": "none", "label": "The wheel keeps your luck"}
        if tier == "common":
            pick = rng.choice(["gold2", "gold15", "item"])
            if pick == "gold2":
                self.purse_cp += 200
                return {"kind": "gold", "cp": 200, "label": "2 gp"}
            if pick == "gold15":
                self.purse_cp += 150
                return {"kind": "gold", "cp": 150, "label": "1 gp 5 sp"}
            item = rng.choice(list(COMMON_ITEMS))
            self.bank.append(item)
            return {"kind": "item", "item": item, "label": item}
        if tier == "uncommon":
            if rng.randint(1, 2) == 1:
                self.purse_cp += 500
                return {"kind": "gold", "cp": 500, "label": "5 gp"}
            item = rng.choice(list(UNCOMMON_ITEMS))
            self.bank.append(item)
            return {"kind": "item", "item": item, "label": item}
        pick = rng.choice(["item", "life", "gold"])
        if pick == "life" and self.lives < LIVES_START:
            self.lives += 1
            return {"kind": "life", "label": "A life, returned"}
        if pick == "gold" or pick == "life":
            self.purse_cp += 1000
            return {"kind": "gold", "cp": 1000, "label": "10 gp"}
        item = rng.choice(list(RARE_ITEMS))
        self.bank.append(item)
        return {"kind": "item", "item": item, "label": item}

    # -- serialization ------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "seed": self.seed, "books": list(self.books), "draws": self.draws,
            "round": self.round, "wins": self.wins, "lives": self.lives,
            "purse_cp": self.purse_cp, "phase": self.phase,
            "stable": [{"name": m.name, "elite": m.elite, "items": list(m.items),
                        "invested_cp": m.invested_cp, "standby": m.standby}
                       for m in self.stable],
            "shop_monsters": [None if s is None else
                              {"name": s.name, "price_cp": s.price_cp,
                               "frozen": s.frozen} for s in self.shop_monsters],
            "shop_items": [None if s is None else
                           {"name": s.name, "price_cp": s.price_cp,
                            "frozen": s.frozen} for s in self.shop_items],
            "bank": list(self.bank), "history": list(self.history),
            "scouted": self.scouted,
        }

    @classmethod
    def from_dict(cls, d: dict, catalog: dict[str, CatalogEntry]) -> "FortuneRun":
        run = cls(seed=d["seed"], books=tuple(d["books"]), catalog=catalog,
                  draws=d["draws"], round=d["round"], wins=d["wins"],
                  lives=d["lives"], purse_cp=d["purse_cp"], phase=d["phase"])
        run.stable = [StableMember(m["name"], m["elite"], list(m["items"]),
                                   m["invested_cp"], m.get("standby", False))
                      for m in d["stable"]]
        run.shop_monsters = [None if s is None else
                             ShopSlot(s["name"], s["price_cp"], s["frozen"])
                             for s in d["shop_monsters"]]
        run.shop_items = [None if s is None else
                          ShopSlot(s["name"], s["price_cp"], s["frozen"])
                          for s in d["shop_items"]]
        run.bank = list(d["bank"])
        run.history = list(d["history"])
        run.scouted = d.get("scouted", False)
        return run


def new_run(seed: int, books: tuple[str, ...],
            catalog: dict[str, CatalogEntry]) -> FortuneRun:
    """Start a run: filter the catalog to the chosen books and roll the first shop."""
    filtered = {n: e for n, e in catalog.items() if e.source in books}
    run = FortuneRun(seed=seed, books=tuple(books), catalog=filtered)
    run._roll_shop(keep_frozen=False)
    return run
