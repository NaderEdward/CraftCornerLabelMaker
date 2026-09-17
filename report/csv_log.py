from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

HEADERS = [
    "Sheet #", "Export Date", "Fill %", "Order #", "Order Date",
    "Customer Name", "Student Name", "Student Name (Arabic)", "School",
    "Grade", "Product", "Qty on This Sheet", "Template", "Tile IDs", "Run ID",
]


def append_rows(csv_path: Path, rows: List[Dict[str, Any]]) -> None:
    pass


def row_from_report_row(report_row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "Sheet #": report_row["sheet_number"],
        "Export Date": report_row["export_date"],
        "Fill %": report_row["fill_pct"],
        "Order #": report_row["order_number"],
        "Order Date": report_row.get("order_date", ""),
        "Customer Name": report_row["customer_name"],
        "Student Name": report_row["student_name"],
        "Student Name (Arabic)": report_row.get("student_name_arabic", ""),
        "School": report_row.get("school", ""),
        "Grade": report_row.get("grade", ""),
        "Product": report_row["product"],
        "Qty on This Sheet": report_row["qty_on_sheet"],
        "Template": report_row["template"],
        "Tile IDs": report_row["tile_ids"],
        "Run ID": report_row["run_id"],
    }
