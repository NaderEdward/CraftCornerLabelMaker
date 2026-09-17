from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core import settings as core_settings
from shopify.client import (
    ShopifyClient, credentials_configured, _normalise_gql_order,
    _is_unfulfilled, _ORDERS_QUERY, _fulfillment_block_reason,
    _PRINTABLE_FULFILLMENT_STATUSES, _KNOWN_NONPRINTABLE_STATUSES,
    _OPEN_FULFILLMENT_ORDER_STATUS,
)
from shopify.ingest import _EXCLUDE_TAGS, _order_tags, _normalise_tag

OUT_DIR = Path(__file__).parent / "diagnostics"


def main() -> int:
    if not credentials_configured():
        print("ERROR: No Shopify credentials. Open the app -> Settings.")
        return 1

    cfg = core_settings.load()
    domain = cfg.get("shopify_domain", "")
    version = cfg.get("shopify_api_version", "2026-07")
    if not domain:
        print("ERROR: Shop domain not set.")
        return 1

    client = ShopifyClient(domain, version)
    ok, msg = client.test_connection()
    if not ok:
        print(f"ERROR: {msg}")
        return 1

    print("=" * 74)
    print("ORDER FILTER DIAGNOSTIC")
    print("=" * 74)
    print(f"Store:   {domain}")
    print(f"Version: {version}")
    print()
    print(f"Printable statuses : {sorted(_PRINTABLE_FULFILLMENT_STATUSES)}")
    print(f"Required FO.status     : {_OPEN_FULFILLMENT_ORDER_STATUS.upper()} (IN_PROGRESS = Ready for pickup)")
    print(f"Exclude tags       : {sorted(_EXCLUDE_TAGS)}")
    print()

    print("Fetching ALL open orders (no filters applied)...")
    print()

    rows = []
    cursor = None
    while True:
        data = client._graphql(_ORDERS_QUERY,
                               {"cursor": cursor, "queryStr": "status:open"})
        conn = data.get("orders", {})
        for edge in conn.get("edges", []):
            node = edge.get("node", {})
            raw_status = node.get("displayFulfillmentStatus")
            order = _normalise_gql_order(node)

            status_ok = _is_unfulfilled(order)
            tags = _order_tags(order)
            blocking = tags.intersection(
                {_normalise_tag(t) for t in _EXCLUDE_TAGS}
            )

            fo_reason = _fulfillment_block_reason(order)
            reasons = []
            if not status_ok:
                if fo_reason:
                    reasons.append(fo_reason)
                else:
                    known = (order["fulfillment_status"]
                             in _KNOWN_NONPRINTABLE_STATUSES)
                    label = "" if known else "  <-- UNRECOGNISED STATUS"
                    reasons.append(
                        f"status={raw_status or '(absent)'}{label}")
            if blocking:
                reasons.append(f"tags={sorted(blocking)}")

            rows.append({
                "order": order.get("name", "?"),
                "raw_status": raw_status,
                "raw_tags": node.get("tags") or [],
                "fulfillment_orders": [
                    {"status": f.get("status"),
                     "requestStatus": f.get("requestStatus"),
                     "holds": [h.get("reason") for h in (f.get("fulfillmentHolds") or [])]}
                    for f in order.get("fulfillment_orders", [])
                ],
                "would_process": not reasons,
                "reasons": reasons,
            })

        page = conn.get("pageInfo", {})
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")

    kept = [r for r in rows if r["would_process"]]
    dropped = [r for r in rows if not r["would_process"]]

    print(f"Total open orders : {len(rows)}")
    print(f"WOULD PROCESS     : {len(kept)}")
    print(f"WOULD SKIP        : {len(dropped)}")
    print()

    print("-" * 74)
    print("WOULD PROCESS")
    print("-" * 74)
    for r in kept:
        fos = ",".join(
            str(f["status"]) for f in r["fulfillment_orders"]) or "-"
        print(f"  {r['order']:<10} status={str(r['raw_status']):<14} "
              f"FO.status={fos:<24} tags={r['raw_tags']}")
    if not kept:
        print("  (none)")
    print()

    print("-" * 74)
    print("WOULD SKIP")
    print("-" * 74)
    for r in dropped:
        print(f"  {r['order']:<10} {'; '.join(r['reasons'])}")
        print(f"  {'':<10} raw tags: {r['raw_tags']}")
        if r["fulfillment_orders"]:
            print(f"  {'':<10} fulfillmentOrders: {r['fulfillment_orders']}")
    if not dropped:
        print("  (none)")
    print()

    unknown = sorted({
        r["raw_status"] for r in rows
        if r["raw_status"]
        and r["raw_status"].lower() not in _PRINTABLE_FULFILLMENT_STATUSES
        and r["raw_status"].lower() not in _KNOWN_NONPRINTABLE_STATUSES
    })
    if unknown:
        print("!" * 74)
        print("UNRECOGNISED FULFILLMENT STATUSES FOUND:")
        for u in unknown:
            print(f"   {u}")
        print("These are being SKIPPED (fail-safe). If any should be")
        print("printed, add it to _PRINTABLE_FULFILLMENT_STATUSES in")
        print("shopify/client.py.")
        print("!" * 74)
        print()

    all_tags = sorted({t for r in rows for t in r["raw_tags"]})
    print("Every tag seen across all open orders:")
    for t in all_tags:
        marker = "  <-- EXCLUDES" if _normalise_tag(t) in {
            _normalise_tag(x) for x in _EXCLUDE_TAGS} else ""
        print(f"   {t!r}{marker}")
    print()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUT_DIR / f"order_filter_{stamp}.json"
    import json
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print(f"Full detail written to: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
