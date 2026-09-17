from __future__ import annotations

from plotter.pack import PAPER_IRON_ON, pack

MARGIN = {"t": 5, "b": 5, "l": 5, "r": 5}


def _tile(tid, order_id, w=200, h=200, gap=10, rotate=False, paper_type=None):
    t = {
        "tile_id": tid, "file": f"tiles/{tid}.png", "w_px": w, "h_px": h,
        "w_mm": 0, "h_mm": 0, "gap_px": gap, "allow_rotate": rotate,
        "order_id": order_id, "order_number": f"#{order_id}",
        "customer_name": "Cust", "student_name": "Student",
        "region_id": "r1", "region_label": "Region 1",
        "template_name": "tpl", "unit_index": 1, "unit_total": 1,
    }
    if paper_type is not None:
        t["paper_type"] = paper_type
    return t


def _manifest(tiles):
    return {"dpi": 300, "tile_count": len(tiles), "tiles": tiles}


def test_ironon_12_tile_order_splits_9_and_3_across_two_sheets():
    from core.units import mm_to_px

    sheet_w_mm, sheet_h_mm, dpi = 215.9, 279.4, 300
    usable_w = mm_to_px(sheet_w_mm, dpi)
    usable_h = mm_to_px(sheet_h_mm, dpi)

    tile_w = usable_w // 3
    tile_h = usable_h // 3

    tiles = [
        _tile(f"i{i:04d}", "bigorder", w=tile_w, h=tile_h, gap=0,
              paper_type=PAPER_IRON_ON)
        for i in range(12)
    ]
    manifest = _manifest(tiles)

    plan = pack(
        manifest, 420, 297, MARGIN, dpi, fill_threshold=0.0,
        ironon_sheet_width_mm=sheet_w_mm, ironon_sheet_height_mm=sheet_h_mm,
        ironon_sheet_dpi=dpi,
    )

    placed = [p["tile_id"] for s in plan["sheets"] for p in s["placements"]]
    assert len(placed) == 12, "all 12 iron-on tiles should be placed"
    assert len(set(placed)) == 12, "no tile placed twice"
    assert plan["unplaced"] == []
    assert plan["oversize_orders"] == []
    assert "#bigorder" not in plan["held_back_orders"]

    per_sheet_counts = sorted(
        (len(s["placements"]) for s in plan["sheets"]), reverse=True
    )
    assert per_sheet_counts == [9, 3], (
        f"expected a 9/3 split across two iron-on sheets, got {per_sheet_counts}"
    )


def test_regular_order_too_big_for_one_sheet_now_splits_across_sheets():
    huge_order = [
        _tile(f"r{i:04d}", "regbig", w=3000, h=3000, gap=0)
        for i in range(3)
    ]
    other = [_tile(f"o{i:04d}", f"other{i}", w=150, h=150, gap=5) for i in range(4)]
    manifest = _manifest(huge_order + other)

    plan = pack(manifest, 420, 297, MARGIN, 300, fill_threshold=0.0)

    placed_ids = {p["tile_id"] for s in plan["sheets"] for p in s["placements"]}
    huge_ids = {t["tile_id"] for t in huge_order}

    assert huge_ids <= placed_ids, "every tile of 'regbig' should be placed"
    assert "#regbig" not in plan["oversize_orders"]
    assert "#regbig" not in plan["held_back_orders"]

    sheets_used = {
        s["local_index"]
        for s in plan["sheets"]
        for p in s["placements"]
        if p["tile_id"] in huge_ids
    }
    assert len(sheets_used) > 1, (
        "expected the 'regbig' order to straddle more than one sheet now "
        "that order-atomicity has been removed"
    )
