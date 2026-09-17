from __future__ import annotations

import json
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional

from PIL import Image

from core.units import mm_to_px, px_to_mm, scale_px
from plotter.render import LabelRecord, NameOnlyRenderer, ValuePackRenderer
from regions import model as region_model
from core.theme_map import NAME_ONLY

WARN_QTY_THRESHOLD = 20

IRONON_EDGE_INSET_MM = 0.1


class IronOnGeometry(NamedTuple):

    enabled: bool
    sheet_w_px: int
    sheet_h_px: int
    inset_px: int
    tile_w_px: int


def _ironon_geometry(sheet_w_mm: float, sheet_h_mm: float,
                     inset_mm: float, dpi: int) -> IronOnGeometry:
    if sheet_w_mm <= 0 or sheet_h_mm <= 0:
        return IronOnGeometry(False, 0, 0, 0, 0)
    sheet_w_px = mm_to_px(sheet_w_mm, dpi)
    sheet_h_px = mm_to_px(sheet_h_mm, dpi)
    inset_px = max(0, mm_to_px(inset_mm, dpi))
    tile_w_px = sheet_w_px - 2 * inset_px
    if tile_w_px < 1:
        raise ValueError(
            f"Iron-on edge inset {inset_mm}mm is too large for a "
            f"{sheet_w_mm}mm sheet at {dpi} DPI."
        )
    return IronOnGeometry(True, sheet_w_px, sheet_h_px, inset_px, tile_w_px)


class TileTooLargeError(RuntimeError):
    pass


class _CachedCrop(NamedTuple):

    file_name: str
    w_px: int
    h_px: int
    w_mm: float
    h_mm: float


@dataclass
class TileMeta:
    tile_id: str
    file: str
    w_px: int
    h_px: int
    w_mm: float
    h_mm: float
    gap_px: int
    gap_x_px: Optional[int]
    gap_y_px: Optional[int]
    allow_rotate: bool
    paper_type: str
    order_id: str
    order_number: str
    customer_name: str
    student_name: str
    region_id: str
    region_label: str
    template_name: str
    unit_index: int
    unit_total: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tile_id": self.tile_id, "file": self.file,
            "w_px": self.w_px, "h_px": self.h_px,
            "w_mm": round(self.w_mm, 1), "h_mm": round(self.h_mm, 1),
            "gap_px": self.gap_px,
            "gap_x_px": self.gap_x_px, "gap_y_px": self.gap_y_px,
            "allow_rotate": self.allow_rotate,
            "order_id": self.order_id, "order_number": self.order_number,
            "customer_name": self.customer_name, "student_name": self.student_name,
            "region_id": self.region_id, "region_label": self.region_label,
            "template_name": self.template_name,
            "paper_type": self.paper_type,
            "unit_index": self.unit_index, "unit_total": self.unit_total,
        }


def _fits_on_sheet(w_mm: float, h_mm: float, usable_w_mm: float,
                   usable_h_mm: float, allow_rotate: bool) -> bool:
    if w_mm <= usable_w_mm and h_mm <= usable_h_mm:
        return True
    if allow_rotate and h_mm <= usable_w_mm and w_mm <= usable_h_mm:
        return True
    return False


def extract_tiles(records: List[Dict[str, Any]], run_tiles_dir: Path,
                  target_dpi: int, sheet_usable_w_mm: float,
                  sheet_usable_h_mm: float, global_gap_mm: float,
                  renderer: ValuePackRenderer,
                  name_only_renderer: "NameOnlyRenderer | None" = None,
                  ironon_sheet_width_mm: float = 0.0,
                  ironon_sheet_height_mm: float = 0.0,
                  ironon_edge_inset_mm: float = IRONON_EDGE_INSET_MM,
                  on_warning: Optional[Callable[[str], None]] = None
                  ) -> Dict[str, Any]:
    ion = _ironon_geometry(ironon_sheet_width_mm, ironon_sheet_height_mm,
                           ironon_edge_inset_mm, target_dpi)
    run_tiles_dir.mkdir(parents=True, exist_ok=True)
    tiles: List[TileMeta] = []
    crop_cache: Dict[str, _CachedCrop] = {}
    file_counter = 0

    for rec in records:
        if rec.get("blocked"):
            flags_str = ", ".join(
                f.get("kind", str(f)) if isinstance(f, dict) else str(f)
                for f in rec.get("flags", [])
            ) or "none"
            log.info(
                "Skipping blocked record for order %s student '%s' "
                "(flags: %s) — requires manual production.",
                rec.get("order_number", "?"),
                rec.get("student_name", "?"),
                flags_str,
            )
            continue

        template_name = rec["template_name"]
        region_set = region_model.load(template_name)
        native_dpi = region_set.template_canvas.get("native_dpi", 300)

        cf = rec.get("custom_fields", {})

        label_record = LabelRecord(
            order_id=rec.get("order_id_label", rec["order_number"]),
            student_name=rec["student_name"],
            student_name_arabic=rec.get("student_name_arabic", ""),
            school=rec.get("school", ""),
            grade=rec.get("grade", ""),
            telephone=rec.get("telephone", ""),
            custom_fields=rec.get("custom_fields", {}),
            template_name=template_name,
            language=rec.get("language", "en"),
        )
        value_pack_key = label_record.cache_key()
        value_pack_img: Optional[Image.Image] = None

        for item in rec["items"]:
            region_id = item["region_id"]
            qty = item["qty"]
            region = region_set.get(region_id)

            if qty > WARN_QTY_THRESHOLD and on_warning:
                on_warning(
                    f"Order {rec['order_number']}: quantity {qty} for region "
                    f"'{region_id}' exceeds the warn threshold "
                    f"({WARN_QTY_THRESHOLD})."
                )

            effective_gap_mm = max(region.gap_mm, global_gap_mm)
            gap_px_target = mm_to_px(effective_gap_mm, target_dpi)

            region_is_ironon = ion.enabled and region.paper_type == "iron_on"
            if region_is_ironon:
                ironon_gap_x_px = ion.inset_px
                ironon_gap_y_px = gap_px_target
                tile_gap_x_px: Optional[int] = ironon_gap_x_px
                tile_gap_y_px: Optional[int] = ironon_gap_y_px
            else:
                ironon_gap_y_px = gap_px_target
                tile_gap_x_px = None
                tile_gap_y_px = None

            crop_key = f"{value_pack_key}|{region_id}"
            cached = crop_cache.get(crop_key)

            if cached is None:
                template_type_for_crop = rec.get("custom_fields", {}).get("template_type", "")
                _is_name_only = (
                    template_name.startswith("name_only")
                    or template_type_for_crop == NAME_ONLY
                )

                if _is_name_only and name_only_renderer is not None:
                    rw = region.rect.w
                    rh = region.rect.h
                    if target_dpi != native_dpi:
                        rw = scale_px(rw, native_dpi, target_dpi)
                        rh = scale_px(rh, native_dpi, target_dpi)
                    crop = name_only_renderer.render_record(
                        label_record, zone_w=rw, zone_h=rh)
                else:
                    if value_pack_img is None:
                        value_pack_img = renderer.render(label_record)
                    crop = value_pack_img.crop(region.rect.as_tuple())
                if (not _is_name_only) and target_dpi != native_dpi:
                    new_w = scale_px(region.rect.w, native_dpi, target_dpi)
                    new_h = scale_px(region.rect.h, native_dpi, target_dpi)
                    crop = crop.resize((new_w, new_h), Image.LANCZOS)

                is_ironon = region_is_ironon
                if is_ironon and crop.width != ion.tile_w_px:
                    scale = ion.tile_w_px / crop.width
                    new_h_scaled = max(1, round(crop.height * scale))
                    crop = crop.resize((ion.tile_w_px, new_h_scaled),
                                       Image.LANCZOS)

                w_px, h_px = crop.size
                w_mm = px_to_mm(w_px, target_dpi)
                h_mm = px_to_mm(h_px, target_dpi)

                if is_ironon:
                    if h_px + 2 * ironon_gap_y_px > ion.sheet_h_px:
                        raise TileTooLargeError(
                            f"Iron-on region '{region_id}' of template "
                            f"'{template_name}' is {h_mm:.1f}mm tall after "
                            f"scaling to the sheet width; with a "
                            f"{px_to_mm(ironon_gap_y_px, target_dpi):.1f}mm "
                            f"gap it does not fit the "
                            f"{px_to_mm(ion.sheet_h_px, target_dpi):.1f}mm "
                            f"sheet height. Order {rec['order_number']} "
                            f"would otherwise be held back invisibly on "
                            f"every run (INV-16)."
                        )
                elif not _fits_on_sheet(w_mm, h_mm, sheet_usable_w_mm,
                                        sheet_usable_h_mm, region.allow_rotate):
                    raise TileTooLargeError(
                        f"Region '{region_id}' of template '{template_name}' "
                        f"is {w_mm:.1f}x{h_mm:.1f}mm and cannot fit the usable "
                        f"sheet area ({sheet_usable_w_mm:.1f}x"
                        f"{sheet_usable_h_mm:.1f}mm) in any permitted "
                        f"orientation (allow_rotate={region.allow_rotate}). "
                        f"Order {rec['order_number']} would otherwise be held "
                        f"back invisibly on every run (INV-16)."
                    )

                file_counter += 1
                file_name = f"t{file_counter:04d}.png"
                crop.save(run_tiles_dir / file_name, "PNG")
                crop.close()

                cached = _CachedCrop(file_name, w_px, h_px, w_mm, h_mm)
                crop_cache[crop_key] = cached

            for unit in range(1, qty + 1):
                tiles.append(TileMeta(
                    tile_id=f"t{len(tiles) + 1:04d}",
                    file=f"tiles/{cached.file_name}",
                    w_px=cached.w_px, h_px=cached.h_px,
                    w_mm=cached.w_mm, h_mm=cached.h_mm,
                    gap_px=gap_px_target,
                    gap_x_px=tile_gap_x_px, gap_y_px=tile_gap_y_px,
                    allow_rotate=False if region_is_ironon else region.allow_rotate,
                    paper_type=region.paper_type,
                    order_id=rec["order_id"], order_number=rec["order_number"],
                    customer_name=rec["customer_name"],
                    student_name=rec["student_name"],
                    region_id=region_id, region_label=region.label,
                    template_name=template_name,
                    unit_index=unit, unit_total=qty,
                ))

        if value_pack_img is not None:
            renderer.release(label_record)

    manifest = {
        "dpi": target_dpi,
        "tile_count": len(tiles),
        "tiles": [t.to_dict() for t in tiles],
    }
    manifest_path = run_tiles_dir / "manifest.json"
    tmp = manifest_path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    tmp.replace(manifest_path)
    return manifest
