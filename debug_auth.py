import requests
import sys

print("=" * 60)
print("Shopify Credential Debug Tool")
print("=" * 60)
print()

shop_domain   = input("Shop domain (e.g. thecraftcorner-eg.myshopify.com): ").strip()
client_id     = input("Client ID: ").strip()
client_secret = input("Client Secret: ").strip()
api_version   = input("API version (press Enter for 2026-07): ").strip() or "2026-07"

print()
print("-" * 60)
print("STEP 1 — Requesting token from Shopify...")
print()

token_url = f"https://{shop_domain}/admin/oauth/access_token"
print(f"  POST {token_url}")
print()

try:
    resp = requests.post(token_url, data={
        "grant_type":    "client_credentials",
        "client_id":     client_id,
        "client_secret": client_secret,
    }, timeout=30)
except requests.RequestException as e:
    print(f"  CONNECTION ERROR: {e}")
    print()
    print("  The shop domain is wrong or there is no internet.")
    input("Press Enter to close...")
    sys.exit(1)

print(f"  HTTP status: {resp.status_code}")
print(f"  Response:    {resp.text[:500]}")
print()

if resp.status_code != 200:
    print("FAILED at token step.")
    print()
    if resp.status_code == 401:
        print("  Shopify says: Unauthorized")
        print()
        print("  Most likely causes:")
        print("  1. App not installed on the store")
        print("     Go to dev.shopify.com/dashboard -> your app -> Install")
        print("  2. Wrong client_id or client_secret")
        print("     Copy them fresh from Dev Dashboard -> API credentials")
        print("  3. App created in wrong place (must be dev.shopify.com)")
    elif resp.status_code == 404:
        print("  Shop domain is wrong or the store does not exist.")
    else:
        print(f"  Unexpected status {resp.status_code}")
    input("Press Enter to close...")
    sys.exit(1)

token      = resp.json().get("access_token")
expires_in = resp.json().get("expires_in", "unknown")
print(f"  Token received: {token[:12]}... (expires in {expires_in}s)")
print()

print("-" * 60)
print("STEP 2 — Testing token against the shop endpoint...")
print()

shop_url = f"https://{shop_domain}/admin/api/{api_version}/shop.json"
print(f"  GET {shop_url}")
print()

try:
    resp2 = requests.get(shop_url, headers={
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }, timeout=30)
except requests.RequestException as e:
    print(f"  CONNECTION ERROR: {e}")
    input("Press Enter to close...")
    sys.exit(1)

print(f"  HTTP status: {resp2.status_code}")
print(f"  Response:    {resp2.text[:300]}")
print()

if resp2.status_code == 200:
    shop_name = resp2.json().get("shop", {}).get("name", "?")
    print("=" * 60)
    print(f"  SUCCESS — Connected to '{shop_name}'")
    print("  Credentials work. Re-enter them in Settings and save.")
    print("=" * 60)
elif resp2.status_code == 401:
    print("  Token issued but rejected on use.")
    print("  Check that read_orders scope is ticked in the Dev Dashboard.")
elif resp2.status_code == 404:
    print(f"  API version '{api_version}' not found.")
    print("  Try 2025-04 or 2025-01")
else:
    print(f"  Unexpected: {resp2.status_code}")

print()
input("Press Enter to close...")
