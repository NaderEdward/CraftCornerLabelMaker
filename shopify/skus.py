from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


def collect_skus(orders_raw_path: Path) -> List[Dict[str, Any]]:
    data = json.loads(orders_raw_path.read_text(encoding="utf-8"))
    counts: Dict[Tuple[str, str], int] = defaultdict(int)

    for order in data.get("orders", []):
        for li in order.get("line_items", []):
            sku   = (li.get("sku") or "").strip()
            title = (li.get("title") or "").strip()
            qty   = int(li.get("quantity") or 0)
            counts[(sku, title)] += qty

    return sorted(
        [{"sku": sku, "title": title, "total_qty": qty}
         for (sku, title), qty in counts.items()],
        key=lambda r: (-r["total_qty"], r["sku"]),
    )


def match_status(sku_map: Dict[str, List[Tuple[str, str]]],
                 sku: str, title: str) -> str:
    sku_lower = sku.lower()
    title_lower = title.lower()
    matched = set()
    for key, owners in sku_map.items():
        if key in sku_lower or key in title_lower:
            for tname, rid in owners:
                matched.add(f"{tname}/{rid}")
    if not matched:
        return "— no match"
    if len(matched) == 1:
        return f"→ {next(iter(matched))}"
    return f"AMBIGUOUS: {', '.join(sorted(matched))}"


def write_skus_xlsx(rows: List[Dict[str, Any]], out_path: Path,
                    sku_map: Optional[Dict] = None) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SKUs"

    headers = ["SKU", "Title", "Total Qty", "Matches Region"]
    widths  = [24,     40,       12,           48]
    hdr_font = Font(name="Arial", bold=True)
    hdr_fill = PatternFill("solid", fgColor="E3F2FD")
    for ci, (h, w) in enumerate(zip(headers, widths), start=1):
        c = ws.cell(row=1, column=ci, value=h)
        c.font = hdr_font
        c.fill = hdr_fill
        ws.column_dimensions[get_column_letter(ci)].width = w

    no_match_fill = PatternFill("solid", fgColor="FFCDD2")
    ambig_fill    = PatternFill("solid", fgColor="FFE0B2")

    for row in rows:
        status = match_status(sku_map, row["sku"], row["title"]) if sku_map else ""
        vals = [row["sku"], row["title"], row["total_qty"], status]
        rn = ws.max_row + 1
        for ci, val in enumerate(vals, start=1):
            c = ws.cell(row=rn, column=ci, value=val)
            c.font = Font(name="Arial", size=10)
        if "no match" in status:
            for ci in range(1, 5):
                ws.cell(row=rn, column=ci).fill = no_match_fill
        elif "AMBIGUOUS" in status:
            for ci in range(1, 5):
                ws.cell(row=rn, column=ci).fill = ambig_fill

    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{ws.max_row}"
    ws.freeze_panes = "A2"

    ws2 = wb.create_sheet("How to use")
    notes = [
        "This file shows every (SKU, title) pair from your fetched orders.",
        "",
        "Red rows = no region sidecar matches this SKU/title yet.",
        "Orange rows = matches MORE THAN ONE region (ambiguous — must fix).",
        "Green rows = matched exactly one region.",
        "",
        "For each red row, decide:",
        "  a) Create a region for this product: add a ProductRegion with",
        "     sku_match containing a substring of the SKU or title, then",
        "     run: python -m cli validate-regions --template <name>",
        "",
        "  b) This product type has no physical label (e.g. a digital add-on):",
        "     note it so you expect it to be warned/skipped every batch.",
        "",
        "Copy the SKU string exactly from this file into your region sidecar.",
        "Matching is substring, case-insensitive, so you can use a short",
        "distinctive fragment rather than the full SKU.",
        "",
        "WARNING: if a fragment matches two regions, transform will hard-error",
        "on every order with that product. Ambiguity is NEVER resolved silently.",
    ]
    for note in notes:
        c = ws2.cell(row=ws2.max_row + 1, column=1, value=note)
        c.font = Font(name="Arial", size=10, bold=note.startswith("WARNING"))
    ws2.column_dimensions["A"].width = 72

    wb.save(out_path)
