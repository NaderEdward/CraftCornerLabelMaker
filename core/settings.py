from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

_SETTINGS_PATH = Path.home() / ".craftcorner_labelmaker" / "settings.json"

_DEFAULTS: Dict[str, Any] = {
    "shopify_domain": "",
    "shopify_api_version": "2026-07",
    "in_progress_tag": "in-progress",
    "tag_done": "AI-Done",
    "tag_flagged": "AI-Flagged",


    "template_folder": "",
    "backgrounds_root": "",

    "output_folder": "",
    "report_folder": "",
    "run_retention_days": 30,

    "sheet_width_mm": 1200.0,
    "sheet_height_mm": 600.0,
    "ironon_sheet_width_mm": 215.9,
    "ironon_sheet_height_mm": 279.4,
    "ironon_sheet_dpi": 300,
    "ironon_fill_threshold": 0.03,
    "margin_t_mm": 5.0,
    "margin_b_mm": 5.0,
    "margin_l_mm": 5.0,
    "margin_r_mm": 5.0,
    "inter_tile_gap_mm": 3.0,
    "sheet_dpi": 150,

    "fill_threshold": 0.20,
    "pack_strategy": "space_optimizer",
    "label_tiles": False,
    "registration_marks": False,

    "field_mapping": {
        "customer_name": [
            "customer.first_name + customer.last_name",
            "shipping_address.name",
        ],
        "student_name": [
            "line_item.properties.Name",
        ],
        "student_name_arabic": [
            "line_item.properties.arabic name",
        ],
        "school": [
            "line_item.properties.school name",
        ],
        "grade": [
            "line_item.properties.Class",
        ],
    },

    "enabler_map": {
        "OC": "Class",
        "OS": "school name",
        "OP": "text-5",
    },

    "phone_label_field": "text-5",

    "comment_field": "comments",

    "last_sheet_number": 0,
}


SCHEMA_VERSION = 2


def _migrate(data: Dict[str, Any]) -> bool:
    changed = False
    version = int(data.get("_schema_version", 1))

    if version < 2:
        if int(data.get("sheet_dpi", 96)) == 96:
            data["sheet_dpi"] = 150
            changed = True

    if version < SCHEMA_VERSION:
        data["_schema_version"] = SCHEMA_VERSION
        changed = True

    return changed


def load() -> Dict[str, Any]:
    data = dict(_DEFAULTS)
    if _SETTINGS_PATH.exists():
        try:
            with open(_SETTINGS_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            data.update(saved)
        except Exception:
            pass

    if _migrate(data):
        try:
            save(data)
        except Exception:
            pass
    return data


def save(data: Dict[str, Any]) -> None:
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _SETTINGS_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp_path.replace(_SETTINGS_PATH)
