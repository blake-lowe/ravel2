---
name: import-monsters
description: Import D&D 5e monsters from a 5e.tools bestiary JSON into the Ravel engine — any book (Monster Manual, Volo's, Mordenkainen's, etc.). Parses the real stat-block data (no hallucination) into our schema, protects hand-curated blocks, validates everything loads and fights across all controllers, and audits imported traits for engine gaps. Use when the user wants to import/add a bestiary, a book of monsters, or a downloaded 5e.tools JSON.
---

# Import Monsters (5e.tools → Ravel)

The importer `tools/import_5etools.py` parses a 5e.tools bestiary JSON **directly** into our
`data/monsters` schema — core stats, defenses, senses, attacks (incl. flat/multi-type + save/grapple
riders), multiattack, recharge/save areas (breath weapons), spellcasting (mapped to spells the engine
owns), legendary actions + resistance. It then runs **`tools/trait_routing.py`** (`route_all`), which
moves abilities the parse left as text into the fields that mechanize them: breath/gaze/self-emanation
→ `areas`, Frightful Presence → `frightful_presence`, Death Burst → `death_burst`, Charge/Pounce →
`pounce`/`bonus_damage`, Swallow/Engulf → `swallow`, and detects boolean flags (`pack_tactics`,
`magic_resistance`, `flyby`, `blood_frenzy`, `magic_weapons`, `leadership`, `false_appearance`,
`swarm`). **Every ability it can't mechanize stays verbatim in `traits`** so nothing is lost.

Only import books the user owns.

## Inputs
- **Bestiary JSON**: a 5e.tools `bestiary-<book>.json` (the user downloads it — from the 5e.tools
  data set — and drops it in `sources/`). Its shape is `{"monster": [ {stat block}, ... ]}`.
- **Book code**: a short slug for the source, e.g. `mm`, `vgm`, `mpmm`, `mtf`. Becomes the output
  subfolder `data/monsters/<book>/` and the provenance tag `"imported": "5etools-<book>"`.

## Steps

1. **Confirm the JSON is present** and count it:
   `python -c "import json; d=json.load(open('sources/bestiary-<book>.json',encoding='utf-8')); print(len(d['monster']),'stat blocks')"`

2. **Run the importer** (creates `data/monsters/<book>/` automatically):
   ```
   python tools/import_5etools.py sources/bestiary-<book>.json <book>
   ```
   It prints `written / skipped(curated) / failed` plus any imported-with-no-attack (they still
   move/dodge) and any hard failures. Re-running is idempotent: it **regenerates** auto-imported
   blocks (so importer improvements + trait routing propagate) and **skips** anything flagged
   `"curated": true`. Prefer re-importing from source over the migration when the JSON is available —
   it recovers everything (grapple riders and dropped spells need the source text). If you only have
   already-imported files and not the JSON, `python tools/upgrade_traits.py [data/monsters/<book>]`
   applies the same trait routing in place (idempotent, skips curated) from the preserved `traits`.

3. **Validate the whole registry loads**:
   `python -c "from ravel import content; content.reload(); print(len(content.all_names()),'monsters load')"`

4. **Exhaustively smoke-test across all controllers** — every new monster must fight without
   crashing under Heuristic and Random (and a small LLM sample). Run from the repo root:
   ```python
   from ravel.sim import run_battle
   from ravel import content; content.reload()
   import json, glob, os, traceback
   new=[json.load(open(f,encoding='utf-8'))['name']
        for f in glob.glob('data/monsters/<book>/*.json')]
   crash=0
   for ai in ('heuristic','random'):
       for n in new:
           try: run_battle([n],['Goblin','Goblin','Goblin'],seed=1,ai=ai)
           except Exception:
               crash+=1; print('ERR',ai,n,traceback.format_exc().splitlines()[-1][:70])
   print(f'{len(new)} monsters x2 controllers: {crash} crashes')
   ```
   Then a **small LLM pass** (slow — one local-model call per decision; keep it tiny) on a handful
   of the more complex casters/legendary monsters, checking `LLMController.fallbacks == 0`
   (all choices legal). And a **determinism** spot-check: the same seed must give an identical log
   twice (`run_battle(...).log == run_battle(...).log`). HP is rolled from hit dice by default
   (`--avg-hp` / `roll_hp=False` opts out), so determinism means "same seed → same rolls → same log".

5. **Audit imported traits for engine gaps** (find where "imported" falls short of "fully
   supported"). Fan out subagents over **batches of 10 monsters** — one agent per batch reads its
   10 files' `traits`/`actions`/`spellcasting` and classifies every combat-relevant ability as
   `supported` / `partial` / `unsupported`, with the concrete engine work each gap needs. Then a
   synthesis agent ranks the engine updates by coverage-per-effort. Give every batch agent the
   **engine-capability spec** (what's mechanized vs. not — attacks/riders, areas, conditions,
   movement modes, trait flags, the ~40-spell library, reactions registry, swallow, auras) so it
   judges accurately; tell it to report only `partial`/`unsupported` findings. A ready-made
   orchestration is the **`audit-imported-traits`** workflow (`.claude/workflows/`) — invoke it with
   `args = { "dir": "data/monsters/<book>", "slugs": [ non-curated slugs ] }` (pass the object as an
   actual JSON value, not a string). It fans out the batches, aggregates by ability, and returns a
   ranked engine-update plan. Verify the headline counts empirically before acting (the batch agents
   can flake); record the results in `docs/ENGINE_GAPS.md`.

6. **Report** to the user: counts (imported / skipped-curated / failed / no-attack), smoke result,
   and the ranked list of engine updates the audit surfaced (highest coverage-per-effort first).

## Protecting hand-edited monsters
Once you tune a block by hand (wire its special mechanics, fix numbers), add `"curated": true` to
its JSON. The importer then never overwrites it on re-run. Curated blocks may live at the top
level or inside a book folder; the loader recurses either way.

## Ranking imported monsters
Imported blocks get real playtested CR ratings via the **cr-rate** / **cr-benchmark** skills:
- A handful of new blocks → `python -m ravel.calib rate-new "Name A;Name B"` (incremental — no
  recalibration; runs the whole pipeline and stores to `ratings.db`).
- A whole book → `python -m ravel.calib rate-all --cap 30` then `bt` / `environments` / `factors`
  (see **cr-benchmark**). Results land in `ratings.db` / `encounter_view`.

## Notes
- **"Imported" ≠ "fully supported."** Auto-imported blocks have faithful *core* mechanics
  (stats/attacks/breath/spells); their *special* abilities sit in `traits` as text until mechanized
  (step 5 finds which are worth doing).
- **Spells** referenced by a stat block only fire if they exist in the engine's spell library
  (`data/spells/`). Unknown spell names are dropped at import — the audit flags casters this hits.
- The importer parses `{@atk}`/`{@hit}`/`{@damage}`/`{@dc}`/`{@recharge}`/`{@spell …}` tags; a save
  ability described only in prose (not an `{@atk}`/area) won't be mechanized — it lands in `traits`.
- Loader recurses subfolders, so `data/monsters/<book>/` is picked up with no code change.
