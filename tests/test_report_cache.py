from __future__ import annotations

import json

import pytest

from report import viewer
from report.excel import append_report

ROWS = [
    {"sheet_number": "014", "export_date": "2026-08-06 14:32", "fill_pct": 0.913,
     "order_number": "#1042", "order_date": "2026-08-01",
     "customer_name": "Sarah", "student_name": "Ahmed",
     "student_name_arabic": "أحمد", "school": "GF", "grade": "3",
     "product": "Large Labels", "qty_on_sheet": 2, "template": "t",
     "tile_ids": "t1", "run_id": "r1"},
    {"sheet_number": "013", "export_date": "2026-08-05 09:10", "fill_pct": 0.88,
     "order_number": "#1038", "order_date": "2026-07-30",
     "customer_name": "Dina", "student_name": "Malak",
     "student_name_arabic": "ملك", "school": "MH", "grade": "4",
     "product": "Pencil Labels", "qty_on_sheet": 3, "template": "t",
     "tile_ids": "t2", "run_id": "r0"},
]


@pytest.fixture()
def reports_dir(tmp_path):
    append_report(tmp_path / "sheets_report.xlsx", ROWS)
    return tmp_path


class TestCacheLifecycle:
    def test_no_cache_before_first_generate(self, reports_dir):
        assert viewer.read_report_cache(reports_dir) is None

    def test_generate_report_writes_the_cache(self, reports_dir):
        viewer.generate_report(
            xlsx_path=reports_dir / "sheets_report.xlsx",
            out_path=reports_dir / "production_report.html",
        )
        assert (reports_dir / viewer.CACHE_FILENAME).exists()

    def test_cache_round_trips_the_payload(self, reports_dir):
        viewer.generate_report(
            xlsx_path=reports_dir / "sheets_report.xlsx",
            out_path=reports_dir / "production_report.html",
        )
        cached = viewer.read_report_cache(reports_dir)
        assert len(cached["sheets"]) == 2
        assert set(cached["products"]) == {"large_labels", "pencil_labels"}
        assert cached["skipped_rows"] == 0

    def test_cache_preserves_sheet_order_newest_first(self, reports_dir):
        viewer.generate_report(
            xlsx_path=reports_dir / "sheets_report.xlsx",
            out_path=reports_dir / "production_report.html",
        )
        cached = viewer.read_report_cache(reports_dir)
        assert [s["no"] for s in cached["sheets"]] == ["014", "013"]

    def test_cache_preserves_arabic(self, reports_dir):
        viewer.generate_report(
            xlsx_path=reports_dir / "sheets_report.xlsx",
            out_path=reports_dir / "production_report.html",
        )
        raw = (reports_dir / viewer.CACHE_FILENAME).read_text(encoding="utf-8")
        assert "أحمد" in raw

    def test_write_is_atomic_no_tmp_left_behind(self, reports_dir):
        viewer.generate_report(
            xlsx_path=reports_dir / "sheets_report.xlsx",
            out_path=reports_dir / "production_report.html",
        )
        leftovers = list(reports_dir.glob("*.tmp"))
        assert leftovers == [], f"temp files left: {leftovers}"


class TestCacheResilience:
    def test_missing_cache_returns_none_not_raise(self, tmp_path):
        assert viewer.read_report_cache(tmp_path) is None

    def test_corrupt_cache_returns_none_not_raise(self, tmp_path):
        (tmp_path / viewer.CACHE_FILENAME).write_text("{not json",
                                                       encoding="utf-8")
        assert viewer.read_report_cache(tmp_path) is None

    def test_empty_workbook_caches_an_empty_history(self, tmp_path):
        viewer.generate_report(
            xlsx_path=tmp_path / "does_not_exist.xlsx",
            out_path=tmp_path / "production_report.html",
        )
        cached = viewer.read_report_cache(tmp_path)
        assert cached is not None and cached["sheets"] == []


class TestHtmlStaysAStandaloneFile:
    def test_html_is_written_to_disk(self, reports_dir):
        out = viewer.generate_report(
            xlsx_path=reports_dir / "sheets_report.xlsx",
            out_path=reports_dir / "production_report.html",
        )
        assert out.exists() and out.stat().st_size > 0

    def test_html_is_self_contained(self, reports_dir):
        out = viewer.generate_report(
            xlsx_path=reports_dir / "sheets_report.xlsx",
            out_path=reports_dir / "production_report.html",
        )
        html = out.read_text(encoding="utf-8")
        assert html.lstrip().startswith("<!DOCTYPE html>")
        for marker in ("http://", "https://", "cdn."):
            assert marker not in html, f"external reference: {marker}"

    def test_html_does_not_fetch_the_cache(self, reports_dir):
        out = viewer.generate_report(
            xlsx_path=reports_dir / "sheets_report.xlsx",
            out_path=reports_dir / "production_report.html",
        )
        html = out.read_text(encoding="utf-8")
        assert viewer.CACHE_FILENAME not in html
        assert "/api/report" not in html

    def test_html_contains_the_rows(self, reports_dir):
        out = viewer.generate_report(
            xlsx_path=reports_dir / "sheets_report.xlsx",
            out_path=reports_dir / "production_report.html",
        )
        html = out.read_text(encoding="utf-8")
        assert "#1042" in html and "أحمد" in html


def test_read_csv_rows_is_gone():
    assert not hasattr(viewer, "_read_csv_rows")
    assert hasattr(viewer, "_read_xlsx_rows")
