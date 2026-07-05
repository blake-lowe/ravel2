"""Structured store for playtested CR ratings — the source of truth the rating scripts
write into (not a post-hoc export). SQLite via stdlib; CSV/JSON are derived views.

One `ratings` row per monster carries the full nuance an encounter builder needs:
the adjusted CR + confidence, the per-composition action-economy vector, the LLM
skill-ceiling delta, and group synergy. `runs` records provenance; `encounter_view`
exposes the UI-facing signals. See docs/CR_CALIBRATION.md.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "calibration" / "ratings.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  kind         TEXT,                       -- 'heuristic' | 'llm'
  bench        TEXT,                       -- json list of bench monster names
  seeds        INTEGER,
  ladder       TEXT,                       -- json
  compositions TEXT,                       -- json list of body counts
  calib_points TEXT,                       -- json [[B*, CR], ...]
  label        TEXT,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ratings (
  name                TEXT PRIMARY KEY,
  nominal_cr          REAL,
  nominal_xp          REAL,
  -- heuristic (canonical) rating
  adjusted_cr         REAL,
  adjusted_xp         REAL,
  raw_cr              REAL,
  ci_lo               REAL,
  ci_hi               REAL,
  flag                TEXT,
  residual            REAL,                -- adjusted_cr - nominal_cr
  -- action-economy sensitivity
  per_composition     TEXT,                -- json {bodies: cr}
  composition_spread  REAL,                -- few-strong CR - many-weak CR (swingy if large)
  group_synergy       REAL,                -- grouped CR - solo CR (nullable; wants friends)
  environment         TEXT DEFAULT 'open',
  -- controller skill ceiling (nullable; filled by the LLM pass)
  adjusted_cr_llm     REAL,
  skill_ceiling_delta REAL,                -- adjusted_cr_llm - adjusted_cr
  llm_flag            TEXT,
  -- Bradley-Terry cross-check (nullable; filled by the round-robin pass)
  bt_cr               REAL,                -- BT strength anchored to CR
  bt_games            INTEGER,             -- comparisons behind it (confidence)
  refined_cr          REAL,                -- consensus of mirror + BT
  bt_disagreement     REAL,                -- adjusted_cr - bt_cr (matchup-dependent if large)
  run_id              INTEGER,
  updated_at          TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
CREATE INDEX IF NOT EXISTS idx_ratings_adjusted ON ratings(adjusted_cr);

-- Per-environment CR (one row per monster x environment). The open baseline lives in
-- ratings.adjusted_cr; this holds underwater/windy/fog/dungeon/lava deltas.
CREATE TABLE IF NOT EXISTS env_ratings (
  name        TEXT,
  environment TEXT,
  env_cr      REAL,
  delta       REAL,                        -- env_cr - open adjusted_cr
  flag        TEXT,
  PRIMARY KEY (name, environment)
);

"""

# What an encounter builder reads: the consensus effective CR/XP plus the advisory signals.
# Recreated on every connect (see _migrate) so it always reflects the latest columns.
ENCOUNTER_VIEW = """
DROP VIEW IF EXISTS encounter_view;
CREATE VIEW encounter_view AS
  SELECT name, nominal_cr, nominal_xp,
         adjusted_cr,
         COALESCE(refined_cr, adjusted_cr)               AS best_cr,       -- mirror+BT consensus
         adjusted_xp,
         ci_lo, ci_hi, flag, residual,
         composition_spread                              AS action_economy_sensitivity,
         skill_ceiling_delta                             AS needs_good_play,
         group_synergy                                   AS wants_friends,
         bt_disagreement                                 AS solo_vs_group, -- neg=boss(1v1), pos=stronger in numbers
         native_env,
         env_sensitivity                                 AS terrain_swing, -- largest env CR shift vs open
         bt_cr
  FROM ratings;
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Open the store for reading and writing. Safe to hold from several
    processes at once (parallel rate-new chunks): WAL journaling plus a long
    busy timeout make the rare, tiny writes queue instead of raising
    'database is locked' — the schema/view DDL below included. Autocommit
    (isolation_level=None) keeps each write's lock at statement length;
    otherwise the caller's implicit transaction stays open across whole
    battle simulations and starves every other writer."""
    conn = sqlite3.connect(str(path), timeout=60.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a DB was first created (CREATE IF NOT EXISTS won't)."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(ratings)")}
    for col, decl in (("bt_cr", "REAL"), ("bt_games", "INTEGER"),
                      ("refined_cr", "REAL"), ("bt_disagreement", "REAL"),
                      ("predicted_cr", "REAL"), ("model_residual", "REAL"),
                      ("native_env", "TEXT"), ("env_sensitivity", "REAL")):
        if col not in have:
            conn.execute(f"ALTER TABLE ratings ADD COLUMN {col} {decl}")
    # refresh the view to the latest columns. The DROP+CREATE must be one atomic
    # write transaction: under autocommit, two processes connecting at once can
    # otherwise interleave (both drop, both create -> 'already exists').
    drop, create = (s.strip() for s in ENCOUNTER_VIEW.strip().split(";", 1))
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(drop)
        conn.execute(create.rstrip(";"))
        conn.execute("COMMIT")
    except sqlite3.OperationalError:
        conn.execute("ROLLBACK")
        # a concurrent connect already refreshed it — nothing left to do
    conn.commit()


def record_run(conn: sqlite3.Connection, kind: str, cfg: dict, bench, calib_points,
               label: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO runs (kind, bench, seeds, ladder, compositions, calib_points, label) "
        "VALUES (?,?,?,?,?,?,?)",
        (kind, json.dumps(bench), cfg.get("seeds"), json.dumps(cfg.get("ladder")),
         json.dumps(cfg.get("compositions")), json.dumps(calib_points), label))
    conn.commit()
    return cur.lastrowid


def record_from_rate(name: str, r: dict, nominal_xp: float, adjusted_xp: float) -> dict:
    """Flatten a rate() result into the ratings columns (heuristic side)."""
    pc = r.get("per_composition") or {}
    spread = None
    if pc:
        keys = sorted(int(k) for k in pc)
        spread = round(pc[keys[0]] - pc[keys[-1]], 2)   # few-strong - many-weak
    grp = r.get("group") or {}
    return {
        "name": name,
        "nominal_cr": r["nominal_cr"],
        "nominal_xp": round(nominal_xp, 1),
        "adjusted_cr": r["adjusted_cr"],
        "adjusted_xp": round(adjusted_xp, 1),
        "raw_cr": r["raw_cr"],
        "ci_lo": r["ci"][0],
        "ci_hi": r["ci"][1],
        "flag": r["flag"],
        "residual": round(r["adjusted_cr"] - r["nominal_cr"], 2),
        "per_composition": json.dumps({int(k): v for k, v in pc.items()}),
        "composition_spread": spread,
        "group_synergy": grp.get("synergy"),
        "environment": next(iter(r.get("by_env", {"open": 0})), "open"),
    }


_HEUR_COLS = ("nominal_cr", "nominal_xp", "adjusted_cr", "adjusted_xp", "raw_cr",
              "ci_lo", "ci_hi", "flag", "residual", "per_composition",
              "composition_spread", "group_synergy", "environment")


def upsert_rating(conn: sqlite3.Connection, rec: dict, run_id: int | None = None) -> None:
    """Insert/update the heuristic fields for a monster, preserving any LLM fields."""
    cols = ["name", *_HEUR_COLS, "run_id"]
    vals = [rec["name"], *[rec.get(c) for c in _HEUR_COLS], run_id]
    updates = ", ".join(f"{c}=excluded.{c}" for c in (*_HEUR_COLS, "run_id"))
    conn.execute(
        f"INSERT INTO ratings ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
        f"ON CONFLICT(name) DO UPDATE SET {updates}, updated_at=CURRENT_TIMESTAMP",
        vals)


def upsert_llm(conn: sqlite3.Connection, name: str, nominal_cr: float,
               heuristic_cr: float, llm_cr: float, delta: float, flag: str) -> None:
    """Set the LLM skill-ceiling fields; create the row if the heuristic pass hasn't run."""
    conn.execute(
        "INSERT INTO ratings (name, nominal_cr, adjusted_cr, adjusted_cr_llm, "
        "skill_ceiling_delta, llm_flag) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET adjusted_cr_llm=excluded.adjusted_cr_llm, "
        "skill_ceiling_delta=excluded.skill_ceiling_delta, llm_flag=excluded.llm_flag, "
        "updated_at=CURRENT_TIMESTAMP",
        (name, nominal_cr, heuristic_cr, llm_cr, delta, flag))


def upsert_bt(conn: sqlite3.Connection, name: str, bt_cr: float, games: int,
              refined_cr: float, disagreement: float) -> None:
    """Set the Bradley-Terry cross-check fields; create the row if none exists."""
    conn.execute(
        "INSERT INTO ratings (name, bt_cr, bt_games, refined_cr, bt_disagreement) "
        "VALUES (?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET bt_cr=excluded.bt_cr, "
        "bt_games=excluded.bt_games, refined_cr=excluded.refined_cr, "
        "bt_disagreement=excluded.bt_disagreement, updated_at=CURRENT_TIMESTAMP",
        (name, bt_cr, games, refined_cr, disagreement))


def upsert_env(conn: sqlite3.Connection, name: str, environment: str, env_cr: float,
               delta: float, flag: str) -> None:
    conn.execute(
        "INSERT INTO env_ratings (name, environment, env_cr, delta, flag) VALUES (?,?,?,?,?) "
        "ON CONFLICT(name, environment) DO UPDATE SET env_cr=excluded.env_cr, "
        "delta=excluded.delta, flag=excluded.flag", (name, environment, env_cr, delta, flag))


def set_env_summary(conn: sqlite3.Connection, name: str, native: str,
                    sensitivity: float) -> None:
    conn.execute("INSERT INTO ratings (name, native_env, env_sensitivity) VALUES (?,?,?) "
                 "ON CONFLICT(name) DO UPDATE SET native_env=excluded.native_env, "
                 "env_sensitivity=excluded.env_sensitivity", (name, native, sensitivity))


def export_csv(conn: sqlite3.Connection, path: Path) -> int:
    import csv
    rows = conn.execute(
        "SELECT name, nominal_cr, nominal_xp, adjusted_cr, adjusted_xp, raw_cr, ci_lo, "
        "ci_hi, flag, residual, per_composition, composition_spread, group_synergy, "
        "adjusted_cr_llm, skill_ceiling_delta FROM ratings ORDER BY residual").fetchall()
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if rows:
            w.writerow(rows[0].keys())
            w.writerows([tuple(r) for r in rows])
    return len(rows)
