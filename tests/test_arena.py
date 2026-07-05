"""Slice 12b arena API: deterministic battles with full replay payloads, config
validation, odds, and the SSE gauntlet. Self-skips without FastAPI."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient      # noqa: E402

from web.app import app                        # noqa: E402

client = TestClient(app)

BOUT = "/api/battle?a=Ogre&b=Goblin,Goblin&seed=3"


def test_arena_meta():
    m = client.get("/api/arena-meta").json()
    assert "lava_cavern" in m["maps"] and "ruins" in m["maps"]
    assert set(m["ais"]) >= {"heuristic", "random", "llm"}
    assert len(m["roster"]) >= 450
    assert any(r["xp"] > 0 for r in m["roster"])


def test_battle_payload():
    d = client.get(BOUT).json()
    assert d["winner"] in ("A", "B", None) and d["rounds"] >= 1
    assert d["log"] and d["events"]
    spawns = [e for e in d["events"] if e["kind"] == "spawn"]
    assert len(spawns) >= 3 and all(e["info"] in ("A", "B") for e in spawns)
    assert d["grid"]["w"] > 0 and d["grid"]["h"] > 0
    assert len(d["combatants"]) == 3
    assert all(c["max_hp"] > 0 and c["team"] in ("A", "B") for c in d["combatants"])
    assert "line" in d["odds"]
    assert d["config"]["seed"] == 3


def test_battle_is_deterministic():
    one, two = client.get(BOUT).json(), client.get(BOUT).json()
    assert one == two, "same permalink must reproduce the identical bout"


def test_battle_on_named_map():
    d = client.get(BOUT + "&map=lava_cavern").json()
    assert d["grid"]["walls"], "lava cavern is walled"
    assert any(h["name"] == "lava" for h in d["grid"]["hazards"])
    assert any("d10 fire" in dmg for h in d["grid"]["hazards"] for dmg in h["damage"])


def test_battle_validation():
    assert client.get("/api/battle?a=Fakemon&b=Goblin").status_code == 422
    assert client.get("/api/battle?a=&b=Goblin").status_code == 422
    assert client.get(BOUT + "&ai=psychic").status_code == 422
    assert client.get(BOUT + "&map=narnia").status_code == 422
    assert client.get(BOUT + "&surprised=C").status_code == 422
    too_many = ",".join(["Goblin"] * 13)
    assert client.get(f"/api/battle?a={too_many}&b=Goblin").status_code == 422


def test_gauntlet_streams():
    with client.stream("GET", "/api/gauntlet?a=Ogre&b=Goblin,Goblin&n=5&seed0=1") as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    frames = [f for f in body.split("\n\n") if f.strip()]
    data = [json.loads(f.split("data: ", 1)[1]) for f in frames if not f.startswith("event:")]
    done = [json.loads(f.split("data: ", 1)[1]) for f in frames if f.startswith("event: done")]
    assert len(data) == 5 and [d["i"] for d in data] == [1, 2, 3, 4, 5]
    assert len(done) == 1
    s = done[0]
    assert s["wins_a"] + s["wins_b"] + s["draws"] == 5
    assert len(s["rounds"]) == 5 and 0 <= s["ci_a"][0] <= s["win_rate_a"] <= s["ci_a"][1] <= 1


def test_js_replay_matches_engine():
    """The client replay is a pure fold over the event stream — its final state
    must agree exactly with the engine's reported survivors."""
    _node_smoke(client.get(BOUT + "&map=ruins").json())


def test_gauntlet_validates_before_streaming():
    assert client.get("/api/gauntlet?a=Fakemon&b=Goblin&n=3").status_code == 422
    assert client.get("/api/gauntlet?a=&b=Goblin&n=3").status_code == 422


def _node_smoke(payload) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump(payload, f)
        path = f.name
    smoke = Path(__file__).parent / "pit_replay_smoke.js"
    proc = subprocess.run([node, str(smoke), path], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_js_replay_folds_survive_events():
    """Undead Fortitude emits survive(hp=1) after damage(hp=0) — the JS fold must
    track it exactly like ravel/reducer.py (review finding)."""
    for seed in range(1, 30):
        d = client.get(f"/api/battle?a=Ogre&b=Zombie,Zombie&seed={seed}").json()
        if any(e["kind"] == "survive" for e in d["events"]):
            _node_smoke(d)
            return
    pytest.fail("no seed in 1..29 produced a survive event — pick a new matchup")


def test_flee_events_remove_routed_creatures():
    """A routed creature that reaches the map edge emits a flee event; the fold
    marks it fled and it never appears among the survivors."""
    for seed in range(1, 60):
        d = client.get(f"/api/battle?a=Ogre&b=Kobold,Kobold,Kobold&seed={seed}").json()
        fled = [e for e in d["events"] if e["kind"] == "flee"]
        if fled:
            survivor_ids = {s[0] for s in d["survivors"]}
            assert all(e["actor"] not in survivor_ids for e in fled)
            _node_smoke(d)
            return
    pytest.fail("no seed in 1..59 produced a rout — pick a more cowardly matchup")


def test_lair_toggle_gates_lair_actions():
    """lair= names the CREATURES fighting in their lair (covers every copy).
    Default is off — an arena bout is nobody's lair."""
    base = "/api/battle?a=Adult Red Dragon&b=Fire Giant,Fire Giant&seed={s}"
    for seed in range(1, 15):
        on = client.get(base.format(s=seed) + "&lair=Adult Red Dragon").json()
        if any("Lair action" in line for line in on["log"]):
            off = client.get(base.format(s=seed)).json()               # default: no lair
            assert not any("Lair action" in line for line in off["log"])
            assert off["winner"] in ("A", "B", None)
            return
    pytest.fail("no seed in 1..14 produced a lair action — check the exemplar")


def test_lair_validation_and_meta():
    assert client.get(BOUT + "&lair=Fakemon").status_code == 422
    roster = {r["name"]: r for r in client.get("/api/arena-meta").json()["roster"]}
    assert roster["Adult Red Dragon"]["has_lair"] is True
    assert roster["Goblin"]["has_lair"] is False


def test_battle_stream_matches_plain_battle():
    """/api/battle-stream ends with a done frame identical to /api/battle for a
    deterministic controller (the progress frames are extra, not different)."""
    q = "a=Ogre&b=Goblin,Goblin&seed=3"
    with client.stream("GET", f"/api/battle-stream?{q}") as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    done = [f for f in body.split("\n\n") if f.startswith("event: done")]
    assert len(done) == 1
    payload = json.loads(done[0].split("data: ", 1)[1])
    assert payload == client.get(f"/api/battle?{q}").json()


def test_fight_with_progress_returns_result():
    """The shared threaded-bout helper yields progress dicts and returns the
    BattleResult — identical to run_battle for a deterministic controller."""
    from ravel.sim import run_battle
    from web.arena import _battle_kwargs, _fight_with_progress
    kw = _battle_kwargs(["Ogre"], ["Goblin", "Goblin"], 3, "heuristic", "",
                        "clear", False, False, "", False, "AB")
    gen = _fight_with_progress(kw, "heuristic", 3)
    ticks = []
    while True:
        try:
            ticks.append(next(gen))
        except StopIteration as stop:
            result = stop.value
            break
    assert all("round" in t and "decisions" in t for t in ticks)
    direct = run_battle(**kw)
    assert (result.winner, result.rounds, result.log) == \
           (direct.winner, direct.rounds, direct.log)


def test_events_carry_altitude():
    """Flyers' spawn/move events carry `alt` so the replay can badge airborne
    combatants; a dragon that climbs must show alt > 0 somewhere."""
    for seed in range(1, 12):
        d = client.get(f"/api/battle?a=Young Red Dragon&b=Ogre,Ogre&seed={seed}").json()
        assert all("alt" in e for e in d["events"])
        if any(e["alt"] > 0 for e in d["events"] if e["kind"] == "move"):
            return
    pytest.fail("the dragon never climbed in seeds 1..11 — check flyer tactics")


def test_pit_page_served():
    page = client.get("/pit")
    assert page.status_code == 200 and "Blood Pit" in page.text
    assert client.get("/", follow_redirects=False).headers["location"] == "/pit"
