from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


SHEET_ID_W_MM = 20.0
SHEET_ID_H_MM = 10.0


def composite_sheet(plan_sheet: Dict[str, Any], manifest: Dict[str, Any],
                    tiles_dir: Path, width_px: int, height_px: int,
                    out_path: Path, dpi: int,
                    tile_dpi: int = 0,
                    label_tiles: bool = False,
                    sheet_number: Optional[int] = None,
                    white_background: bool = False) -> Path:
    tile_by_id = {t["tile_id"]: t for t in manifest["tiles"]}

    bg = (255, 255, 255, 255) if white_background else (0, 0, 0, 0)
    canvas = Image.new("RGBA", (width_px, height_px), bg)

    _tile_dpi = tile_dpi if tile_dpi > 0 else dpi
    _scale = dpi / _tile_dpi if _tile_dpi != dpi else 1.0

    for placement in plan_sheet["placements"]:
        meta = tile_by_id[placement["tile_id"]]
        tile_path = tiles_dir / Path(meta["file"]).name
        if not tile_path.exists():
            raise FileNotFoundError(
                f"Tile file missing for {placement['tile_id']}: {tile_path} "
                f"— this indicates a corrupted run directory."
            )
        with Image.open(tile_path) as raw:
            tile = raw.convert("RGBA")
            if placement.get("rotated"):
                tile = tile.rotate(-90, expand=True)
            if _scale != 1.0:
                tile = tile.resize((max(1, round(tile.width * _scale)),
                                    max(1, round(tile.height * _scale))), Image.LANCZOS)
            x = round(placement["x_px"] * _scale)
            y = round(placement["y_px"] * _scale)
            canvas.alpha_composite(tile, (x, y))

    if label_tiles:
        _draw_labels(canvas, plan_sheet, tile_by_id)

    if sheet_number is not None:
        _draw_sheet_id(canvas, sheet_number, dpi)

    _atomic_save(canvas, out_path, dpi)
    canvas.close()
    return out_path


def _draw_sheet_id(canvas: Image.Image, sheet_number: int, dpi: int) -> None:
    from core.units import mm_to_px

    W, H = canvas.size
    lw = mm_to_px(SHEET_ID_W_MM, dpi)
    lh = mm_to_px(SHEET_ID_H_MM, dpi)
    pad = max(2, mm_to_px(1.5, dpi))

    corners = [
        (W - lw - pad, H - lh - pad),
        (pad, H - lh - pad),
        (W - lw - pad, pad),
        (pad, pad),
    ]

    alpha = canvas.split()[3]

    chosen = corners[0]
    for cx, cy in corners:
        box = (max(0, cx), max(0, cy),
               min(W, cx + lw), min(H, cy + lh))
        region = alpha.crop(box)
        if region.getbbox() is None:
            chosen = (cx, cy)
            break

    x, y = int(chosen[0]), int(chosen[1])

    label = Image.new("RGBA", (lw, lh), (255, 255, 255, 255))
    draw = ImageDraw.Draw(label)
    draw.rectangle([0, 0, lw - 1, lh - 1], outline=(0, 0, 0, 255), width=2)

    text = f"#{sheet_number:03d}"
    font = _best_font(min(lw, lh) // 2)
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        tw, th = draw.textsize(text, font=font)
    tx = (lw - tw) // 2
    ty = (lh - th) // 2
    draw.text((tx, ty), text, fill=(0, 0, 0, 255), font=font)

    canvas.alpha_composite(label, (x, y))
    label.close()


def _best_font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except (OSError, IOError):
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except (OSError, IOError):
            return ImageFont.load_default()


def _atomic_save(canvas: Image.Image, out_path: Path, dpi: int) -> None:
    import time
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    canvas.save(str(tmp_path), "PNG", compress_level=6, dpi=(dpi, dpi))
    try:
        with open(str(tmp_path), "ab") as fh:
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        pass

    _last_err = None
    for _attempt in range(6):
        try:
            tmp_path.replace(out_path)
            _last_err = None
            break
        except PermissionError as _e:
            _last_err = _e
            time.sleep(0.15 * (1 + _attempt))
    if _last_err is not None:
        raise PermissionError(
            f"Could not rename '{tmp_path.name}' to '{out_path.name}' after 6 "
            f"attempts. Another program (Explorer, antivirus) is holding the "
            f"file. Close any thumbnail preview or add the output folder to "
            f"your antivirus exclusion list, then re-run."
        ) from _last_err


def _draw_labels(canvas: Image.Image, plan_sheet: Dict[str, Any],
                 tile_by_id: Dict[str, Any]) -> None:
    draw = ImageDraw.Draw(canvas, "RGBA")
    for placement in plan_sheet["placements"]:
        meta = tile_by_id[placement["tile_id"]]
        x, y = placement["x_px"], placement["y_px"]
        text = meta.get("order_number", "")
        draw.text((x + 2, max(y - 14, 0)), text, fill=(0, 0, 0, 140))
