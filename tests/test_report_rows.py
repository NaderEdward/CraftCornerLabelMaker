from __future__ import annotations

from report.excel import build_report_rows, index_records, record_key


def _tile(tile_id, student, region_id, region_label):
    return {
        "tile_id": tile_id, "file": f"tiles/{tile_id}.png",
        "w_px": 100, "h_px": 100, "w_mm": 10, "h_mm": 10,
        "gap_px": 0, "allow_rotate": False,
        "order_id": "5001", "order_number": "#1042",
        "customer_name": "Sarah Al-Rashidi", "student_name": student,
        "region_id": region_id, "region_label": region_label,
        "template_name": "tpl", "unit_index": 1, "unit_total": 1,
    }


RECORDS = [
    {"order_id": "5001", "order_number": "#1042", "student_name": "Ahmed",
     "student_name_arabic": "أحمد", "school": "Greenfield", "grade": "Grade 3",
     "customer_name": "Sarah Al-Rashidi"},
    {"order_id": "5001", "order_number": "#1042", "student_name": "Layla",
     "student_name_arabic": "ليلى", "school": "Nile Academy", "grade": "KG 2",
     "customer_name": "Sarah Al-Rashidi"},
]


def test_index_records_keeps_both_siblings():
    idx = index_records(RECORDS)
    assert len(idx) == 2
    assert idx[record_key("5001", "Ahmed")]["grade"] == "Grade 3"
    assert idx[record_key("5001", "Layla")]["grade"] == "KG 2"


def test_naive_order_id_index_would_lose_a_sibling():
    naive = {r["order_id"]: r for r in RECORDS}
    assert len(naive) == 1


def test_report_rows_carry_each_students_own_details():
    manifest = {"tiles": [
        _tile("t0001", "Ahmed", "large_labels", "Large Labels"),
        _tile("t0002", "Layla", "shoe_labels", "Shoe Labels"),
    ]}
    plan_sheet = {"utilisation": 0.91, "placements": [
        {"tile_id": "t0001", "x_px": 0, "y_px": 0, "rotated": False},
        {"tile_id": "t0002", "x_px": 200, "y_px": 0, "rotated": False},
    ]}

    rows = build_report_rows(7, "2026-08-04 14:32", plan_sheet, manifest,
                             index_records(RECORDS), "run-1")

    by_student = {r["student_name"]: r for r in rows}
    assert by_student["Ahmed"]["school"] == "Greenfield"
    assert by_student["Ahmed"]["grade"] == "Grade 3"
    assert by_student["Layla"]["school"] == "Nile Academy"
    assert by_student["Layla"]["grade"] == "KG 2"
    assert by_student["Layla"]["student_name_arabic"] == "ليلى"


def test_qty_on_this_sheet_counts_placements_not_order_total():
    manifest = {"tiles": [
        _tile("t0001", "Ahmed", "large_labels", "Large Labels"),
        _tile("t0002", "Ahmed", "large_labels", "Large Labels"),
    ]}
    plan_sheet = {"utilisation": 0.5, "placements": [
        {"tile_id": "t0001", "x_px": 0, "y_px": 0, "rotated": False},
        {"tile_id": "t0002", "x_px": 200, "y_px": 0, "rotated": False},
    ]}
    rows = build_report_rows(7, "d", plan_sheet, manifest,
                             index_records(RECORDS), "run-1")
    assert len(rows) == 1
    assert rows[0]["qty_on_sheet"] == 2
    assert rows[0]["tile_ids"] == "t0001,t0002"
