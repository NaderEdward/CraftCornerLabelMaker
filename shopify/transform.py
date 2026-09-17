from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from regions import model as region_model


def build_sku_map(template_names: List[str]) -> Dict[str, List[Tuple[str, str]]]:
    sku_map: Dict[str, List[Tuple[str, str]]] = {}
    for tname in template_names:
        try:
            rs = region_model.load(tname)
        except FileNotFoundError:
            continue
        for region in rs.regions:
            for sku in region.sku_match:
                key = sku.strip().lower()
                sku_map.setdefault(key, []).append((tname, region.id))
    return sku_map


def load_records(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_records(records_dict: Dict[str, Any], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(records_dict, f, indent=2, ensure_ascii=False)
    tmp.replace(out_path)
    return out_path
