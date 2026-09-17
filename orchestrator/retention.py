from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import List

from core import logging_setup
from orchestrator.journal import Journal

log = logging_setup.get_logger()


def find_prunable_runs(runs_root: Path, retention_days: int) -> List[Path]:
    if retention_days <= 0 or not runs_root.exists():
        return []

    cutoff = time.time() - retention_days * 86400
    prunable: List[Path] = []

    for d in sorted(runs_root.iterdir()):
        if not d.is_dir():
            continue
        try:
            if d.stat().st_mtime >= cutoff:
                continue
        except OSError:
            continue

        journal_path = d / "journal.json"
        if journal_path.exists():
            try:
                if not Journal(d, d.name).is_complete():
                    log.info("Retention: keeping unfinished run %s", d.name)
                    continue
            except Exception:
                log.warning("Retention: unreadable journal in %s, keeping", d.name)
                continue

        prunable.append(d)

    return prunable


def prune_runs(runs_root: Path, retention_days: int,
               dry_run: bool = False) -> List[str]:
    removed: List[str] = []
    for d in find_prunable_runs(runs_root, retention_days):
        if dry_run:
            removed.append(d.name)
            continue
        try:
            shutil.rmtree(d)
            removed.append(d.name)
            log.info("Retention: pruned run %s", d.name)
        except OSError:
            log.warning("Retention: could not prune %s", d.name, exc_info=True)
    return removed
