from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_SHEET_RE = re.compile(r"^sheet_(\d+)\.png(?:\.tmp)?$")


def _folder_max(output_folder: Path) -> int:
    max_n = 0
    if output_folder.exists():
        for p in output_folder.iterdir():
            m = _SHEET_RE.match(p.name)
            if m:
                max_n = max(max_n, int(m.group(1)))
    return max_n


def next_sheet_number(output_folder: Path, settings_counter: Optional[int] = None) -> int:
    folder_max = _folder_max(output_folder)
    base = max(folder_max, settings_counter or 0)
    return base + 1


def reserve_sheet_path(output_folder: Path, number: int) -> Path:
    output_folder.mkdir(parents=True, exist_ok=True)
    path = output_folder / f"sheet_{number:03d}.png"
    tmp = path.with_suffix(".png.tmp")
    tmp.touch(exist_ok=True)
    return path


def sheet_filename(number: int, paper_type: str = "regular") -> str:
    safe_type = paper_type.replace("_", "").lower()
    return f"sheet_{safe_type}_{number:03d}.png"


def next_sheet_number_for_type(output_folder, paper_type: str,
                                settings_counter: int = 0) -> int:
    import re
    safe = paper_type.replace("_","").lower()
    pat  = re.compile(rf"^sheet_{safe}_(\d+)\.png(?:\.tmp)?$")
    folder_max = 0
    from pathlib import Path
    d = Path(output_folder)
    if d.exists():
        for f in d.iterdir():
            m = pat.match(f.name)
            if m:
                folder_max = max(folder_max, int(m.group(1)))
    return max(folder_max, settings_counter) + 1
