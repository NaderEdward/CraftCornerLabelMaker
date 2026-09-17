from __future__ import annotations

import json
from pathlib import Path

import pytest

from shopify.transform import build_sku_map, load_records, write_records


def test_build_sku_map_returns_dict():
    sku_map = build_sku_map(["iron ons"])
    assert isinstance(sku_map, dict)


def test_build_sku_map_known_template_has_entries():
    sku_map = build_sku_map(["iron ons"])
    for key, entries in sku_map.items():
        assert isinstance(entries, list)
        for tname, rid in entries:
            assert isinstance(tname, str) and isinstance(rid, str)


def test_build_sku_map_keys_are_lowercase():
    sku_map = build_sku_map(["iron ons"])
    for key in sku_map:
        assert key == key.lower(), f"key {key!r} is not lowercase"


def test_build_sku_map_missing_template_is_skipped():
    sku_map = build_sku_map(["__does_not_exist__"])
    assert sku_map == {}


def test_build_sku_map_collision_produces_list_with_two_entries(tmp_path, monkeypatch):
    import regions.model as rm

    calls = []

    def fake_load(tname):
        calls.append(tname)
        r = rm.ProductRegion(
            id="r1", label="L",
            rect=rm.Rect(0, 0, 100, 100),
            sku_match=["shared-sku"],
        )
        rs = rm.RegionSet(
            template_name=tname,
            template_canvas={"width": 100, "height": 100},
            template_fingerprint="",
            regions=[r],
        )
        return rs

    monkeypatch.setattr(rm, "load", fake_load)
    sku_map = build_sku_map(["t1", "t2"])
    assert len(sku_map.get("shared-sku", [])) == 2


def _sample_records():
    return {
        "generated_at": "2026-08-05T10:00:00+00:00",
        "template_versions": {},
        "records": [
            {
                "order_id": "1001",
                "order_number": "#1001",
                "customer_name": "Sarah Al-Rashidi",
                "student_name": "Ahmed",
                "student_name_arabic": "أحمد",
                "school": "Greenfield",
                "grade": "3",
                "telephone": "",
                "custom_fields": {},
                "template_name": "iron ons",
                "language": "en",
                "blocked": False,
                "flags": [],
                "items": [{"region_id": "iron_on_labels", "qty": 2,
                            "sku": "", "line_item_id": "1001-0"}],
            }
        ],
        "warnings": [],
    }


def test_write_records_creates_file(tmp_path):
    rec = _sample_records()
    out = tmp_path / "records.json"
    write_records(rec, out)
    assert out.exists()


def test_write_records_is_atomic(tmp_path):
    rec = _sample_records()
    out = tmp_path / "records.json"
    write_records(rec, out)
    tmp = out.with_suffix(".json.tmp")
    assert out.exists()
    assert not tmp.exists()


def test_load_records_round_trips(tmp_path):
    rec = _sample_records()
    out = tmp_path / "records.json"
    write_records(rec, out)
    loaded = load_records(out)
    assert loaded["records"][0]["order_id"] == "1001"
    assert loaded["records"][0]["student_name_arabic"] == "أحمد"


def test_load_records_preserves_items(tmp_path):
    rec = _sample_records()
    out = tmp_path / "records.json"
    write_records(rec, out)
    loaded = load_records(out)
    items = loaded["records"][0]["items"]
    assert len(items) == 1
    assert items[0]["region_id"] == "iron_on_labels"
    assert items[0]["qty"] == 2
