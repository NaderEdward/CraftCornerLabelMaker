from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
NON_UI_DIRS = ["core", "regions", "shopify", "plotter", "report", "orchestrator"]


def _iter_py_files(dirs):
    for d in dirs:
        p = REPO_ROOT / d
        if p.exists():
            yield from p.rglob("*.py")


def test_no_pyqt6_outside_ui():
    offenders = []
    for f in _iter_py_files(NON_UI_DIRS):
        text = f.read_text(encoding="utf-8")
        if "PyQt6" in text:
            offenders.append(str(f))
    assert not offenders, f"PyQt6 imported (desktop UI removed): {offenders}"


def test_no_literal_25_4_outside_units():
    offenders = []
    for f in _iter_py_files(NON_UI_DIRS + ["."]):
        if f.name == "units.py":
            continue
        if "tests" in f.parts:
            continue
        text = f.read_text(encoding="utf-8")
        if "25.4" in text:
            offenders.append(str(f))
    assert not offenders, f"Literal 25.4 found outside core/units.py: {offenders}"


def test_no_convert_rgb_in_composite():
    composite_path = REPO_ROOT / "plotter" / "composite.py"
    text = composite_path.read_text(encoding="utf-8")
    assert 'convert("RGB")' not in text
    assert "convert('RGB')" not in text


def test_no_save_function_in_core_templates():
    templates_path = REPO_ROOT / "core" / "templates.py"
    text = templates_path.read_text(encoding="utf-8")
    assert "def save(" not in text
    assert "def write(" not in text


def test_core_templates_never_opens_files_for_writing():
    templates_path = REPO_ROOT / "core" / "templates.py"
    text = templates_path.read_text(encoding="utf-8")
    assert '"w"' not in text
    assert "'w'" not in text
    assert "json.dump(" not in text


def test_nothing_imports_labelgen():
    offenders = []
    for f in _iter_py_files(NON_UI_DIRS + ["ui", "."]):
        text = f.read_text(encoding="utf-8")
        for line in text.splitlines():
                stripped = line.strip()
                if not (stripped.startswith("import ") or stripped.startswith("from ")):
                    continue
                for marker in ("from LabelGen", "import LabelGen",
                               "from labelgen", "import labelgen"):
                    if stripped.startswith(marker):
                        offenders.append(f"{f}: {stripped}")
    assert not offenders, f"LabelGen imported: {offenders}"


def test_plotter_does_not_import_shopify():
    offenders = []
    for f in (REPO_ROOT / "plotter").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if "shopify" in stripped and (
                stripped.startswith("import ") or stripped.startswith("from ")
            ):
                offenders.append(f"{f}: {stripped}")
    assert not offenders, f"plotter/ imports shopify/: {offenders}"


def test_no_pyqt6_in_orchestrator():
    for f in (REPO_ROOT / "orchestrator").rglob("*.py"):
        assert "PyQt6" not in f.read_text(encoding="utf-8")


def test_settings_merge_policy_keeps_unknown_keys():
    text = (REPO_ROOT / "core" / "settings.py").read_text(encoding="utf-8")
    assert "data.update(saved)" in text
    assert "if k in _DEFAULTS" not in text


def test_access_token_not_in_settings_defaults():
    text = (REPO_ROOT / "core" / "settings.py").read_text(encoding="utf-8")
    assert "access_token" not in text.split("_DEFAULTS")[1].split("def load")[0]
