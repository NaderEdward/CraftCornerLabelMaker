from __future__ import annotations

import time
import unittest.mock as mock

import pytest

import shopify.client as sc
from shopify.client import ShopifyAuthError


@pytest.fixture(autouse=True)
def clean_cache():
    sc._token_cache["token"] = None
    sc._token_cache["expires_at"] = 0.0
    yield
    sc._token_cache["token"] = None
    sc._token_cache["expires_at"] = 0.0


def _creds(cid=None, sec=None, static=None):
    return (
        mock.patch.object(sc, "get_client_credentials", lambda: (cid, sec)),
        mock.patch.object(sc, "get_static_token", lambda: static),
    )


def _fake_oauth(token="shpat_fresh", expires_in=86400):
    return mock.patch.object(
        sc, "_fetch_oauth_token",
        lambda *a, **k: (token, time.time() + expires_in),
    )


class TestPrecedence:
    def test_client_credentials_win_over_stale_static_token(self):
        a, b = _creds(cid="id", sec="secret", static="shpat_DEAD")
        with a, b, _fake_oauth("shpat_fresh"):
            assert sc.get_active_token("shop.myshopify.com") == "shpat_fresh"

    def test_static_token_used_when_no_client_credentials(self):
        a, b = _creds(static="shpat_legacy")
        with a, b:
            assert sc.get_active_token("shop.myshopify.com") == "shpat_legacy"

    def test_no_credentials_raises_actionable_error(self):
        a, b = _creds()
        with a, b, pytest.raises(ShopifyAuthError) as e:
            sc.get_active_token("shop.myshopify.com")
        assert "Settings" in str(e.value)


class TestCaching:
    def test_cached_token_is_reused(self):
        calls = []

        def fake(*a, **k):
            calls.append(1)
            return "shpat_x", time.time() + 86400

        a, b = _creds(cid="id", sec="secret")
        with a, b, mock.patch.object(sc, "_fetch_oauth_token", fake):
            sc.get_active_token("shop.myshopify.com")
            sc.get_active_token("shop.myshopify.com")
        assert len(calls) == 1, "second call should have hit the cache"

    def test_force_refresh_bypasses_cache(self):
        calls = []

        def fake(*a, **k):
            calls.append(1)
            return f"shpat_{len(calls)}", time.time() + 86400

        a, b = _creds(cid="id", sec="secret")
        with a, b, mock.patch.object(sc, "_fetch_oauth_token", fake):
            first = sc.get_active_token("shop.myshopify.com")
            second = sc.get_active_token("shop.myshopify.com", force_refresh=True)
        assert first != second
        assert len(calls) == 2

    def test_expired_cache_refetches(self):
        a, b = _creds(cid="id", sec="secret")
        with a, b, _fake_oauth("shpat_new"):
            sc._token_cache["token"] = "shpat_old"
            sc._token_cache["expires_at"] = time.time() - 1
            assert sc.get_active_token("shop.myshopify.com") == "shpat_new"

    def test_storing_new_credentials_invalidates_cached_token(self):
        sc._token_cache["token"] = "shpat_old"
        sc._token_cache["expires_at"] = time.time() + 86400
        with mock.patch("keyring.set_password", lambda *a, **k: None):
            sc.store_client_credentials("new_id", "new_secret")
        assert sc._token_cache["token"] is None


class TestAuthMode:
    @pytest.mark.parametrize("cid,sec,static,expected", [
        ("id", "secret", None,            "oauth"),
        ("id", "secret", "shpat_legacy",  "oauth"),
        (None, None,     "shpat_legacy",  "static"),
        (None, None,     None,            "none"),
    ])
    def test_auth_mode_reports_effective_path(self, cid, sec, static, expected):
        a, b = _creds(cid, sec, static)
        with a, b:
            assert sc.auth_mode() == expected


class TestKeyringResilience:
    def test_unavailable_keyring_reads_as_not_configured(self):
        with mock.patch("keyring.get_password", side_effect=Exception("no backend")):
            assert sc.get_static_token() is None
            assert sc.get_client_credentials() == (None, None)
            assert sc.credentials_configured() is False

    def test_failure_to_save_is_reported_not_silent(self):
        with mock.patch("keyring.set_password", side_effect=Exception("no backend")):
            with pytest.raises(ShopifyAuthError):
                sc.store_client_credentials("id", "secret")


class TestDiagnostics:
    def test_401_help_names_the_static_token_problem(self):
        a, b = _creds(static="shpat_legacy")
        with a, b:
            msg = sc._401_help("shop.myshopify.com")
        assert "static" in msg and "Client ID" in msg

    def test_401_help_names_scopes_for_oauth(self):
        a, b = _creds(cid="id", sec="secret")
        with a, b:
            msg = sc._401_help("shop.myshopify.com")
        assert "read_orders" in msg
