from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from core import paths
from core import templates as core_templates
from core.units import Rect

SCHEMA_VERSION = 1
_ID_RE = re.compile(r"^[a-z0-9_]+$")


class RegionValidationError(ValueError):
    pass


PAPER_REGULAR = "regular"
PAPER_IRON_ON  = "iron_on"
VALID_PAPER_TYPES = (PAPER_REGULAR, PAPER_IRON_ON)


@dataclass
class ProductRegion:
    id: str
    label: str
    rect: Rect
    sku_match: List[str] = field(default_factory=list)
    gap_mm: float = 0.0
    allow_rotate: bool = False
    notes: str = ""
    paper_type: str = PAPER_REGULAR

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "rect": {"x": self.rect.x, "y": self.rect.y, "w": self.rect.w, "h": self.rect.h},
            "sku_match": list(self.sku_match),
            "gap_mm": self.gap_mm,
            "allow_rotate": self.allow_rotate,
            "notes": self.notes,
            "paper_type": self.paper_type,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProductRegion":
        r = d["rect"]
        if "w" in r and "h" in r:
            rect = Rect(x=int(r["x"]), y=int(r["y"]), w=int(r["w"]), h=int(r["h"]))
        else:
            rect = Rect.from_corners(int(r["x1"]), int(r["y1"]), int(r["x2"]), int(r["y2"]))
        return cls(
            id=d["id"],
            label=d["label"],
            rect=rect,
            sku_match=list(d.get("sku_match", [])),
            gap_mm=float(d.get("gap_mm", 0.0)),
            allow_rotate=bool(d.get("allow_rotate", False)),
            notes=d.get("notes", ""),
            paper_type=d.get("paper_type", PAPER_REGULAR),
        )


@dataclass
class RegionSet:

    template_name: str
    template_canvas: Dict[str, Any]
    template_fingerprint: str
    regions: List[ProductRegion]
    updated_at: str = ""
    schema: int = SCHEMA_VERSION

    def get(self, region_id: str) -> ProductRegion:
        for r in self.regions:
            if r.id == region_id:
                return r
        raise KeyError(f"No region '{region_id}' in template '{self.template_name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "template_name": self.template_name,
            "template_canvas": self.template_canvas,
            "template_fingerprint": self.template_fingerprint,
            "updated_at": self.updated_at,
            "regions": [r.to_dict() for r in self.regions],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RegionSet":
        return cls(
            schema=d.get("schema", SCHEMA_VERSION),
            template_name=d["template_name"],
            template_canvas=d.get("template_canvas", {}),
            template_fingerprint=d.get("template_fingerprint", ""),
            updated_at=d.get("updated_at", ""),
            regions=[ProductRegion.from_dict(r) for r in d.get("regions", [])],
        )


def sidecar_exists(template_name: str) -> bool:
    return paths.region_sidecar_path(template_name).exists()


def load(template_name: str) -> RegionSet:
    p = paths.region_sidecar_path(template_name)
    if not p.exists():
        raise FileNotFoundError(
            f"No region sidecar for template '{template_name}' at {p}. "
            f"This template is not production-ready yet (§6.2)."
        )
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return RegionSet.from_dict(data)


def save(region_set: "RegionSet") -> Path:
    region_set.updated_at = datetime.now(timezone.utc).astimezone().isoformat()
    p = paths.region_sidecar_path(region_set.template_name)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(region_set.to_dict(), f, indent=2, ensure_ascii=False)
    tmp.replace(p)
    return p


def list_orphaned_sidecars() -> List[str]:
    known_templates = set(core_templates.list_names())
    orphans = []
    d = paths.regions_dir()
    for p in d.glob("*.regions.json"):
        name = p.name[: -len(".regions.json")]
        if name not in known_templates:
            orphans.append(name)
    return orphans


def check_fingerprint(region_set: "RegionSet") -> bool:
    try:
        current = core_templates.fingerprint(region_set.template_name)
    except Exception:
        return False
    return current == region_set.template_fingerprint


def new_region_set_for_template(template_name: str) -> RegionSet:
    tpl = core_templates.load(template_name)
    info = core_templates.canvas_info(tpl)
    return RegionSet(
        template_name=template_name,
        template_canvas={
            "width": info.width,
            "height": info.height,
            "native_dpi": info.native_dpi,
        },
        template_fingerprint=core_templates.fingerprint(template_name),
        regions=[],
    )
