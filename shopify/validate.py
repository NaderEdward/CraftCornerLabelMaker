from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from shopify.normalise import (
    detect_script,
    grapheme_count,
    is_plausible_phone,
    parse_subject_list,
)


MAX_ENGLISH_NAME = 30
MIN_ENGLISH_NAME = 2
MAX_ARABIC_NAME  = 30
MAX_CLASS_NAME   = 15
MAX_SCHOOL_NAME  = 30
MAX_SUBJECTS     = 10


@dataclass(frozen=True)
class Flag:
    kind: str
    severity: str
    detail: str = ""
    field: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "detail": self.detail,
            "field": self.field,
        }

    @property
    def is_critical(self) -> bool:
        return self.severity == "critical"


def _flag(kind: str, severity: str, detail: str = "", fld: str = "") -> Flag:
    return Flag(kind=kind, severity=severity, detail=detail, field=fld)


def validate_english_name(name: str) -> List[Flag]:
    flags: List[Flag] = []
    if not name or len(name) < MIN_ENGLISH_NAME:
        flags.append(_flag(
            "MISSING_REQUIRED_NAME", "critical",
            f"English name is missing or too short ('{name}', min {MIN_ENGLISH_NAME} chars).",
            "student_name",
        ))
    elif len(name) > MAX_ENGLISH_NAME:
        flags.append(_flag(
            "NAME_TOO_LONG", "warning",
            f"Name '{name}' is {len(name)} chars, limit {MAX_ENGLISH_NAME}. "
            "Consider font-size reduction or an abbreviation.",
            "student_name",
        ))
    if name and detect_script(name) == "arabic":
        flags.append(_flag(
            "LANGUAGE_SCRIPT_MISMATCH", "warning",
            f"English name field contains Arabic script: '{name}'.",
            "student_name",
        ))
    return flags


def validate_arabic_name(arabic_name: str) -> List[Flag]:
    if not arabic_name:
        return []
    flags: List[Flag] = []
    gc = grapheme_count(arabic_name)
    if gc > MAX_ARABIC_NAME:
        flags.append(_flag(
            "ARABIC_NAME_EXCEEDS_LIMIT", "warning",
            f"Arabic name is {gc} graphemes, limit {MAX_ARABIC_NAME}.",
            "student_name_arabic",
        ))
    if detect_script(arabic_name) == "latin":
        flags.append(_flag(
            "LANGUAGE_SCRIPT_MISMATCH", "warning",
            f"Arabic name field contains Latin script: '{arabic_name}'.",
            "student_name_arabic",
        ))
    return flags


def validate_class_name(class_name: str) -> List[Flag]:
    if not class_name:
        return []
    if len(class_name) > MAX_CLASS_NAME:
        return [_flag(
            "CLASS_NAME_EXCEEDS_LENGTH_LIMIT", "warning",
            f"Class '{class_name}' is {len(class_name)} chars, limit {MAX_CLASS_NAME}.",
            "grade",
        )]
    return []


def validate_school_name(school_name: str) -> List[Flag]:
    if not school_name:
        return []
    if len(school_name) > MAX_SCHOOL_NAME:
        return [_flag(
            "SCHOOL_NAME_EXCEEDS_LENGTH_LIMIT", "warning",
            f"School '{school_name}' is {len(school_name)} chars, limit {MAX_SCHOOL_NAME}.",
            "school",
        )]
    return []


def validate_phone(phone: str) -> List[Flag]:
    if not phone:
        return []
    if not is_plausible_phone(phone):
        return [_flag(
            "INVALID_PHONE_FORMAT", "warning",
            f"Phone '{phone}' does not have a plausible digit count (7–15). "
            "Label will be printed as entered; verify before cutting.",
            "telephone",
        )]
    return []


def validate_subject_list(raw_subjects: str) -> List[Flag]:
    if not raw_subjects:
        return []
    flags: List[Flag] = []
    subjects = parse_subject_list(raw_subjects)
    if len(subjects) > MAX_SUBJECTS:
        flags.append(_flag(
            "SUBJECT_COUNT_EXCEEDED", "warning",
            f"{len(subjects)} subjects detected, sheet maximum is {MAX_SUBJECTS}. "
            f"Subjects: {subjects!r}",
            "subjects",
        ))
    flags.append(_flag(
        "SUBJECT_LIST_REQUIRES_REVIEW", "warning",
        f"Subject list detected and requires operator confirmation: {subjects!r}",
        "subjects",
    ))
    return flags


def validate_comment(comment: str) -> List[Flag]:
    if not comment:
        return []

    lower = comment.lower()
    non_actionable = [
        "whatever i want",
        "whatever you want",
        "اضيفي",
        "ضيفي",
        "add whatever",
    ]
    if any(phrase in lower for phrase in non_actionable):
        return [_flag(
            "NON_ACTIONABLE_INSTRUCTION", "critical",
            f"Comment requires customer contact before production: '{comment}'.",
            "comments",
        )]

    return [_flag(
        "CUSTOM_ORDER_COMMENT_PRESENT", "warning",
        f"Comment requires operator review: '{comment}'.",
        "comments",
    )]


def validate_gpo_linkage(line_items: List[Dict[str, Any]]) -> List[Flag]:
    def _props(li: Dict[str, Any]) -> Dict[str, str]:
        return {p["name"]: p["value"] for p in (li.get("properties") or [])}

    parent_groups = {
        _props(li)["_gpo_product_group"]
        for li in line_items
        if "_gpo_product_group" in _props(li)
    }

    flags: List[Flag] = []
    for li in line_items:
        props = _props(li)
        parent_group = props.get("_gpo_parent_product_group")
        if parent_group and parent_group not in parent_groups:
            flags.append(_flag(
                "UNLINKED_GPO_ADDON", "critical",
                f"GPO child '{li.get('title')}' (variant: '{li.get('variant_title')}', "
                f"group {parent_group}) has no matching parent in this order.",
                "line_items",
            ))
    return flags


def validate_enablers(props: Dict[str, str],
                      enabler_map: Dict[str, str]) -> List[Flag]:
    flags: List[Flag] = []
    for enabler_key, value_key in enabler_map.items():
        if enabler_key in props:
            value = props.get(value_key, "").strip()
            if not value:
                flags.append(_flag(
                    "ENABLER_WITHOUT_VALUE", "critical",
                    f"Enabler '{enabler_key}' is present but its value key "
                    f"'{value_key}' is missing or empty. "
                    "This zone would print blank.",
                    value_key,
                ))
    return flags


def validate_record(
    *,
    student_name: str,
    student_name_arabic: str,
    school: str,
    grade: str,
    telephone: str,
    student_count_in_order: int,
) -> List[Flag]:
    flags: List[Flag] = []
    flags.extend(validate_english_name(student_name))
    flags.extend(validate_arabic_name(student_name_arabic))
    flags.extend(validate_class_name(grade))
    flags.extend(validate_school_name(school))
    flags.extend(validate_phone(telephone))
    if student_count_in_order > 1:
        flags.append(_flag(
            "MULTIPLE_STUDENTS_DETECTED", "informational",
            f"{student_count_in_order} distinct students in this order. "
            "Sheets will be produced per student; verify packaging grouping.",
            "order",
        ))
    return flags


def has_critical(flags: List[Flag]) -> bool:
    return any(f.is_critical for f in flags)
