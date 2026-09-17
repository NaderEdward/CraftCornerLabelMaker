from __future__ import annotations

import logging
from typing import Optional

from core.theme_map import SIGNS, STITCHES, PLAIN_SIGNS, PLAIN_STITCHES, NAME_ONLY, NAME_CUTOUT

_TABLE = {
    (SIGNS, "NCS", False):  "basic_sheets_NCS_signs",
    (SIGNS, "NCS", True):   "basic_sheets_NCS_signs_AR",
    (SIGNS, "NC", False):   "basic_sheets_NC_signs",
    (SIGNS, "NC", True):    "basic_sheets_NC_signs_AR",
    (SIGNS, "name", False): "basic_sheets_name_signs",
    (SIGNS, "name", True):  "basic_sheets_name_signs_AR",

    (STITCHES, "NCS", False):  "basic_sheets_NCS_stitches",
    (STITCHES, "NCS", True):   "basic_sheets_NCS_stitches_AR",
    (STITCHES, "NC", False):   "basic_sheets_NC_stitches",
    (STITCHES, "NC", True):    "basic_sheets_NC_stitches_AR",
    (STITCHES, "name", False): "basic_sheets_name_stitches",
    (STITCHES, "name", True):  "basic_sheets_name_stitches_AR",

    (PLAIN_SIGNS, "NCS", False):  "plain_labels_NCS_signs",
    (PLAIN_SIGNS, "NCS", True):   "plain_labels_NCS_signs_AR",
    (PLAIN_SIGNS, "NC", False):   "plain_labels_NC_signs",
    (PLAIN_SIGNS, "NC", True):    "plain_labels_NC_signs_AR",
    (PLAIN_SIGNS, "name", False): "plain_labels_name_signs",
    (PLAIN_SIGNS, "name", True):  "plain_labels_name_signs_AR",

    (PLAIN_STITCHES, "NCS", False):  "plain_labels_NCS_stitches",
    (PLAIN_STITCHES, "NCS", True):   "plain_labels_NCS_stitches_AR",
    (PLAIN_STITCHES, "NC", False):   "plain_labels_NC_stitches",
    (PLAIN_STITCHES, "NC", True):    "plain_labels_NC_stitches_AR",
    (PLAIN_STITCHES, "name", False): "plain_labels_name_stitches",
    (PLAIN_STITCHES, "name", True):  "plain_labels_name_stitches_AR",

    (NAME_ONLY, "NCS",  False): "name_only_labels",
    (NAME_ONLY, "NCS",  True):  "name_only_labels_AR",
    (NAME_ONLY, "NC",   False): "name_only_labels",
    (NAME_ONLY, "NC",   True):  "name_only_labels_AR",
    (NAME_ONLY, "name", False): "name_only_labels",
    (NAME_ONLY, "name", True):  "name_only_labels_AR",
}

EXTRAS_TEMPLATE = "extras_nc"

log = logging.getLogger(__name__)

_EXTRAS_KEYWORDS = (
    "extra sheet", "extras", "clipart subject", "subject sheet",
    "payment sheet", "shoe label", "sticker sheet",
)


def _field_combo(has_class: bool, has_school: bool) -> str:
    if has_class and has_school:
        return "NCS"
    if has_class:
        return "NC"
    return "name"


def select(
    template_type: str,
    has_arabic: bool,
    has_class: bool,
    has_school: bool,
    is_extras: bool = False,
) -> Optional[str]:
    if is_extras:
        return EXTRAS_TEMPLATE
    return _TABLE.get((template_type, _field_combo(has_class, has_school), has_arabic))


def is_extras_product(product: str) -> bool:
    low = product.lower()
    return any(kw in low for kw in _EXTRAS_KEYWORDS)


def select_name_cutout(
    has_first: bool = False,
    has_nickname: bool = False,
    has_initials: bool = False,
    has_arabic: bool = False,
) -> str:
    if has_first and has_nickname and has_initials:
        return "name_cutout_FFNI"
    if has_first and has_nickname:
        return "name_cutout_FFN"
    if has_first and has_initials:
        return "name_cutout_FFI"
    if has_first:
        return "name_cutout_FF"
    if has_nickname and has_initials:
        return "name_cutout_FNI"
    if has_nickname:
        return "name_cutout_FN"
    if has_initials:
        return "name_cutout_FI"
    return "name_cutout_F"
