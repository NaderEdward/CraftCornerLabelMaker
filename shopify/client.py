from __future__ import annotations

import time
from typing import Any, Dict, Iterator, List, Optional, Tuple
import re

import requests

KEYRING_SERVICE  = "craftcorner_labelmaker"
KEY_CLIENT_ID     = "shopify_client_id"
KEY_CLIENT_SECRET = "shopify_client_secret"
KEY_STATIC_TOKEN  = "shopify_access_token"

_token_cache: Dict[str, Any] = {
    "token": None,
    "expires_at": 0.0,
}

_EXPIRY_BUFFER_SECONDS = 300


def _401_help(shop_domain: str, resp=None) -> str:
    mode = auth_mode()
    body = ""
    if resp is not None:
        try:
            body = resp.text[:200].strip()
        except Exception:
            body = ""

    lines = [
        f"Shopify rejected the request (401) for {shop_domain}.",
        f"Credential mode in use: {mode}.",
    ]
    if mode == "static":
        lines.append(
            "A legacy static shpat_ token is stored. Since 1 Jan 2026 these "
            "are not issued for new apps and old ones are often revoked. "
            "Clear it in Settings and enter your Client ID + Client Secret "
            "from the Dev Dashboard instead."
        )
    elif mode == "oauth":
        lines.append(
            "Client credentials were accepted for the token, but the token "
            "was refused by the Admin API. Usual causes: (1) the app is not "
            "installed on this store, (2) the app is missing the read_orders "
            "scope (and write_orders for tagging), or (3) the Client ID/Secret "
            "belong to a different store."
        )
    else:
        lines.append("No credentials are stored. Enter them in Settings.")
    if body:
        lines.append(f"Shopify said: {body}")
    return " ".join(lines)


class ShopifyAPIError(RuntimeError):
    pass


class ShopifyAuthError(ShopifyAPIError):
    pass


def store_client_credentials(client_id: str, client_secret: str) -> None:
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, KEY_CLIENT_ID,     client_id.strip())
        keyring.set_password(KEYRING_SERVICE, KEY_CLIENT_SECRET, client_secret.strip())
    except Exception as e:
        raise ShopifyAuthError(
            f"Could not save credentials to the OS keychain: {e}"
        ) from e
    _token_cache["token"]      = None
    _token_cache["expires_at"] = 0.0


def _keyring_get(key: str) -> Optional[str]:
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, key)
    except Exception:
        return None


def keyring_available() -> bool:
    try:
        import keyring
        keyring.get_password(KEYRING_SERVICE, "__probe__")
        return True
    except Exception:
        return False


def get_client_credentials() -> Tuple[Optional[str], Optional[str]]:
    return _keyring_get(KEY_CLIENT_ID), _keyring_get(KEY_CLIENT_SECRET)


def store_static_token(token: str) -> None:
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, KEY_STATIC_TOKEN, token.strip())
    except Exception as e:
        raise ShopifyAuthError(
            f"Could not save the token to the OS keychain: {e}"
        ) from e


def get_static_token() -> Optional[str]:
    return _keyring_get(KEY_STATIC_TOKEN)


def clear_all_credentials() -> None:
    import keyring
    for key in (KEY_CLIENT_ID, KEY_CLIENT_SECRET, KEY_STATIC_TOKEN):
        try:
            keyring.delete_password(KEYRING_SERVICE, key)
        except Exception:
            pass
    _token_cache["token"] = None
    _token_cache["expires_at"] = 0.0


def credentials_configured() -> bool:
    cid, sec = get_client_credentials()
    if cid and sec:
        return True
    return bool(get_static_token())


def _fetch_oauth_token(shop_domain: str, client_id: str,
                       client_secret: str) -> Tuple[str, float]:
    url = f"https://{shop_domain}/admin/oauth/access_token"
    resp = requests.post(url, data={
        "grant_type":    "client_credentials",
        "client_id":     client_id,
        "client_secret": client_secret,
    }, timeout=30)

    if resp.status_code in (400, 401):
        raise ShopifyAuthError(
            f"Shopify rejected the client credentials (HTTP {resp.status_code}). "
            f"Check that client_id and client_secret are correct and that the "
            f"app is installed on the store."
        )
    if resp.status_code != 200:
        raise ShopifyAPIError(
            f"Token request failed with HTTP {resp.status_code}: {resp.text[:200]}"
        )

    data = resp.json()
    token      = data["access_token"]
    expires_in = int(data.get("expires_in", 86399))
    expires_at = time.time() + expires_in - _EXPIRY_BUFFER_SECONDS
    return token, expires_at


def get_active_token(shop_domain: str, force_refresh: bool = False) -> str:
    cid, sec = get_client_credentials()

    if cid and sec:
        if (not force_refresh
                and _token_cache["token"]
                and time.time() < _token_cache["expires_at"]):
            return _token_cache["token"]

        token, expires_at = _fetch_oauth_token(shop_domain, cid, sec)
        _token_cache["token"]      = token
        _token_cache["expires_at"] = expires_at
        return token

    static = get_static_token()
    if static:
        return static

    raise ShopifyAuthError(
        "No Shopify credentials configured. Enter your Client ID and "
        "Client Secret (Dev Dashboard → app Settings) in the Settings tab."
    )


def auth_mode() -> str:
    cid, sec = get_client_credentials()
    if cid and sec:
        return "oauth"
    if get_static_token():
        return "static"
    return "none"


def _parse_link_header(link_header: str) -> Dict[str, str]:
    links: Dict[str, str] = {}
    if not link_header:
        return links
    for part in link_header.split(","):
        m = re.match(r'\s*<([^>]+)>;\s*rel="([^"]+)"', part)
        if m:
            links[m.group(2)] = m.group(1)
    return links


def _gid_to_id(gid: str) -> str:
    return gid.rsplit("/", 1)[-1] if gid.startswith("gid://") else gid


def _normalise_gql_order(node: dict) -> dict:
    tags_list = node.get("tags") or []

    gql_line_items = [
        e["node"] for e in (node.get("lineItems") or {}).get("edges", [])
    ]
    rest_line_items = []
    for li in gql_line_items:
        raw_title = li.get("title", "")

        variant = li.get("variant") or {}
        variant_title = variant.get("title", "")
        if not variant_title:
            if " - " in raw_title:
                raw_title, variant_title = raw_title.split(" - ", 1)
                raw_title = raw_title.strip()
                variant_title = variant_title.strip()

        custom_attrs = li.get("customAttributes") or []
        rest_properties = [
            {"name": a.get("key", ""), "value": a.get("value", "")}
            for a in custom_attrs
            if a.get("key")
        ]

        rest_line_items.append({
            "id":            li.get("id", ""),
            "title":         raw_title.strip(),
            "variant_title": variant_title.strip(),
            "quantity":      li.get("quantity", 1),
            "properties":    rest_properties,
        })

    cust = node.get("customer") or {}
    rest_customer = {
        "first_name": cust.get("firstName", ""),
        "last_name":  cust.get("lastName", ""),
        "email":      cust.get("email", ""),
    }

    addr = node.get("shippingAddress") or {}
    rest_addr = {"name": addr.get("name", "")}

    name = node.get("name", "")
    try:
        order_number = int(name.lstrip("#"))
    except (ValueError, AttributeError):
        order_number = name

    return {
        "id":                  _gid_to_id(node.get("id", "")),
        "gid":                 node.get("id", ""),
        "name":                name,
        "order_number":        order_number,
        "tags":                ", ".join(tags_list),
        "fulfillment_status":  (node.get("displayFulfillmentStatus") or "").lower(),
        "fulfillment_orders":  [
            e["node"]
            for e in (node.get("fulfillmentOrders") or {}).get("edges", [])
        ],
        "customer":            rest_customer,
        "shipping_address":    rest_addr,
        "line_items":          rest_line_items,
        "note_attributes":     [
            {"name": a.get("key", ""), "value": a.get("value", "")}
            for a in (node.get("customAttributes") or [])
            if a.get("key")
        ],
        "note":                node.get("note") or "",
        "_raw_gql":            node,
    }


_PRINTABLE_FULFILLMENT_STATUSES = frozenset({"unfulfilled"})

_KNOWN_NONPRINTABLE_STATUSES = frozenset({
    "fulfilled", "partially_fulfilled", "partial", "restocked",
    "ready_for_pickup", "in_progress", "on_hold", "scheduled",
    "pending_fulfillment", "open", "expired", "unshipped",
})


_OPEN_FULFILLMENT_ORDER_STATUS = "open"

_KNOWN_FULFILLMENT_ORDER_STATUSES = frozenset({
    "open", "in_progress", "closed", "cancelled",
    "scheduled", "on_hold", "incomplete",
})


def _fulfillment_block_reason(order: dict) -> Optional[str]:
    for fo in order.get("fulfillment_orders", []):
        holds = fo.get("fulfillmentHolds") or []
        if holds:
            reasons = ", ".join(str(h.get("reason", "?")) for h in holds)
            return f"fulfillmentOrder on hold ({reasons})"

        status = (fo.get("status") or "").lower().strip()
        if status != _OPEN_FULFILLMENT_ORDER_STATUS:
            label = "" if status in _KNOWN_FULFILLMENT_ORDER_STATUSES else " (unrecognised)"
            shown = status or "(absent)"
            if status == "in_progress":
                return f"fulfillmentOrder.status={shown} (Ready for pickup)"
            return f"fulfillmentOrder.status={shown}{label}"
    return None


def _is_unfulfilled(order: dict) -> bool:
    status = (order.get("fulfillment_status") or "").lower().strip()
    if status not in _PRINTABLE_FULFILLMENT_STATUSES:
        return False
    return _fulfillment_block_reason(order) is None


_ORDERS_QUERY = """
query GetOrders($cursor: String, $queryStr: String) {
  orders(first: 50, after: $cursor, query: $queryStr) {
    edges {
      node {
        id
        name
        tags
        displayFulfillmentStatus
        createdAt
        fulfillmentOrders(first: 10) {
          edges {
            node {
              status
              requestStatus
              fulfillmentHolds {
                reason
              }
            }
          }
        }
        customer {
          firstName
          lastName
          email
        }
        shippingAddress {
          name
        }
        lineItems(first: 50) {
          edges {
            node {
              id
              title
              quantity
              customAttributes {
                key
                value
              }
              variant {
                title
              }
            }
          }
        }
        customAttributes {
          key
          value
        }
        note
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""


class ShopifyClient:
    def __init__(self, shop_domain: str, api_version: str = "2025-04",
                 timeout: int = 30):
        self.shop_domain = shop_domain
        self.api_version = api_version
        self.timeout     = timeout
        self._session    = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def _base_url(self) -> str:
        return f"https://{self.shop_domain}/admin/api/{self.api_version}"

    def _auth_header(self) -> str:
        return get_active_token(self.shop_domain)

    def test_connection(self) -> Tuple[bool, str]:
        try:
            token = get_active_token(self.shop_domain)
        except ShopifyAuthError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Could not get token: {e}"

        try:
            resp = self._session.get(
                f"{self._base_url()}/shop.json",
                headers={"X-Shopify-Access-Token": token},
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            return False, f"Connection failed: {e}"

        if resp.status_code == 401:
            return False, _401_help(self.shop_domain, resp)
        if resp.status_code == 404:
            return False, (
                f"Not found (404) — check the API version "
                f"'{self.api_version}' is supported by your store."
            )
        if resp.status_code != 200:
            return False, f"Unexpected status {resp.status_code}: {resp.text[:200]}"

        shop_name = resp.json().get("shop", {}).get("name", "?")
        return True, f"Connected to '{shop_name}'"

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        backoffs = [1, 2, 4]
        attempt  = 0
        token_refreshed = False

        while True:
            token = get_active_token(self.shop_domain,
                                     force_refresh=token_refreshed)
            kwargs.setdefault("headers", {})
            kwargs["headers"]["X-Shopify-Access-Token"] = token

            try:
                resp = self._session.request(method, url,
                                             timeout=self.timeout, **kwargs)
            except requests.RequestException as e:
                if attempt >= len(backoffs):
                    raise ShopifyAPIError(f"Request failed after retries: {e}") from e
                time.sleep(backoffs[attempt])
                attempt += 1
                continue

            if resp.status_code == 401:
                if not token_refreshed:
                    _token_cache["token"]      = None
                    _token_cache["expires_at"] = 0.0
                    token_refreshed = True
                    continue
                raise ShopifyAuthError(_401_help(self.shop_domain, resp))

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "1"))
                time.sleep(retry_after)
                attempt += 1
                if attempt > 3:
                    raise ShopifyAPIError("429 Too Many Requests — exhausted retries.")
                continue

            if resp.status_code >= 500:
                if attempt >= len(backoffs):
                    raise ShopifyAPIError(
                        f"{resp.status_code} server error — exhausted retries."
                    )
                time.sleep(backoffs[attempt])
                attempt += 1
                continue

            limit_header = resp.headers.get("X-Shopify-Shop-Api-Call-Limit")
            if limit_header:
                try:
                    used, cap = (int(x) for x in limit_header.split("/"))
                    if cap and used / cap > 0.8:
                        time.sleep(0.5)
                except ValueError:
                    pass

            return resp

    def _graphql(self, query: str, variables: dict) -> dict:
        url = f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json"
        resp = self._request_with_retry(
            "POST", url,
            json={"query": query, "variables": variables},
        )
        if resp.status_code != 200:
            raise ShopifyAPIError(
                f"GraphQL request failed ({resp.status_code}): {resp.text[:300]}"
            )
        body = resp.json()
        if "errors" in body:
            raise ShopifyAPIError(
                f"GraphQL errors: {body['errors']}"
            )
        return body.get("data", {})

    def iter_orders(self, status: str = "open",
                    fulfillment_status: str = "unshipped",
                    limit: int = 250, **extra_filters) -> Iterator[dict]:
        from shopify.ingest import _EXCLUDE_TAGS

        def _tag_exclude_clauses(tag: str) -> list:
            base = tag.replace("-", " ").replace("_", " ")
            variants = {
                base,
                base.replace(" ", "-"),
                base.replace(" ", "_"),
                base.replace(" ", ""),
                tag,
            }
            return [f'-tag:"{v}"' for v in sorted(variants)]

        exclude_tag_clauses = " ".join(
            clause
            for t in sorted(_EXCLUDE_TAGS)
            for clause in _tag_exclude_clauses(t)
        )
        query_str = (
            f"fulfillment_status:unfulfilled status:open"
            f" -fulfillment_status:ready_for_pickup"
            f" {exclude_tag_clauses}"
        )

        cursor: Optional[str] = None
        while True:
            data = self._graphql(
                _ORDERS_QUERY,
                {"cursor": cursor, "queryStr": query_str},
            )
            connection = data.get("orders", {})
            for edge in connection.get("edges", []):
                node = edge.get("node", {})
                order = _normalise_gql_order(node)
                if not _is_unfulfilled(order):
                    continue
                yield order

            page_info = connection.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")


    def tag_order(self, order_id: str, add_tags: List[str],
                  remove_tags: Optional[List[str]] = None) -> None:
        get_url = f"{self._base_url()}/orders/{order_id}.json"
        resp = self._request_with_retry("GET", get_url,
                                        params={"fields": "id,tags"})
        if resp.status_code != 200:
            raise ShopifyAPIError(f"Could not fetch order {order_id} for tagging")

        current  = resp.json()["order"].get("tags", "") or ""
        existing_lower = {t.strip().lower() for t in current.split(",") if t.strip()}
        existing_list  = [t.strip() for t in current.split(",") if t.strip()]

        remove_lower = {t.strip().lower() for t in (remove_tags or [])}
        kept = [t for t in existing_list if t.lower() not in remove_lower]

        kept_lower = {t.lower() for t in kept}
        to_add = [t for t in add_tags if t.strip().lower() not in kept_lower]

        new_tag_list = kept + to_add
        if sorted(t.lower() for t in new_tag_list) == sorted(existing_lower):
            return

        new_tags = ", ".join(new_tag_list)
        resp = self._request_with_retry(
            "PUT",
            f"{self._base_url()}/orders/{order_id}.json",
            json={"order": {"id": int(order_id), "tags": new_tags}},
        )
        if resp.status_code != 200:
            raise ShopifyAPIError(
                f"Could not tag order {order_id}: {resp.text[:300]}"
            )
