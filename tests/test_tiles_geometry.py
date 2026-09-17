from __future__ import annotations

from plotter.tiles import _fits_on_sheet

USABLE_W, USABLE_H = 400.0, 280.0


def test_normal_tile_fits():
    assert _fits_on_sheet(200, 100, USABLE_W, USABLE_H, allow_rotate=False)


def test_exact_fit_is_allowed():
    assert _fits_on_sheet(USABLE_W, USABLE_H, USABLE_W, USABLE_H, allow_rotate=False)


def test_long_thin_tile_that_fits_no_orientation_is_rejected():
    assert not _fits_on_sheet(500, 10, USABLE_W, USABLE_H, allow_rotate=False)


def test_tall_thin_tile_rejected_without_rotation():
    assert not _fits_on_sheet(10, 500, USABLE_W, USABLE_H, allow_rotate=False)


def test_tall_thin_tile_accepted_with_rotation():
    assert not _fits_on_sheet(10, 300, USABLE_W, USABLE_H, allow_rotate=False)
    assert _fits_on_sheet(10, 300, USABLE_W, USABLE_H, allow_rotate=True)


def test_too_big_in_both_dimensions_rejected_even_with_rotation():
    assert not _fits_on_sheet(900, 900, USABLE_W, USABLE_H, allow_rotate=True)
