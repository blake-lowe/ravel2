"""Slice 12a web layer: the Bestiary API serves every stat block, ratings attach
where they exist, art URLs resolve or degrade gracefully, and the pages load.
Skipped wholesale if FastAPI isn't installed (the engine suite must not require it)."""
import shutil
import subprocess
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient        # noqa: E402

from web.app import MONSTERS, RATINGS, app       # noqa: E402

client = TestClient(app)


def test_monster_list_covers_registry():
    rows = client.get("/api/monsters").json()
    assert len(rows) == len(MONSTERS) >= 450
    assert all(r["name"] and r["cr"] is not None for r in rows if r["name"] != "Spiritual Weapon")
    crs = [r["cr"] for r in rows if r["cr"] is not None]
    assert crs == sorted(crs), "list is sorted by CR"


def test_monster_sources():
    rows = {r["name"]: r["source"] for r in client.get("/api/monsters").json()}
    assert rows["Goblin"] == "MM"
    assert rows["Spiritual Weapon"] == "Ravel"      # house construct, not a book
    assert sum(1 for s in rows.values() if s == "MM") >= 450


def test_detail_exemplar():
    d = client.get("/api/monsters/Young Red Dragon").json()
    assert d["statblock"]["ac"] == 18 and d["statblock"]["cr"] == 10
    assert d["rating"] is None or "adjusted_cr" in d["rating"]
    assert d["images"] and all(u.endswith(".webp") for u in d["images"])


def test_every_monster_detail_serves():
    for name in MONSTERS:
        r = client.get(f"/api/monsters/{name}")
        assert r.status_code == 200, name
        assert r.json()["statblock"]["name"] == name


def test_unknown_monster_404():
    assert client.get("/api/monsters/Tarrasque of Nowhere").status_code == 404


def test_rating_payload_shape():
    if not RATINGS:
        pytest.skip("no ratings.db in this checkout")
    name = next(iter(RATINGS))
    r = client.get(f"/api/monsters/{name}").json()["rating"]
    assert isinstance(r["per_composition"], dict)
    assert "adjusted_cr" in r and "ci_lo" in r and "refined_cr" in r


def test_ratings_aggregate_endpoint():
    rows = client.get("/api/ratings").json()
    if not RATINGS:
        assert rows == []
        return
    assert len(rows) >= 400
    r = rows[0]
    assert {"name", "nominal_cr", "adjusted_cr", "best_cr", "residual"} <= set(r)


def test_art_candidate_chain():
    """Art is remote (5etools-img GitHub mirror); the server sends ordered
    candidates and the client walks them on load error. Pin the ordering:
    MM exact first, dragon-age variants next, then XMM (covers e.g. Poltergeist,
    absent from MM 2014), then tokens."""
    from web.app import IMG_BASE, _image_candidates
    urls = _image_candidates("Young Red Dragon")
    assert urls[0] == f"{IMG_BASE}/MM/Young%20Red%20Dragon.webp"
    assert urls[1] == f"{IMG_BASE}/MM/Red%20Dragon.webp"      # dragon-age fallback
    assert any("/XMM/" in u for u in urls) and any("/tokens/MM/" in u for u in urls)
    mm, xmm = urls.index(f"{IMG_BASE}/MM/Young%20Red%20Dragon.webp"), \
        next(i for i, u in enumerate(urls) if "/XMM/" in u)
    assert mm < xmm                                           # MM 2014 wins over XMM


def test_art_candidate_chain_mpmm():
    """A monster's own source book is probed first (MPMM art lives under
    bestiary/MPMM/), then the books MPMM reprints from (VGM, MTF), then the
    MM/XMM defaults — and the pit's round tokens follow the same order."""
    from web.app import IMG_BASE, _image_candidates
    from web.arena import _token_art
    urls = _image_candidates("Alhoon")
    assert urls[0] == f"{IMG_BASE}/MPMM/Alhoon.webp"
    assert urls[1] == f"{IMG_BASE}/VGM/Alhoon.webp"
    assert urls[2] == f"{IMG_BASE}/MTF/Alhoon.webp"
    assert any("/MM/" in u for u in urls)                     # defaults still there
    assert _token_art("Alhoon")[0] == f"{IMG_BASE}/tokens/MPMM/Alhoon.webp"


def test_art_candidates_fold_accents():
    """The mirror stores ASCII-folded filenames (Deep Rothé -> Deep Rothe.webp);
    the exact spelling is tried first, the folded form as a fallback."""
    from web.app import IMG_BASE, _image_candidates
    urls = _image_candidates("Deep Rothé")
    assert urls[0] == f"{IMG_BASE}/MPMM/Deep%20Roth%C3%A9.webp"
    assert urls[1] == f"{IMG_BASE}/MPMM/Deep%20Rothe.webp"


def test_js_renderer_smoke_every_block():
    """DoD 'every stat block renders without error' — exercised through the real
    JS renderer, not just the API (catches schema-mismatch bugs like range arrays)."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    smoke = Path(__file__).parent / "render_smoke.js"
    proc = subprocess.run([node, str(smoke)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_pages():
    assert client.get("/", follow_redirects=False).status_code in (302, 307)
    page = client.get("/bestiary")
    assert page.status_code == 200 and "Bestiary" in page.text
    assert "Character Builder" in client.get("/builder").text
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/bestiary.js").status_code == 200
