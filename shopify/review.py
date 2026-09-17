from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


_COLUMNS: List[Tuple[str, str, bool, int]] = [
    ("order_number",        "Order #",              False, 10),
    ("order_id",            "Order ID",             False, 16),
    ("include",             "Include?",             True,  10),
    ("customer_name",       "Customer Name",        True,  22),
    ("student_name",        "Student Name",         True,  22),
    ("student_name_arabic", "Arabic Name",          True,  20),
    ("school",              "School",               True,  22),
    ("grade",               "Grade",                True,  10),
    ("template_name",       "Template",             True,  26),
    ("region_id",           "Product / Region",     True,  22),
    ("sku",                 "SKU",                  False, 16),
    ("qty",                 "Qty",                  True,   6),
    ("warning",             "Warning",              False, 40),
]

_LOCKED_FILL   = PatternFill("solid", fgColor="F2F2F2")
_EDITABLE_FILL = PatternFill("solid", fgColor="FFFDE7")
_WARN_FILL     = PatternFill("solid", fgColor="FFCCBC")
_EXCL_FILL     = PatternFill("solid", fgColor="CFD8DC")

_EDITABLE_COLS  = {k for k, _, editable, _ in _COLUMNS if editable}
_IDENTITY_COLS  = {k for k, _, editable, _ in _COLUMNS if not editable}
_KEY_ORDER      = [k for k, *_ in _COLUMNS]


def _flatten_records(records_dict: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
    main_rows: List[Dict] = []
    for rec in records_dict.get("records", []):
        base = {
            "order_number":        rec["order_number"],
            "order_id":            rec["order_id"],
            "include":             "Y",
            "customer_name":       rec.get("customer_name", ""),
            "student_name":        rec["student_name"],
            "student_name_arabic": rec.get("student_name_arabic", ""),
            "school":              rec.get("school", ""),
            "grade":               rec.get("grade", ""),
            "template_name":       rec["template_name"],
            "warning":             "",
        }
        for item in rec.get("items", []):
            main_rows.append({
                **base,
                "region_id": item["region_id"],
                "sku":       item.get("sku", ""),
                "qty":       item.get("qty", 1),
            })

    warning_rows: List[Dict] = []
    for w in records_dict.get("warnings", []):
        warning_rows.append({
            "order_number": w.get("order_number", ""),
            "kind":         w.get("kind", ""),
            "detail":       w.get("detail", ""),
            "line_item_id": w.get("line_item_id", ""),
        })

    return main_rows, warning_rows


def export_review(records_path: Path, out_path: Path) -> None:
    records_dict = json.loads(records_path.read_text(encoding="utf-8"))
    main_rows, warning_rows = _flatten_records(records_dict)

    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "Orders"

    header_font = Font(name="Arial", bold=True, size=10)
    for col_idx, (key, header, editable, width) in enumerate(_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = _LOCKED_FILL if not editable else _EDITABLE_FILL
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(_COLUMNS))}1"

    prev_order = None
    for row_dict in main_rows:
        row_num = ws.max_row + 1
        order_changed = row_dict["order_number"] != prev_order
        prev_order = row_dict["order_number"]

        for col_idx, (key, _, editable, _) in enumerate(_COLUMNS, start=1):
            val = row_dict.get(key, "")
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.font = Font(name="Arial", size=10)
            cell.fill = _EDITABLE_FILL if editable else _LOCKED_FILL
            if key == "student_name_arabic":
                cell.alignment = Alignment(horizontal="right")
            if order_changed and not editable:
                cell.fill = PatternFill("solid", fgColor="E8EAF6")

    ws["C1"].comment = None
    ws.sheet_properties.tabColor = "4CAF50"

    ws2 = wb.create_sheet("Warnings")
    ws2.sheet_properties.tabColor = "FF9800"
    warn_headers = ["Order #", "Kind", "Detail", "Line Item ID",
                    "Action (edit Orders sheet or leave — won't be processed)"]
    for ci, h in enumerate(warn_headers, start=1):
        c = ws2.cell(row=1, column=ci, value=h)
        c.font = Font(name="Arial", bold=True)
        c.fill = _WARN_FILL
        ws2.column_dimensions[get_column_letter(ci)].width = 30

    for w in warning_rows:
        ws2.append([
            w["order_number"], w["kind"], w["detail"], w["line_item_id"],
            "",
        ])

    ws2.freeze_panes = "A2"

    ws3 = wb.create_sheet("Instructions")
    instructions = [
        ("HOW TO USE THIS FILE", True),
        ("", False),
        ("1. Review the Orders sheet. Yellow columns are editable.", False),
        ("2. Set Include? = N for any order you want to skip this batch.", False),
        ("3. Fix Student Name, Arabic Name, School, Grade if wrong.", False),
        ("4. Fix Product / Region or Qty if Shopify data is wrong.", False),
        ("5. Template column: only change if the wrong template was picked.", False),
        ("", False),
        ("6. Save and close this file.", False),
        ("7. Run:  python -m cli import-review --run-dir <dir>", False),
        ("   This validates your changes, shows a diff, and asks to confirm", False),
        ("   before overwriting records.json. Nothing in Shopify is touched.", False),
        ("", False),
        ("8. Then run:  python -m cli extract --run-dir <dir>", False),
        ("             python -m cli pack    --run-dir <dir>", False),
        ("             python -m cli export  --run-dir <dir> --no-tag", False),
        ("   --no-tag produces sheets + report but does NOT tag orders.", False),
        ("   Use this for all test runs.", False),
        ("", False),
        ("9. When you're happy with the sheets:", False),
        ("   python -m cli export --run-dir <dir>   (tags orders in Shopify)", False),
        ("", False),
        ("IDENTITY COLUMNS (grey) cannot be edited — they are Shopify's data.", False),
        ("If the order number or order ID look wrong, the transform step", False),
        ("needs investigating, not this file.", False),
        ("", False),
        ("WARNING: do not add or delete ROWS. Only edit cell values.", False),
        ("The import step matches rows by (Order ID, Region ID) and will", False),
        ("reject structural changes with a clear error.", False),
    ]
    for text, bold in instructions:
        c = ws3.cell(row=ws3.max_row + 1, column=1, value=text)
        c.font = Font(name="Arial", bold=bold, size=11 if bold else 10)
    ws3.column_dimensions["A"].width = 70

    wb.save(out_path)


@dataclass
class ReviewDiff:
    changed_fields: List[str] = field(default_factory=list)
    excluded_orders: List[str] = field(default_factory=list)
    unmatched_rows: List[str] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.changed_fields or self.excluded_orders)

    @property
    def is_clean(self) -> bool:
        return not self.validation_errors

    def summary(self) -> str:
        lines = []
        if self.validation_errors:
            lines.append(f"VALIDATION ERRORS ({len(self.validation_errors)}):")
            lines.extend(f"  ✗ {e}" for e in self.validation_errors)
        if self.excluded_orders:
            lines.append(f"\nEXCLUDED ({len(self.excluded_orders)} orders):")
            lines.extend(f"  - {n}" for n in self.excluded_orders)
        if self.changed_fields:
            lines.append(f"\nFIELD CHANGES ({len(self.changed_fields)}):")
            lines.extend(f"  ~ {c}" for c in self.changed_fields)
        if not lines:
            lines.append("No changes — records.json is unchanged.")
        if self.unmatched_rows:
            lines.append(f"\nWARNING: {len(self.unmatched_rows)} row(s) in the "
                         f"Excel file had no matching record (were rows added?):")
            lines.extend(f"  ? {r}" for r in self.unmatched_rows[:5])
        return "\n".join(lines)


def _read_review_xlsx(xlsx_path: Path) -> List[Dict[str, Any]]:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    if "Orders" not in wb.sheetnames:
        raise ValueError(f"'Orders' sheet not found in {xlsx_path.name}")
    ws = wb["Orders"]
    rows_iter = ws.iter_rows(values_only=True)
    headers = [str(h).strip() if h else "" for h in next(rows_iter, [])]

    header_to_key = {h: k for k, h, *_ in _COLUMNS}
    col_indices = {header_to_key.get(h): i for i, h in enumerate(headers)
                   if header_to_key.get(h)}

    result: List[Dict[str, Any]] = []
    for raw in rows_iter:
        row: Dict[str, Any] = {}
        for key, idx in col_indices.items():
            val = raw[idx]
            row[key] = str(val).strip() if val is not None else ""
        if row.get("order_id"):
            result.append(row)
    return result


def diff_review(records_path: Path, xlsx_path: Path) -> Tuple[ReviewDiff, Dict[str, Any]]:
    original = json.loads(records_path.read_text(encoding="utf-8"))
    xlsx_rows = _read_review_xlsx(xlsx_path)

    diff = ReviewDiff()

    orig_index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for rec in original.get("records", []):
        for item in rec.get("items", []):
            key = (rec["order_id"], item["region_id"])
            orig_index[key] = {"rec": rec, "item": item}

    xlsx_index: Dict[Tuple[str, str], Dict] = {}
    excluded_order_ids: set = set()
    for row in xlsx_rows:
        oid = row.get("order_id", "")
        rid = row.get("region_id", "")
        if not oid:
            continue
        key = (oid, rid)
        if row.get("include", "Y").upper() == "N":
            excluded_order_ids.add(oid)
            diff.excluded_orders.append(
                f"{row.get('order_number', oid)} / {row.get('student_name', '')}"
            )
            continue
        if key not in orig_index:
            diff.unmatched_rows.append(f"order_id={oid} region_id={rid}")
            continue

        try:
            qty = int(row.get("qty") or 0)
        except (ValueError, TypeError):
            diff.validation_errors.append(
                f"{row.get('order_number')}: Qty must be a whole number, "
                f"got '{row.get('qty')}'"
            )
            qty = orig_index[key]["item"]["qty"]

        if qty <= 0 or qty > 50:
            diff.validation_errors.append(
                f"{row.get('order_number')}: Qty {qty} out of range (1–50)"
            )

        xlsx_index[key] = {**row, "qty": qty}

    DIFFED_FIELDS = [
        ("student_name",        "rec"),
        ("student_name_arabic", "rec"),
        ("school",              "rec"),
        ("grade",               "rec"),
        ("template_name",       "rec"),
        ("customer_name",       "rec"),
        ("qty",                 "item"),
        ("region_id",           "item"),
    ]

    new_records: List[Dict[str, Any]] = []
    for rec in original.get("records", []):
        oid = rec["order_id"]
        if oid in excluded_order_ids:
            continue

        new_rec = {**rec}
        new_items = []

        for item in rec.get("items", []):
            key = (oid, item["region_id"])
            if key not in xlsx_index:
                new_items.append({**item})
                continue

            edited = xlsx_index[key]
            orig = orig_index[key]

            for field_name, source in DIFFED_FIELDS:
                if source == "rec":
                    old_val = str(orig["rec"].get(field_name, ""))
                    new_val = str(edited.get(field_name, old_val))
                    if old_val != new_val:
                        diff.changed_fields.append(
                            f"{rec['order_number']} / {rec['student_name']}: "
                            f"{field_name} {old_val!r} → {new_val!r}"
                        )
                        new_rec[field_name] = new_val

            old_qty = item["qty"]
            new_qty = edited.get("qty", old_qty)
            if old_qty != new_qty:
                diff.changed_fields.append(
                    f"{rec['order_number']} / {rec['student_name']}: "
                    f"qty for {item['region_id']} {old_qty} → {new_qty}"
                )
            new_items.append({**item, "qty": new_qty})

        new_rec["items"] = new_items
        new_records.append(new_rec)

    new_records_dict = {
        **original,
        "records": new_records,
        "review_applied": True,
        "excluded_order_ids": sorted(excluded_order_ids),
    }
    return diff, new_records_dict


def apply_review(new_records_dict: Dict[str, Any], records_path: Path) -> None:
    tmp = records_path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(new_records_dict, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(records_path)
