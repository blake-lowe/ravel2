---
name: import-spells
description: Import D&D 5e spells from 5e.tools spell JSONs into the Ravel engine's spell library (data/spells/) — typically to give imported monster casters their full lists. Parses the real spell data into the engine's effect schema, curates what regexes can't, refuses (with a named reason) what the engine can't model, and validates by re-importing the bestiaries and smoke-testing every caster. Use when the user wants to import/add spells, grow the spell library, or casters are missing book spells.
---

# Import Spells (5e.tools → data/spells/)

The importer `tools/import_5etools_spells.py` converts 5e.tools spell JSONs into the engine's
one-file-per-spell schema (`ravel/spells.py`). It targets **the spells monster stat blocks
actually reference** (scanned from `sources/bestiary-*.json`) so the library grows exactly as
fast as the bestiary needs it; `--all` imports everything in the sources instead.

Every spell lands in exactly one bucket — **nothing is silently dropped**:

| bucket | meaning | where it's recorded |
|---|---|---|
| **written** | auto-parsed or curated into `data/spells/<slug>.json` | the file (`"imported": "5etools"`) |
| **INERT** | no arena-combat effect (utility/social/divination/out-of-combat casts) | table in the importer, with the reason |
| **UNMAPPED** | combat-relevant but needs an engine effect kind that doesn't exist | table in the importer; mirror the list into `docs/ENGINE_GAPS.md` |
| **failed** | in no bucket and the parser got nothing — needs human triage | printed; triage into one of the three above |

## Inputs
- **Spell JSONs**: 5e.tools `spells-<book>.json` files in `sources/` (same provenance as the
  bestiaries; `spells-phb.json` + `spells-xge.json` + `spells-tce.json` cover the MM/MPMM
  casters). Only import books the user owns.

## Steps

1. **Measure the gap** (spells referenced by monsters vs the library):
   `{@spell …}` tags in the bestiary sources vs `ravel.spells.known()` — the importer prints
   this as its `wanted` set; a quick pre-count keeps expectations calibrated.

2. **Run it**: `python tools/import_5etools_spells.py`
   Re-running is idempotent: files with `"imported"` are regenerated (parser improvements
   propagate), hand-built library files and anything without the marker are never touched, and
   a spell later ruled INERT/UNMAPPED gets its stale file **retracted** automatically.

3. **Triage the `failed` list to zero** (minus spells from books whose sources aren't
   downloaded). Each name goes into INERT (with a reason), UNMAPPED (with the missing effect
   kind), or OVERRIDES (a hand-written definition).

4. **Review the written spells — this is where the real errors live.** Print a compact table
   (level / target mode / shape / effects per spell) and read every line against the book text.
   Known failure patterns from the first run of this importer, all now guarded but worth
   re-checking on new books:
   - **Smite-family self riders** ("the next time you hit with a weapon attack…") parse as
     attack spells; they're buffs. A guard rejects them — keep them INERT.
   - **Protection clauses read as target caps** ("select up to three creatures … to ignore the
     spell" is Sculpt Spells, not targeting).
   - **Walls and persistent zones** (prismatic wall, wind wall, blade barrier) parse as one-shot
     nukes with every layer's damage summed — wildly wrong; they're UNMAPPED until the engine
     has blocking terrain.
   - **Multi-round channels** (call lightning, enervation, witch bolt, storm of vengeance)
     parse with all rounds' dice at once — curate to one tick, or leave out if one tick would
     misprice it.
   - **Junk matches on flavor dice** (Wish's 1d10-necrotic stress clause became the spell's
     "damage"). If the damage isn't the spell's point, the spell isn't auto-parseable.
   - **Area radii from the wrong sentence** (Call Lightning's 60-ft *cloud* became the damage
     radius; the bolt is 5 ft).
   - **Slug collisions**: the importer's slug and a hand-built file's name can differ
     (`hunter_s_mark` vs `hunters_mark`) — the library-membership check must run by NAME, not
     by file path.
5. **Approximations must be honest**: every curated definition that simplifies the book text
   carries an `"_approx"` field saying exactly what was dropped (the loader ignores it). If an
   approximation would be *stronger* than omission (witch bolt's first-tick-only), prefer
   omission.

6. **Re-import the bestiaries** so caster blocks pick up the newly known spells (the monster
   importer keeps only library spells): `python tools/import_5etools.py sources/bestiary-<book>.json <book>`.
   Note innate casters (Archdruid-style "casts one of the following") land in `innate`, not
   `spells` — check both when verifying.

7. **Validate**:
   - full suite: `python -m pytest -q`
   - roster smoke, all controllers (new spell shapes are a new crash surface):
     every monster × {heuristic, greedy, random} vs 3 goblins — 0 crashes required
   - determinism: same seed twice → identical log, on a heavy caster (Lich)
   - eyeball one caster's log: the new spells actually fire

8. **Re-rate the casters whose blocks changed** (their ratings were measured with thinner
   lists): the changed set = blocks whose `spells`/`innate` reference a newly written spell.
   Use the parallel batch recipe in the **cr-rate** skill / `parallel-rate-batches` memory
   (`rate-new --no-bt` chunks + one BT pass with stale-pair eviction).

9. **Record**: update `docs/ENGINE_GAPS.md` with the UNMAPPED list (each is a named engine
   item, not a deferral) and the library count.

## Notes
- The engine's effect vocabulary (what CAN be modelled): `spell_attack`, `save` (damage /
  condition / modifier_on_fail / forced_move), `auto_damage`, `heal`, `modifier`
  (ac/attack/save/speed/advantage-flags/damage_rider), `aura`, `summon`, `banish`.
  If a spell needs anything else, it's UNMAPPED by definition.
- Conditions must be engine conditions (see `ravel/conditions.py`); a lasting condition with
  no repeat-save clause gets `duration_rounds` (never permanent).
- `data/spells/` files without the `"imported"` marker are treated as hand-built and are
  never overwritten or retracted.
