from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from core.units import mm_to_px, px_to_mm, scale_px
from orchestrator.pipeline import (
    IRONON_EDGE_INSET_MM, IRONON_LETTER_HEIGHT_MM, IRONON_LETTER_WIDTH_MM,
)
from plotter import composite
from plotter.pack import PAPER_IRON_ON, exportable_sheets, pack
from plotter.tiles import _ironon_geometry
from regions import model as region_model

ROOT = Path(__file__).resolve().parent
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = ROOT / "diagnostics" / f"ironon_{STAMP}"
LOG = OUT / "diagnostic.log"

TEMPLATE = "iron ons"
STRIP_COUNT = 3


def emit(message: str) -> None:
    print(message)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def check(name: str, passed: bool, detail: str) -> bool:
    emit(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    return passed


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    regular_w_mm, regular_h_mm = 500.0, 600.0
    dpi = 300
    ironon_threshold = 0.03
    checks: list[bool] = []

    emit("Craft Corner Label Maker — iron-on diagnostic")
    emit(f"Output folder: {OUT}")
    emit(f"Regular sheet under test: {regular_w_mm} x {regular_h_mm} mm")
    emit(f"Iron-on sheet: {IRONON_LETTER_WIDTH_MM} x {IRONON_LETTER_HEIGHT_MM} mm, "
         f"zero margins, {IRONON_EDGE_INSET_MM} mm edge inset")

    try:
        region_set = region_model.load(TEMPLATE)
        native_dpi = region_set.template_canvas.get("native_dpi", 300)
        ironons = [r for r in region_set.regions if r.paper_type == PAPER_IRON_ON]
        checks.append(check(
            "1. Iron-on regions found in the real sidecar",
            bool(ironons),
            f"{len(ironons)} region(s) in '{TEMPLATE}' at native {native_dpi} DPI: "
            + ", ".join(r.id for r in ironons),
        ))
        if not ironons:
            raise RuntimeError(f"No iron_on region in '{TEMPLATE}'.")
        region = ironons[0]

        ion = _ironon_geometry(IRONON_LETTER_WIDTH_MM, IRONON_LETTER_HEIGHT_MM,
                               IRONON_EDGE_INSET_MM, dpi)
        checks.append(check(
            "2. Iron-on tile width equals sheet width less the inset",
            ion.tile_w_px + 2 * ion.inset_px == ion.sheet_w_px,
            f"sheet={ion.sheet_w_px}px, tile={ion.tile_w_px}px "
            f"({px_to_mm(ion.tile_w_px, dpi):.2f} mm), inset={ion.inset_px}px "
            f"({px_to_mm(ion.inset_px, dpi):.3f} mm/side)",
        ))

        w_at_target = scale_px(region.rect.w, native_dpi, dpi)
        h_at_target = scale_px(region.rect.h, native_dpi, dpi)
        h_px = max(1, round(h_at_target * ion.tile_w_px / w_at_target))
        w_px = ion.tile_w_px

        gap_y_px = mm_to_px(region.gap_mm, dpi)
        gap_x_px = ion.inset_px

        tiles_dir = OUT / "tiles"
        tiles_dir.mkdir()
        tile_image = Image.new("RGBA", (w_px, h_px), (28, 132, 214, 255))
        drawer = ImageDraw.Draw(tile_image)
        drawer.rectangle((0, 0, w_px - 1, h_px - 1),
                         outline=(255, 255, 255, 255), width=3)
        drawer.text((12, 12), "IRON-ON DIAGNOSTIC", fill=(255, 255, 255, 255))
        tile_image.save(tiles_dir / "ironon_example.png", "PNG")
        tile_image.close()
        checks.append(check(
            "3. Strip built from the real region geometry",
            (w_px, h_px) == (ion.tile_w_px, h_px),
            f"region {region.rect.w}x{region.rect.h}px @{native_dpi} -> "
            f"{w_px}x{h_px}px @{dpi} "
            f"({px_to_mm(w_px, dpi):.2f} x {px_to_mm(h_px, dpi):.2f} mm), "
            f"gap {region.gap_mm} mm -> gap_x={gap_x_px}px gap_y={gap_y_px}px",
        ))

        manifest = {
            "dpi": dpi,
            "tile_count": STRIP_COUNT,
            "tiles": [{
                "tile_id": f"t{i:04d}",
                "file": "tiles/ironon_example.png",
                "w_px": w_px, "h_px": h_px,
                "w_mm": round(px_to_mm(w_px, dpi), 1),
                "h_mm": round(px_to_mm(h_px, dpi), 1),
                "gap_px": gap_y_px,
                "gap_x_px": gap_x_px, "gap_y_px": gap_y_px,
                "allow_rotate": False,
                "paper_type": PAPER_IRON_ON,
                "order_id": f"IRONON-{i}", "order_number": f"#IRONON-{i}",
                "customer_name": "Diagnostic", "student_name": f"Iron On {i}",
                "region_id": region.id, "region_label": region.label,
                "template_name": TEMPLATE,
                "unit_index": 1, "unit_total": 1,
            } for i in range(1, STRIP_COUNT + 1)],
        }
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2),
                                           encoding="utf-8")

        plan = pack(
            manifest,
            sheet_width_mm=regular_w_mm, sheet_height_mm=regular_h_mm,
            margin_mm={"t": 5.0, "b": 5.0, "l": 5.0, "r": 5.0},
            dpi=dpi, fill_threshold=0.90,
            ironon_sheet_width_mm=IRONON_LETTER_WIDTH_MM,
            ironon_sheet_height_mm=IRONON_LETTER_HEIGHT_MM,
            ironon_sheet_dpi=dpi,
            ironon_fill_threshold=ironon_threshold,
        )
        (OUT / "packing_plan.json").write_text(json.dumps(plan, indent=2),
                                               encoding="utf-8")

        checks.append(check(
            "4. No iron-on order declared oversize",
            not plan["oversize_orders"],
            f"oversize={plan['oversize_orders'] or 'none'}",
        ))
        checks.append(check(
            "5. No iron-on order held back",
            not plan["held_back_orders"],
            f"held_back={plan['held_back_orders'] or 'none'}",
        ))

        sheets = plan.get("sheets", [])
        placed = sum(len(s.get("placements", [])) for s in sheets)
        checks.append(check(
            "6. Every strip was placed",
            placed == STRIP_COUNT,
            f"sheets={len(sheets)}, placements={placed}/{STRIP_COUNT}",
        ))
        if not sheets:
            raise RuntimeError("The packer produced no sheet; see packing_plan.json.")
        sheet = sheets[0]
        checks.append(check(
            "7. Sheet carries Letter geometry and iron-on settings",
            (sheet.get("paper_type") == PAPER_IRON_ON
             and sheet.get("width_mm") == IRONON_LETTER_WIDTH_MM
             and sheet.get("height_mm") == IRONON_LETTER_HEIGHT_MM
             and sheet.get("fill_threshold") == ironon_threshold),
            f"paper={sheet.get('paper_type')}, "
            f"{sheet.get('width_mm')}x{sheet.get('height_mm')}mm, "
            f"utilisation={sheet.get('utilisation')}, "
            f"threshold={sheet.get('fill_threshold')}",
        ))

        sheet_w_px = ion.sheet_w_px
        worst_right = max(p["x_px"] + w_px for p in sheet["placements"])
        checks.append(check(
            "8. Strips span the sheet width without overrunning it",
            all(p["x_px"] == gap_x_px for p in sheet["placements"])
            and worst_right <= sheet_w_px,
            f"x={sorted({p['x_px'] for p in sheet['placements']})}, "
            f"right edge={worst_right}px of {sheet_w_px}px",
        ))

        exportable = exportable_sheets(plan)
        checks.append(check(
            "9. Iron-on survives export filtering",
            len(exportable) >= 1,
            f"exportable sheets={len(exportable)}",
        ))
        if not exportable:
            raise RuntimeError("Sheet filtered out before rendering; see packing_plan.json.")

        sheet_path = OUT / "sheet_ironon_001.png"
        composite.composite_sheet(
            exportable[0], manifest, tiles_dir,
            ion.sheet_w_px, ion.sheet_h_px, sheet_path, dpi, tile_dpi=dpi,
        )
        with Image.open(sheet_path) as rendered:
            rendered_size = rendered.size
            bbox = rendered.split()[-1].getbbox()
        checks.append(check(
            "10. Letter-size PNG rendered",
            rendered_size == (ion.sheet_w_px, ion.sheet_h_px),
            f"PNG={rendered_size[0]} x {rendered_size[1]} px at {dpi} DPI "
            f"({px_to_mm(rendered_size[0], dpi):.1f} x "
            f"{px_to_mm(rendered_size[1], dpi):.1f} mm)",
        ))
        checks.append(check(
            "11. Artwork reaches both side edges",
            bbox is not None and bbox[0] <= ion.inset_px
            and bbox[2] >= sheet_w_px - ion.inset_px,
            f"alpha bbox={bbox} on a {sheet_w_px}px-wide sheet",
        ))

    except Exception as exc:
        emit(f"[FAIL] Unexpected error: {exc}")
        traceback.print_exc(file=sys.stdout)
        with LOG.open("a", encoding="utf-8") as handle:
            traceback.print_exc(file=handle)
        return 1

    passed = all(checks)
    emit(f"\nRESULT: {'PASS' if passed else 'FAIL'}")
    emit("Open packing_plan.json and sheet_ironon_001.png in this diagnostic folder.")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
