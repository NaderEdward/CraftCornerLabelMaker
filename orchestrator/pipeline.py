from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core import logging_setup
from core import paths as core_paths
from core import settings as core_settings
from core.units import mm_to_px
from orchestrator.journal import Journal
from plotter import composite, pack as pack_mod, sheetnum, tiles as tiles_mod
from plotter.pack import PAPER_IRON_ON
from regions.model import PAPER_REGULAR
from plotter.render import (
    NameOnlyRenderer, ValuePackRenderer, assert_arabic_support,
    assert_name_font_support, preflight,
)
from report import excel as report_excel
from report import viewer as report_viewer
from shopify import ingest as shopify_ingest
from shopify import transform as shopify_transform
from shopify import adapter as shopify_adapter
from shopify import writeback as shopify_writeback
from shopify.client import ShopifyClient, credentials_configured

ProgressCB = Callable[[str, int, int], None]

log = logging_setup.get_logger()

IRONON_LETTER_WIDTH_MM = 215.9
IRONON_LETTER_HEIGHT_MM = 279.4
IRONON_EDGE_INSET_MM = 0.1


@dataclass
class RunConfig:
    shopify_domain: str
    shopify_api_version: str
    in_progress_tag: str
    output_folder: Path
    report_folder: Path
    sheet_width_mm: float
    sheet_height_mm: float
    margin_mm: Dict[str, float]
    inter_tile_gap_mm: float
    sheet_dpi: int
    fill_threshold: float
    pack_strategy: str
    label_tiles: bool
    ironon_sheet_width_mm: float
    ironon_sheet_height_mm: float
    ironon_sheet_dpi: int
    ironon_fill_threshold: float
    field_mapping: Dict[str, List[str]]
    enabler_map: Dict[str, str]
    last_sheet_number: int = 0


@dataclass
class ExportResult:
    exported_sheet_numbers: List[int] = field(default_factory=list)
    held_back_orders: List[str] = field(default_factory=list)
    oversize_orders: List[str] = field(default_factory=list)
    tagged_order_ids: List[str] = field(default_factory=list)
    untagged_order_ids: List[str] = field(default_factory=list)
    partially_done_order_ids: List[str] = field(default_factory=list)


def _print_records_summary(records: dict) -> None:
    recs = records.get("records", [])
    warns = records.get("warnings", [])

    ok   = [r for r in recs if not r.get("blocked")]
    held = [r for r in recs if r.get("blocked")]

    print(f"\n{'─'*60}")
    print(f"  Orders parsed: {len(recs)} record(s)  "
          f"✓ {len(ok)} ready   ✗ {len(held)} blocked")
    if warns:
        print(f"  Warnings:  {len(warns)}")
    print(f"{'─'*60}")

    for r in recs:
        blocked = r.get("blocked", False)
        icon = "✗" if blocked else "✓"
        name  = r.get("student_name") or "(no name)"
        ar    = r.get("student_name_arabic", "")
        grade = r.get("grade", "")
        school= r.get("school", "")
        tpl   = r.get("template_name", "")
        items = r.get("items", [])
        order = r.get("order_number", "")

        name_str = f"{name}"
        if ar:
            name_str += f" / {ar}"

        meta = "  ".join(filter(None, [grade, school, tpl]))
        tiles_str = ", ".join(
            f"{it['region_id']}×{it['qty']}" for it in items
        )

        print(f"  {icon} [{order}]  {name_str}")
        if meta:
            print(f"       {meta}")
        if tiles_str:
            print(f"       tiles: {tiles_str}")

        crit_flags = [f for f in r.get("flags", []) if f.get("severity") == "critical"]
        for f in crit_flags:
            print(f"       ⚠  {f['kind']}: {f['detail']}")

    if warns:
        print(f"\n  Transform warnings:")
        for w in warns:
            print(f"    · [{w.get('order_number','')}] {w.get('kind','')}: {w.get('detail','')}")

    print(f"{'─'*60}\n")


class Pipeline:
    def __init__(self, config: RunConfig, on_progress: Optional[ProgressCB] = None):
        self.config = config
        self.on_progress = on_progress or (lambda stage, cur, total: None)

        self.run_id = core_paths.new_run_id()
        self.run_dir = core_paths.run_dir(self.run_id)
        self.journal = Journal(self.run_dir, self.run_id)

        logging_setup.configure(self.run_dir)

        snapshot = {k: (str(v) if isinstance(v, Path) else v)
                    for k, v in asdict(config).items()}
        snapshot["run_id"] = self.run_id
        with open(self.run_dir / "run.json", "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        log.info("Run %s started", self.run_id)

        self._renderer = ValuePackRenderer(strict=True)
        self._name_only_renderer: "NameOnlyRenderer | None" = None

    def _progress(self, stage: str, current: int, total: int) -> None:
        self.on_progress(stage, current, total)


    def fetch(self) -> Path:
        client = ShopifyClient(self.config.shopify_domain,
                               self.config.shopify_api_version)
        out_path = self.run_dir / "orders_raw.json"
        self._progress("fetch", 0, 1)
        shopify_ingest.fetch_orders_raw(client, out_path)
        self._progress("fetch", 1, 1)
        return out_path


    def transform(self) -> Path:
        orders_raw_path = self.run_dir / "orders_raw.json"
        orders_raw = shopify_ingest.load_orders_raw(orders_raw_path)
        self._progress("transform", 0, 1)

        records = shopify_adapter.adapt(
            orders_raw,
            self.run_dir,
        )
        out_path = self.run_dir / "records.json"
        shopify_transform.write_records(records, out_path)
        _print_records_summary(records)
        self._progress("transform", 1, 1)
        return out_path


    def extract(self) -> Path:
        records = shopify_transform.load_records(self.run_dir / "records.json")

        templates_used = sorted({r["template_name"] for r in records["records"]})
        preflight(templates_used)

        if any(r.get("student_name_arabic") for r in records["records"]):
            assert_arabic_support()

        usable_w_mm = (self.config.sheet_width_mm
                      - self.config.margin_mm["l"] - self.config.margin_mm["r"])
        usable_h_mm = (self.config.sheet_height_mm
                      - self.config.margin_mm["t"] - self.config.margin_mm["b"])

        warnings: List[str] = []

        assert_name_font_support(records["records"])

        name_cutout_recs = [r for r in records["records"]
                            if r.get("template_name", "").startswith("name_cutout")
                            and not r.get("blocked")]
        if name_cutout_recs:
            from core.chromatix_renderer import ChromatixRenderer
            by_slug: Dict[str, List[str]] = {}
            for r in name_cutout_recs:
                slug = (r.get("custom_fields", {}).get("theme", "") or "").strip().lower()
                for key in ("full_name", "first_name", "nickname", "initials"):
                    val = (r.get(key) or "").strip()
                    if val:
                        by_slug.setdefault(slug, []).append(val)
                if r.get("student_name"):
                    by_slug.setdefault(slug, []).append(r["student_name"])
            for slug, names in by_slug.items():
                ChromatixRenderer.shared(slug).warm(sorted(set(names)))
                log.info("name_cutout: warmed %d names for slug '%s'",
                         len(set(names)), slug)

        name_only_recs = [r for r in records["records"]
                          if r.get("template_name", "").startswith("name_only")
                          and not r.get("blocked")]
        if name_only_recs:
            from core import name_fonts as nf
            setup_error: str = ""
            for slug in nf.all_slugs():
                slug_recs = [r for r in name_only_recs
                             if r.get("custom_fields", {}).get("theme", "").strip().lower() == slug]
                if not slug_recs:
                    continue
                if self._name_only_renderer is None:
                    try:
                        self._name_only_renderer = NameOnlyRenderer(slug)
                        log.info("NameOnlyRenderer created for slug '%s'", slug)
                    except Exception as exc:
                        setup_error = str(exc)
                        log.error("Failed to create NameOnlyRenderer: %s", exc)
                if self._name_only_renderer and self._name_only_renderer.available:
                    self._name_only_renderer.warm(slug_recs)
                elif not setup_error:
                    setup_error = ("Firefox/geckodriver not available, or the font "
                                   "file is missing from assets/name_fonts/")

            if self._name_only_renderer is None or not self._name_only_renderer.available:
                for r in name_only_recs:
                    r["blocked"] = True
                    r.setdefault("flags", []).append({
                        "kind":   "NAME_ONLY_RENDERER_UNAVAILABLE",
                        "detail": (f"Cannot render name-only labels: {setup_error}. "
                                   f"Check: (1) geckodriver.exe is on PATH or in the "
                                   f"app folder, (2) Firefox is installed, "
                                   f"(3) the font file exists in assets/name_fonts/."),
                        "field":  "theme",
                    })
                msg = (f"{len(name_only_recs)} name-only record(s) blocked — "
                       f"renderer unavailable: {setup_error}")
                log.error(msg)
                warnings.append(msg)

        self._progress("extract", 0, len(records["records"]) or 1)
        tiles_mod.extract_tiles(
            records["records"], self.run_dir / "tiles",
            target_dpi=self.config.sheet_dpi,
            sheet_usable_w_mm=usable_w_mm, sheet_usable_h_mm=usable_h_mm,
            global_gap_mm=self.config.inter_tile_gap_mm,
            renderer=self._renderer,
            name_only_renderer=self._name_only_renderer,
            ironon_sheet_width_mm=IRONON_LETTER_WIDTH_MM,
            ironon_sheet_height_mm=IRONON_LETTER_HEIGHT_MM,
            ironon_edge_inset_mm=IRONON_EDGE_INSET_MM,
            on_warning=warnings.append,
        )
        self._progress("extract", len(records["records"]) or 1, len(records["records"]) or 1)

        for w in warnings:
            log.warning("extract: %s", w)
        if warnings:
            (self.run_dir / "extract_warnings.json").write_text(
                json.dumps(warnings, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        return self.run_dir / "tiles" / "manifest.json"


    def pack(self) -> Path:
        with open(self.run_dir / "tiles" / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        self._progress("pack", 0, 1)
        plan = pack_mod.pack(
            manifest,
            sheet_width_mm=self.config.sheet_width_mm,
            sheet_height_mm=self.config.sheet_height_mm,
            margin_mm=self.config.margin_mm,
            dpi=self.config.sheet_dpi,
            fill_threshold=self.config.fill_threshold,
            strategy=self.config.pack_strategy,
            ironon_sheet_width_mm=IRONON_LETTER_WIDTH_MM,
            ironon_sheet_height_mm=IRONON_LETTER_HEIGHT_MM,
            ironon_sheet_dpi=self.config.ironon_sheet_dpi,
            ironon_fill_threshold=self.config.ironon_fill_threshold,
        )
        plan["sheet_config"]["inter_tile_gap_mm"] = self.config.inter_tile_gap_mm
        out_path = self.run_dir / "packing_plan.json"
        pack_mod.write_plan(plan, out_path)
        self._progress("pack", 1, 1)
        return out_path


    def export(self, force: bool = False, no_tag: bool = False) -> ExportResult:
        with open(self.run_dir / "packing_plan.json", encoding="utf-8") as f:
            plan = json.load(f)
        with open(self.run_dir / "tiles" / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        records = shopify_transform.load_records(self.run_dir / "records.json")
        records_by_key = report_excel.index_records(records["records"])

        exportable = pack_mod.exportable_sheets(plan, force=force)
        if not exportable:
            self.journal.record(
                "export_complete",
                tagging_skipped=True,
                held_back_orders=plan["held_back_orders"],
                exported_count=0,
            )
            log.info(
                "No sheets reached the fill threshold (%.0f%%). "
                "%d order(s) held back. Use force-export to push through.",
                plan["fill_threshold"] * 100,
                len(plan["held_back_orders"]),
            )
            return ExportResult(
                held_back_orders=plan["held_back_orders"],
                oversize_orders=plan["oversize_orders"],
            )

        order_of_tile = {t["tile_id"]: t["order_id"] for t in manifest["tiles"]}
        order_ids_on_exportable = sorted({
            order_of_tile[p["tile_id"]]
            for sheet in exportable
            for p in sheet["placements"]
        })

        order_number_of_id = {t["order_id"]: t["order_number"] for t in manifest["tiles"]}
        order_numbers_on_exportable = {
            order_number_of_id.get(oid, oid) for oid in order_ids_on_exportable
        }
        held_or_oversize_numbers = set(
            plan["held_back_orders"] + plan["oversize_orders"]
        )
        order_id_of_number = {v: k for k, v in order_number_of_id.items()}
        partially_done_ids = sorted({
            order_id_of_number[n]
            for n in order_numbers_on_exportable
            if n in held_or_oversize_numbers and n in order_id_of_number
        })
        fully_done_ids = sorted(
            oid for oid in order_ids_on_exportable
            if order_number_of_id.get(oid, oid) not in held_or_oversize_numbers
        )

        for _stale in self.config.output_folder.glob("*.tmp"):
            try:
                _stale.unlink()
                log.info("Removed stale temp file: %s", _stale.name)
            except OSError:
                log.warning("Could not remove stale temp file: %s", _stale.name)

        paper_counters: Dict[str, int] = {}
        sheet_numbers: List[int] = []
        sheet_filenames: List[str] = []

        for sheet in exportable:
            pt = sheet.get("paper_type", PAPER_REGULAR)
            if pt not in paper_counters:
                paper_counters[pt] = sheetnum.next_sheet_number_for_type(
                    self.config.output_folder, pt, self.config.last_sheet_number)
            n = paper_counters[pt]
            paper_counters[pt] = n + 1
            sheet_numbers.append(n)
            sheet_filenames.append(sheetnum.sheet_filename(n, pt))

        self.journal.record("export_begin", sheet_numbers=sheet_numbers,
                           order_ids=order_ids_on_exportable)

        reg_width_px  = mm_to_px(self.config.sheet_width_mm,         self.config.sheet_dpi)
        reg_height_px = mm_to_px(self.config.sheet_height_mm,        self.config.sheet_dpi)
        ion_width_px  = mm_to_px(IRONON_LETTER_WIDTH_MM,  self.config.ironon_sheet_dpi)
        ion_height_px = mm_to_px(IRONON_LETTER_HEIGHT_MM, self.config.ironon_sheet_dpi)

        exported_numbers: List[int] = []
        report_rows = []
        export_date = self.run_id

        for sheet, number, filename in zip(exportable, sheet_numbers, sheet_filenames):
            out_path = self.config.output_folder / filename
            is_ironon = sheet.get("paper_type") == PAPER_IRON_ON
            canvas_dpi = sheet.get("canvas_dpi", self.config.ironon_sheet_dpi if is_ironon else self.config.sheet_dpi)
            tile_dpi   = manifest.get("dpi", self.config.sheet_dpi)
            w_px = ion_width_px  if is_ironon else reg_width_px
            h_px = ion_height_px if is_ironon else reg_height_px
            composite.composite_sheet(
                sheet, manifest, self.run_dir / "tiles", w_px, h_px,
                out_path, canvas_dpi,
                tile_dpi=tile_dpi,
                label_tiles=self.config.label_tiles,
                sheet_number=None if is_ironon else number,
                white_background=is_ironon,
            )

            self.journal.record("sheet_written", sheet_number=number,
                               paper_type=sheet.get("paper_type", PAPER_REGULAR))
            exported_numbers.append(number)

            report_rows.extend(report_excel.build_report_rows(
                number, export_date, sheet, manifest, records_by_key, self.run_id
            ))

        try:
            report_excel.append_report(
                self.config.report_folder / "sheets_report.xlsx",
                report_rows,
            )
        except report_excel.ReportFileLockedError:
            log.warning(
                "sheets_report.xlsx is open in Excel — report rows not written. "
                "Close Excel and use File > Re-export to retry."
            )
        self.journal.record("report_written")

        self.journal.record("tag_begin",
                            order_ids_done=fully_done_ids,
                            order_ids_partial=partially_done_ids)
        tagged: List[str] = []

        shopify_writeback.write_tag_commands_file(
            order_ids_done=fully_done_ids,
            order_ids_flagged=partially_done_ids,
            out_path=self.run_dir / "tag_commands.txt",
        )
        log.info(
            "Tagging: %d fully done → AI-Done, %d partially done → AI-Flagged",
            len(fully_done_ids), len(partially_done_ids),
        )

        if no_tag:
            log.info("Tagging skipped (--no-tag). See %s", self.run_dir / "tag_commands.txt")
        elif not credentials_configured():
            log.warning(
                "Shopify credentials not found — tagging SKIPPED. "
                "Open Settings and save your credentials. "
                "%d order(s) listed in tag_commands.txt for manual tagging.",
                len(order_ids_on_exportable),
            )
        else:
            client = ShopifyClient(self.config.shopify_domain,
                                   self.config.shopify_api_version)
            log.info("Tagging %d orders AI-Done, %d AI-Flagged",
                     len(fully_done_ids), len(partially_done_ids))
            tagged = shopify_writeback.tag_orders_done(
                client, fully_done_ids,
                on_each_success=lambda oid: self.journal.record("tag_ok", order_id=oid),
                on_each_failure=lambda oid, e: log.warning(
                    "Could not tag order %s as AI-Done: %s", oid, e),
            )
            failed_tag = [oid for oid in fully_done_ids if oid not in tagged]
            to_flag = sorted(set(partially_done_ids) | set(failed_tag))
            if to_flag:
                shopify_writeback.tag_orders_flagged(client, to_flag)

        try:
            cfg = core_settings.load()
            cfg["last_sheet_number"] = max(
                cfg.get("last_sheet_number", 0), *exported_numbers
            ) if exported_numbers else cfg.get("last_sheet_number", 0)
            core_settings.save(cfg)
        except Exception:
            log.warning("Could not persist last_sheet_number", exc_info=True)

        self.journal.record("export_complete", tagging_skipped=no_tag)

        try:
            report_viewer.generate_report(
                xlsx_path=self.config.report_folder / "sheets_report.xlsx",
                latest_plan=plan,
                tile_schematics=report_viewer.schematics_from_plan(
                    {"sheets": exportable}, manifest, exported_numbers,
                    self.config.sheet_dpi,
                ),
                sheet_mm={"w": self.config.sheet_width_mm,
                          "h": self.config.sheet_height_mm},
            )
        except Exception:
            log.warning("Report viewer regeneration failed", exc_info=True)

        return ExportResult(
            exported_sheet_numbers=exported_numbers,
            held_back_orders=plan["held_back_orders"],
            oversize_orders=plan["oversize_orders"],
            tagged_order_ids=tagged,
            untagged_order_ids=[oid for oid in fully_done_ids if oid not in tagged],
            partially_done_order_ids=partially_done_ids,
        )


    def run_all(self, force: bool = False, no_tag: bool = False) -> ExportResult:
        self.fetch()
        self.transform()
        self.extract()
        self.pack()
        return self.export(force=force, no_tag=no_tag)

    def close(self) -> None:
        self._renderer.close()
        if self._name_only_renderer:
            self._name_only_renderer.close()
            self._name_only_renderer = None
