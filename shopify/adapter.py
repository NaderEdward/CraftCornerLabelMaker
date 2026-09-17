from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))
from ShopifyParser import ShopifyLabelParser

from shopify.normalise import normalise_student_key, detect_script
from shopify.validate import Flag
from core import template_selector as tpl_sel
from core import templates as core_templates
from core.theme_map import lookup as theme_lookup, NAME_CUTOUT
from shopify import packs


NAME_CUTOUT_LUNCH_TAG_TEMPLATE = "name_cutout_lunch_tag"
NAME_CUTOUT_LUNCH_TAG_REGION = "lunch_tag"


def run_parser(raw_orders: Dict[str, Any], run_dir: Path) -> List[Dict[str, Any]]:
    parser = ShopifyLabelParser()
    normalized = parser.parse(raw_orders)

    out = run_dir / "normalized_orders.json"
    out.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return normalized


def run_filter(run_dir: Path) -> List[Dict[str, Any]]:
    order_filter_path = Path(__file__).parent.parent / "OrderFilter.py"

    subprocess.run(
        [sys.executable, str(order_filter_path)],
        cwd=str(run_dir),
        check=True,
        capture_output=True,
    )

    clean  = json.loads((run_dir / "clean_orders.json").read_text(encoding="utf-8"))
    review = json.loads((run_dir / "manual_review_orders.json").read_text(encoding="utf-8"))

    for item in review:
        item.setdefault("_review_reasons", [])

    return clean + review


def _build_order_lookup(raw_orders: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    lookup: Dict[str, Dict[str, str]] = {}
    for o in raw_orders.get("orders", []):
        num = str(o.get("name", o.get("order_number", "")))
        cust = o.get("customer") or {}
        full_name = (
            f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip()
            or (o.get("shipping_address") or {}).get("name", "")
        )
        lookup[num] = {
            "order_id": str(o.get("id", num)),
            "customer_name": full_name,
        }
    return lookup


def _flags_from_review_reasons(reasons: List[str]) -> List[Dict[str, Any]]:
    return [
        {"kind": "REVIEW_REQUIRED", "severity": "warning", "detail": r, "field": ""}
        for r in reasons
    ]


def _derive_name_fields(rep: dict) -> dict:
    full_name  = rep.get("name", "").strip()
    first_name = rep.get("first_name", "").strip()
    nickname   = rep.get("nickname", "").strip()
    initials   = rep.get("initials", "").strip()

    if not full_name and first_name:
        full_name = first_name

    return {
        "full_name":  full_name,
        "first_name": first_name,
        "nickname":   nickname,
        "initials":   initials,
    }


def build_records(
    items: List[Dict[str, Any]],
    raw_orders: Dict[str, Any],
    sku_map=None,
    template_versions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    order_lookup = _build_order_lookup(raw_orders)
    transform_warnings: List[Dict[str, Any]] = []

    groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    group_meta: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    for idx, item in enumerate(items):
        order_num    = str(item.get("order_number", ""))
        raw_name     = str(item.get("name", "")).strip()
        theme        = str(item.get("theme", "")).strip()
        product      = str(item.get("product", "")).strip()
        qty          = int(item.get("quantity") or 1)
        arabic_name  = str(item.get("arabic_name", "")).strip()
        class_val    = str(item.get("class", "")).strip()
        school_val   = str(item.get("school_name", "")).strip()

        if "bag tag option" in theme.lower():
            continue

        ttype, reason = theme_lookup(theme)

        if reason == "BLOCKED_THEME":
            transform_warnings.append({
                "order_number": order_num, "kind": "BLOCKED_THEME",
                "detail": (
                    f"Theme '{theme}' is permanently blocked from auto-processing "
                    "(teenage era / jeans). Handle this order manually."
                ),
                "line_item_id": f"{order_num}-{idx}",
            })
            continue

        if reason == "NAME_THEME":
            transform_warnings.append({
                "order_number": order_num, "kind": "NAME_THEME",
                "detail": f"Theme '{theme}' requires manual rendering — skipped.",
                "line_item_id": f"{order_num}-{idx}",
            })
            continue

        if reason == "UNKNOWN_THEME":
            transform_warnings.append({
                "order_number": order_num, "kind": "UNKNOWN_THEME",
                "detail": (
                    f"Theme '{ascii(theme)}' is not in themes_list.json. "
                    "Add it to the correct category in the file, or handle manually."
                ),
                "line_item_id": f"{order_num}-{idx}",
            })
            continue

        if ttype == NAME_CUTOUT:
            _nf_check = _derive_name_fields(item)
            _arabic_fields = [
                label for label, val in (
                    ("Name",         _nf_check["full_name"]),
                    ("First Name",   _nf_check["first_name"]),
                    ("Nickname",     _nf_check["nickname"]),
                    ("Initials",     _nf_check["initials"]),
                    ("Arabic Name",  arabic_name),
                )
                if val and detect_script(val) in ("arabic", "mixed")
            ]
            if _arabic_fields:
                transform_warnings.append({
                    "order_number": order_num, "kind": "NAME_CUTOUT_ARABIC",
                    "severity": "critical",
                    "detail": (
                        f"name_cutout theme '{theme}' has Arabic content in "
                        f"{', '.join(_arabic_fields)} — no name_cutout template "
                        "supports Arabic. Handle this order manually."
                    ),
                    "line_item_id": f"{order_num}-{idx}",
                })
                continue

        from regions import model as region_model

        def _template_for(is_extras_sheet):
            if ttype == NAME_CUTOUT:
                _nf = _derive_name_fields(item)
                return tpl_sel.select_name_cutout(
                    has_first    = bool(_nf["first_name"]),
                    has_nickname = bool(_nf["nickname"]),
                    has_initials = bool(_nf["initials"]),
                    has_arabic   = bool(arabic_name),
                )
            return tpl_sel.select(
                template_type=ttype,
                has_arabic=bool(arabic_name),
                has_class=bool(class_val),
                has_school=bool(school_val),
                is_extras=is_extras_sheet,
            )

        parts = []

        if packs.is_pack(product):
            result = packs.expand(product, item, qty)

            for err in result.errors:
                transform_warnings.append({
                    "order_number": order_num, "kind": "UNKNOWN_PACK_COMPOSITION",
                    "severity": "critical", "detail": err,
                    "line_item_id": f"{order_num}-{idx}",
                })
            if not result.ok:
                continue

            for note in result.review_notes:
                item.setdefault("_review_reasons", []).append(note)

            for comp in result.components:
                if ttype == NAME_CUTOUT and comp.region_id == NAME_CUTOUT_LUNCH_TAG_REGION:
                    t = NAME_CUTOUT_LUNCH_TAG_TEMPLATE
                else:
                    t = _template_for(comp.sheet == "extras")
                if not t:
                    transform_warnings.append({
                        "order_number": order_num, "kind": "UNKNOWN_PRODUCT_VARIANT",
                        "detail": f"No {comp.sheet} template for theme type '{ttype}'.",
                        "line_item_id": f"{order_num}-{idx}",
                    })
                    continue
                parts.append((t, comp.region_id, comp.qty))

        elif packs.crops_for_individual(product, qty) is not None:
            region_id_i, crops_i, warns_i = packs.crops_for_individual(product, qty)
            for w in warns_i:
                item.setdefault("_review_reasons", []).append(w)
            t_i = _template_for(False)
            if not t_i:
                transform_warnings.append({
                    "order_number": order_num, "kind": "UNKNOWN_PRODUCT_VARIANT",
                    "detail": f"No vp template for theme type '{ttype}'.",
                    "line_item_id": f"{order_num}-{idx}",
                })
                continue
            parts.append((t_i, region_id_i, crops_i))

        else:
            product_low = product.lower()
            _lunch_region = None
            if ttype == NAME_CUTOUT:
                try:
                    _lunch_rset = region_model.load(NAME_CUTOUT_LUNCH_TAG_TEMPLATE)
                except FileNotFoundError:
                    _lunch_rset = None
                if _lunch_rset is not None:
                    _lunch_region = next(
                        (r for r in _lunch_rset.regions
                         if any(m in product_low for m in r.sku_match)),
                        None,
                    )

            if _lunch_region is not None:
                parts.append((NAME_CUTOUT_LUNCH_TAG_TEMPLATE, _lunch_region.id, qty))
            else:
                is_extras = tpl_sel.is_extras_product(product)
                tname_single = _template_for(is_extras)
                if not tname_single:
                    transform_warnings.append({
                        "order_number": order_num, "kind": "UNKNOWN_PRODUCT_VARIANT",
                        "detail": f"No template for type={ttype}, extras={is_extras}, "
                                  f"class={bool(class_val)}, school={bool(school_val)}, arabic={bool(arabic_name)}.",
                        "line_item_id": f"{order_num}-{idx}",
                    })
                    continue

                try:
                    rset = region_model.load(tname_single)
                except FileNotFoundError:
                    transform_warnings.append({
                        "order_number": order_num, "kind": "NO_REGION_SIDECAR",
                        "detail": f"No region sidecar for template '{tname_single}'.",
                        "line_item_id": f"{order_num}-{idx}",
                    })
                    continue

                matched_region = next(
                    (r for r in rset.regions
                     if any(m in product_low for m in r.sku_match)),
                    None,
                )
                if not matched_region:
                    transform_warnings.append({
                        "order_number": order_num, "kind": "UNKNOWN_PRODUCT_VARIANT",
                        "detail": f"Product '{product}' not matched in sidecar for "
                                  f"'{tname_single}'. Author a region with a matching "
                                  "sku_match string.",
                        "line_item_id": f"{order_num}-{idx}",
                    })
                    continue
                parts.append((tname_single, matched_region.id, qty))

        valid_parts = []
        for tname_p, region_id_p, qty_p in parts:
            try:
                rset_p = region_model.load(tname_p)
            except FileNotFoundError:
                transform_warnings.append({
                    "order_number": order_num, "kind": "NO_REGION_SIDECAR",
                    "detail": f"No region sidecar for template '{tname_p}'.",
                    "line_item_id": f"{order_num}-{idx}",
                })
                continue
            if not any(r.id == region_id_p for r in rset_p.regions):
                transform_warnings.append({
                    "order_number": order_num, "kind": "UNKNOWN_PRODUCT_VARIANT",
                    "detail": f"Region '{region_id_p}' (from '{product}') is not "
                              f"defined in the sidecar for '{tname_p}'.",
                    "line_item_id": f"{order_num}-{idx}",
                })
                continue
            valid_parts.append((tname_p, region_id_p, qty_p))

        if not valid_parts:
            continue

        student_key = normalise_student_key(raw_name) if raw_name else "__unattributed__"

        for part_i, (tname_p, region_id_p, qty_p) in enumerate(valid_parts):
            group_key = (order_num, student_key, tname_p, theme)
            groups[group_key].append({
                "region_id":    region_id_p,
                "qty":          qty_p,
                "sku":          "",
                "line_item_id": f"{order_num}-{idx}-{part_i}",
                "_raw":         item,
            })
            if group_key not in group_meta:
                group_meta[group_key] = item

    ORDER_CARD_REGION = "order_id"
    for gk, line_items in groups.items():
        _, _, tname_g, _ = gk
        try:
            rset_g = region_model.load(tname_g)
        except FileNotFoundError:
            continue
        has_order_region = any(r.id == ORDER_CARD_REGION for r in rset_g.regions)
        if not has_order_region:
            continue
        already_present = any(li["region_id"] == ORDER_CARD_REGION for li in line_items)
        if already_present:
            continue
        line_items.append({
            "region_id":    ORDER_CARD_REGION,
            "qty":          1,
            "sku":          "__auto_order_id__",
            "line_item_id": f"{gk[0]}-auto-order_id",
            "_raw":         group_meta[gk],
        })

    records: List[Dict[str, Any]] = []

    for (order_num, student_key, tname, _theme), line_items in groups.items():
        rep  = group_meta[(order_num, student_key, tname, _theme)]
        meta = order_lookup.get(order_num, {})

        flags = _flags_from_review_reasons(rep.get("_review_reasons") or [])
        seen  = {f["detail"] for f in flags}
        for li in line_items[1:]:
            for r in (li["_raw"].get("_review_reasons") or []):
                if r not in seen:
                    flags.append({"kind": "REVIEW_REQUIRED", "severity": "warning",
                                  "detail": r, "field": ""})
                    seen.add(r)

        theme_val = rep.get("theme", "")
        ttype_val, _ = theme_lookup(theme_val)
        is_extras_rec = tname == tpl_sel.EXTRAS_TEMPLATE
        if tname == NAME_CUTOUT_LUNCH_TAG_TEMPLATE:
            bg_path = None
        else:
            bg_path = core_templates.resolve_theme_background(
                theme_val, is_extras_rec, ttype_val or ""
            ) if ttype_val else None

        comments_val = rep.get("comments", "").strip()
        phone_val    = rep.get("phone_number", "").strip()
        is_blocked = bool(comments_val) or bool(phone_val)
        if comments_val and not any(f.get("kind") == "custom_comment" for f in flags):
            flags = list(flags) + [{"kind": "custom_comment", "severity": "info",
                                     "detail": "Custom comment — manual production required.",
                                     "field": "comments"}]
        if phone_val and not any(f.get("kind") == "phone_number_present" for f in flags):
            flags = list(flags) + [{"kind": "phone_number_present", "severity": "info",
                                     "detail": f"Phone number present ({phone_val}) — "
                                               "manual production required.",
                                     "field": "phone_number"}]

        records.append({
            "order_id":            meta.get("order_id", order_num),
            "order_number":        order_num,
            "customer_name":       meta.get("customer_name", ""),
            "student_name":        rep.get("name", ""),
            "student_name_arabic": rep.get("arabic_name", ""),
            **_derive_name_fields(rep),
            "school":              rep.get("school_name", ""),
            "grade":               rep.get("class", ""),
            "telephone":           rep.get("phone_number", ""),
            "custom_fields": {
                "theme":              theme_val,
                "template_type":      ttype_val or "",
                "main_sheet_choices": rep.get("main_sheet_choices", ""),
                "subject_choices":    rep.get("subject_choices", ""),
                "pencil_choice":      rep.get("pencil_choice", ""),
                "comments":           comments_val,
                "background_path":    str(bg_path) if bg_path else "",
                **_derive_name_fields(rep),
            },
            "template_name": tname,
            "language":      "en",
            "blocked":       is_blocked,
            "flags":         flags,
            "items": [
                {
                    "region_id":    li["region_id"],
                    "qty":          li["qty"],
                    "sku":          li["sku"],
                    "line_item_id": li["line_item_id"],
                }
                for li in line_items
            ],
        })

    from collections import Counter
    tile_counts: Counter = Counter(
        (r["order_number"], r.get("student_name")) for r in records
    )
    tile_seen: Counter = Counter()
    for r in records:
        key = (r["order_number"], r.get("student_name"))
        tile_seen[key] += 1
        if tile_counts[key] > 1:
            r["order_id_label"] = f"{r['order_number']} ({tile_seen[key]})"
        else:
            r["order_id_label"] = r["order_number"]

    return {
        "generated_at":      datetime.now(timezone.utc).astimezone().isoformat(),
        "template_versions": template_versions or {},
        "records":           records,
        "warnings":          transform_warnings,
    }


def adapt(
    raw_orders: Dict[str, Any],
    run_dir: Path,
    template_versions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    run_parser(raw_orders, run_dir)
    combined = run_filter(run_dir)
    return build_records(combined, raw_orders, template_versions=template_versions)
