from __future__ import annotations

import json
import os
import time

from orchestrator.journal import Journal, find_incomplete_runs
from orchestrator.retention import find_prunable_runs, prune_runs

ORDERS = ["5001", "5002", "5003"]


def _run_dir(tmp_path, name="2026-08-04T14-32-05"):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _journal_through(tmp_path, stop_after: str) -> Journal:
    d = _run_dir(tmp_path)
    j = Journal(d, d.name)
    steps = [
        ("export_begin", dict(sheet_numbers=[7, 8], order_ids=ORDERS)),
        ("sheet_written", dict(sheet_number=7)),
        ("sheet_written", dict(sheet_number=8)),
        ("report_written", {}),
        ("tag_begin", dict(order_ids=ORDERS)),
        ("tag_ok", dict(order_id="5001")),
        ("tag_ok", dict(order_id="5002")),
        ("tag_ok", dict(order_id="5003")),
        ("export_complete", {}),
    ]
    for event, fields in steps:
        j.record(event, **fields)
        if event == stop_after and event != "tag_ok":
            break
    return j


def test_completed_run_is_not_flagged(tmp_path):
    _journal_through(tmp_path, "export_complete")
    assert find_incomplete_runs(tmp_path) == []


def test_crash_before_tagging_reports_all_orders_untagged(tmp_path):
    j = _journal_through(tmp_path, "report_written")
    assert not j.is_complete()
    assert j.untagged_order_ids() == ORDERS
    assert j.written_sheet_numbers() == [7, 8]


def test_crash_midway_through_tagging_reports_only_the_remainder(tmp_path):
    d = _run_dir(tmp_path)
    j = Journal(d, d.name)
    j.record("export_begin", sheet_numbers=[7], order_ids=ORDERS)
    j.record("sheet_written", sheet_number=7)
    j.record("report_written")
    j.record("tag_begin", order_ids=ORDERS)
    j.record("tag_ok", order_id="5001")

    reloaded = Journal(d, d.name)
    assert reloaded.untagged_order_ids() == ["5002", "5003"]
    assert not reloaded.is_complete()


def test_crash_before_any_sheet_written_still_detected(tmp_path):
    j = _journal_through(tmp_path, "export_begin")
    assert not j.is_complete()
    assert j.written_sheet_numbers() == []
    assert j.untagged_order_ids() == ORDERS


def test_journal_survives_reload_from_disk(tmp_path):
    d = _run_dir(tmp_path)
    j = Journal(d, d.name)
    j.record("export_begin", sheet_numbers=[7], order_ids=ORDERS)
    assert json.loads((d / "journal.json").read_text())["steps"]

    reloaded = Journal(d, d.name)
    assert reloaded.order_ids() == ORDERS


def test_find_incomplete_runs_scans_multiple_runs(tmp_path):
    _journal_through(tmp_path, "export_complete")
    d2 = _run_dir(tmp_path, "2026-08-05T09-00-00")
    j2 = Journal(d2, d2.name)
    j2.record("export_begin", sheet_numbers=[9], order_ids=["6001"])

    incomplete = find_incomplete_runs(tmp_path)
    assert [j.run_id for j in incomplete] == ["2026-08-05T09-00-00"]


def _age(path, days):
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def test_old_completed_run_is_prunable(tmp_path):
    _journal_through(tmp_path, "export_complete")
    _age(tmp_path / "2026-08-04T14-32-05", 60)
    assert len(find_prunable_runs(tmp_path, 30)) == 1


def test_recent_run_is_kept(tmp_path):
    _journal_through(tmp_path, "export_complete")
    assert find_prunable_runs(tmp_path, 30) == []


def test_old_UNFINISHED_run_is_never_pruned(tmp_path):
    _journal_through(tmp_path, "report_written")
    _age(tmp_path / "2026-08-04T14-32-05", 365)
    assert find_prunable_runs(tmp_path, 30) == []


def test_prune_actually_removes_and_reports(tmp_path):
    _journal_through(tmp_path, "export_complete")
    target = tmp_path / "2026-08-04T14-32-05"
    _age(target, 60)

    assert prune_runs(tmp_path, 30, dry_run=True) == [target.name]
    assert target.exists(), "dry run must not delete"

    assert prune_runs(tmp_path, 30) == [target.name]
    assert not target.exists()


def test_retention_disabled_when_days_is_zero(tmp_path):
    _journal_through(tmp_path, "export_complete")
    _age(tmp_path / "2026-08-04T14-32-05", 999)
    assert find_prunable_runs(tmp_path, 0) == []
