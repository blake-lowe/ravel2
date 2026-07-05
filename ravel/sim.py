"""Battle setup, single-battle runner, and batch statistics."""
from __future__ import annotations

from dataclasses import dataclass, field

from .controllers import GreedyController, HeuristicController, RandomController
from .dice import RNG
from .engine import Encounter
from .grid import Grid
from .models import Combatant, MonsterDef

ARENA_W = 20
ARENA_H = 16

_FOOT = {"Tiny": 1, "Small": 1, "Medium": 1, "Large": 2, "Huge": 3, "Gargantuan": 4}

# Team entries are monster names (looked up in the registry) or ready MonsterDef
# objects — the Supertemporal Arena fields kitted/elite variants that exist in no
# data file (SPEC 18.8.11). Either way the engine only ever sees a MonsterDef.


def _md_of(entry) -> MonsterDef:
    if isinstance(entry, MonsterDef):
        return entry
    from .content import get
    return get(entry)


def _make(entry, cid: str, team: str, pos: tuple[int, int]) -> Combatant:
    md = _md_of(entry)
    return Combatant(id=cid, team=team, md=md, hp=md.hp, pos=pos,
                     slots=dict(md.spell_slots), innate_left=dict(md.innate))


def _place(names: list, team: str, x_side: str, w: int, h: int):
    combs = []
    n = len(names)
    ys = [int((i + 1) * h / (n + 1)) for i in range(n)]
    for i, name in enumerate(names):
        foot = _FOOT[_md_of(name).size.value]
        # start ~35 ft apart (realistic encounter range, lets chargers pounce)
        x = (w // 2 - 4) if x_side == "left" else (w // 2 + 3)
        x = max(0, min(x, w - foot))
        y = min(max(0, ys[i]), h - foot)
        combs.append(_make(name, f"{team}{i + 1}", team, (x, y)))
    return combs


def _place_at(names: list, team: str, spawns: list[tuple[int, int]], grid: Grid):
    """Place a team onto explicit spawn squares, deconflicting so no two
    combatants ever start stacked. Spawns cycle if a team outnumbers the points;
    a taken (or too-tight, for Large+) square spirals out to the nearest free one."""
    combs = []
    taken: set[tuple[int, int]] = set()      # every cell any placed footprint holds
    for i, name in enumerate(names):
        foot = _FOOT[_md_of(name).size.value]
        sx, sy = spawns[i % len(spawns)] if spawns else (0, 0)
        origin = _free_footprint(grid, (sx, sy), foot, taken)
        taken.update(grid.footprint_cells(origin, foot))
        combs.append(_make(name, f"{team}{i + 1}", team, origin))
    return combs


def deployment_zone(team: str = "A", w: int = ARENA_W, h: int = ARENA_H,
                    map_name: str | None = None) -> set[tuple[int, int]]:
    """Cells a player may deploy onto (SPEC 18.8.10): on the open floor, the team's
    half up to 3 columns short of the midline; on a named map, within Chebyshev 3
    of any of the team's spawn points. Walls and chasms are never deployable."""
    if map_name:
        from .maps import get_map, parse_map
        grid, spawns_a, spawns_b = parse_map(get_map(map_name))
        zone: set[tuple[int, int]] = set()
        for sx, sy in (spawns_a if team == "A" else spawns_b):
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    c = (sx + dx, sy + dy)
                    if (grid.in_bounds(c) and c not in grid.walls
                            and c not in grid.chasm):
                        zone.add(c)
        return zone
    cols = range(0, w // 2 - 2) if team == "A" else range(w // 2 + 2, w)
    return {(x, y) for x in cols for y in range(h)}


def _deploy(entries: list, team: str, spawn_for: list[tuple[int, int]], grid: Grid,
            placements: list, zone: set[tuple[int, int]]):
    """Place a team honoring explicit per-member placements (validated against the
    deployment zone, footprints and overlaps — ValueError on an illegal drop);
    members without a placement auto-place onto their default spawn square."""
    combs: list = [None] * len(entries)
    taken: set[tuple[int, int]] = set()
    for i, e in enumerate(entries):                      # pass 1: explicit drops
        pos = placements[i] if i < len(placements) else None
        if pos is None:
            continue
        md = _md_of(e)
        pos = (int(pos[0]), int(pos[1]))
        foot = _FOOT[md.size.value]
        cells = grid.footprint_cells(pos, foot)
        if not all(c in zone for c in cells):
            raise ValueError(f"{md.name} at {pos}: outside the deployment zone")
        if not grid.footprint_fits(pos, foot, taken):
            raise ValueError(f"{md.name} at {pos}: blocked or overlapping")
        taken.update(cells)
        combs[i] = _make(e, f"{team}{i + 1}", team, pos)
    for i, e in enumerate(entries):                      # pass 2: the rest, auto
        if combs[i] is not None:
            continue
        foot = _FOOT[_md_of(e).size.value]
        origin = _free_footprint(grid, spawn_for[i], foot, taken)
        taken.update(grid.footprint_cells(origin, foot))
        combs[i] = _make(e, f"{team}{i + 1}", team, origin)
    return combs


def _free_footprint(grid: Grid, near, foot: int, taken: set[tuple[int, int]]):
    """Nearest square (spiralling out from `near`, clamped in-bounds) whose whole
    footprint fits without hitting walls or an already-placed combatant."""
    def clamp(p):
        return (max(0, min(p[0], grid.width - foot)),
                max(0, min(p[1], grid.height - foot)))
    origin = clamp(near)
    if grid.footprint_fits(origin, foot, taken):
        return origin
    for radius in range(1, max(grid.width, grid.height) + 1):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:   # only the ring's edge
                    continue
                cand = clamp((origin[0] + dx, origin[1] + dy))
                if grid.footprint_fits(cand, foot, taken):
                    return cand
    return origin                                     # nowhere free: last resort


def build_encounter(team_a: list[str], team_b: list[str], seed: int,
                    w: int = ARENA_W, h: int = ARENA_H, flanking: bool = False,
                    surprised: str | None = None, map_name: str | None = None,
                    high_ground: bool = False, roll_hp: bool = True,
                    underwater: bool = False, weather: str = "clear",
                    lair: tuple[str, ...] | list[str] = (),
                    placements_a: list | None = None) -> Encounter:
    from .models import RulesConfig
    if map_name:
        from .maps import MAP_AMBIENT, get_map, parse_map
        grid, spawns_a, spawns_b = parse_map(get_map(map_name))
        if map_name in MAP_AMBIENT:                # apply the map's lighting
            grid.ambient, grid.ambient_sunlight = MAP_AMBIENT[map_name]
        if placements_a:
            zone = deployment_zone("A", w, h, map_name)
            spawn_for = [spawns_a[i % len(spawns_a)] if spawns_a else (0, 0)
                         for i in range(len(team_a))]
            combs = (_deploy(team_a, "A", spawn_for, grid, placements_a, zone)
                     + _place_at(team_b, "B", spawns_b, grid))
        else:
            combs = (_place_at(team_a, "A", spawns_a, grid)
                     + _place_at(team_b, "B", spawns_b, grid))
        high_ground = high_ground or bool(grid.elevation)
    else:
        grid = Grid(w, h)
        if placements_a:
            n = len(team_a)
            ys = [int((i + 1) * h / (n + 1)) for i in range(n)]
            spawn_for = [(w // 2 - 4, min(max(0, ys[i]), h - 1)) for i in range(n)]
            combs = (_deploy(team_a, "A", spawn_for, grid, placements_a,
                             deployment_zone("A", w, h))
                     + _place(team_b, "B", "right", w, h))
        else:
            combs = _place(team_a, "A", "left", w, h) + _place(team_b, "B", "right", w, h)
    enc = Encounter(grid, combs, RNG(seed),
                    rules=RulesConfig(flanking=flanking, high_ground=high_ground),
                    roll_hp=roll_hp, underwater=underwater, weather=weather,
                    lair_names=frozenset(lair))
    if surprised in ("A", "B"):
        for c in combs:
            if c.team == surprised:
                c.surprised = True
                c.reaction_available = False     # can't react before its first turn
    return enc


def make_controllers(kind: str, seed: int, llm_client=None) -> dict:
    if kind == "heuristic":
        return {"A": HeuristicController(), "B": HeuristicController()}
    if kind == "greedy":
        return {"A": GreedyController(), "B": GreedyController()}
    if kind == "greedy_vs_heuristic":
        return {"A": GreedyController(), "B": HeuristicController()}
    if kind == "random":
        return {"A": RandomController(seed), "B": RandomController(seed + 7919)}
    if kind in ("llm", "llm_vs_heuristic"):
        from .llm import LLMController, OllamaClient
        client = llm_client or OllamaClient()
        a = LLMController(client)
        b = LLMController(client) if kind == "llm" else HeuristicController()
        return {"A": a, "B": b}
    raise ValueError(f"unknown ai kind: {kind}")


@dataclass
class BattleResult:
    winner: str | None
    rounds: int
    survivors: list[tuple[str, str, int, int]]  # (id, name, hp, max)
    log: list[str] = field(default_factory=list)
    events: list = field(default_factory=list)  # typed Event stream (replay; see events.py)


def run_battle(team_a: list[str], team_b: list[str], seed: int = 1,
               ai: str = "heuristic", llm_client=None, flanking: bool = False,
               surprised: str | None = None, map_name: str | None = None,
               roll_hp: bool = True, underwater: bool = False,
               weather: str = "clear",
               lair: tuple[str, ...] | list[str] = (),
               placements_a: list | None = None) -> BattleResult:
    enc = build_encounter(team_a, team_b, seed, flanking=flanking,
                          surprised=surprised, map_name=map_name, roll_hp=roll_hp,
                          underwater=underwater, weather=weather, lair=lair,
                          placements_a=placements_a)
    controllers = make_controllers(ai, seed, llm_client)
    winner = enc.run(controllers)
    survivors = [(c.id, c.name, c.hp, c.max_hp) for c in enc.living()]
    return BattleResult(winner, enc.round, survivors, enc.log, enc.events)


@dataclass
class BatchStats:
    team_a: list[str]
    team_b: list[str]
    trials: int
    wins_a: int = 0
    wins_b: int = 0
    draws: int = 0
    rounds: list[int] = field(default_factory=list)
    winner_hp_frac: list[float] = field(default_factory=list)

    def summary(self) -> str:
        avg_r = sum(self.rounds) / len(self.rounds) if self.rounds else 0
        avg_hp = (sum(self.winner_hp_frac) / len(self.winner_hp_frac) * 100
                  if self.winner_hp_frac else 0)
        a = "+".join(self.team_a)
        b = "+".join(self.team_b)
        pa = 100 * self.wins_a / self.trials
        pb = 100 * self.wins_b / self.trials
        pd = 100 * self.draws / self.trials
        return (
            f"\n=== {a}  vs  {b}   ({self.trials} battles) ===\n"
            f"  Team A ({a}): {self.wins_a} wins  ({pa:.0f}%)\n"
            f"  Team B ({b}): {self.wins_b} wins  ({pb:.0f}%)\n"
            f"  Draws: {self.draws} ({pd:.0f}%)\n"
            f"  Avg rounds: {avg_r:.1f}  (min {min(self.rounds, default=0)}, "
            f"max {max(self.rounds, default=0)})\n"
            f"  Avg winner remaining HP: {avg_hp:.0f}%")


def run_batch(team_a: list[str], team_b: list[str], trials: int = 50,
              ai: str = "heuristic", base_seed: int = 1000,
              llm_client=None) -> BatchStats:
    stats = BatchStats(team_a, team_b, trials)
    max_a = _team_hp(team_a)
    max_b = _team_hp(team_b)
    for t in range(trials):
        res = run_battle(team_a, team_b, seed=base_seed + t, ai=ai, llm_client=llm_client)
        stats.rounds.append(res.rounds)
        if res.winner == "A":
            stats.wins_a += 1
            frac = sum(s[2] for s in res.survivors) / max_a
            stats.winner_hp_frac.append(frac)
        elif res.winner == "B":
            stats.wins_b += 1
            frac = sum(s[2] for s in res.survivors) / max_b
            stats.winner_hp_frac.append(frac)
        else:
            stats.draws += 1
    return stats


def _team_hp(names: list[str]) -> int:
    from .content import get
    return sum(get(n).hp for n in names)


@dataclass
class EvalReport:
    matchup: str
    trials: int
    llm_wins: int
    avg_rounds: float
    legal_choice_pct: float   # share of LLM decisions that were valid (no fallback)

    def summary(self) -> str:
        return (f"\n=== LLM eval: {self.matchup} ({self.trials} battles) ===\n"
                f"  LLM win rate: {100 * self.llm_wins / self.trials:.0f}%\n"
                f"  Avg rounds: {self.avg_rounds:.1f}\n"
                f"  Legal-choice rate: {self.legal_choice_pct:.0f}% "
                f"(higher = model picked valid options without fallback)")


def run_eval(team_a: list[str], team_b: list[str], trials: int = 6,
             base_seed: int = 5000) -> EvalReport:
    """Decision-quality eval: team A is LLM-driven vs a heuristic team B.

    Reports win rate, pace, and the share of model decisions that were legal
    (an objective signal of tactical competence / output validity)."""
    from .llm import LLMController, OllamaClient
    client = OllamaClient()
    wins = rounds = calls = fallbacks = 0
    for t in range(trials):
        enc = build_encounter(team_a, team_b, base_seed + t)
        a = LLMController(client)
        enc.run({"A": a, "B": HeuristicController()})
        wins += enc.winner() == "A"
        rounds += enc.round
        calls += a.calls
        fallbacks += a.fallbacks
    pct = 100 * (1 - fallbacks / calls) if calls else 0
    return EvalReport("+".join(team_a) + " vs " + "+".join(team_b), trials,
                      wins, rounds / trials, pct)
