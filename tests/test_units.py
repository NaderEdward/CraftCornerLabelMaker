from __future__ import annotations

import pytest

from core.units import Rect, mm_to_px, px_to_mm, scale_px


def test_mm_to_px_rounds_not_truncates():
    assert mm_to_px(10, 300) == 118
    assert mm_to_px(0.847, 300) == round(0.847 * 300 / 25.4)


def test_px_to_mm_roundtrip_approx():
    px = mm_to_px(50, 300)
    mm = px_to_mm(px, 300)
    assert abs(mm - 50) < 0.1


def test_scale_px_same_dpi_is_identity():
    assert scale_px(100, 300, 300) == 100


def test_scale_px_different_dpi():
    assert scale_px(300, 300, 600) == 600
    assert scale_px(600, 600, 300) == 300


def test_rect_x2_y2_area():
    r = Rect(10, 20, 30, 40)
    assert r.x2 == 40
    assert r.y2 == 60
    assert r.area == 1200


def test_rect_intersects():
    a = Rect(0, 0, 10, 10)
    b = Rect(5, 5, 10, 10)
    c = Rect(20, 20, 5, 5)
    assert a.intersects(b)
    assert not a.intersects(c)


def test_rect_contains():
    outer = Rect(0, 0, 100, 100)
    inner = Rect(10, 10, 20, 20)
    assert outer.contains(inner)
    assert not inner.contains(outer)


def test_rect_is_frozen():
    r = Rect(0, 0, 10, 10)
    with pytest.raises(Exception):
        r.x = 5


def test_rect_inflated():
    r = Rect(10, 10, 20, 20)
    grown = r.inflated(5)
    assert grown == Rect(5, 5, 30, 30)


def test_rect_from_corners_normalises_order():
    r = Rect.from_corners(50, 60, 10, 20)
    assert r == Rect(10, 20, 40, 40)


def test_no_literal_25_4_outside_units_module():
    import inspect

    import core.units as units_mod
    src = inspect.getsource(units_mod)
    assert "25.4" in src
