"""In-place migration: route already-imported monsters' descriptive `traits` text into the
engine fields that mechanize them (areas / frightful_presence / death_burst / pounce /
bonus_damage / swallow). Curated blocks are left untouched. Idempotent — a routed trait is
removed from `traits`, so re-running is a no-op. Run:

    python tools/upgrade_traits.py [data/monsters/<book>]
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.trait_routing import route_all as upgrade  # noqa: E402,F401


def main():
    import ravel.statblock as sb
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "monsters" / "mm"
    changed = 0
    counts: dict[str, int] = {}
    for f in sorted(glob.glob(str(root / "*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        if d.get("curated"):
            continue
        routed = upgrade(d)
        if not routed:
            continue
        sb.monster_from_dict(d)                 # validate before writing
        Path(f).write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
        changed += 1
        for r in routed:
            counts[r.split(":")[0].split("(")[0]] = \
                counts.get(r.split(":")[0].split("(")[0], 0) + 1
    print(f"upgraded {changed} files. routed:", dict(sorted(counts.items(),
                                                            key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
