from __future__ import annotations

from collections import Counter
from typing import Dict, List

from regions.model import RegionSet, _ID_RE


def validate_region_set(rs: RegionSet) -> List[str]:
    problems: List[str] = []

    canvas_w = rs.template_canvas.get("width", 0)
    canvas_h = rs.template_canvas.get("height", 0)

    seen_ids: Counter = Counter()
    sku_owner: Dict[str, List[str]] = {}

    for region in rs.regions:
        if not _ID_RE.match(region.id):
            problems.append(
                f"Region id '{region.id}' must match ^[a-z0-9_]+$"
            )
        seen_ids[region.id] += 1

        if not region.label.strip():
            problems.append(f"Region '{region.id}' has an empty label")

        if region.rect.w < 1 or region.rect.h < 1:
            problems.append(
                f"Region '{region.id}' has non-positive size "
                f"({region.rect.w}x{region.rect.h})"
            )

        if canvas_w and canvas_h:
            if (region.rect.x < 0 or region.rect.y < 0
                    or region.rect.x2 > canvas_w or region.rect.y2 > canvas_h):
                problems.append(
                    f"Region '{region.id}' extends past canvas bounds "
                    f"(canvas {canvas_w}x{canvas_h}, rect "
                    f"{region.rect.x},{region.rect.y} -> "
                    f"{region.rect.x2},{region.rect.y2})"
                )

        if not region.sku_match:
            problems.append(f"Region '{region.id}' has no sku_match entries")

        if region.gap_mm < 0:
            problems.append(f"Region '{region.id}' has negative gap_mm")

        for sku in region.sku_match:
            key = sku.strip().lower()
            sku_owner.setdefault(key, []).append(region.id)

    for region_id, count in seen_ids.items():
        if count > 1:
            problems.append(f"Duplicate region id '{region_id}' ({count} occurrences)")

    for sku, owners in sku_owner.items():
        if len(set(owners)) > 1:
            problems.append(
                f"sku_match '{sku}' matches multiple regions: {sorted(set(owners))} "
                f"— warning at authoring time; this is a HARD ERROR at transform "
                f"time (§6.4), ambiguity must never be resolved silently."
            )

    return problems


def is_production_ready(rs: RegionSet) -> bool:
    return len(validate_region_set(rs)) == 0
