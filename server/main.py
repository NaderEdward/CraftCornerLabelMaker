from __future__ import annotations

import asyncio
from datetime import datetime
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import (FastAPI, HTTPException, BackgroundTasks,
                     File, Form, UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from typing import Any, Dict, List, Optional

from core import paths as core_paths
from core import settings as core_settings
from core import logging_setup

log = logging_setup.get_logger()

app = FastAPI(title="Craft Corner Label Maker", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])

_current_pipeline = None
_run_progress: Dict[str, Any] = {"stage": "", "current": 0, "total": 0, "done": False, "error": None}


@app.get("/api/settings")
def get_settings():
    cfg = core_settings.load()
    try:
        from shopify.client import (credentials_configured, get_client_credentials,
                                    get_static_token, auth_mode, keyring_available)
        cid, _ = get_client_credentials()
        static  = get_static_token()
        cfg["_creds_configured"] = credentials_configured()
        cfg["_auth_mode"]        = auth_mode()
        cfg["_keyring_ok"]       = keyring_available()
        cfg["_has_client_id"]    = bool(cid)
        cfg["_has_static_token"] = bool(static)
    except Exception:
        cfg["_creds_configured"] = False
        cfg["_has_client_id"]    = False
        cfg["_has_static_token"] = False
        cfg["_auth_mode"]        = "none"
        cfg["_keyring_ok"]       = False
    return cfg


class SettingsPayload(BaseModel):
    settings: Dict[str, Any]
    client_id:     Optional[str] = None
    client_secret: Optional[str] = None
    static_token:  Optional[str] = None


@app.post("/api/settings")
def save_settings(payload: SettingsPayload):
    cfg = core_settings.load()
    cfg.update(payload.settings)
    core_settings.save(cfg)

    if payload.client_id and payload.client_secret:
        from shopify.client import store_client_credentials
        store_client_credentials(payload.client_id, payload.client_secret)
    if payload.static_token:
        from shopify.client import store_static_token
        store_static_token(payload.static_token)

    return {"ok": True}


@app.post("/api/settings/reset-sheet-count")
def reset_sheet_count(body: dict):
    value = int(body.get("value", 0))
    if value < 0:
        raise HTTPException(400, "value must be >= 0")
    cfg = core_settings.load()
    old = cfg.get("last_sheet_number", 0)
    cfg["last_sheet_number"] = value
    core_settings.save(cfg)
    return {"ok": True, "previous": old, "next_sheet": value + 1}


@app.post("/api/shopify/clear-credentials")
def clear_shopify_credentials():
    from shopify.client import clear_all_credentials
    clear_all_credentials()
    return {"ok": True, "message": "Stored Shopify credentials cleared."}


@app.post("/api/shopify/test")
def test_shopify_connection():
    cfg = core_settings.load()
    from shopify.client import ShopifyClient, credentials_configured
    if not credentials_configured():
        return {"ok": False, "message": "No credentials configured. Enter Client ID + Secret or Static token in Settings."}
    client = ShopifyClient(cfg["shopify_domain"], cfg["shopify_api_version"])
    ok, message = client.test_connection()
    return {"ok": ok, "message": message}


@app.get("/api/shopify/order-count")
def get_order_count():
    cfg = core_settings.load()
    from shopify.client import ShopifyClient, ShopifyAPIError, credentials_configured
    from shopify.ingest import _is_eligible, _is_unfulfilled
    if not credentials_configured():
        raise HTTPException(400, "No credentials")
    client = ShopifyClient(cfg["shopify_domain"], cfg["shopify_api_version"])
    try:
        count = sum(
            1 for o in client.iter_orders()
            if _is_unfulfilled(o) and _is_eligible(o)
        )
        return {"count": count}
    except ShopifyAPIError as e:
        raise HTTPException(502, str(e))


@app.get("/api/templates")
def list_templates():
    from core import templates as core_templates
    from regions import model as region_model
    from regions import validate as region_validate

    result = []
    for name in core_templates.list_names():
        has_sidecar = region_model.sidecar_exists(name)
        problems = [p for p in core_templates.validate(name) if "native_dpi" not in p]
        ready = has_sidecar and not problems
        if has_sidecar:
            rs = region_model.load(name)
            problems += region_validate.validate_region_set(rs)
            fp_ok = region_model.check_fingerprint(rs)
            regions = [{"id": r.id, "label": r.label, "sku_match": r.sku_match}
                       for r in rs.regions]
        else:
            regions = []
            fp_ok = True
        result.append({
            "name": name, "ready": ready and not problems,
            "has_sidecar": has_sidecar, "fingerprint_ok": fp_ok,
            "problems": problems, "regions": regions,
        })
    return result


class ScanFolderReq(BaseModel):
    folder: str
    category: str
    recursive: bool = False


class ImportPathsReq(BaseModel):
    paths: List[str]
    category: str
    is_extras: bool = False
    overwrite: bool = False
    theme_overrides: Dict[str, str] = {}


class RemoveThemeReq(BaseModel):
    theme: str
    category: str
    delete_file: bool = False


@app.get("/api/themes")
def get_themes():
    from core import theme_admin
    return {
        "categories": list(theme_admin.CATEGORIES),
        "labels": {c: theme_admin.theme_map.TYPE_LABELS[c]
                   for c in theme_admin.CATEGORIES},
        "themes": theme_admin.list_themes(),
        "themes_list_path": str(theme_admin.themes_list_path()),
        "backgrounds_write_root": str(theme_admin.backgrounds_write_root()),
    }


@app.post("/api/themes/scan-folder")
def scan_theme_folder(req: ScanFolderReq):
    from core import theme_admin
    from dataclasses import asdict
    try:
        cands = theme_admin.scan_folder(req.folder, req.category, req.recursive)
    except NotADirectoryError as e:
        raise HTTPException(400, str(e))
    except OSError as e:
        raise HTTPException(400, f"Could not read folder: {e}")
    return [asdict(c) for c in cands]


@app.post("/api/themes/import-paths")
def import_themes_from_paths(req: ImportPathsReq):
    from core import theme_admin
    from dataclasses import asdict
    if req.category not in theme_admin.CATEGORIES:
        raise HTTPException(400, f"Unknown category: {req.category}")
    res = theme_admin.import_many(
        req.paths, req.category,
        is_extras=req.is_extras, overwrite=req.overwrite,
        theme_overrides=req.theme_overrides,
    )
    return asdict(res)


@app.post("/api/themes/upload")
async def upload_themes(
    category: str = Form(...),
    is_extras: bool = Form(False),
    overwrite: bool = Form(False),
    themes: str = Form("{}"),
    files: List[UploadFile] = File(...),
):
    from core import theme_admin
    from dataclasses import asdict
    import tempfile, shutil as _shutil

    if category not in theme_admin.CATEGORIES:
        raise HTTPException(400, f"Unknown category: {category}")

    try:
        overrides = json.loads(themes) or {}
    except json.JSONDecodeError:
        overrides = {}

    tmpdir = Path(tempfile.mkdtemp(prefix="cc_theme_upload_"))
    try:
        staged: List[str] = []
        for f in files:
            safe = Path(f.filename or "unnamed").name
            dest = tmpdir / safe
            with open(dest, "wb") as out:
                _shutil.copyfileobj(f.file, out)
            staged.append(str(dest))
            if safe in overrides:
                overrides[str(dest)] = overrides[safe]

        res = theme_admin.import_many(
            staged, category,
            is_extras=is_extras, overwrite=overwrite,
            theme_overrides=overrides,
        )
        return asdict(res)
    finally:
        _shutil.rmtree(tmpdir, ignore_errors=True)


@app.post("/api/themes/remove")
def remove_theme(req: RemoveThemeReq):
    from core import theme_admin
    from dataclasses import asdict
    if req.category not in theme_admin.CATEGORIES:
        raise HTTPException(400, f"Unknown category: {req.category}")
    return asdict(theme_admin.remove_theme(
        req.theme, req.category, delete_file=req.delete_file))


class ScanAllThemesReq(BaseModel):
    folder: str
    overwrite: bool = False

@app.post("/api/scan-all-themes")
def scan_all_themes(req: ScanAllThemesReq):
    from core import theme_admin, name_fonts as nf
    from dataclasses import asdict
    from pathlib import Path as _Path

    root = _Path(req.folder)
    if not root.is_dir():
        raise HTTPException(400, f"Folder not found: {root}")

    summary = {}

    ARTWORK_CATS = ["signs", "stitches", "plain_signs", "plain_stitches", "name_cutout"]
    for cat in ARTWORK_CATS:
        sub = root / cat
        if not sub.is_dir():
            summary[cat] = {"skipped": [f"{sub} not found"]}
            continue
        try:
            paths = [str(f) for f in sorted(sub.iterdir())
                     if f.is_file() and f.suffix.lower() in (".png",".jpg",".jpeg")]
            if not paths:
                summary[cat] = {"skipped": ["no image files found"]}
                continue
            result = theme_admin.import_many(
                paths, cat, is_extras=False, overwrite=req.overwrite)
            summary[cat] = asdict(result)
        except Exception as e:
            summary[cat] = {"errors": [str(e)]}

    font_sub = root / "name_fonts"
    if font_sub.is_dir():
        registry = nf.load_registry()
        font_result = nf.FontImportResult()
        for f in sorted(font_sub.iterdir()):
            if not f.is_file() or f.suffix.lower() not in (".otf",".ttf",".woff",".woff2"):
                continue
            slug = nf.derive_slug(f.name)
            nf.import_font(f, slug, overwrite=req.overwrite, result=font_result)
        summary["name_fonts"] = asdict(font_result)
    else:
        summary["name_fonts"] = {"skipped": [f"{font_sub} not found"]}

    return summary


class NameFontUpsertReq(BaseModel):
    slug:           str
    font_file:      str
    class_font_file: str = ""
    stroke_px:      int  = 12
    stroke_color:   str  = "#ffffff"
    line_gap_mult:  float = 1.0
    gap_from_name:  int  = 8
    force_uppercase: bool = True
    strip_pattern:  str  = r"[^A-Z\s]"

class NameFontRemoveReq(BaseModel):
    slug:        str
    delete_file: bool = False

class NameFontScanReq(BaseModel):
    folder: str

class NameFontImportPathsReq(BaseModel):
    paths:     List[str]
    slug_map:  Dict[str, str] = {}
    overwrite: bool = False
    params_map: Dict[str, dict] = {}


@app.get("/api/name-fonts")
def get_name_fonts():
    from core import name_fonts as nf
    return {
        "fonts":            nf.list_fonts(),
        "name_fonts_dir":   str(nf.name_fonts_dir()),
        "config_path":      str(nf._config_path()),
    }


@app.post("/api/name-fonts/scan-folder")
def scan_name_fonts_folder(req: NameFontScanReq):
    from core import name_fonts as nf
    try:
        return nf.scan_folder(req.folder)
    except NotADirectoryError as e:
        raise HTTPException(400, str(e))


@app.post("/api/name-fonts/import-paths")
def import_name_fonts_from_paths(req: NameFontImportPathsReq):
    from core import name_fonts as nf
    from dataclasses import asdict
    result = nf.FontImportResult()
    for src_str in req.paths:
        src  = Path(src_str)
        slug = req.slug_map.get(src.name, nf.derive_slug(src.name))
        params = req.params_map.get(src.name, {})
        nf.import_font(src, slug, overwrite=req.overwrite,
                       params=params, result=result)
    return asdict(result)


@app.post("/api/name-fonts/upload")
async def upload_name_fonts(
    slug:       str  = Form(...),
    overwrite:  bool = Form(False),
    stroke_px:  int  = Form(12),
    stroke_color: str = Form("#ffffff"),
    line_gap_mult: float = Form(1.0),
    gap_from_name: int = Form(8),
    force_uppercase: bool = Form(True),
    files: List[UploadFile] = File(...),
):
    import tempfile, shutil as _shutil
    from core import name_fonts as nf
    from dataclasses import asdict
    params = {
        "stroke_px":       stroke_px,
        "stroke_color":    stroke_color,
        "line_gap_mult":   line_gap_mult,
        "gap_from_name":   gap_from_name,
        "force_uppercase": force_uppercase,
    }
    tmpdir = Path(tempfile.mkdtemp(prefix="cc_font_upload_"))
    result = nf.FontImportResult()
    try:
        for f in files:
            safe = Path(f.filename or "unnamed").name
            dest = tmpdir / safe
            with open(dest, "wb") as out:
                _shutil.copyfileobj(f.file, out)
            nf.import_font(dest, slug, overwrite=overwrite,
                           params=params, result=result)
        return asdict(result)
    finally:
        _shutil.rmtree(tmpdir, ignore_errors=True)


@app.post("/api/name-fonts/upsert")
def upsert_name_font(req: NameFontUpsertReq):
    from core import name_fonts as nf
    registry = nf.load_registry()
    slug = req.slug.lower().strip()
    if slug not in registry:
        raise HTTPException(404, f"Slug '{slug}' not in registry. Upload the font first.")
    registry[slug].update({
        "font_file":       req.font_file or registry[slug].get("font_file",""),
        "class_font_file": req.class_font_file,
        "stroke_px":       req.stroke_px,
        "stroke_color":    req.stroke_color,
        "line_gap_mult":   req.line_gap_mult,
        "gap_from_name":   req.gap_from_name,
        "force_uppercase": req.force_uppercase,
        "strip_pattern":   req.strip_pattern,
    })
    nf.save_registry(registry)
    return {"ok": True, "slug": slug}


@app.post("/api/name-fonts/remove")
def remove_name_font(req: NameFontRemoveReq):
    from core import name_fonts as nf
    from dataclasses import asdict
    return asdict(nf.remove_font(req.slug, delete_file=req.delete_file))


def _build_pipeline_config():
    from orchestrator.pipeline import RunConfig
    cfg = core_settings.load()
    return RunConfig(
        shopify_domain=cfg["shopify_domain"],
        shopify_api_version=cfg["shopify_api_version"],
        in_progress_tag=cfg["in_progress_tag"],
        output_folder=core_paths.default_output_folder(),
        report_folder=core_paths.default_report_folder(),
        sheet_width_mm=cfg["sheet_width_mm"],
        sheet_height_mm=cfg["sheet_height_mm"],
        margin_mm={"t": cfg["margin_t_mm"], "b": cfg["margin_b_mm"],
                   "l": cfg["margin_l_mm"], "r": cfg["margin_r_mm"]},
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


@app.get("/api/pipeline/run")
async def run_pipeline(force: bool = False):
    async def event_generator():
        global _current_pipeline, _run_progress
        _run_progress = {"stage": "", "current": 0, "total": 0, "done": False, "error": None}

        from orchestrator.pipeline import Pipeline

        def on_progress(stage, current, total):
            _run_progress.update(stage=stage, current=current, total=total)

        config = _build_pipeline_config()
        _current_pipeline = Pipeline(config, on_progress=on_progress)

        stages = [
            ("fetch",     lambda: _current_pipeline.fetch()),
            ("transform", lambda: _current_pipeline.transform()),
            ("extract",   lambda: _current_pipeline.extract()),
            ("pack",      lambda: _current_pipeline.pack()),
            ("export",    lambda: _current_pipeline.export(force=force)),
        ]

        for stage_name, fn in stages:
            _run_progress["stage"] = stage_name
            yield {"event": "progress", "data": json.dumps(_run_progress)}
            await asyncio.sleep(0)
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, fn)
            except Exception as e:
                _run_progress["error"] = str(e)
                yield {"event": "error", "data": json.dumps({"stage": stage_name, "message": str(e)})}
                return

        _run_progress["done"] = True
        yield {"event": "done", "data": json.dumps({
            "run_id":          _current_pipeline.run_id,
            "exported_sheets": getattr(result, "exported_sheet_numbers", []),
            "held_back":       getattr(result, "held_back_orders", []),
            "oversize":        getattr(result, "oversize_orders", []),
            "tagged":          getattr(result, "tagged_order_ids", []),
            "untagged":        getattr(result, "untagged_order_ids", []),
            "partially_done":  getattr(result, "partially_done_order_ids", []),
        })}

    return EventSourceResponse(event_generator())


@app.get("/api/pipeline/status")
def pipeline_status():
    return _run_progress


@app.post("/api/pipeline/fetch-only")
def fetch_orders_only():
    from orchestrator.pipeline import Pipeline
    config = _build_pipeline_config()
    pipeline = Pipeline(config)
    try:
        path = pipeline.fetch()
        records_path = pipeline.transform()
        import json as _json
        records = _json.load(open(records_path, encoding="utf-8"))
        return {
            "run_id": pipeline.run_id,
            "order_count": len(records.get("records", [])),
            "warnings": records.get("warnings", []),
            "records": records.get("records", []),
        }
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get("/api/report")
def get_report_data(refresh: bool = False):
    from report import viewer

    reports_dir = core_paths.default_report_folder()

    if not refresh:
        cached = viewer.read_report_cache(reports_dir)
        if cached is not None:
            return {**cached, "source": "cache"}

    xlsx_path = reports_dir / "sheets_report.xlsx"
    rows, skipped = viewer._read_xlsx_rows(xlsx_path)
    products = viewer._build_products(rows)
    sheets   = viewer._build_sheets(rows, {})
    data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sheet_mm": {"w": 420, "h": 297},
        "sheets": sheets,
        "pending": [],
        "skipped_rows": skipped,
    }
    try:
        viewer.write_report_cache(data, products, reports_dir)
    except OSError:
        pass
    return {**data, "products": products, "source": "rebuilt"}


@app.get("/api/report/html")
def open_report_html(refresh: bool = False):
    from report import viewer

    reports_dir = core_paths.default_report_folder()
    out_path = reports_dir / "production_report.html"

    if refresh or not out_path.exists():
        viewer.generate_report(
            xlsx_path=reports_dir / "sheets_report.xlsx",
            out_path=out_path,
        )
    return FileResponse(str(out_path), media_type="text/html")


@app.get("/api/runs")
def list_runs():
    runs_dir = core_paths.runs_dir()
    runs = []
    for d in sorted(runs_dir.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        journal_path = d / "journal.json"
        complete = False
        if journal_path.exists():
            from orchestrator.journal import Journal
            complete = Journal(d, d.name).is_complete()
        runs.append({"run_id": d.name, "complete": complete})
    return runs[:20]


@app.get("/runs/{run_id}/{filename}")
def serve_run_file(run_id: str, filename: str):
    p = core_paths.runs_dir() / run_id / filename
    if not p.exists() or not p.is_file():
        raise HTTPException(404)
    return FileResponse(str(p))


@app.get("/api/doctor")
def doctor():
    from core import templates as core_templates
    from plotter.render import FontManager
    results = {}
    try:
        FontManager.assert_available(sorted({
            *FontManager.RECOMMENDATIONS["en"],
            *FontManager.RECOMMENDATIONS["ar"],
        }))
        results["fonts"] = {"ok": True}
    except Exception as e:
        results["fonts"] = {"ok": False, "message": str(e)}

    template_results = []
    for name in core_templates.list_names():
        probs = core_templates.validate(name)
        template_results.append({"name": name, "ok": not [p for p in probs if "native_dpi" not in p], "problems": probs})
    results["templates"] = template_results

    from core.render_engine import ARABIC_SUPPORT
    results["arabic"] = {"ok": ARABIC_SUPPORT}

    return results


STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="127.0.0.1", port=8000, reload=False)
