from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from report import csv_log, viewer
from report.excel import append_report

ROWS = [
    {"sheet_number": "014", "export_date": "2026-08-04 14:32", "fill_pct": 0.913,
     "order_number": "#1042", "order_date": "2026-08-01",
     "customer_name": "Sarah Al-Rashidi", "student_name": "Ahmed Al-Rashidi",
     "student_name_arabic": "أحمد الراشدي", "school": "Greenfield",
     "grade": "Grade 3", "product": "Large Labels", "qty_on_sheet": 2,
     "template": "baby_minnie", "tile_ids": "t0001,t0002", "run_id": "run-1"},
    {"sheet_number": "014", "export_date": "2026-08-04 14:32", "fill_pct": 0.913,
     "order_number": "#1043", "order_date": "2026-08-01",
     "customer_name": "Mona Mahmoud", "student_name": "Sara Mahmoud",
     "student_name_arabic": "سارة", "school": "Greenfield", "grade": "Grade 2",
     "product": "Meeting Labels", "qty_on_sheet": 1,
     "template": "baby_minnie", "tile_ids": "t0003", "run_id": "run-1"},
    {"sheet_number": "013", "export_date": "2026-08-03 09:10", "fill_pct": 0.884,
     "order_number": "#1038", "order_date": "2026-07-30",
     "customer_name": "Dina Sherif", "student_name": "Malak Sherif",
     "student_name_arabic": "ملك", "school": "Manor House", "grade": "Grade 4",
     "product": "Pencil Labels", "qty_on_sheet": 3,
     "template": "baby_minnie", "tile_ids": "t0010", "run_id": "run-0"},
]


@pytest.fixture()
def report_paths(tmp_path):
    xlsx_path = tmp_path / "sheets_report.xlsx"
    append_report(xlsx_path, ROWS)
    return xlsx_path, tmp_path / "production_report.html"


def _embedded_data(html: str) -> dict:
    match = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    assert match, "DATA literal not found in generated report"
    return json.loads(match.group(1))


def test_report_generates_and_is_self_contained(report_paths):
    xlsx_path, out_path = report_paths
    viewer.generate_report(xlsx_path=xlsx_path, out_path=out_path)

    html = out_path.read_text(encoding="utf-8")
    assert html.lstrip().startswith("<!DOCTYPE html>")
    for marker in ("http://", "https://", "cdn.", "//fonts.googleapis"):
        assert marker not in html, f"external reference found: {marker}"


def test_sheet_and_row_counts_match_the_xlsx(report_paths):
    xlsx_path, out_path = report_paths
    viewer.generate_report(xlsx_path=xlsx_path, out_path=out_path)
    data = _embedded_data(out_path.read_text(encoding="utf-8"))

    assert len(data["sheets"]) == 2
    assert sum(len(s["rows"]) for s in data["sheets"]) == len(ROWS)


def test_sheets_are_newest_first(report_paths):
    xlsx_path, out_path = report_paths
    viewer.generate_report(xlsx_path=xlsx_path, out_path=out_path)
    data = _embedded_data(out_path.read_text(encoding="utf-8"))
    assert [s["no"] for s in data["sheets"]] == ["014", "013"]


def test_arabic_survives_round_trip(report_paths):
    xlsx_path, out_path = report_paths
    viewer.generate_report(xlsx_path=xlsx_path, out_path=out_path)
    html = out_path.read_text(encoding="utf-8")
    assert "أحمد الراشدي" in html


def test_malformed_rows_are_skipped_and_counted(tmp_path):
    import openpyxl
    xlsx_path = tmp_path / "sheets_report.xlsx"
    append_report(xlsx_path, ROWS)

    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb["Production"]
    ws.append([""] + ["bad"] * (len(csv_log.HEADERS) - 1))
    wb.save(xlsx_path)

    out_path = tmp_path / "report.html"
    viewer.generate_report(xlsx_path=xlsx_path, out_path=out_path)
    data = _embedded_data(out_path.read_text(encoding="utf-8"))

    assert data["skipped_rows"] == 1
    assert sum(len(s["rows"]) for s in data["sheets"]) == len(ROWS)


def test_missing_xlsx_renders_empty_state_not_a_crash(tmp_path):
    out_path = tmp_path / "report.html"
    viewer.generate_report(xlsx_path=tmp_path / "nope.xlsx", out_path=out_path)
    data = _embedded_data(out_path.read_text(encoding="utf-8"))
    assert data["sheets"] == []


def test_schematics_convert_placements_to_millimetres():
    manifest = {"tiles": [
        {"tile_id": "t0001", "w_mm": 72.3, "h_mm": 101.1,
         "region_label": "Meeting Labels"},
    ]}
    plan = {"sheets": [{"placements": [
        {"tile_id": "t0001", "x_px": 1181, "y_px": 590, "rotated": False},
    ]}]}

    out = viewer.schematics_from_plan(plan, manifest, [7], dpi=300)
    rect = out["007"][0]
    assert rect["x"] == pytest.approx(100.0, abs=0.2)
    assert rect["y"] == pytest.approx(50.0, abs=0.2)
    assert rect["w"] == 72.3
    assert rect["p"] == "meeting_labels"


def test_schematics_swap_dimensions_when_rotated():
    manifest = {"tiles": [
        {"tile_id": "t0001", "w_mm": 72.3, "h_mm": 101.1, "region_label": "M"},
    ]}
    plan = {"sheets": [{"placements": [
        {"tile_id": "t0001", "x_px": 0, "y_px": 0, "rotated": True},
    ]}]}
    rect = viewer.schematics_from_plan(plan, manifest, [1], dpi=300)["001"][0]
    assert (rect["w"], rect["h"]) == (101.1, 72.3)


def test_products_get_distinct_colours(report_paths):
    xlsx_path, out_path = report_paths
    viewer.generate_report(xlsx_path=xlsx_path, out_path=out_path)
    html = out_path.read_text(encoding="utf-8")
    match = re.search(r"const PRODUCTS = (\{.*?\});\n", html, re.S)
    products = json.loads(match.group(1))
    assert set(products) == {"large_labels", "meeting_labels", "pencil_labels"}
    colours = [p["colour"] for p in products.values()]
    assert len(set(colours)) == len(colours), "products must be distinguishable"
