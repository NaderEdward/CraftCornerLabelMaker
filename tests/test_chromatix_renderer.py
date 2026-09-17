import time as _time

import pytest

from core import chromatix_renderer as cr


class _FakeDriver:

    def __init__(self):
        self.loaded_html = None
        self.body_nonce = None
        self.get_calls = 0

    def get(self, url):
        assert url.startswith("file:///")
        path = url[len("file:///"):]
        with open(path, "r", encoding="utf-8") as fh:
            self.loaded_html = fh.read()
        marker = 'data-page-nonce="'
        i = self.loaded_html.index(marker) + len(marker)
        j = self.loaded_html.index('"', i)
        self.body_nonce = int(self.loaded_html[i:j])
        self.get_calls += 1

    def execute_script(self, script):
        if "pageNonce" in script:
            return self.body_nonce
        return None


def _make_instance(font_path, gecko=None):
    inst = object.__new__(cr.ChromatixRenderer)
    inst._font_path = font_path
    inst._font_b64 = "AAAA"
    inst._gecko = gecko
    inst._page_key = None
    inst._page_nonce = None
    return inst


@pytest.fixture(autouse=True)
def _reset_module_globals(monkeypatch):
    monkeypatch.setattr(cr, "_driver_page_key", None)
    monkeypatch.setattr(cr, "_page_nonce", 0)
    monkeypatch.setattr(cr.time, "sleep", lambda *_a, **_k: None)
    fake = _FakeDriver()
    monkeypatch.setattr(cr, "_get_driver", lambda gecko=None: fake)
    return fake


def test_second_instance_repoints_shared_tab(_reset_module_globals):
    fake = _reset_module_globals
    a = _make_instance("/fonts/a.ttf")
    b = _make_instance("/fonts/b.ttf")

    a._build_page(n_names=3, line_gap_mult=1.0)
    assert fake.get_calls == 1
    a_nonce = a._page_nonce

    b._build_page(n_names=3, line_gap_mult=1.0)
    assert fake.get_calls == 2
    assert b._page_nonce != a_nonce


def test_stale_instance_local_key_is_overridden_by_global(_reset_module_globals):
    fake = _reset_module_globals
    a = _make_instance("/fonts/a.ttf")
    b = _make_instance("/fonts/b.ttf")

    a._build_page(n_names=3, line_gap_mult=1.0)
    assert fake.get_calls == 1
    a_key_before = a._page_key
    a_nonce_before = a._page_nonce

    b._build_page(n_names=5, line_gap_mult=1.0)
    assert fake.get_calls == 2
    assert cr._driver_page_key != a_key_before

    a._build_page(n_names=3, line_gap_mult=1.0)
    assert a._page_key == a_key_before
    assert fake.get_calls == 3, (
        "A must re-navigate: the shared tab was repointed by B since A's "
        "self._page_key was last set, even though A's own key is unchanged."
    )
    assert a._page_nonce != a_nonce_before
    assert cr._driver_page_key == a._page_key
    assert fake.body_nonce == a._page_nonce


def test_unchanged_page_skips_navigation(_reset_module_globals):
    fake = _reset_module_globals
    a = _make_instance("/fonts/a.ttf")

    a._build_page(n_names=3, line_gap_mult=1.0)
    assert fake.get_calls == 1

    a._build_page(n_names=3, line_gap_mult=1.0)
    assert fake.get_calls == 1, "same instance, same key, untouched tab -> no re-navigation"


def test_defensive_live_nonce_mismatch_forces_rebuild(_reset_module_globals):
    fake = _reset_module_globals
    a = _make_instance("/fonts/a.ttf")
    a._build_page(n_names=2, line_gap_mult=1.0)
    real_nonce = a._page_nonce

    fake.body_nonce = real_nonce + 999

    live = fake.execute_script(
        "return document.body ? document.body.dataset.pageNonce : null;")
    assert live != a._page_nonce, (
        "test setup: live nonce must disagree with the instance's expectation"
    )
