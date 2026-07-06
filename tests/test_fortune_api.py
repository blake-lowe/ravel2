"""Slice 12e web layer: the Supertemporal Arena API - lobby, shop actions,
deployment, battle payload (replay-shaped), the wheel, and the Book of Ages.
Skipped wholesale if FastAPI isn't installed (the engine suite must not require it)."""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient        # noqa: E402

import web.fortune as wf                          # noqa: E402
from web.app import app                           # noqa: E402

client = TestClient(app)


def start(seed=42, books=("MM",), handle="Testy"):
    r = client.post("/api/fortune/new",
                    json={"books": list(books), "seed": seed, "handle": handle})
    assert r.status_code == 200, r.text
    return r.json()


def test_meta_lists_books_items_and_odds():
    m = client.get("/api/fortune/meta").json()
    labels = {b["label"] for b in m["books"]}
    assert "MM" in labels
    assert len(m["items"]) == 23           # 4 common / 8 uncommon / 11 rare
    ring = m["wheel"]["outer_ring"]
    assert ring.count("none") == 3 and ring.count("common") == 5
    assert ring.count("advance") == 2
    assert "nonenone" not in "".join(ring), "no-prize sectors are spread out"
    mid = m["wheel"]["middle_ring"]
    assert mid.count("none") == 1 and mid.count("advance") == 2
    assert m["team_cap"] == 5 and m["lives"] == 3


def test_new_run_state_shape():
    s = start()
    assert s["phase"] == "shop" and s["round"] == 1 and s["lives"] == 3
    assert s["purse_cp"] == 1000 and s["cap"] == 1
    assert len(s["shop"]["monsters"]) == 5 and len(s["shop"]["items"]) == 2
    for slot in s["shop"]["monsters"]:
        assert slot["cr"] <= 1 and slot["source"] == "MM"
        assert slot["price"] and slot["art"]
        assert slot["hp"] > 0 and slot["ac"] > 0 and slot["size"]
    assert len(s["foresight"]) == 3
    assert s["enemy"] == [] and not s["scouted"], "the opposition is a paid secret"
    assert s["handle"] == "Testy"
    assert s["train_cap"] == 3 and s["set_size"] == 4 and s["sets_awarded"] == []


def test_scouting_reveals_the_bill():
    s = start(seed=17)
    rid = s["run_id"]
    s = client.post(f"/api/fortune/run/{rid}/action", json={"action": "scout"}).json()
    assert s["scouted"] and s["enemy"], "divination buys the composition"
    assert s["purse_cp"] == 950
    r = client.post(f"/api/fortune/run/{rid}/action", json={"action": "scout"})
    assert r.status_code == 422                # once per round
    client.post(f"/api/fortune/run/{rid}/action", json={"action": "buy", "slot": 0})
    d = client.get(f"/api/fortune/run/{rid}/deploy").json()
    assert d["enemy"] and d["scouted"]
    assert all(c["team"] == "A" for c in d["combatants"]), "deploy shows your side only"


def test_unknown_books_rejected():
    r = client.post("/api/fortune/new", json={"books": ["NOPE"], "seed": 1})
    assert r.status_code == 422


def test_shop_actions_roundtrip():
    s = start(seed=7)
    rid = s["run_id"]
    s = client.post(f"/api/fortune/run/{rid}/action",
                    json={"action": "buy", "slot": 0}).json()
    assert len(s["stable"]) == 1 and s["purse_cp"] < 1000
    member = s["stable"][0]
    assert member["ac"] and member["hp"] and member["art"]
    s = client.post(f"/api/fortune/run/{rid}/action",
                    json={"action": "freeze", "kind": "monster", "slot": 1}).json()
    kept = s["shop"]["monsters"][1]["name"]
    s = client.post(f"/api/fortune/run/{rid}/action",
                    json={"action": "reroll"}).json()
    assert s["shop"]["monsters"][1]["name"] == kept
    r = client.post(f"/api/fortune/run/{rid}/action",
                    json={"action": "sell", "target": 99})
    assert r.status_code == 422


def test_deploy_battle_and_wheel_flow():
    s = start(seed=11)
    rid = s["run_id"]
    for slot in range(3):
        r = client.post(f"/api/fortune/run/{rid}/action",
                        json={"action": "buy", "slot": slot})
        if r.status_code != 200:      # purse ran dry: two is plenty
            break
    d = client.get(f"/api/fortune/run/{rid}/deploy").json()
    assert d["zone"] and d["grid"]["w"] > 0 and d["combatants"]
    a_tokens = [c for c in d["combatants"] if c["team"] == "A"]
    assert a_tokens and all(c["token_art"] for c in a_tokens)
    cell = next(c for c in d["zone"])
    r = client.post(f"/api/fortune/run/{rid}/battle",
                    json={"placements": [list(cell)]})
    assert r.status_code == 200, r.text
    payload = r.json()
    b = payload["battle"]
    assert set(b) >= {"winner", "rounds", "log", "events", "grid", "combatants"}
    st = payload["state"]
    assert st["round"] == 2
    if payload["outcome"]["won"]:
        assert st["phase"] == "wheel" and payload["outcome"]["spin_owed"]
        sp = client.post(f"/api/fortune/run/{rid}/spin").json()
        assert sp["spin"]["tier"] in ("none", "common", "uncommon", "rare")
        assert sp["state"]["phase"] == "shop"
    else:
        assert st["lives"] == 2 and st["phase"] == "shop"


def test_illegal_placement_rejected():
    s = start(seed=13)
    rid = s["run_id"]
    client.post(f"/api/fortune/run/{rid}/action", json={"action": "buy", "slot": 0})
    r = client.post(f"/api/fortune/run/{rid}/battle",
                    json={"placements": [[19, 0]]})    # enemy half of the floor
    assert r.status_code == 422


def test_battle_seed_is_deterministic():
    logs = []
    for _ in range(2):
        s = start(seed=99)
        rid = s["run_id"]
        client.post(f"/api/fortune/run/{rid}/action", json={"action": "buy", "slot": 0})
        r = client.post(f"/api/fortune/run/{rid}/battle", json={"placements": []})
        logs.append(r.json()["battle"]["log"])
    assert logs[0] == logs[1]


def test_book_of_ages_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(wf, "DB_PATH", tmp_path / "runs.db")
    s = start(seed=55, handle="Shemeshka's Debtor")
    rid = s["run_id"]
    run = wf.RUNS[rid]
    wf._persist(rid, run)
    rows = client.get("/api/fortune/leaderboard").json()
    assert rows and rows[0]["handle"] == "Shemeshka's Debtor"
    assert rows[0]["seed"] == 55 and rows[0]["books"] == ["MM"]


def test_bench_action_and_inscription(tmp_path, monkeypatch):
    monkeypatch.setattr(wf, "DB_PATH", tmp_path / "runs.db")
    s = start(seed=23)
    rid = s["run_id"]
    client.post(f"/api/fortune/run/{rid}/action", json={"action": "buy", "slot": 0})
    s = client.post(f"/api/fortune/run/{rid}/action",
                    json={"action": "bench", "target": 0}).json()
    assert s["stable"][0]["standby"]
    s = client.post(f"/api/fortune/run/{rid}/action",
                    json={"action": "bench", "target": 0}).json()
    assert not s["stable"][0]["standby"]
    r = client.post(f"/api/fortune/run/{rid}/inscribe", json={"initials": "abc"})
    assert r.status_code == 422, "the Book only takes initials at the gate's close"
    run = wf.RUNS[rid]
    run.phase = "over"
    wf._persist(rid, run)
    r = client.post(f"/api/fortune/run/{rid}/inscribe", json={"initials": "abc!"})
    assert r.status_code == 200 and r.json()["initials"] == "ABC"
    rows = client.get("/api/fortune/leaderboard").json()
    assert rows[0]["initials"] == "ABC" and rows[0]["created"]


def test_missing_run_is_404():
    assert client.get("/api/fortune/run/deadbeef").status_code == 404


def test_page_serves():
    r = client.get("/supertemporal")
    assert r.status_code == 200 and "Supertemporal Arena" in r.text
    for other in ("/pit", "/bestiary", "/builder"):
        assert "/supertemporal" in client.get(other).text, f"nav link missing on {other}"
