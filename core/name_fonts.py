from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from core import paths


NAME_FONTS_DEFAULT: Dict[str, dict] = {
    "cutout chromatix": {
        "font_file":       "CHROMATIX COLORFUL.OTF",
        "stroke_px":       13,
        "stroke_color":    "#ffffff",
        "line_gap_mult":   -0.8,
        "gap_from_name":   8,
        "class_font_file": "BEAUTIFUL SMILE.OTF",
        "force_uppercase": True,
        "strip_pattern":   r"[^A-Z\s]",
        "size_scale":      None,
    },
}

CASE_MODE_PATTERNS: Dict[str, str] = {
    "upper": r"[^A-Z\s]",
    "title": r"[^A-Za-z\s]",
}


def set_case_mode(registry: Dict[str, dict], slug: str, mode: str) -> None:
    mode = mode.strip().lower()
    if mode not in CASE_MODE_PATTERNS:
        raise ValueError(f"case_mode must be one of {sorted(CASE_MODE_PATTERNS)}, got {mode!r}")
    entry = registry[slug]
    entry["case_mode"]       = mode
    entry["strip_pattern"]   = CASE_MODE_PATTERNS[mode]
    entry["force_uppercase"] = (mode == "upper")


def name_fonts_dir() -> Path:
    return paths.app_root() / "assets" / "name_fonts"


def _config_path() -> Path:
    return paths.app_root() / "data" / "name_fonts_config.json"


def load_registry() -> Dict[str, dict]:
    p = _config_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(NAME_FONTS_DEFAULT)


def save_registry(data: Dict[str, dict]) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
    _sync_themes_list(list(data.keys()))
    from core import theme_map
    theme_map.invalidate_cache()


def _sync_themes_list(slugs: List[str]) -> None:
    from core import theme_admin
    tl_path = theme_admin.themes_list_path()
    if not tl_path.exists():
        return
    tl = json.loads(tl_path.read_text(encoding="utf-8"))
    tl["name_cutout"] = sorted(set(s.lower().strip() for s in slugs))
    tl["name_only"] = [e for e in tl.get("name_only", [])
                       if e not in tl["name_cutout"]]
    tmp = tl_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(tl, indent=4, ensure_ascii=False), encoding="utf-8")
    tmp.replace(tl_path)


def get(slug: str) -> Optional[dict]:
    return load_registry().get(slug.lower().strip())


def font_path(slug: str) -> Optional[Path]:
    entry = get(slug)
    if not entry:
        return None
    p = name_fonts_dir() / entry["font_file"]
    return p if p.exists() else None


def class_font_path(slug: str) -> Optional[Path]:
    entry = get(slug)
    if not entry:
        return None
    cf = entry.get("class_font_file")
    if not cf:
        return None
    p = name_fonts_dir() / cf
    return p if p.exists() else None


def all_slugs() -> List[str]:
    return sorted(load_registry().keys())


def resolve_font(font_file: str) -> Optional[Path]:
    p = name_fonts_dir() / font_file
    return p if p.exists() else None


_STRIP_PREFIXES = ["chromatix", "cutout", "bubble", "brush"]

def derive_slug(filename: str) -> str:
    stem = Path(filename).stem.lower()
    stem = re.sub(r"[_\-]+", " ", stem).strip()
    stem = re.sub(r"^\d{8,}\s+", "", stem).strip()
    if not stem.startswith("name cutout") and not stem.startswith("name_cutout"):
        for prefix in _STRIP_PREFIXES:
            if stem == prefix or stem.startswith(prefix + " "):
                stem = stem[len(prefix):].strip()
                break
    return stem


import shutil
from dataclasses import dataclass, field

FONT_SUFFIXES = (".otf", ".ttf", ".woff", ".woff2")


@dataclass
class FontImportResult:
    added:   List[str] = field(default_factory=list)
    copied:  List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    errors:  List[str] = field(default_factory=list)


def import_font(
    src: Path,
    slug: str,
    overwrite: bool = False,
    params: Optional[dict] = None,
    result: Optional[FontImportResult] = None,
) -> FontImportResult:
    res = result or FontImportResult()
    src = Path(src)
    slug = slug.lower().strip()

    if not src.is_file():
        res.errors.append(f"{src.name} — file not found")
        return res
    if src.suffix.lower() not in FONT_SUFFIXES:
        res.skipped.append(f"{src.name} — not a font file")
        return res
    if not slug:
        res.errors.append(f"{src.name} — slug is empty")
        return res

    dest_dir = name_fonts_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    if dest.exists() and not overwrite:
        res.skipped.append(f"{src.name} — already exists (enable overwrite to replace)")
    else:
        try:
            shutil.copy2(src, dest)
            res.copied.append(src.name)
        except OSError as e:
            res.errors.append(f"{src.name} — copy failed: {e}")
            return res

    registry = load_registry()
    if slug not in registry or overwrite:
        registry[slug] = {
            **(params or {}),
            "font_file": src.name,
        }
        registry[slug].setdefault("stroke_px",        13)
        registry[slug].setdefault("stroke_color",     "#ffffff")
        registry[slug].setdefault("line_gap_mult",    -0.8)
        registry[slug].setdefault("gap_from_name",    8)
        registry[slug].setdefault("force_uppercase",  True)
        registry[slug].setdefault("strip_pattern",    r"[^A-Z\s]")
        registry[slug].setdefault("case_mode",         "upper")
        registry[slug].setdefault("size_scale",        None)
        save_registry(registry)
        res.added.append(slug)

    return res


def remove_font(slug: str, delete_file: bool = False) -> FontImportResult:
    res = FontImportResult()
    slug = slug.lower().strip()
    registry = load_registry()
    if slug not in registry:
        res.skipped.append(f"'{slug}' not in registry")
        return res
    entry = registry.pop(slug)
    save_registry(registry)
    res.added.append(slug)
    if delete_file:
        fp = name_fonts_dir() / entry.get("font_file", "")
        if fp.exists():
            try:
                fp.unlink()
                res.copied.append(fp.name)
            except OSError as e:
                res.errors.append(f"{fp.name} — delete failed: {e}")
    return res


def list_fonts() -> List[dict]:
    registry = load_registry()
    out = []
    for slug, entry in sorted(registry.items()):
        ff  = name_fonts_dir() / entry.get("font_file", "")
        cff_name = entry.get("class_font_file")
        cff = (name_fonts_dir() / cff_name) if cff_name else None
        out.append({
            "slug":             slug,
            "font_file":        entry.get("font_file", ""),
            "class_font_file":  cff_name or "",
            "stroke_px":        entry.get("stroke_px", 12),
            "stroke_color":     entry.get("stroke_color", "#ffffff"),
            "line_gap_mult":    entry.get("line_gap_mult", 1.0),
            "gap_from_name":    entry.get("gap_from_name", 8),
            "force_uppercase":  entry.get("force_uppercase", True),
            "case_mode":        entry.get("case_mode", "upper"),
            "size_scale":       entry.get("size_scale", None),
            "font_file_exists": ff.exists(),
            "class_font_exists": cff.exists() if cff else False,
        })
    return out


def scan_folder(folder: str) -> List[dict]:
    d = Path(folder)
    if not d.is_dir():
        raise NotADirectoryError(f"Not a folder: {d}")
    registry = load_registry()
    out = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.suffix.lower() not in FONT_SUFFIXES:
            continue
        slug = derive_slug(f.name)
        out.append({
            "source_path":    str(f),
            "original_name":  f.name,
            "suggested_slug": slug,
            "already_registered": slug in registry,
            "file_exists_in_dir": (name_fonts_dir() / f.name).exists(),
        })
    return out
