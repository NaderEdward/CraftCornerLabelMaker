from __future__ import annotations

import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import argparse
import json
import sys
from pathlib import Path

from core import paths as core_paths
from core import settings as core_settings
from core import templates as core_templates
from orchestrator.pipeline import Pipeline, RunConfig


def _config_from_settings() -> RunConfig:
    cfg = core_settings.load()
    return RunConfig(
        shopify_domain=cfg["shopify_domain"],
        shopify_api_version=cfg["shopify_api_version"],
        in_progress_tag=cfg["in_progress_tag"],
        output_folder=core_paths.default_output_folder(),
        report_folder=core_paths.default_report_folder(),
        sheet_width_mm=cfg["sheet_width_mm"],
        sheet_height_mm=cfg["sheet_height_mm"],
        margin_mm={
            "t": cfg["margin_t_mm"], "b": cfg["margin_b_mm"],
            "l": cfg["margin_l_mm"], "r": cfg["margin_r_mm"],
        },
        inter_tile_gap_mm=cfg["inter_tile_gap_mm"],
        sheet_dpi=cfg["sheet_dpi"],
        fill_threshold=cfg["fill_threshold"],
        pack_strategy=cfg["pack_strategy"],
        label_tiles=cfg["label_tiles"],
        ironon_sheet_width_mm=cfg.get("ironon_sheet_width_mm", 215.9),
        ironon_sheet_height_mm=cfg.get("ironon_sheet_height_mm", 279.4),
        ironon_sheet_dpi=cfg.get("ironon_sheet_dpi", 300),
        ironon_fill_threshold=cfg.get("ironon_fill_threshold", 0.03),
        field_mapping=cfg["field_mapping"],
        enabler_map=cfg.get("enabler_map", {"OC": "Class", "OS": "school name", "OP": "text-5"}),
        last_sheet_number=cfg.get("last_sheet_number", 0),
    )


def cmd_validate_regions(args: argparse.Namespace) -> int:
    from regions import model as region_model
    from regions import validate as region_validate

    problems = core_templates.validate(args.template)
    for p in problems:
        print(f"[template] {p}")

    if not region_model.sidecar_exists(args.template):
        print(f"No region sidecar for '{args.template}' — nothing to validate.")
        return 1

    rs = region_model.load(args.template)
    region_problems = region_validate.validate_region_set(rs)
    for p in region_problems:
        print(f"[region] {p}")

    if not region_model.check_fingerprint(rs):
        print("[region] WARNING: template_fingerprint mismatch — "
              "artwork may have changed since these regions were drawn.")

    if args.render_preview:
        _render_region_previews(args.template, rs, Path(args.render_preview))

    return 1 if (problems or region_problems) else 0


def _render_region_previews(template_name: str, rs, out_dir: Path) -> None:
    from PIL import ImageDraw

    from core.render_engine import LabelConfig, LabelGenerator
    from core.units import px_to_mm

    out_dir.mkdir(parents=True, exist_ok=True)
    generator = LabelGenerator()
    cfg = LabelConfig(
        name="Sample Name", school="Sample School", grade="Grade 1",
        template_name=template_name,
    )
    img = generator.generate(cfg)
    for region in rs.regions:
        overlay = img.copy()
        draw = ImageDraw.Draw(overlay)
        draw.rectangle(region.rect.as_tuple(), outline=(255, 0, 0, 255), width=6)
        dpi = rs.template_canvas.get("native_dpi", 300)
        w_mm = px_to_mm(region.rect.w, dpi)
        h_mm = px_to_mm(region.rect.h, dpi)
        fname = f"{region.id}_{w_mm:.1f}x{h_mm:.1f}mm.png"
        overlay.save(out_dir / fname)
        print(f"Wrote {out_dir / fname}")


def cmd_stage(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir) if args.run_dir else None
    config = _config_from_settings()
    pipeline = Pipeline(config)
    if run_dir is not None:
        pipeline.run_dir = run_dir
        pipeline.run_id = run_dir.name

    stage = args.stage
    no_tag = getattr(args, "no_tag", False)
    try:
        if stage == "fetch":
            print(pipeline.fetch())
        elif stage == "transform":
            print(pipeline.transform())
        elif stage == "extract":
            print(pipeline.extract())
        elif stage == "pack":
            print(pipeline.pack())
        elif stage == "export":
            result = pipeline.export(force=args.force, no_tag=no_tag)
            print(json.dumps(result.__dict__, indent=2))
        elif stage == "run-all":
            result = pipeline.run_all(force=args.force, no_tag=no_tag)
            print(json.dumps(result.__dict__, indent=2))
    finally:
        pipeline.close()
    return 0


def cmd_list_templates(args: argparse.Namespace) -> int:
    from regions import model as region_model
    from regions import validate as region_validate

    names = core_templates.list_names()
    if not names:
        print("No templates found. Check the template_folder setting.")
        return 1

    for name in names:
        problems = core_templates.validate(name)
        blocking = [p for p in problems if "native_dpi" not in p]
        if not region_model.sidecar_exists(name):
            blocking.append("no region sidecar — not production-ready (§6.2)")
        else:
            rs = region_model.load(name)
            blocking += region_validate.validate_region_set(rs)
            if not region_model.check_fingerprint(rs):
                problems.append("template_fingerprint mismatch — re-check regions")

        status = "READY" if not blocking else "NOT READY"
        print(f"[{status}] {name}")
        for p in blocking:
            print(f"    ERROR: {p}")
        for p in problems:
            if p not in blocking:
                print(f"    warn:  {p}")

    for orphan in region_model.list_orphaned_sidecars():
        print(f"[ORPHAN] {orphan} — sidecar with no matching template")
    return 0


def cmd_propose_regions(args: argparse.Namespace) -> int:
    from PIL import Image

    from regions import model as region_model
    from regions.propose import propose_regions

    tpl = core_templates.load(args.template)
    info = core_templates.canvas_info(tpl)
    bg_path = core_templates.resolve_background(info.background_image)
    if bg_path is None:
        print(f"Cannot resolve background '{info.background_image}'. "
              f"See assets/README.md — proposal needs the artwork.")
        return 1

    with Image.open(bg_path) as im:
        rects = propose_regions(im.convert("RGBA"), min_area_px=args.min_area)

    if not rects:
        print("No candidate regions found. The artwork may not have "
              "transparent gutters between products; author by hand.")
        return 1

    rects.sort(key=lambda r: (r.y, r.x))
    region_set = region_model.new_region_set_for_template(args.template)
    region_set.regions = [
        region_model.ProductRegion(
            id=f"region_{i + 1:02d}",
            label=f"UNNAMED REGION {i + 1} — rename me",
            rect=r,
            sku_match=[],
            gap_mm=0.0,
            allow_rotate=False,
            notes="AUTO-PROPOSED DRAFT. Verify against the artwork before use.",
        )
        for i, r in enumerate(rects)
    ]

    out = args.out or region_model.paths.region_sidecar_path(
        args.template + ".draft"
    )
    from pathlib import Path as _P
    out = _P(out)
    out.write_text(
        json.dumps(region_set.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Proposed {len(rects)} draft region(s) -> {out}")
    print("REVIEW REQUIRED: name each region, set sku_match, then move it "
          "to assets/Cut Zones and Templates/Regions/<template>.regions.json and run validate-regions.")
    return 0


def cmd_prune_runs(args: argparse.Namespace) -> int:
    from orchestrator.retention import prune_runs

    cfg = core_settings.load()
    days = args.days if args.days is not None else cfg.get("run_retention_days", 30)
    removed = prune_runs(core_paths.runs_dir(), days, dry_run=args.dry_run)
    verb = "Would prune" if args.dry_run else "Pruned"
    print(f"{verb} {len(removed)} run(s): {removed or '-'}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from core import paths as p
    from plotter.render import preflight

    print(f"App root:        {p.app_root()}")
    print(f"Template folder: {p.template_folder()}")
    print(f"Fonts folder:    {p.bundled_fonts_dir()}")
    print(f"Output folder:   {p.default_output_folder()}")
    print(f"Report folder:   {p.default_report_folder()}")
    print()

    failures = 0
    try:
        preflight()
        print("[ok]   bundled fonts present")
    except Exception as e:
        print(f"[FAIL] fonts: {e}")
        failures += 1

    names = core_templates.list_names()
    print(f"[info] {len(names)} template(s) discovered")
    for name in names:
        info = core_templates.canvas_info(core_templates.load(name))
        bg = core_templates.resolve_background(info.background_image)
        if bg:
            print(f"  [ok]   {name}: canvas {info.width}x{info.height} "
                  f"@{info.native_dpi}dpi, background resolved")
        elif info.background_image:
            print(f"  [warn] {name}: canvas {info.width}x{info.height} "
                  f"@{info.native_dpi}dpi, background not on disk "
                  f"('{info.background_image}') — renders without it")
        else:
            print(f"  [ok]   {name}: canvas {info.width}x{info.height} "
                  f"@{info.native_dpi}dpi, no background (zones only)")

    from core.render_engine import ARABIC_SUPPORT
    if ARABIC_SUPPORT:
        print("[ok]   Arabic support available")
    else:
        print("[warn] Arabic support NOT installed — batches containing "
              "Arabic names will be refused (correctly)")

    print()
    print("FAILURES:", failures)
    return 1 if failures else 0


def cmd_export_review(args: argparse.Namespace) -> int:
    from shopify.review import export_review

    run_dir = Path(args.run_dir)
    records_path = run_dir / "records.json"
    if not records_path.exists():
        print(f"No records.json in {run_dir}. Run 'transform' first.")
        return 1

    out = Path(args.out) if args.out else run_dir / "orders_review.xlsx"
    export_review(records_path, out)
    print(f"Wrote {out}")
    print(f"Edit it, then run:  python -m cli import-review --run-dir {run_dir}")
    return 0


def cmd_import_review(args: argparse.Namespace) -> int:
    from shopify.review import apply_review, diff_review

    run_dir = Path(args.run_dir)
    records_path = run_dir / "records.json"
    xlsx_path = Path(args.xlsx) if args.xlsx else run_dir / "orders_review.xlsx"

    if not records_path.exists():
        print(f"No records.json in {run_dir}.")
        return 1
    if not xlsx_path.exists():
        print(f"No review file found at {xlsx_path}. Run export-review first.")
        return 1

    try:
        diff, new_records = diff_review(records_path, xlsx_path)
    except Exception as e:
        print(f"Error reading review file: {e}")
        return 1

    print(diff.summary())

    if not diff.is_clean:
        print("\nValidation errors above must be fixed before importing.")
        return 1

    if not diff.has_changes:
        print("\nNo changes — records.json unchanged.")
        return 0

    if not args.yes:
        answer = input("\nApply these changes to records.json? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted. records.json unchanged.")
            return 0

    apply_review(new_records, records_path)
    print("\nApplied. records.json updated.")
    print(f"Next:  python -m cli extract --run-dir {run_dir}")
    print(f"       python -m cli pack    --run-dir {run_dir}")
    print(f"       python -m cli export  --run-dir {run_dir} --no-tag")
    return 0


def cmd_list_skus(args: argparse.Namespace) -> int:
    from shopify.skus import collect_skus, write_skus_xlsx
    from shopify.transform import build_sku_map

    run_dir = Path(args.run_dir)
    orders_raw = run_dir / "orders_raw.json"
    if not orders_raw.exists():
        print(f"No orders_raw.json in {run_dir}. Run 'fetch' first.")
        return 1

    rows = collect_skus(orders_raw)

    sku_map = build_sku_map(core_templates.list_names())

    out = run_dir / "skus.xlsx"
    write_skus_xlsx(rows, out, sku_map=sku_map)

    print(f"\n{'SKU':<30} {'Title':<40} {'Qty':>6}  Match")
    print("-" * 90)
    for r in rows:
        from shopify.skus import match_status
        status = match_status(sku_map, r["sku"], r["title"])
        print(f"{r['sku']:<30} {r['title']:<40} {r['total_qty']:>6}  {status}")

    print(f"\nFull table with match status: {out}")
    unmatched = sum(
        1 for r in rows
        if "no match" in (lambda: __import__("shopify.skus", fromlist=["match_status"])
                         .match_status(sku_map, r["sku"], r["title"]))()
    )
    if unmatched:
        print(f"\n{unmatched} SKU(s) have no region match — see red rows in {out.name}")
    return 0


def cmd_render_template(args: argparse.Namespace) -> int:
    from plotter.render_template import render_template

    out = Path(args.out) if args.out else Path(f"{args.template}_reference.png")

    sample = {}
    if args.name:        sample["name"]         = args.name
    if args.arabic:      sample["name_arabic"]  = args.arabic
    if args.school:      sample["school"]        = args.school
    if args.grade:       sample["grade"]         = args.grade
    if args.order:       sample["order_number"]  = args.order

    grid = 0 if args.no_grid else int(args.grid or 100)

    try:
        img = render_template(args.template, out, sample=sample,
                              grid_spacing_px=grid, annotate=(grid > 0))
    except Exception as e:
        print(f"Render failed: {e}")
        return 1

    w, h = img.size
    print(f"Canvas: {w} × {h} px")
    print(f"Wrote:  {out}")
    print()
    print("Open this file in any image editor that shows cursor pixel position")
    print("(GIMP: bottom bar, Photoshop: Info panel, Windows Photos: not suitable).")
    print()
    print("For each product area on the sheet, note x, y, w, h in pixels and")
    print("write them into assets/Cut Zones and Templates/Regions/<template>.regions.json.")
    print("Then run: python -m cli validate-regions --template <name> --render-preview out/")
    return 0


def cmd_untag(args: argparse.Namespace) -> int:
    from orchestrator.journal import Journal
    from shopify.client import ShopifyClient, ShopifyAPIError

    run_dir = Path(args.run_dir)
    journal = Journal(run_dir, run_dir.name)
    tagged = journal.tagged_order_ids()

    if not tagged:
        print("No orders were tagged in this run (nothing to undo).")
        return 0

    print(f"Orders tagged in this run: {tagged}")

    if not args.yes:
        answer = input(
            f"Remove '{args.tag}' from {len(tagged)} order(s)? [y/N] "
        ).strip().lower()
        if answer != "y":
            print("Aborted.")
            return 0

    cfg = core_settings.load()
    from shopify.client import credentials_configured
    if not credentials_configured():
        print("No Shopify credentials found. Configure them in Settings first.")
        return 1

    client = ShopifyClient(cfg["shopify_domain"],
                           cfg.get("shopify_api_version", "2025-04"))

    failed = []
    for order_id in tagged:
        try:
            resp = client._request_with_retry(
                "GET",
                f"https://{client.shop_domain}/admin/api/{client.api_version}"
                f"/orders/{order_id}.json",
                params={"fields": "id,tags"},
            )
            if resp.status_code != 200:
                failed.append(order_id)
                continue
            current_tags = resp.json()["order"].get("tags", "") or ""
            new_tags = ", ".join(
                t.strip() for t in current_tags.split(",")
                if t.strip().lower() != args.tag.strip().lower()
            )
            put_resp = client._request_with_retry(
                "PUT",
                f"https://{client.shop_domain}/admin/api/{client.api_version}"
                f"/orders/{order_id}.json",
                json={"order": {"id": int(order_id), "tags": new_tags}},
            )
            if put_resp.status_code == 200:
                print(f"  untagged {order_id}")
            else:
                failed.append(order_id)
        except ShopifyAPIError as e:
            print(f"  failed {order_id}: {e}")
            failed.append(order_id)

    if failed:
        print(f"\nFailed to untag {len(failed)}: {failed}")
        return 1
    print(f"\nDone. {len(tagged)} order(s) untagged — they will reappear in the next fetch.")
    return 0


def cmd_rebuild_report(args: argparse.Namespace) -> int:
    from report import excel as report_excel

    csv_path = core_paths.default_report_folder() / "sheets_report.csv"
    xlsx_path = core_paths.default_report_folder() / "sheets_report.xlsx"
    report_excel.rebuild_from_csv(csv_path, xlsx_path)
    print(f"Rebuilt {xlsx_path} from {csv_path}")
    return 0


def cmd_reset_sheet_number(args: argparse.Namespace) -> int:
    cfg = core_settings.load()
    new_val = max(0, args.number)
    old_val = cfg.get("last_sheet_number", 0)
    cfg["last_sheet_number"] = new_val
    core_settings.save(cfg)
    next_n = new_val + 1
    print(f"Sheet counter reset: {old_val} → {new_val}. Next sheet will be #{next_n:03d}.")
    return 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    vr = sub.add_parser("validate-regions", help="Validate a template's region sidecar")
    vr.add_argument("--template", required=True)
    vr.add_argument("--render-preview", help="Directory to write crop-boundary preview PNGs")
    vr.set_defaults(func=cmd_validate_regions)

    for stage in ("fetch", "transform", "extract", "pack", "export", "run-all"):
        sp = sub.add_parser(stage, help=f"Run the {stage} stage")
        sp.add_argument("--run-dir", help="Existing run directory to operate on")
        sp.add_argument("--force", action="store_true",
                        help="Force-export (bypass fill threshold)")
        if stage in ("export", "run-all"):
            sp.add_argument("--no-tag", action="store_true",
                            help="Produce sheets + report but do NOT tag orders in Shopify. "
                                 "Use for all test runs.")
        sp.set_defaults(func=cmd_stage, stage=stage)

    rr = sub.add_parser("rebuild-report", help="Regenerate sheets_report.xlsx from the CSV")
    rr.set_defaults(func=cmd_rebuild_report)

    er = sub.add_parser("export-review",
                        help="Export records.json to editable orders_review.xlsx (SAFE)")
    er.add_argument("--run-dir", required=True)
    er.add_argument("--out", help="Override output path")
    er.set_defaults(func=cmd_export_review)

    ir = sub.add_parser("import-review",
                        help="Import edited orders_review.xlsx back into records.json")
    ir.add_argument("--run-dir", required=True)
    ir.add_argument("--xlsx", help="Override input path")
    ir.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    ir.set_defaults(func=cmd_import_review)

    ls = sub.add_parser("list-skus",
                        help="List every SKU/title in orders_raw.json (SAFE)")
    ls.add_argument("--run-dir", required=True)
    ls.set_defaults(func=cmd_list_skus)

    rt = sub.add_parser("render-template",
                        help="Render a value pack with sample text + pixel grid")
    rt.add_argument("--template", required=True)
    rt.add_argument("--out", help="Output PNG path")
    rt.add_argument("--name",   help="Sample student name")
    rt.add_argument("--arabic", help="Sample Arabic name")
    rt.add_argument("--school", help="Sample school")
    rt.add_argument("--grade",  help="Sample grade")
    rt.add_argument("--order",  help="Sample order number")
    rt.add_argument("--grid",   help="Grid spacing in pixels (default 100)")
    rt.add_argument("--no-grid", action="store_true", help="Disable grid overlay")
    rt.set_defaults(func=cmd_render_template)

    ut = sub.add_parser("untag",
                        help="Remove in-progress tag from a run's orders (undo)")
    ut.add_argument("--run-dir", required=True)
    ut.add_argument("--tag", default="in-progress")
    ut.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    ut.set_defaults(func=cmd_untag)

    lt = sub.add_parser("list-templates", help="Show templates and readiness")
    lt.set_defaults(func=cmd_list_templates)

    pr = sub.add_parser("propose-regions",
                        help="Draft regions from the background alpha (review required)")
    pr.add_argument("--template", required=True)
    pr.add_argument("--out", help="Where to write the draft sidecar")
    pr.add_argument("--min-area", type=int, default=2000,
                    help="Ignore components smaller than this many pixels")
    pr.set_defaults(func=cmd_propose_regions)

    pu = sub.add_parser("prune-runs", help="Delete old completed run directories")
    pu.add_argument("--days", type=int, help="Override run_retention_days")
    pu.add_argument("--dry-run", action="store_true")
    pu.set_defaults(func=cmd_prune_runs)

    dr = sub.add_parser("doctor", help="Check the installation; no output produced")
    dr.set_defaults(func=cmd_doctor)

    rsn = sub.add_parser("reset-sheet-number",
                         help="Reset the sheet counter to any value (0 = restart from #001)")
    rsn.add_argument("--number", type=int, default=0,
                     help="Set last_sheet_number to this value (next sheet = this + 1)")
    rsn.set_defaults(func=cmd_reset_sheet_number)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
