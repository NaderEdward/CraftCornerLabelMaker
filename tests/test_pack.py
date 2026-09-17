from __future__ import annotations

import json

from plotter.pack import exportable_sheets, pack


def _manifest(tiles):
    return {"dpi": 300, "tile_count": len(tiles), "tiles": tiles}


def _tile(tid, order_id, w=200, h=200, gap=10, rotate=False):
    return {
        "tile_id": tid, "file": f"tiles/{tid}.png", "w_px": w, "h_px": h,
        "w_mm": 0, "h_mm": 0, "gap_px": gap, "allow_rotate": rotate,
        "order_id": order_id, "order_number": f"#{order_id}",
        "customer_name": "Cust", "student_name": "Student",
        "region_id": "r1", "region_label": "Region 1",
        "template_name": "tpl", "unit_index": 1, "unit_total": 1,
    }


MARGIN = {"t": 5, "b": 5, "l": 5, "r": 5}


def test_no_overlapping_placements():
    tiles = [_tile(f"t{i:04d}", f"ord{i}") for i in range(6)]
    manifest = _manifest(tiles)
    plan = pack(manifest, 420, 297, MARGIN, 300, fill_threshold=0.0)

    for sheet in plan["sheets"]:
        placed = sheet["placements"]
        for i, a in enumerate(placed):
            for b in placed[i + 1:]:
                a_rect = (a["x_px"], a["y_px"], a["x_px"] + 200, a["y_px"] + 200)
                b_rect = (b["x_px"], b["y_px"], b["x_px"] + 200, b["y_px"] + 200)
                overlap = not (a_rect[2] <= b_rect[0] or b_rect[2] <= a_rect[0]
                              or a_rect[3] <= b_rect[1] or b_rect[3] <= a_rect[1])
                assert not overlap, f"Overlap between {a['tile_id']} and {b['tile_id']}"


def test_every_tile_placed_exactly_once_or_unplaced():
    tiles = [_tile(f"t{i:04d}", f"ord{i}") for i in range(5)]
    manifest = _manifest(tiles)
    plan = pack(manifest, 420, 297, MARGIN, 300, fill_threshold=0.0)

    placed_ids = [p["tile_id"] for s in plan["sheets"] for p in s["placements"]]
    all_ids = {t["tile_id"] for t in tiles}
    accounted = set(placed_ids) | set(plan["unplaced"])
    assert accounted == all_ids
    assert len(placed_ids) == len(set(placed_ids)), "A tile was placed more than once"


def test_space_optimizer_inherits_null_axis_gaps():
    tile = _tile("t0001", "ord0", gap=10)
    tile["gap_x_px"] = None
    tile["gap_y_px"] = None

    plan = pack(
        _manifest([tile]), 420, 297, MARGIN, 300,
        fill_threshold=0.0, strategy="space_optimizer",
    )

    assert [p["tile_id"] for s in plan["sheets"] for p in s["placements"]] == ["t0001"]


def test_individually_oversize_tile_still_flagged_oversize():
    from core.units import mm_to_px

    usable_w = mm_to_px(420 - MARGIN["l"] - MARGIN["r"], 300)
    usable_h = mm_to_px(297 - MARGIN["t"] - MARGIN["b"], 300)

    huge = [_tile("h0001", "big", w=usable_w + 500, h=usable_h + 500, gap=0)]
    small_orders = [
        [_tile(f"s{i:04d}", f"small{i}", w=100, h=100, gap=5)]
        for i in range(10)
    ]
    tiles = huge + [t for grp in small_orders for t in grp]
    manifest = _manifest(tiles)
    plan = pack(manifest, 420, 297, MARGIN, 300, fill_threshold=0.0)

    all_placed = {p["tile_id"] for s in plan["sheets"] for p in s["placements"]}
    assert "h0001" not in all_placed
    assert "#big" in plan["oversize_orders"]
    for grp in small_orders:
        for t in grp:
            assert t["tile_id"] in all_placed


def test_order_splits_across_sheets_when_it_does_not_fit_one():
    from core.units import mm_to_px

    usable_w = mm_to_px(420 - MARGIN["l"] - MARGIN["r"], 300)
    usable_h = mm_to_px(297 - MARGIN["t"] - MARGIN["b"], 300)

    tile_w = usable_w // 3
    tile_h = usable_h // 3

    order_tiles = [
        _tile(f"m{i:04d}", "multi", w=tile_w, h=tile_h, gap=0) for i in range(12)
    ]
    manifest = _manifest(order_tiles)
    plan = pack(manifest, 420, 297, MARGIN, 300, fill_threshold=0.0)

    placed_ids = [p["tile_id"] for s in plan["sheets"] for p in s["placements"]]
    multi_ids = {t["tile_id"] for t in order_tiles}
    assert set(placed_ids) == multi_ids, "every tile of the order must be placed"
    assert len(placed_ids) == len(set(placed_ids)), "no tile placed twice"
    assert plan["unplaced"] == []
    assert plan["oversize_orders"] == []
    assert "#multi" not in plan["held_back_orders"]
    assert len(plan["sheets"]) >= 2, "the order should have required more than one sheet"


def test_determinism_same_input_same_output():
    tiles = [_tile(f"t{i:04d}", f"ord{i}", w=100 + (i % 3) * 20, h=100) for i in range(8)]
    manifest = _manifest(tiles)
    plan_a = pack(manifest, 420, 297, MARGIN, 300, fill_threshold=0.0)
    plan_b = pack(manifest, 420, 297, MARGIN, 300, fill_threshold=0.0)
    assert json.dumps(plan_a, sort_keys=True) == json.dumps(plan_b, sort_keys=True)


def test_exportable_sheets_respects_threshold():
    tiles = [_tile(f"t{i:04d}", f"ord{i}") for i in range(3)]
    manifest = _manifest(tiles)
    plan = pack(manifest, 420, 297, MARGIN, 300, fill_threshold=0.99)
    assert exportable_sheets(plan, force=False) == []
    assert len(exportable_sheets(plan, force=True)) >= 1


def _big_manifest(n_orders=60, tiles_per_order=3):
    tiles = []
    n = 0
    for o in range(n_orders):
        for k in range(tiles_per_order):
            n += 1
            tiles.append(_tile(f"t{n:04d}", f"ord{o:03d}",
                               w=900 + (o % 5) * 100, h=700 + (k % 3) * 120,
                               gap=12))
    return _manifest(tiles)


def test_multi_sheet_pack_terminates_and_places_everything():
    manifest = _big_manifest()
    plan = pack(manifest, 420, 297, MARGIN, 300, fill_threshold=0.90)

    placed = [p["tile_id"] for s in plan["sheets"] for p in s["placements"]]
    assert len(placed) == len(set(placed)), "a tile was placed twice"
    assert len(placed) == manifest["tile_count"], "not every tile was placed"
    assert plan["unplaced"] == []
    assert plan["oversize_orders"] == []
    assert len(plan["sheets"]) > 1, "this fixture should need several sheets"


def test_multi_sheet_pack_allows_orders_to_straddle_sheets():
    manifest = _big_manifest()
    plan = pack(manifest, 420, 297, MARGIN, 300, fill_threshold=0.90)

    placed = [p["tile_id"] for s in plan["sheets"] for p in s["placements"]]
    assert len(placed) == len(set(placed)), "a tile was placed twice"
    assert len(placed) == manifest["tile_count"], "not every tile was placed"
    assert plan["unplaced"] == []
    assert plan["oversize_orders"] == []

    sheet_of_order = {}
    for sheet in plan["sheets"]:
        tile_ids = {p["tile_id"] for p in sheet["placements"]}
        for t in manifest["tiles"]:
            if t["tile_id"] in tile_ids:
                sheet_of_order.setdefault(t["order_id"], set()).add(sheet["local_index"])

    straddling = {o: s for o, s in sheet_of_order.items() if len(s) > 1}
    assert straddling, (
        "expected at least one order to straddle sheet boundaries with this "
        "fixture now that order-atomicity has been removed"
    )


def test_realistic_utilisation_is_recorded_for_threshold_calibration():
    manifest = _big_manifest()
    plan = pack(manifest, 420, 297, MARGIN, 300, fill_threshold=0.90)
    utils = [s["utilisation"] for s in plan["sheets"]]
    assert all(0.0 <= u <= 1.0 for u in utils)
    assert max(utils) < 1.0, "utilisation above 1.0 means gaps leaked into the numerator"


def test_placements_are_in_absolute_sheet_coordinates():
    from core.units import mm_to_px

    manifest = _manifest([_tile("t0001", "ord0", w=300, h=300, gap=0)])
    plan = pack(manifest, 420, 297, MARGIN, 300, fill_threshold=0.0)

    placement = plan["sheets"][0]["placements"][0]
    expected = mm_to_px(MARGIN["l"], 300)
    assert placement["x_px"] >= expected
    assert placement["y_px"] >= mm_to_px(MARGIN["t"], 300)


def test_all_tiles_lie_within_the_margins():
    from core.units import mm_to_px

    manifest = _big_manifest(n_orders=20)
    plan = pack(manifest, 420, 297, MARGIN, 300, fill_threshold=0.0)

    size_of = {t["tile_id"]: (t["w_px"], t["h_px"]) for t in manifest["tiles"]}
    left = mm_to_px(MARGIN["l"], 300)
    top = mm_to_px(MARGIN["t"], 300)
    right = mm_to_px(420 - MARGIN["r"], 300)
    bottom = mm_to_px(297 - MARGIN["b"], 300)

    for sheet in plan["sheets"]:
        for p in sheet["placements"]:
            w, h = size_of[p["tile_id"]]
            if p["rotated"]:
                w, h = h, w
            assert p["x_px"] >= left, "tile crosses the left margin"
            assert p["y_px"] >= top, "tile crosses the top margin"
            assert p["x_px"] + w <= right, "tile crosses the right margin"
            assert p["y_px"] + h <= bottom, "tile crosses the bottom margin"


STRATEGIES = ["maxrects", "shelf", "grid"]


def _mixed_region_manifest():
    tiles = []
    n = 0
    for region, (w, h) in {"large": (900, 400), "meeting": (400, 500),
                           "shoe": (300, 300)}.items():
        for i in range(6):
            n += 1
            t = _tile(f"t{n:04d}", f"ord{n:03d}", w=w, h=h, gap=10)
            t["region_id"] = region
            t["region_label"] = region
            tiles.append(t)
    return _manifest(tiles)


def _assert_no_overlaps(plan, manifest):
    size_of = {t["tile_id"]: (t["w_px"], t["h_px"]) for t in manifest["tiles"]}
    for sheet in plan["sheets"]:
        boxes = []
        for p in sheet["placements"]:
            w, h = size_of[p["tile_id"]]
            if p["rotated"]:
                w, h = h, w
            boxes.append((p["x_px"], p["y_px"], p["x_px"] + w, p["y_px"] + h,
                          p["tile_id"]))
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                overlap = not (a[2] <= b[0] or b[2] <= a[0]
                               or a[3] <= b[1] or b[3] <= a[1])
                assert not overlap, f"{a[4]} overlaps {b[4]}"


def test_every_strategy_produces_a_valid_plan():
    manifest = _mixed_region_manifest()
    for strategy in STRATEGIES:
        plan = pack(manifest, 420, 297, MARGIN, 300, fill_threshold=0.0,
                    strategy=strategy)
        placed = [p["tile_id"] for s in plan["sheets"] for p in s["placements"]]
        assert len(placed) == len(set(placed)), f"{strategy}: tile placed twice"
        assert len(placed) == manifest["tile_count"], f"{strategy}: tiles lost"
        _assert_no_overlaps(plan, manifest)


def test_every_strategy_is_deterministic():
    manifest = _mixed_region_manifest()
    for strategy in STRATEGIES:
        a = pack(manifest, 420, 297, MARGIN, 300, 0.0, strategy=strategy)
        b = pack(manifest, 420, 297, MARGIN, 300, 0.0, strategy=strategy)
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_unknown_strategy_raises_rather_than_silently_using_maxrects():
    import pytest

    manifest = _mixed_region_manifest()
    with pytest.raises(ValueError, match="Unknown pack strategy"):
        pack(manifest, 420, 297, MARGIN, 300, 0.0, strategy="definitely-not-real")


def test_grid_groups_like_products_together():
    manifest = _mixed_region_manifest()
    plan = pack(manifest, 420, 297, MARGIN, 300, 0.0, strategy="grid")
    region_of = {t["tile_id"]: t["region_id"] for t in manifest["tiles"]}

    for sheet in plan["sheets"]:
        rows = {}
        for p in sheet["placements"]:
            rows.setdefault(p["y_px"], set()).add(region_of[p["tile_id"]])
        for y, regions in rows.items():
            assert len(regions) == 1, f"row y={y} mixes regions {regions}"


def test_maxrects_beats_grid_on_utilisation():
    manifest = _mixed_region_manifest()
    best = {}
    for strategy in STRATEGIES:
        plan = pack(manifest, 420, 297, MARGIN, 300, 0.0, strategy=strategy)
        best[strategy] = max(s["utilisation"] for s in plan["sheets"])
    assert best["maxrects"] >= best["grid"]
