from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.units import Rect, mm_to_px


PAPER_REGULAR = "regular"
PAPER_IRON_ON  = "iron_on"


@dataclass
class PackTile:
    tile_id: str
    w_px: int
    h_px: int
    gap_px: int
    allow_rotate: bool
    order_id: str
    paper_type: str = PAPER_REGULAR
    region_id: str = ""
    gap_x_px: Optional[int] = None
    gap_y_px: Optional[int] = None

    @property
    def gx(self) -> int:
        return self.gap_px if self.gap_x_px is None else self.gap_x_px

    @property
    def gy(self) -> int:
        return self.gap_px if self.gap_y_px is None else self.gap_y_px

    @property
    def inflated_w(self) -> int:
        return self.w_px + 2 * self.gx

    @property
    def inflated_h(self) -> int:
        return self.h_px + 2 * self.gy


def _group_by_order(tiles: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for t in tiles:
        groups.setdefault(t["order_id"], []).append(t)
    return groups


def _order_sort_key(order_tiles: List[Dict[str, Any]]) -> Tuple[int, str]:
    total_area = sum(t["w_px"] * t["h_px"] for t in order_tiles)
    min_tile_id = min(t["tile_id"] for t in order_tiles)
    return (-total_area, min_tile_id)


def _tiles_largest_first(order_tiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(order_tiles, key=lambda t: (-(t["w_px"] * t["h_px"]), t["tile_id"]))


def _try_place_order(sheet: Any, order_tiles: List[Dict[str, Any]],
                     all_tiles: Dict[str, "PackTile"]) -> bool:
    for t in _tiles_largest_first(order_tiles):
        if not sheet.try_place(all_tiles[t["tile_id"]]):
            return False
    return True


class MaxRectsSheet:

    def __init__(self, usable_w: int, usable_h: int):
        self.usable_w = usable_w
        self.usable_h = usable_h
        self.free_rects: List[Rect] = [Rect(0, 0, usable_w, usable_h)]
        self.placements: List[Dict[str, Any]] = []

    def snapshot(self) -> "MaxRectsSheet":
        clone = MaxRectsSheet(self.usable_w, self.usable_h)
        clone.free_rects = list(self.free_rects)
        clone.placements = list(self.placements)
        return clone

    def _find_best(self, w: int, h: int) -> Optional[Tuple[int, Rect, bool]]:
        best = None
        for idx, fr in enumerate(self.free_rects):
            for rotated, (tw, th) in ((False, (w, h)), (True, (h, w))):
                if tw <= fr.w and th <= fr.h:
                    score = min(fr.w - tw, fr.h - th)
                    key = (score, idx)
                    if best is None or key < (best[0], best[1]):
                        best = (score, idx, fr, rotated)
        if best is None:
            return None
        _, idx, fr, rotated = best
        return idx, fr, rotated

    def try_place(self, tile: PackTile) -> bool:
        w, h = tile.inflated_w, tile.inflated_h
        found = self._find_best(w, h) if tile.allow_rotate else self._find_best_no_rotate(w, h)
        if found is None:
            return False
        idx, fr, rotated = found
        pw, ph = (h, w) if rotated else (w, h)
        placed_rect = Rect(fr.x, fr.y, pw, ph)

        new_free: List[Rect] = []
        for other in self.free_rects:
            if not other.intersects(placed_rect):
                new_free.append(other)
                continue
            new_free.extend(self._split(other, placed_rect))
        self.free_rects = self._prune(new_free)

        off_x, off_y = (tile.gy, tile.gx) if rotated else (tile.gx, tile.gy)
        inner_x = placed_rect.x + off_x
        inner_y = placed_rect.y + off_y
        self.placements.append({
            "tile_id": tile.tile_id,
            "x_px": inner_x, "y_px": inner_y,
            "rotated": rotated,
            "_w": tile.w_px, "_h": tile.h_px,
        })
        return True

    def _find_best_no_rotate(self, w: int, h: int) -> Optional[Tuple[int, Rect, bool]]:
        best = None
        for idx, fr in enumerate(self.free_rects):
            if w <= fr.w and h <= fr.h:
                score = min(fr.w - w, fr.h - h)
                if best is None or score < best[0]:
                    best = (score, idx, fr, False)
        if best is None:
            return None
        _, idx, fr, rotated = best
        return idx, fr, rotated

    @staticmethod
    def _split(free: Rect, used: Rect) -> List[Rect]:
        out: List[Rect] = []
        if used.x > free.x:
            out.append(Rect(free.x, free.y, used.x - free.x, free.h))
        if used.x2 < free.x2:
            out.append(Rect(used.x2, free.y, free.x2 - used.x2, free.h))
        if used.y > free.y:
            out.append(Rect(free.x, free.y, free.w, used.y - free.y))
        if used.y2 < free.y2:
            out.append(Rect(free.x, used.y2, free.w, free.y2 - used.y2))
        return [r for r in out if r.w > 0 and r.h > 0]

    @staticmethod
    def _prune(rects: List[Rect]) -> List[Rect]:
        keep: List[Rect] = []
        for i, r in enumerate(rects):
            contained = False
            for j, other in enumerate(rects):
                if i != j and other.contains(r) and r != other:
                    contained = True
                    break
            if not contained:
                keep.append(r)
        return keep

    def utilisation(self, tiles_by_id: Dict[str, PackTile]) -> float:
        return _utilisation(self.placements, tiles_by_id,
                            self.usable_w * self.usable_h)


class ShelfSheet:
    def __init__(self, usable_w: int, usable_h: int):
        self.usable_w = usable_w
        self.usable_h = usable_h
        self.placements: List[Dict[str, Any]] = []
        self._cursor_x = 0
        self._cursor_y = 0
        self._shelf_h = 0

    def snapshot(self) -> "ShelfSheet":
        clone = ShelfSheet(self.usable_w, self.usable_h)
        clone.placements = list(self.placements)
        clone._cursor_x = self._cursor_x
        clone._cursor_y = self._cursor_y
        clone._shelf_h = self._shelf_h
        return clone

    def try_place(self, tile: PackTile) -> bool:
        w, h = tile.inflated_w, tile.inflated_h
        if self._cursor_x + w > self.usable_w:
            self._cursor_x = 0
            self._cursor_y += self._shelf_h
            self._shelf_h = 0
        if self._cursor_x + w > self.usable_w or self._cursor_y + h > self.usable_h:
            return False
        self.placements.append({
            "tile_id": tile.tile_id,
            "x_px": self._cursor_x + tile.gx,
            "y_px": self._cursor_y + tile.gy,
            "rotated": False,
            "_w": tile.w_px, "_h": tile.h_px,
        })
        self._cursor_x += w
        self._shelf_h = max(self._shelf_h, h)
        return True

    def utilisation(self, tiles_by_id: Dict[str, PackTile]) -> float:
        return _utilisation(self.placements, tiles_by_id,
                            self.usable_w * self.usable_h)


class GridSheet:

    def __init__(self, usable_w: int, usable_h: int):
        self.usable_w = usable_w
        self.usable_h = usable_h
        self.placements: List[Dict[str, Any]] = []
        self._bands: Dict[str, List[int]] = {}
        self._next_band_top = 0

    def snapshot(self) -> "GridSheet":
        clone = GridSheet(self.usable_w, self.usable_h)
        clone.placements = list(self.placements)
        clone._bands = {k: list(v) for k, v in self._bands.items()}
        clone._next_band_top = self._next_band_top
        return clone

    def try_place(self, tile: PackTile) -> bool:
        w, h = tile.inflated_w, tile.inflated_h
        region = tile.region_id or "__default__"

        band = self._bands.get(region)
        if band is None:
            if self._next_band_top + h > self.usable_h:
                return False
            band = [self._next_band_top, 0, self._next_band_top, h]
            self._bands[region] = band
            self._next_band_top += h

        band_top, cursor_x, cursor_y, row_h = band
        is_bottom_band = (cursor_y + row_h) >= self._next_band_top

        if cursor_x + w > self.usable_w:
            if not is_bottom_band:
                return False
            new_y = cursor_y + row_h
            if new_y + h > self.usable_h:
                return False
            cursor_x, cursor_y, row_h = 0, new_y, h
            self._next_band_top = new_y + h

        if cursor_y + h > self.usable_h:
            return False
        if h > row_h:
            if not is_bottom_band:
                return False
            row_h = h
            self._next_band_top = max(self._next_band_top, cursor_y + row_h)

        self.placements.append({
            "tile_id": tile.tile_id,
            "x_px": cursor_x + tile.gx,
            "y_px": cursor_y + tile.gy,
            "rotated": False,
            "_w": tile.w_px, "_h": tile.h_px,
        })
        self._bands[region] = [band_top, cursor_x + w, cursor_y, row_h]
        return True

    def utilisation(self, tiles_by_id: Dict[str, PackTile]) -> float:
        return _utilisation(self.placements, tiles_by_id,
                            self.usable_w * self.usable_h)


def _utilisation(placements: List[Dict[str, Any]],
                 tiles_by_id: Dict[str, PackTile], usable_area: int) -> float:
    if usable_area <= 0:
        return 0.0
    used = sum(
        tiles_by_id[p["tile_id"]].w_px * tiles_by_id[p["tile_id"]].h_px
        for p in placements
    )
    return used / usable_area


_STRATEGIES = {
    "maxrects": MaxRectsSheet,
    "shelf": ShelfSheet,
    "grid": GridSheet,
    "space_optimizer": None,
}


def _pack_with_space_optimizer(
    tiles_raw: List[Dict[str, Any]],
    all_tiles: Dict[str, "PackTile"],
    orders: Dict[str, List[Dict[str, Any]]],
    usable_w: int, usable_h: int,
    margin_l_px: int, margin_t_px: int,
    fill_threshold: float,
    default_paper: str,
    atomic: bool = True,
) -> Dict[str, Any]:
    from plotter.SpaceOptimizer import ShopifyOrderItem, SpaceOptimizer, LabelSheet

    item_map: Dict[str, ShopifyOrderItem] = {}
    item_gap: Dict[str, tuple] = {}
    for t in tiles_raw:
        gap_x = t.get("gap_x_px")
        gap_y = t.get("gap_y_px")
        gx = t["gap_px"] if gap_x is None else gap_x
        gy = t["gap_px"] if gap_y is None else gap_y
        item_map[t["tile_id"]] = ShopifyOrderItem(
            item_id=t["tile_id"],
            order_id=t["order_id"],
            w=t["w_px"] + 2 * gx,
            h=t["h_px"] + 2 * gy,
            is_filler=False,
            can_rotate=t.get("allow_rotate", False),
        )
        item_gap[t["tile_id"]] = (gx, gy)

    oversize_orders: List[str] = []
    unplaced_ids: List[str] = []
    packable_items: List[ShopifyOrderItem] = []

    for oid in sorted(orders):
        order_tile_dicts = orders[oid]
        order_items = [item_map[t["tile_id"]] for t in order_tile_dicts]
        fits = all(i.w <= usable_w and i.h <= usable_h
                   or (i.can_rotate and i.h <= usable_w and i.w <= usable_h)
                   for i in order_items)
        if not fits:
            oversize_orders.append(order_tile_dicts[0]["order_number"])
            unplaced_ids.extend(t["tile_id"] for t in order_tile_dicts)
        else:
            packable_items.extend(order_items)

    optimizer = SpaceOptimizer(usable_w, usable_h)
    sa_time = min(2.0, max(0.5, len(packable_items) * 0.05))
    label_sheets: List[LabelSheet] = optimizer.pack_simulated_annealing(
        packable_items, max_time_seconds=sa_time, atomic=atomic
    )

    placed_item_ids = {pi.item_id for ls in label_sheets for pi in ls.placed_items}
    for oid in sorted(orders):
        order_tile_ids = [t["tile_id"] for t in orders[oid] if t["tile_id"] not in unplaced_ids]
        missing = [tid for tid in order_tile_ids if tid not in placed_item_ids]
        if not missing:
            continue
        if atomic or len(missing) == len(order_tile_ids):
            oversize_orders.append(orders[oid][0]["order_number"])
            unplaced_ids.extend(missing)
        else:
            unplaced_ids.extend(missing)

    sheets_out: List[Dict[str, Any]] = []
    for i, ls in enumerate(label_sheets):
        if not ls.placed_items:
            continue
        util = ls.get_density()
        placements = []
        for pi in ls.placed_items:
            gx, gy = item_gap.get(pi.item_id, (0, 0))
            placements.append({
                "tile_id": pi.item_id,
                "x_px": pi.x + gx + margin_l_px,
                "y_px": pi.y + gy + margin_t_px,
                "rotated": pi.rotated,
            })
        sheets_out.append({
            "local_index": i,
            "utilisation": round(util, 4),
            "placements": placements,
            "paper_type": default_paper,
        })

    placed_order_ids = {
        pi.order_id
        for ls in label_sheets for pi in ls.placed_items
    }
    order_id_by_number = {v[0]["order_number"]: oid for oid, v in orders.items()}
    already_oversize_ids = {order_id_by_number.get(on) for on in oversize_orders}
    held_back = [
        orders[oid][0]["order_number"]
        for oid in sorted(orders)
        if oid not in placed_order_ids and oid not in already_oversize_ids
    ]

    return {
        "sheet_config": {
            "usable_w_px": usable_w, "usable_h_px": usable_h,
            "margin_l_px": margin_l_px, "margin_t_px": margin_t_px,
        },
        "fill_threshold": fill_threshold,
        "sheets": sheets_out,
        "held_back_orders": held_back,
        "oversize_orders": oversize_orders,
        "unplaced": unplaced_ids,
        "paper_types_present": [default_paper],
    }


def _pack_one_group(tiles: List[Dict[str, Any]], sheet_width_mm: float,
                    sheet_height_mm: float, margin_mm: Dict[str, float],
                    dpi: int, fill_threshold: float, strategy: str,
                    paper_type: str, canvas_dpi: int = 0) -> Dict[str, Any]:
    sub_manifest = {"dpi": dpi, "tile_count": len(tiles), "tiles": tiles}
    plan = _pack_single(sub_manifest, sheet_width_mm, sheet_height_mm, margin_mm,
                        dpi, fill_threshold, strategy)
    _cdpi = canvas_dpi if canvas_dpi > 0 else dpi
    for sheet in plan["sheets"]:
        sheet["paper_type"] = paper_type
        sheet["canvas_dpi"] = _cdpi
        sheet["fill_threshold"] = fill_threshold
        sheet["width_mm"] = sheet_width_mm
        sheet["height_mm"] = sheet_height_mm
        sheet["margin_mm"] = dict(margin_mm)
        sheet["pack_dpi"] = dpi
    plan["paper_type"] = paper_type
    return plan


def pack(manifest: Dict[str, Any], sheet_width_mm: float, sheet_height_mm: float,
         margin_mm: Dict[str, float], dpi: int, fill_threshold: float,
         strategy: str = "space_optimizer",
         ironon_sheet_width_mm: float = 215.9,
         ironon_sheet_height_mm: float = 279.4,
         ironon_sheet_dpi: int = 300,
         ironon_fill_threshold: float = 0.03) -> Dict[str, Any]:
    all_tiles = manifest.get("tiles", [])
    regular_tiles = [
        tile for tile in all_tiles
        if tile.get("paper_type", PAPER_REGULAR) != PAPER_IRON_ON
    ]
    ironon_tiles = [
        tile for tile in all_tiles
        if tile.get("paper_type", PAPER_REGULAR) == PAPER_IRON_ON
    ]

    regular_plan = None
    if regular_tiles:
        regular_plan = _pack_one_group(
            regular_tiles, sheet_width_mm, sheet_height_mm, margin_mm, dpi,
            fill_threshold, strategy, PAPER_REGULAR, canvas_dpi=dpi,
        )

    ironon_plan = None
    if ironon_tiles:
        ironon_plan = _pack_one_group(
            ironon_tiles, ironon_sheet_width_mm, ironon_sheet_height_mm,
            {"t": 0, "b": 0, "l": 0, "r": 0}, dpi,
            ironon_fill_threshold, strategy, PAPER_IRON_ON,
            canvas_dpi=ironon_sheet_dpi,
        )

    if regular_plan and ironon_plan:
        return {
            "sheet_config": regular_plan["sheet_config"],
            "fill_threshold": fill_threshold,
            "sheets": regular_plan["sheets"] + ironon_plan["sheets"],
            "held_back_orders": sorted(set(
                regular_plan["held_back_orders"] + ironon_plan["held_back_orders"]
            )),
            "oversize_orders": sorted(set(
                regular_plan["oversize_orders"] + ironon_plan["oversize_orders"]
            )),
            "unplaced": regular_plan["unplaced"] + ironon_plan["unplaced"],
            "paper_types_present": [PAPER_REGULAR, PAPER_IRON_ON],
        }
    if regular_plan:
        return regular_plan
    if ironon_plan:
        return ironon_plan
    return _pack_one_group(
        [], sheet_width_mm, sheet_height_mm, margin_mm, dpi,
        fill_threshold, strategy, PAPER_REGULAR, canvas_dpi=dpi,
    )

def _pack_single(manifest: Dict[str, Any], sheet_width_mm: float, sheet_height_mm: float,
                 margin_mm: Dict[str, float], dpi: int, fill_threshold: float,
                 strategy: str = "maxrects") -> Dict[str, Any]:
    _default_paper = (
        manifest["tiles"][0].get("paper_type", PAPER_REGULAR)
        if manifest.get("tiles") else PAPER_REGULAR
    )
    if strategy not in _STRATEGIES:
        raise ValueError(
            f"Unknown pack strategy '{strategy}'. "
            f"Available: {sorted(_STRATEGIES)}"
        )
    SheetClass = _STRATEGIES[strategy]

    usable_w = mm_to_px(sheet_width_mm - margin_mm["l"] - margin_mm["r"], dpi)
    usable_h = mm_to_px(sheet_height_mm - margin_mm["t"] - margin_mm["b"], dpi)
    margin_l_px = mm_to_px(margin_mm["l"], dpi)
    margin_t_px = mm_to_px(margin_mm["t"], dpi)

    all_tiles: Dict[str, PackTile] = {}
    for t in manifest["tiles"]:
        all_tiles[t["tile_id"]] = PackTile(
            tile_id=t["tile_id"], w_px=t["w_px"], h_px=t["h_px"],
            gap_px=t["gap_px"], allow_rotate=t["allow_rotate"],
            order_id=t["order_id"],
            paper_type=t.get("paper_type", PAPER_REGULAR),
            region_id=t.get("region_id", ""),
            gap_x_px=t.get("gap_x_px"), gap_y_px=t.get("gap_y_px"),
        )

    orders = _group_by_order(manifest["tiles"])

    if strategy == "space_optimizer":
        atomic = False
        return _pack_with_space_optimizer(
            manifest["tiles"], all_tiles, orders,
            usable_w, usable_h, margin_l_px, margin_t_px,
            fill_threshold, _default_paper, atomic=atomic,
        )

    oversize_orders: List[str] = []
    unplaced: List[str] = []
    packable_orders: Dict[str, List[Dict[str, Any]]] = {}
    for order_id in sorted(orders):
        order_tiles = orders[order_id]
        probe = SheetClass(usable_w, usable_h)
        if _try_place_order(probe, order_tiles, all_tiles):
            packable_orders[order_id] = order_tiles
        else:
            oversize_orders.append(order_tiles[0]["order_number"])
            unplaced.extend(t["tile_id"] for t in order_tiles)

    order_queue = sorted(packable_orders.keys(),
                        key=lambda oid: _order_sort_key(packable_orders[oid]))

    sheets: List[Any] = []
    placed_order_ids: set = set()
    pending = list(order_queue)

    while pending:
        sheet = SheetClass(usable_w, usable_h)
        still_pending: List[str] = []

        for order_id in pending:
            order_tiles = packable_orders[order_id]
            trial = sheet.snapshot()
            if _try_place_order(trial, order_tiles, all_tiles):
                sheet = trial
                placed_order_ids.add(order_id)
            else:
                still_pending.append(order_id)

        sheets.append(sheet)
        pending = still_pending

    held_back_orders = [
        packable_orders[oid][0]["order_number"]
        for oid in sorted(packable_orders)
        if oid not in placed_order_ids
    ]

    sheets_out = []
    for i, sheet in enumerate(sheets):
        if not sheet.placements:
            continue
        util = sheet.utilisation(all_tiles)
        absolute_placements = [
            {
                "tile_id": p["tile_id"],
                "x_px": p["x_px"] + margin_l_px,
                "y_px": p["y_px"] + margin_t_px,
                "rotated": p["rotated"],
            }
            for p in sheet.placements
        ]
        sheets_out.append({
            "local_index": i,
            "utilisation": round(util, 4),
            "placements": absolute_placements,
            "paper_type": _default_paper,
        })

    return {
        "sheet_config": {
            "width_mm": sheet_width_mm, "height_mm": sheet_height_mm, "dpi": dpi,
            "margin_mm": margin_mm, "inter_tile_gap_mm": None,
        },
        "fill_threshold": fill_threshold,
        "sheets": sheets_out,
        "held_back_orders": held_back_orders,
        "oversize_orders": oversize_orders,
        "unplaced": unplaced,
    }


def exportable_sheets(plan: Dict[str, Any], force: bool = False) -> List[Dict[str, Any]]:
    if force:
        return plan["sheets"]
    default = plan["fill_threshold"]
    result = []
    for s in plan["sheets"]:
        if s.get("paper_type") == PAPER_IRON_ON:
            result.append(s)
        elif s["utilisation"] >= s.get("fill_threshold", default):
            result.append(s)
    return result


def write_plan(plan: Dict[str, Any], out_path) -> None:
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    tmp.replace(out_path)
