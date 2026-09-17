import sys, json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core import settings as core_settings
from shopify.client import ShopifyClient, credentials_configured

cfg = core_settings.load()

if not credentials_configured():
    print("ERROR: No Shopify credentials found.")
    print("Open the app, go to Settings, enter your credentials and save.")
    input("Press Enter to close...")
    sys.exit(1)

domain  = cfg.get("shopify_domain", "")
version = cfg.get("shopify_api_version", "2026-07")

if not domain:
    print("ERROR: Shop domain not set. Open the app -> Settings.")
    input("Press Enter to close...")
    sys.exit(1)

print("=" * 60)
print("Craft Corner — Raw API Fetch")
print("=" * 60)
print()
print("Store:   %s" % domain)
print("Version: %s" % version)
print()

client = ShopifyClient(domain, version)

ok, message = client.test_connection()
if not ok:
    print("ERROR: %s" % message)
    input("Press Enter to close...")
    sys.exit(1)
print("Connected: %s" % message)
print()

print("How many orders to fetch?")
print("  1 = just the most recent order (quickest)")
print("  10 = last 10 orders")
print("  all = everything unfulfilled (may take a moment)")
print()
choice = input("Enter 1 / 10 / all  [default: 10]: ").strip().lower() or "10"

limit = None
if choice == "all":
    limit = 250
elif choice.isdigit():
    limit = int(choice)
else:
    limit = 10

print()
print("Fetching orders...")

orders = []
for i, order in enumerate(client.iter_orders(
        status="open",
        fulfillment_status="unfulfilled",
        limit=250)):
    orders.append(order)
    print("  fetched %d orders..." % len(orders), end="\r")
    if limit and limit != 250 and len(orders) >= limit:
        break

print()
print("Fetched %d orders." % len(orders))

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
out_path  = Path(__file__).parent / ("raw_orders_%s.json" % timestamp)

with open(out_path, "w", encoding="utf-8") as f:
    json.dump({
        "fetched_at":   datetime.now().isoformat(),
        "shop_domain":  domain,
        "api_version":  version,
        "order_count":  len(orders),
        "orders":       orders,
    }, f, indent=2, ensure_ascii=False)

print()
print("Saved to: %s" % out_path.name)
print("File size: %.1f KB" % (out_path.stat().st_size / 1024))
print()

if orders:
    print("=" * 60)
    print("STRUCTURE OF FIRST ORDER  (for parsing analysis)")
    print("=" * 60)
    o = orders[0]

    def show(label, value, indent=0):
        prefix = "  " * indent
        if isinstance(value, list):
            print("%s%s: [%d items]" % (prefix, label, len(value)))
        elif isinstance(value, dict):
            print("%s%s:" % (prefix, label))
            for k, v in value.items():
                show(k, v, indent+1)
        else:
            val_str = str(value)
            if len(val_str) > 80:
                val_str = val_str[:80] + "..."
            print("%s%s: %s" % (prefix, label, val_str))

    top_skip = {'line_items','note_attributes','shipping_address',
                'billing_address','customer','tax_lines','refunds',
                'fulfillments','shipping_lines','discount_codes',
                'payment_gateway_names'}
    print("\nTop-level fields:")
    for k, v in o.items():
        if k not in top_skip:
            show(k, v, 1)

    print("\ncustomer:")
    cust = o.get("customer", {})
    for k,v in cust.items():
        if k not in {'default_address','addresses','tax_exemptions',
                     'email_marketing_consent','sms_marketing_consent'}:
            show(k, v, 1)

    print("\nnote_attributes: [%d items]" % len(o.get("note_attributes",[])))
    for na in o.get("note_attributes", []):
        print("    name=%r  value=%r" % (na.get("name"), na.get("value")))

    print("\nline_items: [%d items]" % len(o.get("line_items",[])))
    for li in o.get("line_items", []):
        print("  ---")
        li_skip = {'tax_lines','discount_allocations','duties','applied_discounts'}
        for k,v in li.items():
            if k not in li_skip:
                if k == "properties":
                    print("    properties: [%d items]" % len(v))
                    for p in v:
                        print("      name=%r  value=%r" % (p.get("name"), p.get("value")))
                else:
                    show(k, v, 2)

print()
print("=" * 60)
print("Open %s to see the complete raw JSON." % out_path.name)
print("=" * 60)
print()
input("Press Enter to close...")
