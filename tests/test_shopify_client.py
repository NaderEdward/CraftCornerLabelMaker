from __future__ import annotations

import json
from pathlib import Path

import pytest

from shopify.client import (
    ShopifyClient, ShopifyAPIError, ShopifyAuthError,
    _parse_link_header, credentials_configured,
    _normalise_gql_order, _is_unfulfilled, _gid_to_id,
)
from shopify.ingest import _is_eligible, _order_tags, TAG_DONE, TAG_FLAGGED
import shopify.client as _sc
import unittest.mock as _mock

FIXTURES = Path(__file__).parent.parent / "shopify" / "fixtures"

_FAKE_TOKEN = "shpat_" + "a" * 32


@pytest.fixture(autouse=True)
def _stub_auth():
    with _mock.patch.object(_sc, "get_active_token", lambda *a, **k: _FAKE_TOKEN), \
         _mock.patch("keyring.get_password", return_value=None):
        yield


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, headers=None, text=""):
        self.status_code = status_code
        self._json = json_body if json_body is not None else {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.headers = {}

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self._responses:
            raise AssertionError(f"Unexpected extra request: {method} {url}")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def _gql_order(name="#1042", tags=None, status="UNFULFILLED"):
    return {
        "id": f"gid://shopify/Order/500{name.lstrip('#')}",
        "name": name,
        "tags": tags or [],
        "displayFulfillmentStatus": status,
        "createdAt": "2026-08-01T10:00:00Z",
        "customer": {"firstName": "Test", "lastName": "User", "email": "t@t.com"},
        "shippingAddress": {"name": "Test User"},
        "lineItems": {"edges": []},
        "customAttributes": [],
        "note": "",
    }


def _gql_page(orders, has_next=False, cursor=None):
    return {
        "data": {
            "orders": {
                "edges": [{"node": o} for o in orders],
                "pageInfo": {
                    "hasNextPage": has_next,
                    "endCursor": cursor or "abc123",
                },
            }
        }
    }


def _client(responses):
    client = ShopifyClient("shop.myshopify.com")
    client._session = FakeSession(responses)
    return client


NEXT_URL = "https://shop.myshopify.com/admin/api/2024-01/orders.json?page_info=abc"


def test_parse_link_header_extracts_next():
    header = f'<{NEXT_URL}>; rel="next"'
    assert _parse_link_header(header)["next"] == NEXT_URL


def test_parse_link_header_handles_previous_and_next():
    header = f'<https://a/prev>; rel="previous", <{NEXT_URL}>; rel="next"'
    links = _parse_link_header(header)
    assert links["next"] == NEXT_URL
    assert links["previous"] == "https://a/prev"


def test_parse_link_header_empty():
    assert _parse_link_header("") == {}


def test_gid_to_id_extracts_numeric():
    assert _gid_to_id("gid://shopify/Order/12345678") == "12345678"


def test_gid_to_id_passthrough_for_plain_id():
    assert _gid_to_id("12345678") == "12345678"


def test_normalise_gql_order_tags_are_comma_string():
    node = _gql_order(tags=["rush", "AI-Done"])
    order = _normalise_gql_order(node)
    assert "rush" in order["tags"] and "AI-Done" in order["tags"]


def test_normalise_gql_order_fulfillment_status_lowercased():
    node = _gql_order(status="UNFULFILLED")
    assert _normalise_gql_order(node)["fulfillment_status"] == "unfulfilled"


def test_normalise_gql_order_custom_attributes_mapped():
    node = _gql_order()
    node["customAttributes"] = [{"key": "Student Name", "value": "Ahmed"}]
    order = _normalise_gql_order(node)
    assert order["note_attributes"][0] == {"name": "Student Name", "value": "Ahmed"}


def test_normalise_gql_order_line_item_custom_attributes():
    node = _gql_order()
    node["lineItems"] = {"edges": [{"node": {
        "id": "gid://shopify/LineItem/1",
        "title": "Baby Minnie",
        "quantity": 2,
        "customAttributes": [{"key": "Name", "value": "Sara"}],
        "variant": {"title": "Large Labels"},
    }}]}
    order = _normalise_gql_order(node)
    li = order["line_items"][0]
    assert li["title"] == "Baby Minnie"
    assert li["variant_title"] == "Large Labels"
    assert li["properties"][0] == {"name": "Name", "value": "Sara"}


def test_is_unfulfilled_for_unfulfilled():
    assert _is_unfulfilled({"fulfillment_status": "unfulfilled"})


def test_is_unfulfilled_rejects_null_status():
    assert not _is_unfulfilled({"fulfillment_status": None})


def test_is_unfulfilled_rejects_partial():
    assert not _is_unfulfilled({"fulfillment_status": "partial"})


def test_is_not_unfulfilled_for_fulfilled():
    assert not _is_unfulfilled({"fulfillment_status": "fulfilled"})


def test_order_tags_parses_comma_string():
    assert _order_tags({"tags": "rush, AI-Done"}) == {"rush", "ai done"}


def test_order_tags_empty():
    assert _order_tags({"tags": ""}) == set()
    assert _order_tags({}) == set()


def test_is_eligible_unflagged_order():
    assert _is_eligible({"tags": "rush", "fulfillment_status": "unfulfilled"})


def test_is_eligible_blocks_ai_done():
    assert not _is_eligible({"tags": "AI-Done"})


def test_is_eligible_blocks_ai_flagged():
    assert not _is_eligible({"tags": "AI-Flagged"})


def test_is_eligible_blocks_in_progress():
    assert not _is_eligible({"tags": "in-progress"})


def test_tag_excluded_does_not_match_substring():
    order = {"tags": "not-in-progress-yet"}
    assert _is_eligible(order), "substring match must not block an eligible order"


def test_iter_orders_single_page():
    orders = [_gql_order("#1042"), _gql_order("#1043")]
    client = _client([FakeResponse(200, _gql_page(orders, has_next=False))])
    result = list(client.iter_orders())
    assert len(result) == 2
    assert result[0]["name"] == "#1042"


def test_iter_orders_follows_cursor_pagination():
    page1 = [_gql_order("#1042"), _gql_order("#1043"), _gql_order("#1044")]
    page2 = [_gql_order("#1045"), _gql_order("#1046")]
    client = _client([
        FakeResponse(200, _gql_page(page1, has_next=True, cursor="cur1")),
        FakeResponse(200, _gql_page(page2, has_next=False)),
    ])
    result = list(client.iter_orders())
    assert len(result) == 5
    assert result[-1]["name"] == "#1046"


def test_iter_orders_second_call_sends_cursor():
    page1 = [_gql_order("#1042")]
    page2 = [_gql_order("#1043")]
    client = _client([
        FakeResponse(200, _gql_page(page1, has_next=True, cursor="THECURSOR")),
        FakeResponse(200, _gql_page(page2, has_next=False)),
    ])
    list(client.iter_orders())
    second_body = client._session.calls[1][2]["json"]
    assert second_body["variables"]["cursor"] == "THECURSOR"


def test_iter_orders_skips_fulfilled_orders():
    orders = [_gql_order("#1042", status="FULFILLED"),
              _gql_order("#1043", status="UNFULFILLED")]
    client = _client([FakeResponse(200, _gql_page(orders, has_next=False))])
    result = list(client.iter_orders())
    assert len(result) == 1
    assert result[0]["name"] == "#1043"


def test_429_mid_pagination_is_retried(monkeypatch):
    monkeypatch.setattr("shopify.client.time.sleep", lambda s: None)
    page1 = [_gql_order("#1042"), _gql_order("#1043"), _gql_order("#1044")]
    page2 = [_gql_order("#1045"), _gql_order("#1046")]
    client = _client([
        FakeResponse(200, _gql_page(page1, has_next=True, cursor="c1")),
        FakeResponse(429, {}, {"Retry-After": "0"}),
        FakeResponse(200, _gql_page(page2, has_next=False)),
    ])
    result = list(client.iter_orders())
    assert len(result) == 5


def test_500_mid_pagination_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr("shopify.client.time.sleep", lambda s: None)
    page1 = [_gql_order("#1042")]
    page2 = [_gql_order("#1043")]
    client = _client([
        FakeResponse(200, _gql_page(page1, has_next=True, cursor="c1")),
        FakeResponse(500, {}, {}, "boom"),
        FakeResponse(200, _gql_page(page2, has_next=False)),
    ])
    result = list(client.iter_orders())
    assert len(result) == 2


def test_persistent_500_raises(monkeypatch):
    monkeypatch.setattr("shopify.client.time.sleep", lambda s: None)
    client = _client([FakeResponse(500, {}, {}, "boom")] * 6)
    with pytest.raises(ShopifyAPIError):
        list(client.iter_orders())


def test_401_retried_once_then_raises(monkeypatch):
    monkeypatch.setattr("shopify.client.time.sleep", lambda s: None)
    client = _client([FakeResponse(401), FakeResponse(401)])
    with pytest.raises(ShopifyAuthError):
        list(client.iter_orders())
    assert len(client._session.calls) == 2


def test_rate_limit_header_triggers_throttle(monkeypatch):
    _sc._token_cache["token"] = _FAKE_TOKEN
    _sc._token_cache["expires_at"] = float("inf")
    slept = []
    monkeypatch.setattr("shopify.client.time.sleep", lambda s: slept.append(s))
    client = _client([
        FakeResponse(200, _gql_page([], has_next=False),
                     {"X-Shopify-Shop-Api-Call-Limit": "39/40"}),
    ])
    list(client.iter_orders())
    assert slept


def test_rate_limit_below_threshold_no_throttle(monkeypatch):
    _sc._token_cache["token"] = _FAKE_TOKEN
    _sc._token_cache["expires_at"] = float("inf")
    slept = []
    monkeypatch.setattr("shopify.client.time.sleep", lambda s: slept.append(s))
    client = _client([
        FakeResponse(200, _gql_page([], has_next=False),
                     {"X-Shopify-Shop-Api-Call-Limit": "4/40"}),
    ])
    list(client.iter_orders())
    assert not slept


def test_tag_order_skips_put_when_already_tagged():
    _sc._token_cache["token"] = _FAKE_TOKEN
    _sc._token_cache["expires_at"] = float("inf")
    client = _client([
        FakeResponse(200, {"order": {"id": 1, "tags": "rush, in-progress"}}),
    ])
    client.tag_order("1", ["in-progress"])
    assert len(client._session.calls) == 1

def test_tag_order_appends_preserving_existing_tags():
    _sc._token_cache["token"] = _FAKE_TOKEN
    _sc._token_cache["expires_at"] = float("inf")
    client = _client([
        FakeResponse(200, {"order": {"id": 1, "tags": "rush"}}),
        FakeResponse(200, {"order": {"id": 1}}),
    ])
    client.tag_order("1", ["in-progress"])
    put_body = client._session.calls[1][2]["json"]["order"]["tags"]
    assert "rush" in put_body and "in-progress" in put_body


def test_tag_order_removes_tag():
    _sc._token_cache["token"] = _FAKE_TOKEN
    _sc._token_cache["expires_at"] = float("inf")
    client = _client([
        FakeResponse(200, {"order": {"id": 1, "tags": "AI-Flagged, rush"}}),
        FakeResponse(200, {"order": {"id": 1}}),
    ])
    client.tag_order("1", add_tags=["AI-Done"], remove_tags=["AI-Flagged"])
    put_body = client._session.calls[1][2]["json"]["order"]["tags"]
    assert "AI-Done" in put_body
    assert "AI-Flagged" not in put_body
    assert "rush" in put_body


def test_test_connection_success():
    _sc._token_cache["token"] = _FAKE_TOKEN
    _sc._token_cache["expires_at"] = float("inf")
    shop_json = json.loads((FIXTURES / "shop.json").read_text())
    client = _client([FakeResponse(200, shop_json)])
    ok, _msg = client.test_connection()
    assert ok


def test_test_connection_unauthorized_is_reported_not_raised():
    _sc._token_cache["token"] = _FAKE_TOKEN
    _sc._token_cache["expires_at"] = float("inf")
    client = _client([FakeResponse(401)])
    ok, _msg = client.test_connection()
    assert not ok
