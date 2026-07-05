"""Monster registry — fully file-driven. One JSON stat block per file under
`data/monsters/`. Edit/add a file there and it shows up; no code changes needed.
"""
from __future__ import annotations

from pathlib import Path

from .models import Combatant, MonsterDef
from .statblock import load_dir

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "monsters"

_M: dict[str, MonsterDef] = load_dir(DATA_DIR)


def reload() -> None:
    """Re-read the data directory (after editing/adding stat-block files)."""
    global _M
    _M = load_dir(DATA_DIR)


def get(name: str) -> MonsterDef:
    key = name.lower()
    if key not in _M:
        raise KeyError(f"unknown monster '{name}'. known: {sorted(_M)}")
    return _M[key]


def all_names() -> list[str]:
    return [md.name for md in sorted(_M.values(), key=lambda m: (m.cr, m.name))]


def make(name: str, cid: str, team: str, pos: tuple[int, int]) -> Combatant:
    md = get(name)
    return Combatant(id=cid, team=team, md=md, hp=md.hp, pos=pos,
                     slots=dict(md.spell_slots), innate_left=dict(md.innate))
