# Ravel 2

A deterministic D&D 5e battle engine with an LLM used only to *choose* (never to
compute), plus a web UI: the **Bestiary** and **The Blood Pit** arena. Docs live in
`docs/` (SPEC, ROADMAP, ARCHITECTURE, STRATEGY); project rules in `CLAUDE.md`.

## Run the website

```bash
python -m pip install fastapi uvicorn
python -m uvicorn web.app:app --reload
```

Open <http://127.0.0.1:8000> — **The Blood Pit** (book a match, replay it blow by
blow, or run a many-seed gauntlet; every bout is a shareable permalink) and the
**Bestiary**. The character builder arrives with ROADMAP Slice 12c.

Monster art loads from the [5etools-img GitHub mirror](https://github.com/5etools-mirror-3/5etools-img)
(override the base URL with the `RAVEL_IMG_BASE` env var). Offline, the Bestiary
renders text-only.

Restart the server after adding monsters or ratings (data is loaded at startup).

## CLI

```bash
python -m ravel.cli list                                   # roster by CR
python -m ravel.cli fight "Ogre" "Goblin,Goblin" --seed 3  # one battle, full log
python -m ravel.cli batch "Troll" "Owlbear" -n 50          # aggregate win rates
```

`--ai llm` drives decisions with a local Ollama model (`gemma4:12b` at
`localhost:11434`) — slow; keep `-n` small.

## Tests

```bash
python -m pytest -q
```

The engine is stdlib-only; `fastapi`/`uvicorn`/`httpx` are needed only for the web
layer and its tests (which self-skip when absent).
