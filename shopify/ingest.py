from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

from shopify.client import (ShopifyClient, _is_unfulfilled,
                            _fulfillment_block_reason)

TAG_DONE    = "AI-Done"
TAG_FLAGGED = "AI-Flagged"

_EXCLUDE_TAGS = frozenset(["in-progress", TAG_DONE, TAG_FLAGGED])


def _normalise_tag(tag: str) -> str:
    lowered = tag.strip().lower()
    for sep in ("-", "_"):
        lowered = lowered.replace(sep, " ")
    return " ".join(lowered.split())


def _order_tags(order: Dict[str, Any]) -> Set[str]:
    raw = order.get("tags", "") or ""
    return {_normalise_tag(t) for t in raw.split(",") if t.strip()}


def _is_eligible(order: Dict[str, Any]) -> bool:
    tags = _order_tags(order)
    return not tags.intersection({_normalise_tag(t) for t in _EXCLUDE_TAGS})


def fetch_orders_raw(client: ShopifyClient, out_path: Path,
                     excluded_tag: str = "in-progress") -> Path:
    import logging
    log = logging.getLogger(__name__)

    all_fetched: List[Dict[str, Any]] = []
    excluded_log: List[Dict[str, Any]] = []
    orders: List[Dict[str, Any]] = []

    for order in client.iter_orders():
        all_fetched.append(order)
        num = order.get("name", order.get("id", "?"))
        status = (order.get("fulfillment_status") or "").strip()

        reasons = []
        if not _is_unfulfilled(order):
            fo_reason = _fulfillment_block_reason(order)
            if fo_reason:
                reasons.append(fo_reason)
            else:
                reasons.append(f"fulfillment_status={status or '(absent)'}")
        blocking = _order_tags(order).intersection(
            {_normalise_tag(t) for t in _EXCLUDE_TAGS}
        )
        if blocking:
            reasons.append(f"tagged: {', '.join(sorted(blocking))}")

        if reasons:
            reason = "; ".join(reasons)
            log.info("Skipping order %s — %s", num, reason)
            excluded_log.append({
                "order": num, "reason": reason,
                "fulfillment_status": status,
                "tags": order.get("tags", ""),
            })
        else:
            orders.append(order)

    log.info(
        "Fetch complete: %d returned by API, %d eligible, %d excluded",
        len(all_fetched), len(orders), len(excluded_log),
    )

    payload = {
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "source": "shopify_graphql",
        "shop_domain": client.shop_domain,
        "api_version": client.api_version,
        "filter": {
            "status": "open",
            "fulfillment_status": "unfulfilled",
            "exclude_tags": sorted(_EXCLUDE_TAGS),
        },
        "order_count": len(orders),
        "excluded_count": len(excluded_log),
        "excluded": excluded_log,
        "orders": orders,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    tmp.replace(out_path)
    return out_path


def load_orders_raw(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
