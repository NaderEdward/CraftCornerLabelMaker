from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import paths

DEFAULT_NATIVE_DPI = 300


@dataclass(frozen=True)
class CanvasInfo:
    width: int
    height: int
    native_dpi: int
    background_image: str


class TemplateNotFoundError(FileNotFoundError):
    pass


def _search_dirs() -> List[Path]:
    return [paths.template_folder(), paths.bundled_templates_assets_dir()]


def list_names() -> List[str]:
    names = set()
    for d in _search_dirs():
        if d.exists():
            names.update(p.stem for p in d.glob("*.json"))
    return sorted(names)


def load(name: str) -> Dict[str, Any]:
    for d in _search_dirs():
        p = d / f"{name}.json"
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    raise TemplateNotFoundError(f"Template '{name}' not found in {_search_dirs()}")

def path_for(name: str) -> Optional[Path]:
    for d in _search_dirs():
        p = d / f"{name}.json"
        if p.exists():
            return p
    return None


def resolve_background(filename: str) -> Optional[Path]:
    if not filename:
        return None
    basename = Path(filename).name
    bg_root = paths.bundled_assets_dir() / "backgrounds"
    candidates = [
        *(bg_root / sub / basename
          for sub in ("signs", "stitches", "plain_signs", "plain_stitches")),
        paths.bundled_assets_dir() / basename,
        paths.bundled_templates_assets_dir() / basename,
        Path(filename),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def resolve_theme_background(theme: str, is_extras: bool,
                              template_type: str) -> Optional[Path]:
    from core.theme_map import background_subfolder
    slug = theme.lower().strip()
    prefixes = ["extras", "extra"] if is_extras else ["vp"]

    subfolder = background_subfolder(template_type)
    subfolders = [subfolder] + [
        s for s in ("signs", "stitches", "plain_signs", "plain_stitches")
        if s != subfolder
    ]

    roots = []
    ext_root = paths.backgrounds_root()
    if ext_root:
        roots.append(ext_root)
    roots.append(paths.backgrounds_fallback_dir())

    for root in roots:
        for sub in subfolders:
            d = root / sub
            if not d.is_dir():
                continue
            for p in sorted(d.iterdir()):
                if p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                    continue
                stem = p.stem.lower()
                for pref in prefixes:
                    if template_type == "name_cutout":
                        if stem.startswith(pref):
                            return p
                    elif stem.startswith(f"{pref} {slug}"):
                        return p
    return None


def describe_background_search(theme: str, is_extras: bool,
                                template_type: str) -> str:
    from core.theme_map import background_subfolder
    slug = theme.lower().strip()
    prefix = "Extras" if is_extras else "VP"
    subfolder = background_subfolder(template_type)

    lines = [f"Looking for a file whose name starts with: \"{prefix} {slug}\""]

    ext_root = paths.backgrounds_root()
    if ext_root:
        lines.append(f"Backgrounds root (auto-detected): {ext_root}")
    else:
        lines.append(
            "No backgrounds root found. Expected a folder named 'All themes' "
            "on any drive (e.g. A:\\All themes), or set 'backgrounds_root' in Settings."
        )

    roots = ([ext_root] if ext_root else []) + [paths.bundled_assets_dir() / "backgrounds"]
    for root in roots:
        d = root / subfolder
        if not d.is_dir():
            lines.append(f"  MISSING FOLDER: {d}")
            continue
        files = [p.name for p in sorted(d.iterdir())
                 if p.suffix.lower() in (".png", ".jpg", ".jpeg")]
        if files:
            shown = files
            lines.append(f"  {d} contains {len(files)} image(s): {shown}")
        else:
            lines.append(f"  {d} is empty")
    return "\n".join(lines)


def canvas_info(tpl: Dict[str, Any]) -> CanvasInfo:
    canvas = tpl.get("canvas", {})
    return CanvasInfo(
        width=int(canvas.get("width", 0)),
        height=int(canvas.get("height", 0)),
        native_dpi=int(canvas.get("native_dpi", DEFAULT_NATIVE_DPI)),
        background_image=canvas.get("background_image", ""),
    )


def fingerprint(name: str) -> str:
    tpl = load(name)
    canvas = tpl.get("canvas", {})
    h = hashlib.sha256()
    h.update(json.dumps(canvas, sort_keys=True).encode("utf-8"))
    bg_file = canvas.get("background_image", "")
    bg_path = resolve_background(bg_file)
    if bg_path and bg_path.exists():
        h.update(bg_path.read_bytes())
    return f"sha256:{h.hexdigest()}"


def validate(name: str) -> List[str]:
    problems: List[str] = []
    try:
        tpl = load(name)
    except TemplateNotFoundError as e:
        return [str(e)]

    if "canvas" not in tpl:
        problems.append("Missing 'canvas' block")
        return problems

    info = canvas_info(tpl)
    if info.width <= 0 or info.height <= 0:
        problems.append(f"Invalid canvas dimensions: {info.width}x{info.height}")
    if "native_dpi" not in tpl["canvas"]:
        problems.append(
            "canvas.native_dpi is absent — defaulting to 300 (§6.1.3). "
            "Physical sizing is unverified until this is set explicitly."
        )
    if info.background_image:
        bg = resolve_background(info.background_image)
        if bg is None:
            problems.append(
                f"Background image '{info.background_image}' could not be resolved. "
                "Clear canvas.background_image in the template JSON — backgrounds are "
                "now injected per theme at render time via resolve_theme_background()."
            )
    return problems
