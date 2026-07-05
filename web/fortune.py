"""The Supertemporal Arena web API (ROADMAP Slice 12e) — a thin wrapper over the
pure run-state machine in `ravel.fortune`.

The engine owns every rule; this module owns the IO: run sessions in memory,
finished runs persisted to sqlite (`data/fortune/runs.db`, the Book of Aeons),
and battle payloads shaped exactly like `/api/battle` so the Pit's replay
renderer works unchanged. Shemeshka thanks you for your patronage.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ravel import content
from ravel.fortune import (
    ITEM_PRICE_CP, ITEMS, LIVES_START, MIDDLE_RING, OUTER_RING, REROLL_CP,
    SCOUT_CP, STABLE_CAP, TEAM_CAP,
    CatalogEntry, FortuneError, FortuneRun, apply_kit, coins, new_run,
)
from ravel.maps import MAPS
from ravel.sim import build_encounter, deployment_zone

from .arena import _grid_payload, _token_art

router = APIRouter()

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "fortune" / "runs.db"
MAX_ACTIVE_RUNS = 500

RUNS: dict[str, FortuneRun] = {}
HANDLES: dict[str, str] = {}


# -- catalog: the shoppable world, built from the app's registries -------------

def _catalog() -> dict[str, CatalogEntry]:
    from .app import MONSTERS, MONSTER_SOURCES, RATINGS
    cat: dict[str, CatalogEntry] = {}
    for name, block in MONSTERS.items():
        cr = block.get("cr")
        if cr is None:
            continue
        r = RATINGS.get(name) or {}
        best = (r.get("refined_cr") if r.get("refined_cr") is not None
                else r.get("adjusted_cr"))
        cat[name] = CatalogEntry(
            name=name, cr=float(cr), source=MONSTER_SOURCES.get(name, "Ravel"),
            best_cr=best, adjusted_xp=r.get("adjusted_xp"))
    return cat


def _books() -> list[dict]:
    cat = _catalog()
    counts: dict[str, int] = {}
    for e in cat.values():
        counts[e.source] = counts.get(e.source, 0) + 1
    return [{"label": b, "monsters": n} for b, n in sorted(counts.items())]


# -- the Book of Ages (sqlite) ---------------------------------------------------

def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY, handle TEXT, seed INTEGER, books TEXT,
        wins INTEGER, rounds INTEGER, years INTEGER,
        stable TEXT, history TEXT, created TEXT, initials TEXT DEFAULT '')""")
    try:                                    # older Books of Aeons: add the column
        conn.execute("ALTER TABLE runs ADD COLUMN initials TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    return conn


def _persist(rid: str, run: FortuneRun, initials: str = "") -> None:
    years = sum(h.get("years", 0) for h in run.history)
    with _db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (rid, HANDLES.get(rid, "Anonymous Berk"), run.seed,
             json.dumps(list(run.books)), run.wins, len(run.history), years,
             json.dumps([{"name": m.name, "elite": m.elite, "items": m.items}
                         for m in run.stable]),
             json.dumps(run.history),
             datetime.now(timezone.utc).isoformat(timespec="seconds"),
             initials))


def _inscribe(rid: str, initials: str) -> None:
    with _db() as conn:
        conn.execute("UPDATE runs SET initials = ? WHERE id = ?", (initials, rid))


@router.get("/api/fortune/leaderboard")
def leaderboard(limit: int = 20) -> list[dict]:
    """The Book of Aeons: the longest-lucky stables ever to leave the arena."""
    if not DB_PATH.exists():
        return []
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY wins DESC, rounds ASC, created ASC"
            " LIMIT ?", (max(1, min(100, limit)),)).fetchall()
    return [{
        "handle": r["handle"], "initials": r["initials"] or "",
        "seed": r["seed"], "books": json.loads(r["books"]),
        "wins": r["wins"], "rounds": r["rounds"], "years": r["years"],
        "stable": json.loads(r["stable"]), "created": r["created"],
    } for r in rows]


# -- views -------------------------------------------------------------------------

def _art(name: str) -> list[str]:
    return _token_art(name.rstrip("★ ").strip() or name)


def _shop_view(run: FortuneRun) -> dict:
    monsters = []
    for s in run.shop_monsters:
        if s is None:
            monsters.append(None)
            continue
        e = run.catalog[s.name]
        md = content.get(s.name)
        monsters.append({"name": s.name, "price_cp": s.price_cp,
                         "price": coins(s.price_cp), "frozen": s.frozen,
                         "cr": e.cr, "best_cr": e.best_cr, "source": e.source,
                         "ac": md.ac, "hp": md.hp, "speed": md.speed,
                         "fly": md.fly, "swim": md.swim, "size": md.size.value,
                         "type": md.mtype, "alignment": md.alignment,
                         "art": _art(s.name)})
    items = []
    for s in run.shop_items:
        if s is None:
            items.append(None)
            continue
        it = ITEMS[s.name]
        items.append({"name": s.name, "price_cp": s.price_cp,
                      "price": coins(s.price_cp), "frozen": s.frozen,
                      "rarity": it.rarity, "effect": it.effect, "blurb": it.blurb})
    return {"monsters": monsters, "items": items}


def _stable_view(run: FortuneRun) -> list[dict]:
    out = []
    for m in run.stable:
        md = apply_kit(content.get(m.name), m.elite, tuple(m.items))
        out.append({
            "name": m.name, "elite": m.elite, "invested_cp": m.invested_cp,
            "standby": m.standby,
            "items": [{"name": n, "rarity": ITEMS[n].rarity, "effect": ITEMS[n].effect,
                       "blurb": ITEMS[n].blurb} for n in m.items],
            "ac": md.ac, "hp": md.hp, "speed": md.speed,
            "fly": md.fly, "swim": md.swim,
            "size": md.size.value, "cr": run.catalog[m.name].cr,
            "type": md.mtype, "alignment": md.alignment,
            "art": _art(m.name),
        })
    return out


def _enemy_view(run: FortuneRun) -> list[dict]:
    counts: dict[str, int] = {}
    for n in run.enemy_team():
        counts[n] = counts.get(n, 0) + 1
    return [{"name": n, "count": c, "cr": run.catalog[n].cr, "art": _art(n)}
            for n, c in sorted(counts.items())]


def _state(rid: str, run: FortuneRun) -> dict:
    years = sum(h.get("years", 0) for h in run.history)
    return {
        "run_id": rid, "phase": run.phase, "round": run.round, "wins": run.wins,
        "lives": run.lives, "lives_max": LIVES_START,
        "purse_cp": run.purse_cp, "purse": coins(run.purse_cp),
        "cap": run.cap(), "books": list(run.books),
        "team_cap": TEAM_CAP, "stable_cap": STABLE_CAP,
        "reroll_cp": REROLL_CP, "scout_cp": SCOUT_CP,
        "scouted": run.scouted,
        "shop": _shop_view(run),
        "stable": _stable_view(run),
        "bank": [{"name": n, "rarity": ITEMS[n].rarity, "effect": ITEMS[n].effect,
                  "blurb": ITEMS[n].blurb} for n in run.bank],
        "foresight": run.foresight(3),
        "enemy": (_enemy_view(run)
                  if run.phase == "shop" and run.scouted else []),
        "history": run.history, "years": years,
        "handle": HANDLES.get(rid, "Anonymous Berk"),
    }


def _get_run(rid: str) -> FortuneRun:
    run = RUNS.get(rid)
    if run is None:
        raise HTTPException(404, "no such run (the arena moves fast; it may have "
                                 "aged out of memory — start another)")
    return run


# -- run lifecycle -------------------------------------------------------------------

class NewRun(BaseModel):
    books: list[str]
    seed: int | None = None
    handle: str = "Anonymous Berk"


@router.get("/api/fortune/meta")
def meta() -> dict:
    """Everything the lobby needs: books, item catalog, wheel odds, house rules."""
    return {
        "books": _books(),
        "items": [asdict(i) for i in ITEMS.values()],
        "item_prices": {k: coins(v) for k, v in ITEM_PRICE_CP.items()},
        "team_cap": TEAM_CAP, "lives": LIVES_START,
        "reroll": coins(REROLL_CP), "scout": coins(SCOUT_CP),
        "maps": sorted(MAPS),
        # the ring layouts ARE the mechanics — the client draws exactly these
        "wheel": {"outer_ring": list(OUTER_RING), "middle_ring": list(MIDDLE_RING),
                  "center_ring": ["rare"] * 10},
    }


@router.post("/api/fortune/new")
def new(req: NewRun) -> dict:
    if len(RUNS) >= MAX_ACTIVE_RUNS:
        raise HTTPException(503, "the arena is at capacity tonight")
    seed = req.seed if req.seed is not None else secrets.randbelow(2**31 - 1)
    try:
        run = new_run(seed, tuple(req.books), _catalog())
    except FortuneError as exc:
        raise HTTPException(422, str(exc)) from exc
    rid = secrets.token_hex(8)
    RUNS[rid] = run
    HANDLES[rid] = (req.handle or "Anonymous Berk")[:40]
    return _state(rid, run)


@router.get("/api/fortune/run/{rid}")
def get_state(rid: str) -> dict:
    return _state(rid, _get_run(rid))


class Action(BaseModel):
    action: str                    # reroll | buy | buy_item | sell | train | freeze | attach
    slot: int | None = None
    target: int | None = None
    other: int | None = None
    kind: str = "monster"


@router.post("/api/fortune/run/{rid}/action")
def act(rid: str, req: Action) -> dict:
    run = _get_run(rid)
    try:
        if req.action == "reroll":
            run.reroll()
        elif req.action == "scout":
            run.scout()
        elif req.action == "buy":
            run.buy(req.slot, train_into=req.target)
        elif req.action == "buy_item":
            run.buy_item(req.slot, req.target)
        elif req.action == "sell":
            run.sell(req.target)
        elif req.action == "train":
            run.train(req.target, req.other)
        elif req.action == "bench":
            run.bench(req.target)
        elif req.action == "freeze":
            run.toggle_freeze(req.kind, req.slot)
        elif req.action == "attach":
            run.attach_bank_item(req.slot, req.target)
        else:
            raise HTTPException(422, f"unknown action: {req.action}")
    except FortuneError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (TypeError, IndexError) as exc:
        raise HTTPException(422, f"bad action arguments: {exc}") from exc
    return _state(rid, run)


# -- deployment & battle ----------------------------------------------------------------

@router.get("/api/fortune/run/{rid}/deploy")
def deploy_info(rid: str) -> dict:
    """The pre-battle board: map, weather, the legal drop zone, and the default
    formation (the client drags team A's tokens from these starting cells)."""
    run = _get_run(rid)
    if run.phase != "shop":
        raise HTTPException(422, f"not in the shop phase (currently: {run.phase})")
    if not run.stable:
        raise HTTPException(422, "the stable is empty — buy a monster first")
    map_name, weather = run.round_env(run.round)
    enc = build_encounter(run.player_defs(), run.enemy_team(),
                          seed=run.battle_seed(run.round), map_name=map_name,
                          roll_hp=False, weather=weather)
    from .arena import _combatant_payload
    combs = _combatant_payload(enc)
    for c in combs:
        c["token_art"] = _art(c["name"])
    return {
        "round": run.round, "map": map_name, "weather": weather,
        "zone": sorted(deployment_zone("A", map_name=map_name)),
        "grid": _grid_payload(enc),
        # your side only: the far corner stays dark unless a pit hand was bribed
        "combatants": [c for c in combs if c["team"] == "A"],
        "enemy": _enemy_view(run) if run.scouted else [],
        "scouted": run.scouted,
    }


class Deployment(BaseModel):
    placements: list[list[int] | None] = []


@router.post("/api/fortune/run/{rid}/battle")
def battle(rid: str, req: Deployment) -> dict:
    run = _get_run(rid)
    map_name, weather = run.round_env(run.round)
    placements = [tuple(p) if p else None for p in req.placements]
    player = run.player_defs()
    enemy = run.enemy_team()
    seed = run.battle_seed(run.round)
    try:
        result = run.fight(placements or None)
    except FortuneError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:                      # illegal drop from _deploy
        raise HTTPException(422, str(exc)) from exc
    enc = build_encounter(player, enemy, seed, map_name=map_name, roll_hp=False,
                          weather=weather, placements_a=placements or None)
    from .arena import _combatant_payload
    combs = _combatant_payload(enc)
    for c in combs:
        c["token_art"] = _art(c["name"])
    if run.phase == "over":
        _persist(rid, run)
    return {
        "battle": {
            "config": {"map": map_name or "", "weather": weather, "seed": seed},
            "winner": result.winner, "rounds": result.rounds,
            "survivors": result.survivors, "log": result.log,
            "events": [asdict(e) for e in result.events],
            "grid": _grid_payload(enc), "combatants": combs,
        },
        "outcome": {"won": result.winner == "A",
                    "years": result.rounds * 10,
                    "spin_owed": run.phase == "wheel"},
        "state": _state(rid, run),
    }


class Inscription(BaseModel):
    initials: str


@router.post("/api/fortune/run/{rid}/inscribe")
def inscribe(rid: str, req: Inscription) -> dict:
    """Carve up to three letters beside a finished run in the Book of Aeons."""
    run = _get_run(rid)
    if run.phase != "over":
        raise HTTPException(422, "the Book only takes initials when the gate closes")
    letters = "".join(c for c in req.initials.upper() if c.isalnum())[:3]
    if not letters:
        raise HTTPException(422, "give the Book something to carve (A-Z, 0-9)")
    _inscribe(rid, letters)
    return {"initials": letters}


@router.post("/api/fortune/run/{rid}/spin")
def spin(rid: str) -> dict:
    run = _get_run(rid)
    try:
        res = run.spin()
    except FortuneError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"spin": res, "state": _state(rid, run)}
