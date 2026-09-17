from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

APP_DIR_NAME = ".label_generator"


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def app_root() -> Path:
    return _app_root()


def user_home_app_dir() -> Path:
    d = Path.home() / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def craftcorner_data_dir() -> Path:
    d = Path.home() / ".craftcorner_labelmaker"
    d.mkdir(parents=True, exist_ok=True)
    return d


def runs_dir() -> Path:
    d = craftcorner_data_dir() / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_run_id() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H-%M-%S")


def run_dir(run_id: str) -> Path:
    d = runs_dir() / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "tiles").mkdir(exist_ok=True)
    (d / "sheets").mkdir(exist_ok=True)
    return d


def cut_zones_and_templates_dir() -> Path:
    return bundled_assets_dir() / "Cut Zones and Templates"


def cut_zones_dir() -> Path:
    return cut_zones_and_templates_dir() / "Cut Zones"


def regions_dir() -> Path:
    d = cut_zones_and_templates_dir() / "Regions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def region_sidecar_path(template_name: str) -> Path:
    return regions_dir() / f"{template_name}.regions.json"


def bundled_assets_dir() -> Path:
    return _app_root() / "assets"


def bundled_fonts_dir() -> Path:
    return bundled_assets_dir() / "fonts"


def bundled_templates_assets_dir() -> Path:
    return cut_zones_and_templates_dir() / "Templates"


def template_folder() -> Path:
    from core import settings

    cfg = settings.load()
    configured = cfg.get("template_folder")
    if configured:
        p = Path(configured)
        if p.exists():
            return p
    return bundled_templates_assets_dir()


def backgrounds_root() -> Optional[Path]:
    from core import settings
    import platform

    cfg = settings.load()
    configured = cfg.get("backgrounds_root", "")
    if configured:
        p = Path(configured)
        if p.exists():
            return p

    candidates = []
    if platform.system() == "Windows":
        import string
        for letter in string.ascii_uppercase:
            candidates.append(Path(f"{letter}:\\All themes"))
    candidates.append(Path.home() / "All themes")

    for c in candidates:
        if c.exists():
            return c
    return None


def backgrounds_fallback_dir() -> Path:
    return bundled_assets_dir() / "backgrounds"


def reports_dir() -> Path:
    d = _app_root() / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_output_folder() -> Path:
    from core import settings

    cfg = settings.load()
    configured = cfg.get("output_folder")
    if configured:
        return Path(configured)
    d = craftcorner_data_dir() / "sheets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_report_folder() -> Path:
    from core import settings

    cfg = settings.load()
    configured = cfg.get("report_folder")
    if configured:
        d = Path(configured)
        d.mkdir(parents=True, exist_ok=True)
        return d
    sheets = default_output_folder()
    d = sheets.parent / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d
