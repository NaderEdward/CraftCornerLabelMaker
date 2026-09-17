from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

SIGNS          = "signs"
STITCHES       = "stitches"
PLAIN_SIGNS    = "plain_signs"
PLAIN_STITCHES = "plain_stitches"
NAME_ONLY      = "name_only"
NAME_CUTOUT    = "name_cutout"

TYPE_LABELS = {
    SIGNS:          "Signs labels",
    STITCHES:       "Stitches labels",
    PLAIN_SIGNS:    "Plain signs labels",
    PLAIN_STITCHES: "Plain stitches labels",
    NAME_ONLY:      "Name-only (decorative font)",
    NAME_CUTOUT:    "Name cutout (Chromatix value pack)",
}

_JSON_KEY_TO_TYPE: Dict[str, str] = {
    "Signs labels":          SIGNS,
    "Stitches labels":       STITCHES,
    "Plain signs labels":    PLAIN_SIGNS,
    "Plain stitches labels": PLAIN_STITCHES,
    "signs":                 SIGNS,
    "stitches":              STITCHES,
    "plain_signs":           PLAIN_SIGNS,
    "plain_stitches":        PLAIN_STITCHES,
    "name_only":             NAME_ONLY,
    "name_cutout":           NAME_CUTOUT,
}

BACKGROUND_SUBFOLDER: Dict[str, str] = {
    SIGNS:          "signs",
    STITCHES:       "stitches",
    PLAIN_SIGNS:    "plain_signs",
    PLAIN_STITCHES: "plain_stitches",
    NAME_ONLY:      "",
    NAME_CUTOUT:    "name_cutout",
}

_cache: Optional[Dict[str, str]] = None


def _data_path() -> Path:
    from core import paths
    return paths.app_root() / "data" / "themes_list.json"


def _build_map() -> Dict[str, str]:
    p = _data_path()
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    mapping: Dict[str, str] = {}
    for json_key, themes in data.items():
        ttype = _JSON_KEY_TO_TYPE.get(json_key)
        if not ttype:
            continue
        for theme in themes:
            mapping[theme.lower().strip()] = ttype
    return mapping


def _get_map() -> Dict[str, str]:
    global _cache
    if _cache is None:
        _cache = _build_map()
    return _cache


def invalidate_cache() -> None:
    global _cache
    _cache = None


BLOCKED_THEMES: frozenset = frozenset({
    "teenage era",
    "jeans",
})


def lookup(theme: str) -> Tuple[Optional[str], str]:
    key = theme.lower().strip()
    if key in BLOCKED_THEMES:
        return None, "BLOCKED_THEME"
    ttype = _get_map().get(key)
    if ttype:
        return ttype, ""
    if theme.lower().startswith("name"):
        return None, "NAME_THEME"
    return None, "UNKNOWN_THEME"


def background_subfolder(template_type: str) -> str:
    return BACKGROUND_SUBFOLDER.get(template_type, template_type)
