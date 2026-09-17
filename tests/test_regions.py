from __future__ import annotations

from core.units import Rect
from regions.model import ProductRegion, RegionSet
from regions.validate import validate_region_set


def _region(id_="large_labels", x=0, y=0, w=100, h=100, sku=("SKU-A",)):
    return ProductRegion(id=id_, label="Large Labels", rect=Rect(x, y, w, h),
                         sku_match=list(sku))


def test_valid_region_set_has_no_problems():
    rs = RegionSet(
        template_name="tpl", template_canvas={"width": 1000, "height": 1000},
        template_fingerprint="sha256:x", regions=[_region()],
    )
    assert validate_region_set(rs) == []


def test_region_outside_canvas_is_flagged():
    rs = RegionSet(
        template_name="tpl", template_canvas={"width": 100, "height": 100},
        template_fingerprint="sha256:x",
        regions=[_region(x=50, y=50, w=100, h=100)],
    )
    problems = validate_region_set(rs)
    assert any("extends past canvas" in p for p in problems)


def test_duplicate_ids_flagged():
    rs = RegionSet(
        template_name="tpl", template_canvas={"width": 1000, "height": 1000},
        template_fingerprint="sha256:x",
        regions=[_region(id_="a"), _region(id_="a", x=200)],
    )
    problems = validate_region_set(rs)
    assert any("Duplicate region id" in p for p in problems)


def test_sku_collision_across_regions_is_flagged():
    rs = RegionSet(
        template_name="tpl", template_canvas={"width": 1000, "height": 1000},
        template_fingerprint="sha256:x",
        regions=[
            _region(id_="a", sku=("SHARED",)),
            _region(id_="b", x=200, sku=("SHARED",)),
        ],
    )
    problems = validate_region_set(rs)
    assert any("matches multiple regions" in p for p in problems)


def test_zero_size_region_flagged():
    rs = RegionSet(
        template_name="tpl", template_canvas={"width": 1000, "height": 1000},
        template_fingerprint="sha256:x",
        regions=[_region(w=0, h=0)],
    )
    problems = validate_region_set(rs)
    assert any("non-positive size" in p for p in problems)


def test_region_roundtrip_to_dict_from_dict():
    region = _region()
    d = region.to_dict()
    restored = ProductRegion.from_dict(d)
    assert restored == region


def test_region_accepts_two_corner_format():
    d = {"id": "a", "label": "A", "rect": {"x1": 10, "y1": 20, "x2": 110, "y2": 220},
        "sku_match": ["X"]}
    region = ProductRegion.from_dict(d)
    assert region.rect == Rect(10, 20, 100, 200)
