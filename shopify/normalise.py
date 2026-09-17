from __future__ import annotations

import re
import unicodedata
from typing import List, Literal


_ARABIC_RANGES = [
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
]


_PRICE_TOKEN_RE = re.compile(
    r'\s*\d+\s*(?:LE|EGP|جنيه)\s*$',
    re.IGNORECASE,
)

_WS_RE = re.compile(r'\s+')

_NON_PRINTABLE_RE = re.compile(
    r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f'
    r'\U000e0000-\U000effff]'
)

_NUMERIC_PREFIX_RE = re.compile(r'^\d+[.\-\)]\s*')

_SUBJECT_SPLIT_RE = re.compile(r'[\r\n,/|]+')

_PHONE_STRIP_RE = re.compile(r'[\s\-().+]')


def collapse_whitespace(s: str) -> str:
    return _WS_RE.sub(' ', s).strip()


def strip_non_printable(s: str) -> str:
    return _NON_PRINTABLE_RE.sub('', s)


def is_arabic_char(c: str) -> bool:
    cp = ord(c)
    return any(lo <= cp <= hi for lo, hi in _ARABIC_RANGES)


ScriptKind = Literal["arabic", "latin", "mixed", "empty"]


def detect_script(s: str) -> ScriptKind:
    arabic = 0
    latin = 0
    for c in s:
        if is_arabic_char(c):
            arabic += 1
        elif c.isalpha():
            latin += 1
    if arabic == 0 and latin == 0:
        return "empty"
    if arabic > 0 and latin == 0:
        return "arabic"
    if latin > 0 and arabic == 0:
        return "latin"
    return "mixed"


def grapheme_count(s: str) -> int:
    return len(unicodedata.normalize('NFC', s))


def smart_title_case(s: str) -> str:
    words = s.split(' ')
    result = []
    for word in words:
        hyphen_parts = []
        for segment in word.split('-'):
            if "'" in segment:
                apos_parts = segment.split("'")
                segment = "'".join(p.capitalize() for p in apos_parts)
            else:
                segment = segment.capitalize()
            hyphen_parts.append(segment)
        result.append('-'.join(hyphen_parts))
    return ' '.join(result)


def normalise_name(s: str) -> str:
    s = strip_non_printable(s)
    s = collapse_whitespace(s)
    if detect_script(s) in ("latin", "mixed"):
        s = smart_title_case(s)
    return s


def normalise_arabic_name(s: str) -> str:
    s = strip_non_printable(s)
    s = collapse_whitespace(s)
    return s


def normalise_student_key(s: str) -> str:
    return collapse_whitespace(strip_non_printable(s)).lower()


def strip_price_token(s: str) -> str:
    return _PRICE_TOKEN_RE.sub('', s).strip()


def normalise_variant(variant_title: str) -> str:
    return collapse_whitespace(strip_price_token(variant_title))


def extract_digits(phone: str) -> str:
    return _PHONE_STRIP_RE.sub('', phone)


def is_plausible_phone(phone: str) -> bool:
    digits = extract_digits(phone)
    return digits.isdigit() and 7 <= len(digits) <= 15


def parse_subject_list(raw: str) -> List[str]:
    tokens = _SUBJECT_SPLIT_RE.split(raw)
    result = []
    for t in tokens:
        t = collapse_whitespace(t)
        t = _NUMERIC_PREFIX_RE.sub('', t).strip()
        if t:
            result.append(t)
    return result
