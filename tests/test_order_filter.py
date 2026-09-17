from __future__ import annotations

import pytest

from shopify.client import (
    _fulfillment_block_reason,
    _is_unfulfilled, _normalise_gql_order,
    _PRINTABLE_FULFILLMENT_STATUSES,
)
from shopify.ingest import _EXCLUDE_TAGS, _is_eligible, _normalise_tag


def _node(status="UNFULFILLED", tags=None):
    return {
        "id": "gid://shopify/Order/1", "name": "#1001",
        "tags": tags or [], "displayFulfillmentStatus": status,
        "lineItems": {"edges": []},
    }


class TestFulfillmentStatus:
    def test_unfulfilled_is_printable(self):
        assert _is_unfulfilled(_normalise_gql_order(_node("UNFULFILLED")))

    @pytest.mark.parametrize("status", [
        "READY_FOR_PICKUP",
        "IN_PROGRESS",
        "ON_HOLD",
        "SCHEDULED",
        "FULFILLED",
        "PARTIALLY_FULFILLED",
        "RESTOCKED",
    ])
    def test_non_unfulfilled_statuses_are_skipped(self, status):
        assert not _is_unfulfilled(_normalise_gql_order(_node(status)))

    def test_absent_status_is_skipped_not_printed(self):
        assert not _is_unfulfilled(_normalise_gql_order(_node(None)))
        assert not _is_unfulfilled({})

    def test_unknown_future_status_is_skipped(self):
        assert not _is_unfulfilled(
            _normalise_gql_order(_node("SOME_NEW_STATUS_2027")))

    def test_allowlist_is_exactly_unfulfilled(self):
        assert _PRINTABLE_FULFILLMENT_STATUSES == frozenset({"unfulfilled"})


class TestTagNormalisation:
    @pytest.mark.parametrize("spelling", [
        "in-progress", "in progress", "In Progress", "IN-PROGRESS",
        "in_progress", "In_Progress", "IN_PROGRESS", "  in-progress  ",
        "in  progress",
    ])
    def test_every_in_progress_spelling_is_blocked(self, spelling):
        assert not _is_eligible({"tags": spelling}), (
            f"{spelling!r} slipped through — order would be printed twice")

    @pytest.mark.parametrize("spelling", [
        "AI-Done", "ai done", "AI_Done", "ai-done", "AI DONE",
    ])
    def test_every_ai_done_spelling_is_blocked(self, spelling):
        assert not _is_eligible({"tags": spelling})

    @pytest.mark.parametrize("spelling", [
        "AI-Flagged", "ai flagged", "AI_Flagged", "ai-flagged",
    ])
    def test_every_ai_flagged_spelling_is_blocked(self, spelling):
        assert not _is_eligible({"tags": spelling})

    def test_underscore_variant_regression(self):
        assert _normalise_tag("in_progress") == _normalise_tag("in-progress")

    def test_substring_does_not_block(self):
        assert _is_eligible({"tags": "not-in-progress-yet"})

    def test_unrelated_tags_do_not_block(self):
        assert _is_eligible({"tags": "rush, vip, gift"})

    def test_blocking_tag_among_many_still_blocks(self):
        assert not _is_eligible({"tags": "rush, In_Progress, vip"})

    def test_empty_tags_are_eligible(self):
        assert _is_eligible({"tags": ""})
        assert _is_eligible({})


class TestCombinedEligibility:
    def test_unfulfilled_and_untagged_is_processed(self):
        order = _normalise_gql_order(_node("UNFULFILLED", ["rush"]))
        assert _is_unfulfilled(order) and _is_eligible(order)

    def test_ready_for_pickup_untagged_is_rejected_on_status(self):
        order = _normalise_gql_order(_node("READY_FOR_PICKUP", []))
        assert not _is_unfulfilled(order)
        assert _is_eligible(order)

    def test_unfulfilled_but_tagged_is_rejected_on_tags(self):
        order = _normalise_gql_order(_node("UNFULFILLED", ["in_progress"]))
        assert _is_unfulfilled(order)
        assert not _is_eligible(order)


class TestServerSideQueryVariants:
    def test_query_excludes_underscore_tag_variants(self):
        def clauses(tag):
            base = tag.replace("-", " ").replace("_", " ")
            return {base, base.replace(" ", "-"),
                    base.replace(" ", "_"), base.replace(" ", ""), tag}

        for tag in _EXCLUDE_TAGS:
            variants = clauses(tag)
            assert any("_" in v for v in variants), tag
            assert any("-" in v for v in variants), tag
            assert any(" " in v for v in variants), tag


class TestReadyForPickupViaFulfillmentOrders:

    def _order(self, status="UNFULFILLED", fos=()):
        return _normalise_gql_order({
            "id": "gid://shopify/Order/1", "name": "#1001", "tags": [],
            "displayFulfillmentStatus": status,
            "lineItems": {"edges": []},
            "fulfillmentOrders": {"edges": [{"node": f} for f in fos]},
        })

    def _fo(self, status="OPEN", request_status="UNSUBMITTED", holds=()):
        return {"status": status, "requestStatus": request_status,
                "fulfillmentHolds": [{"reason": h} for h in holds]}

    def test_open_fulfillment_order_prints(self):
        assert _is_unfulfilled(self._order(fos=[self._fo("OPEN")]))

    def test_in_progress_is_ready_for_pickup_and_is_skipped(self):
        o = self._order(fos=[self._fo("IN_PROGRESS", "UNSUBMITTED")])
        assert o["fulfillment_status"] == "unfulfilled"
        assert not _is_unfulfilled(o)

    def test_reason_names_ready_for_pickup_in_plain_words(self):
        o = self._order(fos=[self._fo("IN_PROGRESS")])
        reason = _fulfillment_block_reason(o)
        assert "in_progress" in reason and "Ready for pickup" in reason

    @pytest.mark.parametrize("status", ["CLOSED", "CANCELLED", "ON_HOLD"])
    def test_non_open_statuses_are_skipped(self, status):
        assert not _is_unfulfilled(self._order(fos=[self._fo(status)]))

    def test_unknown_future_status_is_skipped(self):
        assert not _is_unfulfilled(self._order(fos=[self._fo("SOME_NEW_2027")]))

    def test_request_status_alone_never_decides(self):
        open_o = self._order(fos=[self._fo("OPEN", "UNSUBMITTED")])
        ready  = self._order(fos=[self._fo("IN_PROGRESS", "UNSUBMITTED")])
        assert _is_unfulfilled(open_o) != _is_unfulfilled(ready)

    def test_all_fulfillment_orders_must_be_open(self):
        o = self._order(fos=[self._fo("CLOSED"), self._fo("IN_PROGRESS")])
        assert not _is_unfulfilled(o)

    def test_mixed_open_and_closed_is_skipped(self):
        o = self._order(fos=[self._fo("OPEN"), self._fo("CLOSED")])
        assert not _is_unfulfilled(o)

    def test_fulfillment_hold_is_skipped(self):
        o = self._order(fos=[self._fo("OPEN", holds=["AWAITING_PAYMENT"])])
        assert not _is_unfulfilled(o)
        assert "AWAITING_PAYMENT" in _fulfillment_block_reason(o)

    def test_no_fulfillment_orders_does_not_block(self):
        o = self._order(fos=[])
        assert _fulfillment_block_reason(o) is None
        assert _is_unfulfilled(o)

    def test_missing_key_is_safe(self):
        assert _fulfillment_block_reason({}) is None

    def test_fulfilled_order_skipped_regardless_of_fulfillment_orders(self):
        assert not _is_unfulfilled(
            self._order("FULFILLED", fos=[self._fo("OPEN")]))


class TestAgainstRealFetch:

    @staticmethod
    def _fixture():
        import json
        from pathlib import Path
        p = (Path(__file__).parent.parent / "shopify" / "fixtures"
             / "orders_pickup_mix.json")
        return json.loads(p.read_text(encoding="utf-8"))["orders"]

    def test_every_order_classified_correctly(self):
        wrong = [o["name"] for o in self._fixture()
                 if _is_unfulfilled(o) != o["expected_printable"]]
        assert not wrong, f"misclassified: {wrong}"

    def test_exactly_ten_would_print(self):
        printable = [o["name"] for o in self._fixture() if _is_unfulfilled(o)]
        assert len(printable) == 10, printable

    def test_the_five_pickup_orders_are_skipped(self):
        skipped = {o["name"] for o in self._fixture()
                   if not _is_unfulfilled(o)}
        assert skipped == {"#Test1001", "#Test1002", "#Test1003",
                           "#Test1004", "#Test1005"}

    def test_order_level_status_is_useless_on_this_data(self):
        assert {o["fulfillment_status"] for o in self._fixture()} == {"unfulfilled"}

    def test_request_status_is_useless_on_this_data(self):
        seen = {f.get("requestStatus")
                for o in self._fixture()
                for f in o["fulfillment_orders"]}
        assert seen == {"UNSUBMITTED"}, (
            f"requestStatus varied ({seen}) — re-examine whether it is "
            f"usable after all")


def test_query_requests_fulfillment_orders():
    from shopify.client import _ORDERS_QUERY
    assert "fulfillmentOrders" in _ORDERS_QUERY
    assert "requestStatus" in _ORDERS_QUERY
    assert "fulfillmentHolds" in _ORDERS_QUERY
