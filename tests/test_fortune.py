"""Supertemporal Arena run-state machine (SPEC 18.8) - golden, property, unit."""
import pytest

from ravel import content
from ravel.fortune import (
    COMMON_ITEMS, ITEM_CAP, ITEMS, LIVES_START, MIDDLE_RING, OUTER_RING,
    RARE_ITEMS, SET_SIZE, TRAIN_CAP, TRAIN_ITEM, UNCOMMON_ITEMS,
    CatalogEntry, FortuneError, FortuneRun, ShopSlot, StableMember, align_key,
    apply_kit, coins, cr_cap, enemy_size, is_boss_round, new_run, price_cp,
    type_key,
)
from ravel.sim import build_encounter, deployment_zone


def full_catalog(max_cr: float = 3.0) -> dict[str, CatalogEntry]:
    """Every registry monster up to max_cr, unrated, under one 'ALL' book."""
    out = {}
    for name in content.all_names():
        md = content.get(name)
        if md.cr <= max_cr:
            out[name] = CatalogEntry(name=name, cr=md.cr, source="ALL",
                                     mtype=md.mtype, alignment=md.alignment)
    return out


CATALOG = full_catalog()
BOOKS = ("ALL",)


def lowest_cr_name() -> str:
    return min(CATALOG.values(), key=lambda e: (e.cr, e.name)).name


# --- golden determinism -------------------------------------------------------

def scripted_run(seed: int) -> dict:
    run = new_run(seed, BOOKS, CATALOG)
    run.buy(0)
    run.buy(1)
    run.reroll()
    run.buy(0)
    run.fight()
    if run.phase == "wheel":
        run.spin()
    return run.to_dict()


def test_golden_same_seed_same_run():
    assert scripted_run(42) == scripted_run(42)


def test_golden_different_seed_diverges():
    assert scripted_run(42) != scripted_run(43)


def test_serialization_roundtrip():
    run = new_run(7, BOOKS, CATALOG)
    run.buy(0)
    run.toggle_freeze("monster", 1)
    d = run.to_dict()
    clone = FortuneRun.from_dict(d, run.catalog)
    assert clone.to_dict() == d
    run.reroll()
    clone.reroll()
    assert clone.to_dict() == run.to_dict()


# --- shop properties ------------------------------------------------------------

def test_shop_respects_cap_and_books():
    for seed in range(1, 21):
        run = new_run(seed, BOOKS, CATALOG)
        assert len(run.shop_monsters) == 5 and len(run.shop_items) == 2
        for slot in run.shop_monsters:
            e = run.catalog[slot.name]
            assert e.cr <= run.cap() == 1
            assert e.source in BOOKS
        for slot in run.shop_items:
            assert ITEMS[slot.name].rarity in ("common", "uncommon")


def test_prices_scale_with_pr_over_tier():
    par = CatalogEntry("X", 1.0, "ALL")
    assert price_cp(par, 1) == 300                 # 3 gp x CR 1 at tier 1
    assert price_cp(par, 3) == 100                 # the same creature, cheaper later
    goblin = CatalogEntry("X", 0.25, "ALL")
    assert price_cp(goblin, 1) == 75               # 7 sp 5 cp — change matters
    dud = CatalogEntry("X", 1.0, "ALL", best_cr=0.5)
    assert price_cp(dud, 1) == 150                 # playtested CR is the price tag
    hot = CatalogEntry("X", 1.0, "ALL", best_cr=2.5)
    assert price_cp(hot, 1) == 750                 # overtuned stock costs real coin
    zero = CatalogEntry("X", 0.0, "ALL")
    assert price_cp(zero, 4) == 5                  # even a commoner isn't free


def test_freeze_survives_reroll():
    run = new_run(3, BOOKS, CATALOG)
    kept = run.shop_monsters[2].name
    run.toggle_freeze("monster", 2)
    run.reroll()
    assert run.shop_monsters[2].name == kept and run.shop_monsters[2].frozen
    run.toggle_freeze("monster", 2)
    assert not run.shop_monsters[2].frozen


def test_reroll_costs_5_sp():
    run = new_run(4, BOOKS, CATALOG)
    before = run.purse_cp
    run.reroll()
    assert run.purse_cp == before - 50


def test_scout_costs_5_sp_once_and_resets_on_battle():
    run = new_run(14, BOOKS, CATALOG)
    assert not run.scouted
    run.scout()
    assert run.scouted and run.purse_cp == 950
    with pytest.raises(FortuneError):          # the pit hand already talked
        run.scout()
    d = run.to_dict()
    assert d["scouted"] and FortuneRun.from_dict(d, run.catalog).scouted
    run.buy(0)
    run.fight()
    assert not run.scouted                     # next round: a fresh secret


def test_cannot_overspend():
    run = new_run(5, BOOKS, CATALOG)
    run.purse_cp = 10
    with pytest.raises(FortuneError):
        run.buy(0)
    with pytest.raises(FortuneError):
        run.reroll()


# --- economy: buy / sell / train / items ------------------------------------------

def stocked_run(seed: int = 9) -> FortuneRun:
    """A run with a hand-stocked shop for exact-arithmetic tests."""
    name = lowest_cr_name()
    run = new_run(seed, BOOKS, CATALOG)
    run.shop_monsters = [ShopSlot(name, 300), ShopSlot(name, 300),
                         ShopSlot(name, 300), None, None]
    run.shop_items = [ShopSlot("Oil of Keen Edges", 400),
                      ShopSlot("Rust-Ward Talisman", 200)]
    return run


def test_buy_sell_refund_half_invested():
    run = stocked_run()
    run.buy(0)
    assert run.purse_cp == 700 and run.stable[0].invested_cp == 300
    refund = run.sell(0)
    assert refund == 150 and run.purse_cp == 850 and not run.stable


def test_buy_into_training_and_manual_train():
    run = stocked_run()
    run.buy(0)
    run.buy(1, train_into=0)                       # dupe dragged onto its twin
    assert run.stable[0].elite == 1 and run.stable[0].invested_cp == 600
    run.buy(2)                                     # second copy, then merge
    run.train(0, 1)
    assert len(run.stable) == 1 and run.stable[0].elite == 2
    assert run.stable[0].invested_cp == 900


def test_train_rejects_different_monsters():
    run = stocked_run()
    run.buy(0)
    other = next(n for n in CATALOG if n != run.stable[0].name)
    run.stable.append(StableMember(other, invested_cp=300))
    with pytest.raises(FortuneError):
        run.train(0, 1)


def test_items_attach_and_cap():
    run = stocked_run()
    run.buy(0)
    run.buy_item(0, 0)
    assert run.stable[0].items == ["Oil of Keen Edges"]
    assert run.purse_cp == 300                     # 1000 - 300 - 400
    run.stable[0].items = list(COMMON_ITEMS[:ITEM_CAP])
    with pytest.raises(FortuneError):
        run.buy_item(1, 0)
    run.bank.append("Planar Heartstone")
    run.stable[0].items.pop()
    run.attach_bank_item(0, 0)
    assert "Planar Heartstone" in run.stable[0].items and not run.bank


def test_stable_cap_is_5_fighting_plus_1_standby():
    run = stocked_run()
    name = lowest_cr_name()
    run.stable = [StableMember(name) for _ in range(5)]
    run.buy(0)                                     # the 6th goes to the standby stall
    assert len(run.stable) == 6 and run.stable[5].standby
    assert len(run.player_defs()) == 5             # ...and sits out the battle
    with pytest.raises(FortuneError):              # no 7th
        run.buy(1)
    with pytest.raises(FortuneError):              # can't field it onto a full field
        run.bench(5)


def test_bench_moves_and_trades():
    run = stocked_run()
    name = lowest_cr_name()
    run.stable = [StableMember(name, elite=k) for k in range(5)]
    run.bench(1)                                   # to the stall
    assert run.stable[1].standby and len(run.fielded()) == 4
    run.bench(3)                                   # trades places with the occupant
    assert not run.stable[1].standby and run.stable[3].standby
    run.bench(3)                                   # back to the field (room exists)
    assert not run.stable[3].standby
    d = run.to_dict()
    assert FortuneRun.from_dict(d, run.catalog).to_dict() == d
    with pytest.raises(FortuneError):
        run.bench(9)


# --- the shelf gilds with the tiers ---------------------------------------------------

def test_item_rarity_scales_with_tier():
    from ravel.dice import RNG
    from ravel.fortune import item_rarity

    def hist(tier):
        rng = RNG(99)
        out = {"common": 0, "uncommon": 0, "rare": 0}
        for _ in range(4000):
            out[item_rarity(tier, rng)] += 1
        return out

    t1, t5 = hist(1), hist(5)
    assert t1["rare"] == 0                       # no rares on the early shelf
    assert t5["rare"] > 0                        # ...but tier 5 stocks them
    assert t5["uncommon"] > t1["uncommon"]       # the shelf gilds as tiers climb
    assert t5["common"] < t1["common"]


# --- fusion: old stock made new --------------------------------------------------------

def test_fusion_by_kind_climbs_the_ladder():
    beasts = sorted(n for n in CATALOG if type_key(CATALOG[n]) == "beast"
                    and CATALOG[n].cr <= 0.5)
    a, b = beasts[0], beasts[1]
    run = new_run(8, BOOKS, CATALOG)
    run.round = 9                                # cap 5: the formula runs uncapped
    run.stable = [StableMember(a, items=["Rust-Ward Talisman"], invested_cp=100),
                  StableMember(b, elite=2, invested_cp=50)]
    name = run.fuse(0, 1)
    assert len(run.stable) == 1
    m = run.stable[0]
    assert m.name == name and m.elite == 0       # neither training...
    assert m.items == [] and m.invested_cp == 150   # ...nor items survive
    e = run.catalog[name]
    assert type_key(e) == "beast"                # kind is kept
    target = 1 + (CATALOG[a].cr + CATALOG[b].cr) / 2
    band = max(x.cr for x in CATALOG.values()
               if type_key(x) == "beast" and x.cr <= target)
    assert e.cr == band                          # the highest band under 1 + avg


def test_fusion_by_creed_keeps_the_creed_and_the_cap_binds():
    ce = sorted(n for n in CATALOG if align_key(CATALOG[n]) == "chaotic evil")
    x, y = next((x, y) for x in ce for y in ce
                if type_key(CATALOG[x]) != type_key(CATALOG[y]))
    run = new_run(12, BOOKS, CATALOG)            # round 1: the cap is CR 1
    run.stable = [StableMember(x), StableMember(y)]
    name = run.fuse(0, 1)
    assert align_key(run.catalog[name]) == "chaotic evil"
    assert run.catalog[name].cr <= run.cap()     # the stock tier binds the result


def test_fusion_requires_shared_kind_or_creed():
    ns = sorted(CATALOG)
    x, y = next((x, y) for x in ns for y in ns
                if type_key(CATALOG[x]) != type_key(CATALOG[y])
                and align_key(CATALOG[x]) != align_key(CATALOG[y]))
    run = new_run(13, BOOKS, CATALOG)
    run.stable = [StableMember(x), StableMember(y)]
    with pytest.raises(FortuneError):
        run.fuse(0, 1)
    with pytest.raises(FortuneError):
        run.fuse(0, 0)


# --- the training cap & overtier offerings -------------------------------------------

def test_training_caps_at_three_and_summons_overtier():
    run = stocked_run()
    name = lowest_cr_name()
    run.stable = [StableMember(name, elite=2), StableMember(name)]
    run.train(0, 1)                                # 2 + 0 + 1 = all three stars
    assert run.stable[0].elite == TRAIN_CAP
    bonus = [s for s in run.shop_monsters if s is not None and s.overtier]
    assert len(bonus) == 1, "a third star summons an overtier offering"
    e = run.catalog[bonus[0].name]
    assert run.cap() < e.cr <= run.cap() + 1       # the band above the tier
    run.stable.append(StableMember(name))
    with pytest.raises(FortuneError):              # no fourth star by merging
        run.train(0, 1)
    with pytest.raises(FortuneError):              # ...nor by feeding a shop copy
        run.buy(0, train_into=0)
    run.reroll()                                   # the earned offering rides out
    assert any(s and s.overtier for s in run.shop_monsters)
    idx = next(i for i, s in enumerate(run.shop_monsters) if s and s.overtier)
    run.purse_cp = 10 ** 6
    run.buy(idx)                                   # ...and buys like any stock
    assert not any(s and s.overtier for s in run.shop_monsters)
    assert run.stable[-1].name == bonus[0].name
    d = run.to_dict()                              # overtier flag round-trips
    assert FortuneRun.from_dict(d, run.catalog).to_dict() == d


def test_manual_of_gainful_exercise_trains():
    run = stocked_run()
    run.buy(0)
    run.shop_items = [ShopSlot(TRAIN_ITEM, 500), None]
    run.buy_item(0, 0)
    m = run.stable[0]
    assert m.elite == 1 and m.items == []          # trained, not carried
    assert run.purse_cp == 1000 - 300 - 500
    assert m.invested_cp == 800                    # sell-back counts the manual
    m.elite = TRAIN_CAP
    run.shop_items = [ShopSlot(TRAIN_ITEM, 500), None]
    with pytest.raises(FortuneError):              # no fourth star from a book
        run.buy_item(0, 0)
    run.bank.append(TRAIN_ITEM)                    # nor from a wheel-won manual
    with pytest.raises(FortuneError):
        run.attach_bank_item(0, 0)
    m.elite = 1
    run.attach_bank_item(0, 0)                     # the wheel's manual trains free
    assert m.elite == 2 and not run.bank


def test_type_set_of_four_summons_matching_overtier():
    run = new_run(31, BOOKS, CATALOG)
    beasts = sorted(n for n in CATALOG if type_key(CATALOG[n]) == "beast")[:SET_SIZE]
    assert len(beasts) == SET_SIZE
    run.purse_cp = 10 ** 6
    run.shop_monsters = [ShopSlot(n, 10) for n in beasts] + [None]
    for k in range(SET_SIZE):
        run.buy(k)
    bonus = [s for s in run.shop_monsters if s is not None and s.overtier]
    assert len(bonus) == 1, "four of a kind completes the set"
    assert type_key(run.catalog[bonus[0].name]) == "beast"   # the set's own kind
    assert run.catalog[bonus[0].name].cr > run.cap()
    assert run.sets_awarded == {"beast"}
    run.shop_monsters[0] = ShopSlot(beasts[0], 10)
    run.buy(0)                                     # a fifth beast pays nothing more
    assert sum(1 for s in run.shop_monsters if s is not None and s.overtier) == 1
    d = run.to_dict()                              # sets_awarded round-trips
    assert FortuneRun.from_dict(d, run.catalog).to_dict() == d


# --- kit application ---------------------------------------------------------------

def test_apply_kit_deltas():
    md = content.get(lowest_cr_name())
    kitted = apply_kit(md, elite=2, items=("Oil of Keen Edges", "Rust-Ward Talisman",
                                           "Flask of Elemental Vigor"))
    assert kitted.ac == md.ac + 2 + 1              # 2 training + talisman
    assert kitted.hp == md.hp + 5                  # the flask; training pays in damage
    assert kitted.name == md.name + " ★★"
    for name, atk in md.attacks.items():
        assert kitted.attacks[name].attack_bonus == atk.attack_bonus + 1
        if atk.damage:                             # 2 training + the oil
            assert kitted.attacks[name].damage[0].bonus == atk.damage[0].bonus + 3
    assert md.ac == content.get(lowest_cr_name()).ac    # base untouched


def test_apply_kit_wards_and_slayers():
    md = content.get(lowest_cr_name())
    kitted = apply_kit(md, items=("Ring of Warmth", "Periapt of Proof against Poison",
                                  "Dragon Slayer"))
    assert "cold" in kitted.resistances and "cold" not in md.resistances
    assert "poison" in kitted.immunities
    assert kitted.adv_against_types == frozenset({"dragon"})
    assert kitted.ac == md.ac and kitted.hp == md.hp
    for name, atk in md.attacks.items():           # Dragon Slayer is a +1 weapon
        if atk.damage:
            assert kitted.attacks[name].damage[0].bonus == atk.damage[0].bonus + 1


def test_kit_advantage_matches_types_and_alignments():
    from dataclasses import replace

    from ravel.rules import kit_advantage
    md = content.get(lowest_cr_name())
    slayer = apply_kit(md, items=("Dragon Slayer",))
    talisman = apply_kit(md, items=("Talisman of Pure Good",))
    dragon = replace(md, mtype="dragon")
    giant = replace(md, mtype="giant")
    assert kit_advantage(slayer, dragon) and not kit_advantage(slayer, giant)
    assert kit_advantage(talisman, replace(md, alignment="C E"))      # 5e.tools codes
    assert kit_advantage(talisman, replace(md, alignment="chaotic evil"))  # prose
    assert not kit_advantage(talisman, replace(md, alignment="L G"))
    assert not kit_advantage(talisman, replace(md, alignment="U"))
    assert not kit_advantage(md, dragon)           # bare claws favor no one


def test_apply_kit_noop_returns_same_def():
    md = content.get(lowest_cr_name())
    assert apply_kit(md) is md


# --- ladder & enemy generation --------------------------------------------------------

def test_cr_cap_ladder():
    assert [cr_cap(r) for r in range(1, 8)] == [1, 1, 2, 2, 3, 3, 4]


def test_enemy_size_ramp():
    assert [enemy_size(r) for r in range(1, 8)] == [3, 3, 4, 4, 5, 5, 5]


def test_enemy_generation_properties():
    for seed in (1, 5, 11, 23):
        run = new_run(seed, BOOKS, CATALOG)
        for r in (1, 2, 4, 5):                             # non-boss rounds
            team = run.enemy_team(r)
            assert team == run.enemy_team(r)               # pure in (seed, round)
            assert 1 <= len(team) <= enemy_size(r)
            for name in team:
                assert run.catalog[name].cr <= cr_cap(r)


def test_enemy_squads_share_a_type_or_an_alignment():
    typed = aligned_only = 0
    for seed in (1, 5, 11, 23, 42, 57):
        run = new_run(seed, BOOKS, CATALOG)
        for r in (1, 2, 4, 5, 6):                          # non-boss rounds
            team = run.enemy_team(r)
            kinds = {type_key(CATALOG[n]) for n in team}
            aligns = {align_key(CATALOG[n]) for n in team}
            assert len(kinds) == 1 or len(aligns) == 1, \
                (seed, r, team)                            # a cohort, not a menagerie
            typed += len(kinds) == 1
            aligned_only += len(kinds) > 1                 # bound ONLY by alignment
    assert typed and aligned_only, "both cohesion modes take the field"


def test_align_key_normalizes_codes_and_prose():
    def e(a):
        return CatalogEntry("X", 1.0, "ALL", alignment=a)
    assert align_key(e("C E")) == "chaotic evil" == align_key(e("chaotic evil"))
    assert align_key(e("U")) == "unaligned" == align_key(e(""))
    assert align_key(e("L G")) == "lawful good"


def test_boss_rounds_field_a_single_xp_matched_monster():
    assert [r for r in range(1, 13) if is_boss_round(r)] == [3, 7, 11]
    assert not is_boss_round(1) and not is_boss_round(5)
    big = full_catalog(10.0)
    for seed in (2, 9, 31):
        run = FortuneRun(seed=seed, books=BOOKS, catalog=big)
        for r in (3, 7):
            team = run.enemy_team(r)
            assert len(team) == 1                       # one huge monster
            assert team == run.enemy_team(r)            # still deterministic
            assert big[team[0]].cr > cr_cap(r), "the cap does not bind the boss"
    # a shallow catalog falls back to the nearest thing it has to the budget
    run = FortuneRun(seed=4, books=BOOKS, catalog=CATALOG)   # tops out at CR 3
    boss = run.enemy_team(7)
    assert len(boss) == 1 and CATALOG[boss[0]].cr == 3.0


def test_foresight_is_stable_and_previewable():
    run = new_run(6, BOOKS, CATALOG)
    q = run.foresight(3)
    assert [f["round"] for f in q] == [1, 2, 3]
    run.reroll()                                           # draws advance...
    assert run.foresight(3) == q                           # ...foresight doesn't


# --- the wheel ---------------------------------------------------------------------

def test_wheel_odds_over_many_spins():
    run = new_run(8, BOOKS, CATALOG)
    tally = {"none": 0, "common": 0, "uncommon": 0, "rare": 0}
    n = 4000
    for _ in range(n):
        run.phase = "wheel"
        res = run.spin()
        tally[res["tier"]] += 1
        assert 1 <= res["outer"] <= 10
        if res["tier"] == "rare":
            assert OUTER_RING[res["outer"] - 1] == "advance"
            assert MIDDLE_RING[res["middle"] - 1] == "advance"
            assert res["center"] is not None
    # expected: none .32, common .50, uncommon .14, rare .04
    assert 0.27 <= tally["none"] / n <= 0.37
    assert 0.45 <= tally["common"] / n <= 0.55
    assert 0.10 <= tally["uncommon"] / n <= 0.18
    assert 0.025 <= tally["rare"] / n <= 0.055


def test_wheel_prizes_land():
    run = new_run(10, BOOKS, CATALOG)
    for _ in range(400):
        bank, lives = len(run.bank), run.lives
        run.phase = "wheel"
        res = run.spin()
        kind = res["prize"]["kind"]
        if kind == "gold":       # the purse resets to 10 gp, the prize lands on top
            assert run.purse_cp == 1000 + res["prize"]["cp"]
        elif kind == "item":
            assert run.purse_cp == 1000                    # reset, nothing on top
            assert len(run.bank) == bank + 1
            assert run.bank[-1] == res["prize"]["item"]
        elif kind == "life":
            assert run.lives == lives + 1 <= LIVES_START
    seen = {ITEMS[i].rarity for i in run.bank}
    assert "common" in seen                        # the common pool actually pays items


def test_spin_requires_wheel_phase():
    run = new_run(12, BOOKS, CATALOG)
    with pytest.raises(FortuneError):
        run.spin()


# --- battles & the run arc ------------------------------------------------------------

def test_fight_bookkeeping_to_run_end():
    run = new_run(21, BOOKS, CATALOG)
    run.buy(0)
    fights = 0
    while run.phase != "over" and fights < 12:
        if run.phase == "wheel":
            run.spin()
            continue
        wins, lives, rnd = run.wins, run.lives, run.round
        run.fight()
        fights += 1
        assert run.round == rnd + 1
        if run.phase == "wheel":
            assert run.wins == wins + 1 and run.lives == lives
        else:
            assert run.lives == lives - 1 and run.wins == wins
    assert run.history and all("won" in h for h in run.history)
    if run.phase == "over":
        assert run.lives == 0 and len([h for h in run.history if not h["won"]]) == 3


def test_purse_resets_to_10_gp_each_night():
    # a lone mook against ogres: a guaranteed beating — and then a fresh stake
    strong = {n: e for n, e in full_catalog(4.0).items() if e.cr >= 2}
    run = FortuneRun(seed=77, books=BOOKS, catalog=strong)
    run.stable = [StableMember(lowest_cr_name())]
    run.purse_cp = 40                        # nearly broke going in
    run.fight()
    assert run.phase == "shop" and run.purse_cp == 1000   # made whole — no more, no less


def test_fight_requires_a_stable():
    run = new_run(30, BOOKS, CATALOG)
    with pytest.raises(FortuneError):
        run.fight()


def test_losses_end_the_run_at_three():
    # a lone mook against ogres: guaranteed beatings, deterministic per seed
    strong = {n: e for n, e in full_catalog(4.0).items() if e.cr >= 2}
    run = FortuneRun(seed=77, books=BOOKS, catalog=strong)
    run.stable = [StableMember(lowest_cr_name())]
    losses = 0
    while run.phase != "over":
        assert losses < 3
        if run.phase == "wheel":
            run.spin()
            continue
        before = run.lives
        run.fight()
        if run.lives < before:
            losses += 1
    assert run.lives == 0 and losses == 3


# --- deployment (engine seam) ----------------------------------------------------------

def test_placements_honored_on_open_floor():
    name = lowest_cr_name()
    enc = build_encounter([name, name], [name], seed=1, placements_a=[(2, 3), None])
    assert enc.combatants["A1"].pos == (2, 3)


def test_placements_rejected_outside_zone_and_overlapping():
    name = lowest_cr_name()
    with pytest.raises(ValueError):
        build_encounter([name], [name], seed=1, placements_a=[(15, 3)])
    with pytest.raises(ValueError):
        build_encounter([name, name], [name], seed=1,
                        placements_a=[(2, 3), (2, 3)])


def test_placements_on_named_map_respect_spawn_zone():
    name = lowest_cr_name()
    zone = deployment_zone("A", map_name="ruins")
    assert zone
    cell = sorted(zone)[0]
    enc = build_encounter([name], [name], seed=1, map_name="ruins",
                          placements_a=[cell])
    assert enc.combatants["A1"].pos == cell
    outside = next((x, y) for x in range(40) for y in range(40)
                   if (x, y) not in zone)
    with pytest.raises(ValueError):
        build_encounter([name], [name], seed=1, map_name="ruins",
                        placements_a=[outside])


def test_monsterdef_team_entries_fight():
    md = apply_kit(content.get(lowest_cr_name()), elite=1)
    enc = build_encounter([md], [lowest_cr_name()], seed=2)
    assert enc.combatants["A1"].md.ac == content.get(lowest_cr_name()).ac + 1


# --- currency ---------------------------------------------------------------------------

def test_coins_change():
    assert coins(460) == "4 gp 6 sp"
    assert coins(305) == "3 gp 5 cp"
    assert coins(7) == "7 cp"
    assert coins(0) == "0 cp"
    assert coins(1000) == "10 gp"
