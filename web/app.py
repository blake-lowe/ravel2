"""The Blood Pit web service (ROADMAP Slice 12a) — FastAPI over the pure engine.

Read-only in 12a: serves the monster registry (raw stat-block JSON straight from
`data/monsters/`), playtested CR ratings from `data/calibration/ratings.db`, local
5e.tools art, and the static no-build frontend. No engine import is needed yet;
battles arrive with Slice 12b via `ravel.sim`.

Run:  python -m uvicorn web.app:app --reload
LAN:  python -m uvicorn web.app:app --host 0.0.0.0 --port 8000
      (0.0.0.0 binds all interfaces so other machines on the network can reach it;
      open the port in Windows Firewall once — see CLAUDE.md.)
"""
from __future__ import annotations

import json
import os
import sqlite3
import unicodedata
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
MONSTER_DIR = ROOT / "data" / "monsters"
DB_PATH = ROOT / "data" / "calibration" / "ratings.db"
STATIC_DIR = Path(__file__).resolve().parent / "static"
# Monster art comes from the 5etools-img GitHub mirror; art lives at
# <base>/<SOURCE>/<Monster Name>.webp. Override for a different mirror/CDN.
IMG_BASE = os.environ.get(
    "RAVEL_IMG_BASE",
    "https://raw.githubusercontent.com/5etools-mirror-3/5etools-img/main/bestiary")

RATING_FIELDS = ("nominal_cr", "nominal_xp", "adjusted_cr", "adjusted_xp", "ci_lo",
                 "ci_hi", "flag", "residual", "composition_spread", "group_synergy",
                 "adjusted_cr_llm", "skill_ceiling_delta", "llm_flag", "bt_cr",
                 "bt_games", "refined_cr", "bt_disagreement", "environment")


# Book label per data/monsters/ subdirectory; files at the top level are ours.
SOURCE_LABELS = {"mm": "MM"}


def _load_monsters() -> tuple[dict[str, dict], dict[str, str]]:
    """Name -> raw stat-block dict (straight from the source-of-truth JSON files)
    plus name -> source book, derived from the block's subdirectory. A malformed
    file (hand-edited blocks are invited) is skipped with a warning, never
    allowed to take the whole site down."""
    reg: dict[str, dict] = {}
    sources: dict[str, str] = {}
    for p in sorted(MONSTER_DIR.rglob("*.json")):
        try:
            block = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[bestiary] skipping unreadable stat block {p}: {exc}")
            continue
        if isinstance(block, dict) and block.get("name"):
            reg[block["name"]] = block
            sub = p.parent.name if p.parent != MONSTER_DIR else ""
            sources[block["name"]] = SOURCE_LABELS.get(sub, sub.upper() or "Ravel")
    return reg, sources


def _load_ratings() -> tuple[dict[str, dict], dict[str, list]]:
    """Name -> rating row (per_composition parsed), and name -> env-delta rows.
    Missing/empty DB degrades to no ratings — the Bestiary must render regardless."""
    if not DB_PATH.exists():
        return {}, {}
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        ratings: dict[str, dict] = {}
        for row in conn.execute(f"SELECT name, per_composition, {', '.join(RATING_FIELDS)}"
                                " FROM ratings"):
            r = {k: row[k] for k in RATING_FIELDS}
            try:
                r["per_composition"] = json.loads(row["per_composition"] or "{}")
            except json.JSONDecodeError:
                r["per_composition"] = {}
            ratings[row["name"]] = r
        env: dict[str, list] = {}
        for row in conn.execute("SELECT name, environment, env_cr, delta, flag"
                                " FROM env_ratings ORDER BY environment"):
            env.setdefault(row["name"], []).append(
                {k: row[k] for k in ("environment", "env_cr", "delta", "flag")})
        return ratings, env
    except sqlite3.OperationalError:        # schema not there yet
        return {}, {}
    finally:
        conn.close()


MONSTERS, MONSTER_SOURCES = _load_monsters()
RATINGS, ENV_RATINGS = _load_ratings()

app = FastAPI(title="Ravel — The Blood Pit", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

from .arena import router as arena_router        # noqa: E402  (needs app's RATINGS)
from .builder import router as builder_router    # noqa: E402
from .fortune import router as fortune_router    # noqa: E402

app.include_router(arena_router)
app.include_router(builder_router)
app.include_router(fortune_router)


# Art fallback chain, per monster: its own source book first (MPMM art lives
# under bestiary/MPMM/), then the books that printed the same creature earlier
# (MPMM reprints Volo's and Mordenkainen's Tome of Foes), then MM 2014 and the
# 2024 Monster Manual (XMM) which illustrates creatures MM 2014 didn't (e.g.
# Poltergeist), then the round tokens in the same order. Remote existence can't
# be probed cheaply, so the server sends every candidate in order and the
# browser walks the list on image-load errors.
BASE_ART_DIRS = ("MM", "XMM")
REPRINT_FALLBACKS = {"MPMM": ("VGM", "MTF")}


def art_dirs(name: str) -> tuple[str, ...]:
    """Ordered 5etools-img bestiary directories to probe for this monster's art.
    Source labels double as mirror directory names (mm -> MM, mpmm -> MPMM);
    'Ravel' house constructs have no book of their own and use the defaults."""
    src = MONSTER_SOURCES.get(name, "")
    dirs = [src] if src and src != "Ravel" else []
    dirs += REPRINT_FALLBACKS.get(src, ())
    dirs += [d for d in BASE_ART_DIRS if d not in dirs]
    return tuple(dirs)


def name_variants(name: str) -> list[str]:
    """Filename spellings to try per art directory: the exact name, dragon-age
    prefixes stripped (dragons may share one image per color), and ASCII-folded
    forms — the mirror stores 'Deep Rothé' as 'Deep Rothe.webp'."""
    names = [name]
    for prefix in ("Young ", "Adult ", "Ancient "):
        if name.startswith(prefix):
            names.append(name[len(prefix):])
    for n in list(names):
        folded = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
        if folded and folded not in names:
            names.append(folded)
    return names


def _image_candidates(name: str) -> list[str]:
    dirs = art_dirs(name)
    return [f"{IMG_BASE}/{src}/{quote(cand)}.webp"
            for src in (*dirs, *(f"tokens/{d}" for d in dirs))
            for cand in name_variants(name)]


# -- API --------------------------------------------------------------------

@app.get("/api/monsters")
def list_monsters() -> list[dict]:
    out = []
    for name, b in MONSTERS.items():
        r = RATINGS.get(name)
        out.append({
            "name": name,
            "cr": b.get("cr"),
            "type": b.get("type"),
            "source": MONSTER_SOURCES.get(name, ""),
            "size": b.get("size"),
            "ac": b.get("ac"),
            "hp": b.get("hp"),
            "alignment": b.get("alignment"),
            "adjusted_cr": r["adjusted_cr"] if r else None,
            "best_cr": (r["refined_cr"] if r and r["refined_cr"] is not None
                        else r["adjusted_cr"] if r else None),
            "flag": r["flag"] if r else None,
        })
    out.sort(key=lambda m: (m["cr"] if m["cr"] is not None else -1, m["name"]))
    return out


@app.get("/api/ratings")
def all_ratings() -> list[dict]:
    """Every playtested rating — feeds the Bestiary's aggregate figures."""
    return [{
        "name": name,
        "nominal_cr": r["nominal_cr"],
        "adjusted_cr": r["adjusted_cr"],
        "best_cr": r["refined_cr"] if r["refined_cr"] is not None else r["adjusted_cr"],
        "residual": r["residual"],
        "ci_lo": r["ci_lo"],
        "ci_hi": r["ci_hi"],
        "flag": r["flag"],
    } for name, r in RATINGS.items() if r["adjusted_cr"] is not None]


@app.get("/api/monsters/{name}")
def monster_detail(name: str) -> dict:
    block = MONSTERS.get(name)
    if block is None:
        raise HTTPException(404, f"no such monster: {name}")
    return {
        "statblock": block,
        "rating": RATINGS.get(name),
        "env": ENV_RATINGS.get(name, []),
        "images": _image_candidates(name),   # ordered; the client walks on error
    }


# -- pages ------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    return RedirectResponse("/pit")         # the Blood Pit is the main event


@app.get("/bestiary", include_in_schema=False)
def bestiary_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "bestiary.html")


@app.get("/pit", include_in_schema=False)
def pit_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "pit.html")


@app.get("/builder", include_in_schema=False)
def builder_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "builder.html")


@app.get("/supertemporal", include_in_schema=False)
def supertemporal_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "supertemporal.html")
