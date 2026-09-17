from __future__ import annotations

import pytest

from shopify import packs

STANDARD_MAIN = "Standard.. 1 large - 1 medium - 1 subject - 1 payment sheet"
OPT2_MAIN     = "2 Large & 2 medium sheets only"
OPT3_MAIN     = "1 Large - 2 medium  - 1 subjects sheets"
STANDARD_PEN  = "Standard.. 1 pencil sheet - 1 shoe labels sheet"
ALT_PEN       = "2 pencil sheets only"


def counts(product, item, qty=1):
    res = packs.expand(product, item, qty)
    assert res.ok, res.errors
    return {c.region_id: c.qty for c in res.components}


def sheets(product, item, qty=1):
    res = packs.expand(product, item, qty)
    return {c.region_id: c.sheet for c in res.components}


class TestValuePackStandard:
    ITEM = {"main_sheet_choices": STANDARD_MAIN, "pencil_choice": STANDARD_PEN}

    def test_full_standard_contents(self):
        assert counts("Value pack (155 labels)", self.ITEM) == {
            "large_labels": 1, "medium_labels": 1,
            "subject_sheet": 1, "payment_sheet": 1,
            "pencil_labels": 1, "shoe_labels": 1,
            "iron_on_labels": 2,
            "bag_tag": 1, "lunch_tag": 1,
        }

    def test_iron_on_is_crops_not_labels(self):
        assert counts("Value pack (155 labels)", self.ITEM)["iron_on_labels"] == 2

    def test_split_across_both_artworks(self):
        s = sheets("Value pack (155 labels)", self.ITEM)
        assert s["large_labels"]  == "vp"
        assert s["payment_sheet"] == "extras"
        assert s["subject_sheet"] == "extras"
        assert s["shoe_labels"]   == "extras"


class TestValuePackVariants:
    def test_option2_has_no_subject_or_payment(self):
        c = counts("Value pack (155 labels)",
                   {"main_sheet_choices": OPT2_MAIN, "pencil_choice": ALT_PEN})
        assert c["large_labels"] == 2
        assert c["medium_labels"] == 2
        assert "subject_sheet" not in c
        assert "payment_sheet" not in c

    def test_option3_double_space_still_matches(self):
        c = counts("Value pack (155 labels)",
                   {"main_sheet_choices": OPT3_MAIN, "pencil_choice": STANDARD_PEN})
        assert c["large_labels"] == 1
        assert c["medium_labels"] == 2
        assert c["subject_sheet"] == 1
        assert "payment_sheet" not in c

    def test_alt_pencil_drops_shoe_labels(self):
        c = counts("Value pack (155 labels)",
                   {"main_sheet_choices": STANDARD_MAIN, "pencil_choice": ALT_PEN})
        assert c["pencil_labels"] == 2
        assert "shoe_labels" not in c

    def test_quantity_multiplies_every_component(self):
        item = {"main_sheet_choices": STANDARD_MAIN, "pencil_choice": STANDARD_PEN}
        one  = counts("Value pack (155 labels)", item, 1)
        two  = counts("Value pack (155 labels)", item, 2)
        assert two == {k: v * 2 for k, v in one.items()}


class TestUnknownOptions:
    def test_unrecognised_option_is_an_error_not_a_guess(self):
        res = packs.expand("Value pack (155 labels)",
                           {"main_sheet_choices": "something invented",
                            "pencil_choice": ALT_PEN})
        assert not res.ok
        assert any("unrecognised option" in e for e in res.errors)

    def test_missing_selection_is_an_error(self):
        res = packs.expand("Value pack (155 labels)", {"pencil_choice": ALT_PEN})
        assert not res.ok


class TestMiniAndMicro:
    def test_mini_pack_contents(self):
        assert counts("Mini pack (103 labels)", {}) == {
            "large_labels": 1, "medium_labels": 1, "pencil_labels": 1,
            "iron_on_labels": 1,
            "bag_tag": 1,
        }

    def test_micro_pack_contents(self):
        assert counts("Micro pack (84 labels)", {}) == {
            "mixed_labels": 1, "pencil_labels": 1, "bag_tag": 1,
        }

    def test_mini_micro_need_no_choices(self):
        assert packs.expand("Mini pack (103 labels)", {}).ok
        assert packs.expand("Micro pack (84 labels)", {}).ok


class TestIronOnCounts:
    @pytest.mark.parametrize("labels,crops", [(3, 1), (6, 2), (12, 4), (24, 8)])
    def test_pack_size_converts_to_crop_count(self, labels, crops):
        region, n, warns = packs.crops_for_individual(f"Iron on labels ({labels} pack)")
        assert region == "iron_on_labels"
        assert n == crops
        assert warns == []

    def test_non_multiple_rounds_up_and_warns(self):
        _region, n, warns = packs.crops_for_individual("Iron on labels (10 pack)")
        assert n == 4
        assert warns and "spare" in warns[0]

    def test_missing_count_warns_rather_than_crashing(self):
        _region, n, warns = packs.crops_for_individual("Iron on labels")
        assert n == 1
        assert warns

    def test_line_quantity_multiplies_crops(self):
        _region, n, _w = packs.crops_for_individual("Iron on labels (6 pack)", qty=3)
        assert n == 6

    def test_non_ironon_product_returns_none(self):
        assert packs.crops_for_individual("Large labels") is None


class TestPackMatching:
    @pytest.mark.parametrize("product,expected", [
        ("Value pack (155 labels)", "value pack"),
        ("Mini pack (103 labels)",  "mini pack"),
        ("Micro pack (84 labels)",  "micro pack"),
        ("Large labels",            None),
        ("Iron on labels (6 pack)", None),
    ])
    def test_match_pack(self, product, expected):
        assert packs.match_pack(product) == expected
