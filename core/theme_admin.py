from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from core import paths
from core import theme_map

CATEGORIES = (
    theme_map.SIGNS,
    theme_map.STITCHES,
    theme_map.PLAIN_SIGNS,
    theme_map.PLAIN_STITCHES,
)

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")

_STRIP_PREFIXES = ("extras", "extra", "vp")

_STRIP_SUFFIXES = ("copy", "empty", "blank", "final", "new")


def derive_theme_name(filename: str) -> str:
    stem = Path(filename).stem.lower()
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()

    for pref in _STRIP_PREFIXES:
        if stem.startswith(pref + " "):
            stem = stem[len(pref) + 1:].strip()
            break

    changed = True
    while changed:
        changed = False
        for suf in _STRIP_SUFFIXES:
            if stem.endswith(" " + suf):
                stem = stem[: -(len(suf) + 1)].strip()
                changed = True
    return stem


def target_filename(theme: str, is_extras: bool, suffix: str) -> str:
    prefix = "Extras" if is_extras else "VP"
    return f"{prefix} {theme}{suffix.lower()}"


def themes_list_path() -> Path:
    return paths.app_root() / "data" / "themes_list.json"


def load_themes_list() -> Dict[str, List[str]]:
    p = themes_list_path()
    if not p.exists():
        return {c: [] for c in CATEGORIES}
    data = json.loads(p.read_text(encoding="utf-8"))
    for c in CATEGORIES:
        data.setdefault(c, [])
    return data


def save_themes_list(data: Dict[str, List[str]]) -> None:
    p = themes_list_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    ordered = {c: sorted(set(t.lower().strip() for t in data.get(c, []) if t.strip()))
               for c in CATEGORIES}
    for k, v in data.items():
        if k not in ordered:
            ordered[k] = v

    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ordered, indent=4, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
    theme_map.invalidate_cache()


def backgrounds_write_root() -> Path:
    ext = paths.backgrounds_root()
    return ext if ext else paths.backgrounds_fallback_dir()


@dataclass
class Candidate:
    source_path: str
    original_name: str
    theme: str
    already_listed: bool = False
    background_exists: bool = False


def scan_folder(folder: str | Path, category: str, recursive: bool = False) -> List[Candidate]:
    d = Path(folder)
    if not d.is_dir():
        raise NotADirectoryError(f"Not a folder: {d}")

    listing = load_themes_list().get(category, [])
    existing = set(listing)

    it = d.rglob("*") if recursive else d.iterdir()
    out: List[Candidate] = []
    for p in sorted(it):
        if not p.is_file() or p.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        theme = derive_theme_name(p.name)
        if not theme:
            continue
        dest = backgrounds_write_root() / category / target_filename(theme, False, p.suffix)
        out.append(Candidate(
            source_path=str(p),
            original_name=p.name,
            theme=theme,
            already_listed=theme in existing,
            background_exists=dest.exists(),
        ))
    return out


@dataclass
class ImportResult:
    added: List[str] = field(default_factory=list)
    copied: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def import_theme(
    src: Path | str,
    category: str,
    theme: Optional[str] = None,
    is_extras: bool = False,
    overwrite: bool = False,
    result: Optional[ImportResult] = None,
    _list_cache: Optional[Dict[str, List[str]]] = None,
) -> ImportResult:
    res = result or ImportResult()
    src = Path(src)

    if category not in CATEGORIES:
        res.errors.append(f"{src.name} — unknown category '{category}'")
        return res
    if not src.is_file():
        res.errors.append(f"{src.name} — file not found")
        return res
    if src.suffix.lower() not in IMAGE_SUFFIXES:
        res.skipped.append(f"{src.name} — not an image")
        return res

    name = (theme or derive_theme_name(src.name)).lower().strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        res.skipped.append(f"{src.name} — could not derive a theme name")
        return res

    dest_dir = backgrounds_write_root() / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / target_filename(name, is_extras, src.suffix)

    if dest.exists() and not overwrite:
        res.skipped.append(f"{dest.name} — already exists (enable overwrite to replace)")
    else:
        try:
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            shutil.copy2(src, tmp)
            tmp.replace(dest)
            res.copied.append(dest.name)
        except OSError as e:
            res.errors.append(f"{src.name} — copy failed: {e}")
            return res

    data = _list_cache if _list_cache is not None else load_themes_list()
    if name not in data.get(category, []):
        data.setdefault(category, []).append(name)
        res.added.append(name)
    if _list_cache is None:
        save_themes_list(data)

    return res


def import_many(
    sources: List[Path | str],
    category: str,
    is_extras: bool = False,
    overwrite: bool = False,
    theme_overrides: Optional[Dict[str, str]] = None,
) -> ImportResult:
    res = ImportResult()
    data = load_themes_list()
    overrides = theme_overrides or {}

    for s in sources:
        p = Path(s)
        import_theme(
            p, category,
            theme=overrides.get(str(p)) or overrides.get(p.name),
            is_extras=is_extras, overwrite=overwrite,
            result=res, _list_cache=data,
        )

    save_themes_list(data)
    return res


def list_themes() -> Dict[str, List[Dict[str, object]]]:
    from core import templates as core_templates

    data = load_themes_list()
    out: Dict[str, List[Dict[str, object]]] = {}
    for cat in CATEGORIES:
        rows = []
        for theme in sorted(data.get(cat, [])):
            bg = core_templates.resolve_theme_background(theme, False, cat)
            rows.append({
                "theme": theme,
                "has_background": bg is not None,
                "background_file": bg.name if bg else None,
            })
        out[cat] = rows
    return out


def remove_theme(theme: str, category: str, delete_file: bool = False) -> ImportResult:
    res = ImportResult()
    name = theme.lower().strip()
    data = load_themes_list()

    if name in data.get(category, []):
        data[category] = [t for t in data[category] if t != name]
        save_themes_list(data)
        res.added.append(name)
    else:
        res.skipped.append(f"{name} — not listed under {category}")

    if delete_file:
        from core import templates as core_templates
        bg = core_templates.resolve_theme_background(name, False, category)
        if bg and bg.exists():
            try:
                bg.unlink()
                res.copied.append(bg.name)
            except OSError as e:
                res.errors.append(f"{bg.name} — delete failed: {e}")
    return res
