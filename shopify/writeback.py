from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from shopify.client import ShopifyClient, ShopifyAPIError
from shopify.ingest import TAG_DONE, TAG_FLAGGED


def tag_orders(client: ShopifyClient, order_ids: List[str], tag: str,
               on_each_success: Optional[Callable[[str], None]] = None,
               on_each_failure: Optional[Callable[[str, Exception], None]] = None,
               ) -> List[str]:
    succeeded: List[str] = []
    for order_id in order_ids:
        try:
            client.tag_order(order_id, [tag])
            succeeded.append(order_id)
            if on_each_success:
                on_each_success(order_id)
        except ShopifyAPIError as e:
            if on_each_failure:
                on_each_failure(order_id, e)
    return succeeded


def tag_orders_done(client: ShopifyClient, order_ids: List[str],
                    on_each_success: Optional[Callable[[str], None]] = None,
                    on_each_failure: Optional[Callable[[str, Exception], None]] = None,
                    ) -> List[str]:
    succeeded: List[str] = []
    for order_id in order_ids:
        try:
            client.tag_order(order_id, add_tags=[TAG_DONE],
                             remove_tags=[TAG_FLAGGED])
            succeeded.append(order_id)
            if on_each_success:
                on_each_success(order_id)
        except ShopifyAPIError as e:
            if on_each_failure:
                on_each_failure(order_id, e)
    return succeeded


def tag_orders_flagged(client: ShopifyClient, order_ids: List[str],
                       on_each_success: Optional[Callable[[str], None]] = None,
                       on_each_failure: Optional[Callable[[str, Exception], None]] = None,
                       ) -> List[str]:
    return tag_orders(client, order_ids, TAG_FLAGGED,
                      on_each_success=on_each_success,
                      on_each_failure=on_each_failure)


def write_manual_tag_list(order_numbers: List[str], out_path: Path,
                          action: str = "AI-Done") -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"order_number\taction\ttag\n")
        for num in order_numbers:
            f.write(f"{num}\t{action}\t{action}\n")


def write_tag_commands_file(order_ids_done: List[str],
                             order_ids_flagged: List[str],
                             out_path: Path) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("Craft Corner Label Maker — Pending Tag Actions\n")
        f.write("=" * 50 + "\n\n")
        if order_ids_done:
            f.write(f"[{TAG_DONE}] — {len(order_ids_done)} order(s)\n")
            for oid in order_ids_done:
                f.write(f"  {oid}\n")
            f.write("\n")
        if order_ids_flagged:
            f.write(f"[{TAG_FLAGGED}] — {len(order_ids_flagged)} order(s)\n")
            for oid in order_ids_flagged:
                f.write(f"  {oid}\n")
            f.write("\n")
        if not order_ids_done and not order_ids_flagged:
            f.write("(no orders to tag)\n")
