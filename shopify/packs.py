from __future__ import annotations

import json
from dataclasses import dataclass
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PACK_COUNT_RE = re.compile(r"\((\d+)\s*pack\)", re.IGNORECASE)


@dataclass(frozen=True)
class Component:
    region_id: str
    qty: int
    sheet: str


@dataclass
class ExpansionResult:
    components: List[Component]
    errors: List[str]
    review_notes: List[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def _norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


@lru_cache(maxsize=1)
def _config() -> Dict[str, Any]:
    from core import paths
    p = paths.app_root() / "data" / "pack_composition.json"
    if not p.exists():
        return {"packs": {}, "choice_fields": {}, "sheet_of_region": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def invalidate_cache() -> None:
    _config.cache_clear()


def match_pack(product: str) -> Optional[str]:
    low = _norm(product)
    for key in _config().get("packs", {}):
        if key in low:
            return key
    return None


def is_pack(product: str) -> bool:
    return match_pack(product) is not None


def label_count_in_title(product: str) -> Optional[int]:
    m = _PACK_COUNT_RE.search(product or "")
    return int(m.group(1)) if m else None


def match_individual(product: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    low = _norm(product)
    for key, spec in _config().get("individual_products", {}).items():
        if key.startswith("_"):
            continue
        if key in low:
            return key, spec
    return None


def crops_for_individual(product: str, qty: int = 1) -> Optional[Tuple[str, int, List[str]]]:
    hit = match_individual(product)
    if hit is None:
        return None
    _key, spec = hit
    region = spec["region"]
    warnings: List[str] = []

    if not spec.get("count_from_title"):
        return region, max(1, qty), warnings

    per = int(_config().get("labels_per_region", {}).get(region, 1))
    total = label_count_in_title(product)

    if total is None:
        warnings.append(
            f"'{product}' has no '(N pack)' count in its name — assuming one crop "
            f"of {per} label(s). Verify before cutting."
        )
        return region, max(1, qty), warnings

    crops, remainder = divmod(total, per)
    if remainder:
        crops += 1
        warnings.append(
            f"'{product}' asks for {total} labels but each crop holds {per}. "
            f"Cutting {crops} crops ({crops * per} labels) — "
            f"{crops * per - total} spare."
        )
    return region, max(1, crops) * max(1, qty), warnings


def expand(product: str, item: Dict[str, Any], qty: int = 1) -> ExpansionResult:
    cfg        = _config()
    pack_key   = match_pack(product)
    components: List[Component] = []
    errors:     List[str] = []
    notes:      List[str] = []

    if pack_key is None:
        return ExpansionResult([], [f"'{product}' is not a known pack type."], [])

    pack       = cfg["packs"][pack_key]
    sheet_of   = cfg.get("sheet_of_region", {})
    choice_cfg = cfg.get("choice_fields", {})

    totals: Dict[str, int] = {}

    def add(region: str, n: int) -> None:
        totals[region] = totals.get(region, 0) + n

    for c in pack.get("always", []):
        add(c["region"], int(c["qty"]))

    for choice_name in pack.get("choices", []):
        spec = choice_cfg.get(choice_name)
        if not spec:
            errors.append(f"Pack '{pack_key}' references unknown choice '{choice_name}'.")
            continue

        field    = spec["source_field"]
        raw      = str(item.get(field, "") or "").strip()
        options  = spec.get("options", {})

        if not raw:
            if spec.get("optional"):
                continue
            errors.append(
                f"{pack.get('label', pack_key)}: no selection for '{field}'. "
                f"Expected one of: {sorted(options)}"
            )
            continue

        chosen = options.get(_norm(raw))
        if chosen is None:
            errors.append(
                f"{pack.get('label', pack_key)}: unrecognised option for '{field}': "
                f"'{raw}'. Add it to data/pack_composition.json."
            )
            continue

        for c in chosen:
            add(c["region"], int(c["qty"]))

    if pack.get("needs_review"):
        notes.append(pack.get("review_note", f"{pack_key} contents unconfirmed."))

    for region, n in totals.items():
        sheet = sheet_of.get(region)
        if sheet is None:
            errors.append(
                f"Region '{region}' has no sheet assignment in "
                "pack_composition.json (expected 'vp' or 'extras')."
            )
            continue
        components.append(Component(region_id=region, qty=n * max(1, qty), sheet=sheet))

    components.sort(key=lambda c: (c.sheet, c.region_id))
    return ExpansionResult(components, errors, notes)


def describe(product: str, item: Dict[str, Any], qty: int = 1) -> str:
    res = expand(product, item, qty)
    if not res.ok:
        return f"{product}: " + "; ".join(res.errors)
    parts = [f"{c.region_id}×{c.qty}" for c in res.components]
    return f"{product} → " + ", ".join(parts)
