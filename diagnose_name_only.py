from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

OK   = "  [PASS]"
BAD  = "  [FAIL]"
WARN = "  [WARN]"
INFO = "       "

_failures = []


def stage(n, title):
    print(f"\n{'='*70}\n{n}. {title}\n{'='*70}")


def fail(msg):
    print(f"{BAD} {msg}")
    _failures.append(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name",  default="Nader Edward")
    ap.add_argument("--class", dest="klass", default="G9C")
    ap.add_argument("--theme", default="name cutout chromatix")
    ap.add_argument("--out",   default="diagnostic_output.png")
    args = ap.parse_args()

    print(f"Synthetic order:  name={args.name!r}  class={args.klass!r}  theme={args.theme!r}")

    stage(1, "theme_map.lookup()")
    try:
        from core.theme_map import lookup, NAME_ONLY
        ttype, reason = lookup(args.theme)
        if ttype == NAME_ONLY:
            print(f"{OK} theme resolves to NAME_ONLY")
        else:
            fail(f"theme '{args.theme}' → ({ttype!r}, {reason!r}), expected name_only. "
                 f"Add it to themes_list.json['name_only'] via the Themes tab.")
            return report()
    except Exception as e:
        fail(f"lookup raised: {e}"); traceback.print_exc(); return report()

    stage(2, "name_fonts registry")
    from core import name_fonts as nf
    entry = nf.get(args.theme)
    if not entry:
        fail(f"no registry entry for '{args.theme}' in data/name_fonts_config.json")
        return report()
    print(f"{OK} registry entry found")
    print(f"{INFO} font_file       = {entry.get('font_file')!r}")
    print(f"{INFO} class_font_file = {entry.get('class_font_file')!r}")
    print(f"{INFO} stroke_px       = {entry.get('stroke_px')}")

    fp = nf.font_path(args.theme)
    if fp and fp.exists():
        print(f"{OK} font file exists: {fp}")
    else:
        fail(f"font file missing. Expected in {nf.name_fonts_dir()}")

    cfp = nf.class_font_path(args.theme)
    if cfp and cfp.exists():
        print(f"{OK} class font exists: {cfp.name}")
    else:
        print(f"{WARN} class font NOT set/found — the class strip will be skipped. "
              f"Set class_font_file in the registry.")

    stage(3, "template_selector.select()")
    from core import template_selector as ts
    tname = ts.select(ttype, has_arabic=False,
                      has_class=bool(args.klass), has_school=False)
    if tname:
        print(f"{OK} template = {tname}")
    else:
        fail("template_selector returned None"); return report()

    stage(4, "template JSON + region sidecar")
    from core import templates as core_templates, paths as core_paths
    try:
        tpl = core_templates.load(tname)
        print(f"{OK} template loads, canvas={tpl['canvas']['width']}x{tpl['canvas']['height']}"
              f" @ {tpl['canvas'].get('native_dpi')}dpi")
    except Exception as e:
        fail(f"template load failed: {e}"); return report()

    problems = core_templates.validate(tname)
    if problems:
        print(f"{WARN} validate() problems: {problems}")
    else:
        print(f"{OK} validate() clean")

    from regions import model as region_model
    try:
        rs = region_model.load(tname)
        print(f"{OK} sidecar loads, {len(rs.regions)} regions")
    except Exception as e:
        fail(f"sidecar load failed: {e}"); return report()

    if not region_model.check_fingerprint(rs):
        print(f"{WARN} fingerprint mismatch — regions may not line up with artwork")
    else:
        print(f"{OK} fingerprint matches")

    stage(5, "name sanitisation")
    from core.chromatix_renderer import primary_name, sanitize
    prim  = primary_name(args.name)
    clean = sanitize(args.name,
                     entry.get("force_uppercase", True),
                     entry.get("strip_pattern"))
    print(f"{INFO} raw       = {args.name!r}")
    print(f"{INFO} primary   = {prim!r}")
    print(f"{INFO} printed   = {clean!r}")
    if clean:
        print(f"{OK} produces printable text")
    else:
        fail("sanitisation produced empty string — nothing would render")

    stage(6, "ChromatixRenderer availability")
    import shutil as _sh
    gd = Path("geckodriver.exe")
    gd2 = Path("geckodriver")
    if gd.exists() or gd2.exists():
        print(f"{OK} geckodriver found in app folder")
    elif _sh.which("geckodriver"):
        print(f"{OK} geckodriver found on PATH")
    else:
        print(f"{WARN} geckodriver not found — only needed for the optional "
              f"Firefox renderer; the offline SVG renderer is used instead")

    ff = None
    for c in [r"C:\Program Files\Mozilla Firefox\firefox.exe",
              r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"]:
        if Path(c).exists(): ff = c; break
    if ff or _sh.which("firefox"):
        print(f"{OK} Firefox found")
    else:
        print(f"{WARN} Firefox not found — optional; offline renderer is used instead")

    try:
        from plotter.render import NameOnlyRenderer
        r = NameOnlyRenderer(args.theme)
        if r.available:
            print(f"{OK} NameOnlyRenderer constructed and available")
        else:
            fail("NameOnlyRenderer constructed but .available is False "
                 "(font encode failed, or selenium/Pillow missing)")
            r = None
    except Exception as e:
        fail(f"NameOnlyRenderer construction raised: {e}")
        traceback.print_exc()
        r = None

    stage(7, "render one label")
    if r is None:
        fail("skipped — renderer unavailable")
    else:
        try:
            img = r._renderer.get(args.name, grade=args.klass,
                                  max_w=1235, max_h=560)
            bbox = img.getbbox()
            if bbox is None:
                fail("rendered image is COMPLETELY EMPTY (all transparent)")
            else:
                print(f"{OK} rendered {img.width}x{img.height}, content bbox={bbox}")
                out = Path(args.out)
                img.save(out)
                print(f"{OK} saved → {out.resolve()}")
        except Exception as e:
            fail(f"render raised: {e}")
            traceback.print_exc()

    return report()


def report():
    print(f"\n{'='*70}")
    if _failures:
        print(f"RESULT: {len(_failures)} FAILURE(S)\n")
        for i, f in enumerate(_failures, 1):
            print(f"  {i}. {f}")
        print("\nFix the first failure and re-run.")
        return 1
    print("RESULT: ALL CHECKS PASSED")
    print("A name-only order should render correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
