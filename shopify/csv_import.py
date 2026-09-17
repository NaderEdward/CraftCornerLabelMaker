from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

COLUMN_MAP = {
    "order_id": "Name",
    "sku": "Lineitem sku",
    "title": "Lineitem name",
    "qty": "Lineitem quantity",
    "customer_first": "Billing Name",
    "phone": "Phone",
    "tags": "Tags",
    "note_attributes": "Notes",
}


def import_csv(csv_path: Path, out_path: Path) -> Path:
    grouped: Dict[str, Dict[str, Any]] = {}
    order_seq: List[str] = []

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get(COLUMN_MAP["order_id"], "").strip()
            if not name:
                continue
            if name not in grouped:
                order_seq.append(name)
                grouped[name] = {
                    "id": name.lstrip("#"),
                    "name": name,
                    "tags": row.get(COLUMN_MAP["tags"], "") or "",
                    "customer": {"first_name": row.get(COLUMN_MAP["customer_first"], ""),
                                 "last_name": ""},
                    "phone": row.get(COLUMN_MAP["phone"], ""),
                    "note_attributes": [],
                    "line_items": [],
                }
            grouped[name]["line_items"].append({
                "id": f"{name}_{len(grouped[name]['line_items'])}",
                "sku": row.get(COLUMN_MAP["sku"], "") or "",
                "title": row.get(COLUMN_MAP["title"], "") or "",
                "quantity": int(row.get(COLUMN_MAP["qty"], "0") or 0),
                "properties": [],
            })

    orders = [grouped[name] for name in order_seq]
    payload = {
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "source": "csv_import",
        "shop_domain": "",
        "api_version": "",
        "filter": {"note": "csv_import — no server-side filtering applied"},
        "order_count": len(orders),
        "orders": orders,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    tmp.replace(out_path)
    return out_path
