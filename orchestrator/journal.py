from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


class Journal:

    def __init__(self, run_dir: Path, run_id: str):
        self.run_dir = run_dir
        self.run_id = run_id
        self.path = run_dir / "journal.json"
        self.steps: List[Dict[str, Any]] = []
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.steps = data.get("steps", [])

    def _write(self) -> None:
        payload = {"run_id": self.run_id, "steps": self.steps}
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self.path)

    def record(self, event: str, **fields: Any) -> None:
        self.steps.append({
            "t": datetime.now(timezone.utc).astimezone().isoformat(),
            "event": event,
            **fields,
        })
        self._write()

    def is_complete(self) -> bool:
        return any(s["event"] == "export_complete" for s in self.steps)

    def tagging_was_skipped(self) -> bool:
        for s in self.steps:
            if s["event"] == "export_complete":
                return bool(s.get("tagging_skipped", False))
        return False

    def sheet_numbers(self) -> List[int]:
        for s in self.steps:
            if s["event"] == "export_begin":
                return s.get("sheet_numbers", [])
        return []

    def order_ids(self) -> List[str]:
        for s in self.steps:
            if s["event"] == "export_begin":
                return s.get("order_ids", [])
        return []

    def tagged_order_ids(self) -> List[str]:
        return [s["order_id"] for s in self.steps if s["event"] == "tag_ok"]

    def written_sheet_numbers(self) -> List[int]:
        return [s["sheet_number"] for s in self.steps if s["event"] == "sheet_written"]

    def untagged_order_ids(self) -> List[str]:
        tagged = set(self.tagged_order_ids())
        return [oid for oid in self.order_ids() if oid not in tagged]


def find_incomplete_runs(runs_root: Path, limit: int = 20) -> List[Journal]:
    incomplete: List[Journal] = []
    if not runs_root.exists():
        return incomplete
    run_dirs = sorted(runs_root.iterdir(), key=lambda p: p.name, reverse=True)[:limit]
    for d in run_dirs:
        journal_path = d / "journal.json"
        if journal_path.exists():
            j = Journal(d, d.name)
            if not j.is_complete():
                incomplete.append(j)
    return incomplete
