from __future__ import annotations

import pytest

from core.units import mm_to_px, px_to_mm
from plotter.pack import PAPER_IRON_ON, PackTile, exportable_sheets, pack
from plotter.tiles import IRONON_EDGE_INSET_MM, _ironon_geometry

LETTER_W_MM = 215.9
LETTER_H_MM = 279.4
DPI = 300


def _ion():
    return _ironon_geometry(LETTER_W_MM, LETTER_H_MM, IRONON_EDGE_INSET_MM, DPI)


def _tile(tile_id, order_id, ion, h_px, gap_y_px):
    return {
        "tile_id": tile_id, "file": "tiles/x.png",
        "w_px": ion.tile_w_px, "h_px": h_px,
        "w_mm": px_to_mm(ion.tile_w_px, DPI), "h_mm": px_to_mm(h_px, DPI),
        "gap_px": gap_y_px,
        "gap_x_px": ion.inset_px, "gap_y_px": gap_y_px,
        "allow_rotate": False, "paper_type": PAPER_IRON_ON,
        "order_id": order_id, "order_number": f"#{order_id}",
        "customer_name": "c", "student_name": "s",
        "region_id": "iron_on_labels", "region_label": "Iron-On Labels",
        "template_name": "iron ons", "unit_index": 1, "unit_total": 1,
    }


def _pack(tiles):
    return pack(
        {"dpi": DPI, "tile_count": len(tiles), "tiles": tiles},
        sheet_width_mm=500.0, sheet_height_mm=600.0,
        margin_mm={"t": 5.0, "b": 5.0, "l": 5.0, "r": 5.0},
        dpi=DPI, fill_threshold=0.90,
        ironon_sheet_width_mm=LETTER_W_MM,
        ironon_sheet_height_mm=LETTER_H_MM,
        ironon_sheet_dpi=DPI, ironon_fill_threshold=0.03,
    )


class TestIronOnGeometry:
    def test_tile_plus_inset_is_exactly_the_sheet_width(self):
        ion = _ion()
        assert ion.tile_w_px + 2 * ion.inset_px == ion.sheet_w_px
        assert ion.sheet_w_px == mm_to_px(LETTER_W_MM, DPI)

    def test_strip_width_is_letter_width_less_the_inset(self):
        ion = _ion()
        assert px_to_mm(ion.tile_w_px, DPI) == pytest.approx(LETTER_W_MM, abs=0.25)
        assert px_to_mm(ion.tile_w_px, DPI) < LETTER_W_MM

    def test_disabled_when_no_sheet_size_given(self):
        assert not _ironon_geometry(0, 0, 0.1, DPI).enabled

    def test_absurd_inset_is_rejected_not_silently_clamped(self):
        with pytest.raises(ValueError):
            _ironon_geometry(LETTER_W_MM, LETTER_H_MM, 200.0, DPI)


class TestFullWidthStripPacks:
    def test_full_width_strip_with_a_real_gap_is_not_oversize(self):
        ion = _ion()
        gap = mm_to_px(3.0, DPI)
        plan = _pack([_tile("t0001", "O1", ion, 438, gap)])
        assert plan["oversize_orders"] == []
        assert plan["held_back_orders"] == []
        assert len(plan["sheets"]) == 1

    def test_isotropic_gap_would_have_failed(self):
        ion = _ion()
        gap = mm_to_px(3.0, DPI)
        old = PackTile("t", ion.tile_w_px, 438, gap, False, "O1")
        assert old.inflated_w > ion.sheet_w_px
        new = PackTile("t", ion.tile_w_px, 438, gap, False, "O1",
                       gap_x_px=ion.inset_px, gap_y_px=gap)
        assert new.inflated_w <= ion.sheet_w_px

    def test_strips_stack_vertically_and_stay_inside_the_sheet(self):
        ion = _ion()
        gap = mm_to_px(2.0, DPI)
        tiles = [_tile(f"t{i:04d}", f"O{i}", ion, 438, gap) for i in range(1, 6)]
        plan = _pack(tiles)
        placed = [p for s in plan["sheets"] for p in s["placements"]]
        assert len(placed) == 5
        assert {p["x_px"] for p in placed} == {ion.inset_px}
        assert all(p["x_px"] + ion.tile_w_px <= ion.sheet_w_px for p in placed)
        assert len({p["y_px"] for p in placed}) == 5

    def test_vertical_gap_is_preserved_between_strips(self):
        ion = _ion()
        gap = mm_to_px(2.0, DPI)
        tiles = [_tile(f"t{i:04d}", f"O{i}", ion, 438, gap) for i in range(1, 4)]
        plan = _pack(tiles)
        ys = sorted(p["y_px"] for s in plan["sheets"] for p in s["placements"])
        for a, b in zip(ys, ys[1:]):
            assert b - (a + 438) >= 2 * gap - 1

    def test_sheet_carries_its_own_letter_geometry(self):
        ion = _ion()
        plan = _pack([_tile("t0001", "O1", ion, 438, mm_to_px(3.0, DPI))])
        sheet = plan["sheets"][0]
        assert sheet["paper_type"] == PAPER_IRON_ON
        assert sheet["width_mm"] == LETTER_W_MM
        assert sheet["height_mm"] == LETTER_H_MM
        assert sheet["margin_mm"] == {"t": 0, "b": 0, "l": 0, "r": 0}

    def test_one_strip_clears_the_iron_on_threshold(self):
        ion = _ion()
        plan = _pack([_tile("t0001", "O1", ion, 438, mm_to_px(3.0, DPI))])
        assert len(exportable_sheets(plan)) == 1


class TestIronOnAlwaysWhiteLetterPage:

    def _render(self, tmp_path, strip_count):
        from PIL import Image
        from plotter import composite
        from plotter.pack import exportable_sheets

        ion = _ion()
        gap = mm_to_px(2.0, DPI)
        h = 380
        tiles_dir = tmp_path / "tiles"
        tiles_dir.mkdir(exist_ok=True)
        Image.new("RGBA", (ion.tile_w_px, h), (20, 120, 200, 255)).save(
            tiles_dir / "x.png")

        tiles = []
        for i in range(1, strip_count + 1):
            t = _tile(f"t{i:04d}", f"O{i}", ion, h, gap)
            t["file"] = "tiles/x.png"
            tiles.append(t)
        manifest = {"dpi": DPI, "tile_count": len(tiles), "tiles": tiles}
        plan = _pack(tiles)
        sheet = exportable_sheets(plan)[0]

        out = tmp_path / f"sheet_{strip_count}.png"
        composite.composite_sheet(
            sheet, manifest, tiles_dir, ion.sheet_w_px, ion.sheet_h_px,
            out, DPI, tile_dpi=DPI, sheet_number=1,
            white_background=(sheet.get("paper_type") == PAPER_IRON_ON),
        )
        return sheet, Image.open(out), ion

    def test_full_sheet_is_white_letter_page(self, tmp_path):
        sheet, img, ion = self._render(tmp_path, 7)
        assert sheet["utilisation"] > 0.8, "this case must actually be full"
        assert img.size == (ion.sheet_w_px, ion.sheet_h_px)
        assert img.getpixel((5, 5)) == (255, 255, 255, 255)

    def test_nearly_empty_sheet_is_white_letter_page(self, tmp_path):
        sheet, img, ion = self._render(tmp_path, 1)
        assert sheet["utilisation"] < 0.3, "this case must actually be sparse"
        assert img.size == (ion.sheet_w_px, ion.sheet_h_px)
        assert img.getpixel((5, 5)) == (255, 255, 255, 255)

    def test_fill_level_does_not_change_canvas(self, tmp_path):
        _, full, _ = self._render(tmp_path, 7)
        _, empty, _ = self._render(tmp_path, 1)
        assert full.size == empty.size

    def test_background_is_fully_opaque_not_transparent(self, tmp_path):
        for count in (1, 7):
            _, img, _ = self._render(tmp_path, count)
            assert img.split()[3].getextrema() == (255, 255), (
                f"{count}-strip sheet has transparent pixels")
