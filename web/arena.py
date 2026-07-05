"""The Blood Pit arena API (ROADMAP Slice 12b) — thin wrappers over `ravel.sim`.

`/api/battle` runs one deterministic bout and returns everything a client replay
needs: the typed event stream (round + log-index stamped), the prose log, a static
map description, combatant metadata, and the touts' pre-fight line. `/api/gauntlet`
streams a seed sweep as Server-Sent Events. The engine stays pure; this module is
an outer layer (imports ravel, never the reverse).
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ravel import content
from ravel.maps import MAPS
from ravel.sim import BattleResult, build_encounter, make_controllers, run_battle

router = APIRouter()

WEATHERS = ("clear", "fog", "rain", "wind")
AIS = ("heuristic", "greedy", "greedy_vs_heuristic", "random", "llm", "llm_vs_heuristic")
MAX_TEAM = 12          # keep one request's simulation bounded
MAX_GAUNTLET = 500


def _ratings() -> dict:
    from .app import RATINGS      # lazy: avoids a circular import at module load
    return RATINGS


def _parse_team(spec: str, label: str) -> list[str]:
    names = [n.strip() for n in (spec or "").split(",") if n.strip()]
    if not names:
        raise HTTPException(422, f"team {label} is empty")
    if len(names) > MAX_TEAM:
        raise HTTPException(422, f"team {label}: at most {MAX_TEAM} combatants")
    known = set(content.all_names())
    for n in names:
        if n not in known:
            raise HTTPException(422, f"no such monster: {n}")
    return names


def _check(ai: str, map_name: str | None, weather: str) -> None:
    if ai not in AIS:
        raise HTTPException(422, f"ai must be one of {AIS}")
    if map_name and map_name not in MAPS:
        raise HTTPException(422, f"map must be one of {sorted(MAPS)} (or omitted)")
    if weather not in WEATHERS:
        raise HTTPException(422, f"weather must be one of {WEATHERS}")


def _team_xp(names: list[str]) -> float:
    ratings = _ratings()
    total = 0.0
    for n in names:
        r = ratings.get(n) or {}
        total += r.get("adjusted_xp") or r.get("nominal_xp") or 0.0
    return total


def _odds(team_a: list[str], team_b: list[str]) -> dict:
    xa, xb = _team_xp(team_a), _team_xp(team_b)
    if not xa or not xb:
        return {"a_xp": xa, "b_xp": xb, "line": "the touts refuse the book — unrated flesh in the pit"}
    fav, dog = ("A", "B") if xa >= xb else ("B", "A")
    ratio = max(xa, xb) / min(xa, xb)
    # express as a small odds fraction, e.g. 1.5 -> 3:2
    best = (1, 1)
    err = ratio
    for q in range(1, 7):
        p = round(ratio * q)
        if p and abs(p / q - ratio) < err:
            best, err = (p, q), abs(p / q - ratio)
    corner = "Red" if fav == "A" else "Black"
    line = (f"the touts lay {best[0]}:{best[1]} on the {corner} corner"
            if best != (1, 1) else "the touts call it even money")
    return {"a_xp": round(xa), "b_xp": round(xb), "favorite": fav, "underdog": dog,
            "ratio": round(ratio, 2), "line": line}


def _grid_payload(enc) -> dict:
    g = enc.grid
    return {
        "w": g.width, "h": g.height,
        "walls": sorted(g.walls),
        "difficult": sorted(g.difficult),
        "water": sorted(g.water),
        "cover": sorted(g.cover_obstacles),
        "elevation": {f"{x},{y}": v for (x, y), v in sorted(g.elevation.items())},
        "chasm": {f"{x},{y}": v for (x, y), v in sorted(g.chasm.items())},
        "hazards": [{"name": z.name, "cells": sorted(z.cells),
                     "difficult": bool(getattr(z, "difficult", False)),
                     "damage": [f"{d.count}d{d.sides} {d.type}" for d in (z.damage or ())]}
                    for z in g.hazards],
        "ambient": g.ambient,
        "light": _light_payload(enc),
    }


def _light_payload(enc) -> dict:
    """Static map lighting for the board overlay, straight from the engine's own
    model (ambient + fixed sources, walls shadowing, weather dousing flames). Only
    the not-bright cells are sent — bright is the board's default, unshaded look.
    Purely for display; the fight's mechanics already used this same computation."""
    g = enc.grid
    dim, dark = [], []
    for y in range(g.height):
        for x in range(g.width):
            cell = (x, y)
            if cell in g.walls:
                continue                       # opaque hatch, nothing to shade
            level = enc.light_level(cell)
            if level == "dim":
                dim.append(cell)
            elif level == "dark":
                dark.append(cell)
    sources = [{"pos": list(lg.origin), "radius": lg.bright_radius}
               for lg in g.lights if lg.origin is not None]
    return {"dim": dim, "dark": dark, "sources": sources,
            "sunlight": bool(g.ambient_sunlight and g.ambient >= 1.0)}


def _token_art(name: str) -> list[str]:
    """Ordered candidate URLs for the round 5e.tools token art (client walks on
    error), probing the monster's own source book first — see app.art_dirs."""
    from .app import IMG_BASE, art_dirs, name_variants
    from urllib.parse import quote
    return [f"{IMG_BASE}/tokens/{src}/{quote(n)}.webp"
            for src in art_dirs(name) for n in name_variants(name)]


def _combatant_payload(enc) -> list[dict]:
    return [{
        "id": c.id, "name": c.name, "team": c.team,
        "hp": c.hp, "max_hp": c.max_hp,
        "size": c.md.size.value, "cells": c.footprint,
        "pos": list(c.pos),
        "ac": c.ac, "speed": c.md.speed, "fly": c.md.fly,
        "token_art": _token_art(c.name),
    } for c in enc.combatants.values()]


def _battle_kwargs(a, b, seed, ai, map_name, weather, underwater, flanking,
                   surprised, avg_hp, lair):
    return dict(team_a=a, team_b=b, seed=seed, ai=ai,
                map_name=map_name or None, weather=weather, underwater=underwater,
                flanking=flanking, surprised=surprised or None,
                roll_hp=not avg_hp, lair=lair)


@router.get("/api/arena-meta")
def arena_meta() -> dict:
    """Everything the config UI needs to book a match."""
    ratings = _ratings()
    roster = []
    for name in content.all_names():
        r = ratings.get(name) or {}
        roster.append({"name": name,
                       "cr": r.get("nominal_cr"),
                       "best_cr": (r.get("refined_cr") if r.get("refined_cr") is not None
                                   else r.get("adjusted_cr")),
                       "xp": r.get("adjusted_xp") or r.get("nominal_xp") or 0,
                       "has_lair": content.get(name).lair_action is not None})
    return {"maps": sorted(MAPS), "weathers": list(WEATHERS), "ais": list(AIS),
            "max_team": MAX_TEAM, "max_gauntlet": MAX_GAUNTLET, "roster": roster}


def _validate_bout(a, b, ai, map_name, weather, surprised, lair):
    team_a, team_b = _parse_team(a, "A"), _parse_team(b, "B")
    _check(ai, map_name or None, weather)
    if surprised not in ("", "A", "B"):
        raise HTTPException(422, "surprised must be A, B, or omitted")
    lair_names = [n.strip() for n in (lair or "").split(",") if n.strip()]
    known = set(content.all_names())
    for n in lair_names:
        if n not in known:
            raise HTTPException(422, f"lair: no such monster: {n}")
    return team_a, team_b, lair_names


def _package(result, team_a, team_b, seed, kw, config) -> dict:
    # Deterministic snapshot of the same encounter (same seed -> identical build)
    # purely for the static map + full combatant metadata.
    enc = build_encounter(team_a, team_b, seed, flanking=kw["flanking"],
                          surprised=kw["surprised"], map_name=kw["map_name"],
                          roll_hp=kw["roll_hp"], underwater=kw["underwater"],
                          weather=kw["weather"], lair=kw["lair"])
    return {
        "config": config,
        "winner": result.winner,
        "rounds": result.rounds,
        "survivors": result.survivors,
        "log": result.log,
        "events": [asdict(e) for e in result.events],
        "grid": _grid_payload(enc),
        "combatants": _combatant_payload(enc),
        "odds": _odds(team_a, team_b),
    }


def _config_echo(team_a, team_b, seed, ai, map, weather, underwater, flanking,
                 surprised, avg_hp, lair) -> dict:
    return {"a": ",".join(team_a), "b": ",".join(team_b), "seed": seed, "ai": ai,
            "map": map, "weather": weather, "underwater": underwater,
            "flanking": flanking, "surprised": surprised, "avg_hp": avg_hp,
            "lair": lair}


@router.get("/api/battle")
def battle(a: str, b: str, seed: int = 1, ai: str = "heuristic",
           map: str = "", weather: str = "clear", underwater: bool = False,
           flanking: bool = False, surprised: str = "", avg_hp: bool = False,
           lair: str = "") -> dict:
    team_a, team_b, lair_names = _validate_bout(a, b, ai, map, weather, surprised, lair)
    kw = _battle_kwargs(team_a, team_b, seed, ai, map, weather, underwater,
                        flanking, surprised, avg_hp, lair_names)
    try:
        result = run_battle(**kw)
    except Exception as exc:                       # e.g. Ollama down for ai=llm*
        raise HTTPException(502, f"the bout could not be fought: {exc}") from exc
    return _package(result, team_a, team_b, seed, kw,
                    _config_echo(team_a, team_b, seed, ai, map, weather,
                                 underwater, flanking, surprised, avg_hp, lair))


class _CountingClient:
    """Wraps the Ollama client to count decisions for live progress reporting.
    Pure pass-through otherwise — the LLM still only selects among options."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0

    def chat_json(self, *args, **kwargs):
        self.calls += 1
        return self.inner.chat_json(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def _fight_with_progress(kw: dict, ai: str, seed: int):
    """Run one bout in a worker thread, yielding {round, decisions} progress
    dicts every ~0.5s while it fights; returns the BattleResult (generator
    return value). Raises RuntimeError on a failed bout (e.g. Ollama down)."""
    import threading

    counter = None
    if "llm" in ai:
        from ravel.llm import OllamaClient
        counter = _CountingClient(OllamaClient())
    # Built identically to run_battle's own encounter, so the poll loop can
    # read the live round while the thread fights the (same, deterministic) bout.
    enc = build_encounter(**{k: v for k, v in kw.items() if k != "ai"})
    box: dict = {}

    def work():
        try:
            controllers = make_controllers(ai, seed, llm_client=counter)
            winner = enc.run(controllers)
            box["result"] = BattleResult(
                winner, enc.round,
                [(c.id, c.name, c.hp, c.max_hp) for c in enc.living()],
                enc.log, enc.events)
        except Exception as exc:
            box["error"] = str(exc)

    t = threading.Thread(target=work, daemon=True)
    t.start()
    while t.is_alive():
        yield {"round": enc.round, "decisions": counter.calls if counter else 0}
        t.join(0.5)
    if "error" in box:
        raise RuntimeError(box["error"])
    return box["result"]


@router.get("/api/battle-stream")
def battle_stream(a: str, b: str, seed: int = 1, ai: str = "heuristic",
                  map: str = "", weather: str = "clear", underwater: bool = False,
                  flanking: bool = False, surprised: str = "", avg_hp: bool = False,
                  lair: str = "") -> StreamingResponse:
    """Like /api/battle, but streams progress frames while the bout is fought —
    for LLM cornermen, whose one-call-per-decision pace can take minutes."""
    import threading
    import time

    team_a, team_b, lair_names = _validate_bout(a, b, ai, map, weather, surprised, lair)
    kw = _battle_kwargs(team_a, team_b, seed, ai, map, weather, underwater,
                        flanking, surprised, avg_hp, lair_names)
    config = _config_echo(team_a, team_b, seed, ai, map, weather, underwater,
                          flanking, surprised, avg_hp, lair)

    def stream():
        start = time.time()
        gen = _fight_with_progress(kw, ai, seed)
        while True:
            try:
                p = next(gen)
            except StopIteration as stop:
                result = stop.value
                break
            except RuntimeError as exc:
                yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
                return
            p["elapsed"] = round(time.time() - start)
            yield "data: " + json.dumps(p) + "\n\n"
        payload = _package(result, team_a, team_b, seed, kw, config)
        yield "event: done\ndata: " + json.dumps(payload) + "\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


def _wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = wins / n
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, center - half), min(1.0, center + half)


@router.get("/api/gauntlet")
def gauntlet(a: str, b: str, n: int = 50, seed0: int = 1, ai: str = "heuristic",
             map: str = "", weather: str = "clear", underwater: bool = False,
             flanking: bool = False, surprised: str = "",
             avg_hp: bool = False, lair: str = "") -> StreamingResponse:
    """Run n seeds and stream each bout's outcome as Server-Sent Events."""
    team_a, team_b, lair_names = _validate_bout(a, b, ai, map, weather, surprised, lair)
    n = max(1, min(n, MAX_GAUNTLET))

    def stream():
        wins = {"A": 0, "B": 0, None: 0}
        rounds: list[int] = []
        for i in range(n):
            seed = seed0 + i
            kw = _battle_kwargs(team_a, team_b, seed, ai, map, weather,
                                underwater, flanking, surprised, avg_hp, lair_names)
            try:
                if "llm" in ai:
                    # slow bouts: tick frames report the live round + decision
                    # count so the client isn't silent for minutes per bout
                    gen = _fight_with_progress(kw, ai, seed)
                    while True:
                        try:
                            p = next(gen)
                        except StopIteration as stop:
                            r = stop.value
                            break
                        yield ("event: tick\ndata: " + json.dumps({
                            "i": i + 1, "n": n, "seed": seed,
                            "round": p["round"], "decisions": p["decisions"]}) + "\n\n")
                else:
                    r = run_battle(**kw)
            except Exception as exc:
                yield f"event: error\ndata: {json.dumps({'seed': seed, 'error': str(exc)})}\n\n"
                return
            wins[r.winner] = wins.get(r.winner, 0) + 1
            rounds.append(r.rounds)
            hp_frac = (sum(hp for _, _, hp, _ in r.survivors)
                       / max(1, sum(mx for _, _, _, mx in r.survivors)))
            yield ("data: " + json.dumps({
                "i": i + 1, "n": n, "seed": seed, "winner": r.winner,
                "rounds": r.rounds, "hp_frac": round(hp_frac, 3)}) + "\n\n")
        lo, hi = _wilson(wins["A"], n)
        yield ("event: done\ndata: " + json.dumps({
            "n": n, "wins_a": wins["A"], "wins_b": wins["B"],
            "draws": n - wins["A"] - wins["B"],
            "win_rate_a": round(wins["A"] / n, 3),
            "ci_a": [round(lo, 3), round(hi, 3)],
            "avg_rounds": round(sum(rounds) / len(rounds), 2),
            "rounds": rounds}) + "\n\n")

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
