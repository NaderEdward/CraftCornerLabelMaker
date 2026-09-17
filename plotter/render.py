from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import OrderedDict
from typing import Dict

from PIL import Image

from core.render_engine import (
    ARABIC_SUPPORT,
    FontManager,
    LabelConfig,
    LabelGenerator,
    MissingBackgroundError,
    MissingFontError,
)
from core.theme_map import NAME_ONLY


__all__ = [
    "ArabicSupportMissingError", "LabelRecord", "MissingBackgroundError",
    "MissingFontError", "ValuePackRenderer", "assert_arabic_support",
    "NameOnlyRenderer", "preflight",
]


class ArabicSupportMissingError(RuntimeError):
    pass


def preflight(template_names=None) -> None:
    FontManager.assert_available(sorted({
        *FontManager.RECOMMENDATIONS["en"],
        *FontManager.RECOMMENDATIONS["ar"],
    }))

    if not template_names:
        return

    from core import templates as core_templates
    from regions import model as region_model
    from regions import validate as region_validate

    for name in template_names:
        problems = [p for p in core_templates.validate(name)
                    if "native_dpi" not in p]
        if problems:
            raise RuntimeError(f"Template '{name}' is not usable: {problems}")
        region_set = region_model.load(name)
        region_problems = region_validate.validate_region_set(region_set)
        if region_problems:
            raise RuntimeError(f"Regions for '{name}' are invalid: {region_problems}")


def assert_name_font_support(records) -> None:
    from core.chromatix_renderer import NameFontUnavailable, diagnose
    from core.theme_map import NAME_CUTOUT, NAME_ONLY

    slugs = set()
    for r in records:
        if r.get("blocked"):
            continue
        cf = r.get("custom_fields", {}) or {}
        tname = r.get("template_name", "") or ""
        if (cf.get("template_type") in (NAME_ONLY, NAME_CUTOUT)
                or tname.startswith(("name_only", "name_cutout"))):
            slugs.add((cf.get("theme", "") or "").strip())

    problems = [p for p in (diagnose(s) for s in sorted(slugs)) if p]
    if problems:
        raise NameFontUnavailable(
            "Decorative name themes cannot be rendered on this machine:\n  - "
            + "\n  - ".join(problems)
            + "\nNo sheets were produced. Fix the above, or exclude these "
              "orders from the run and make them manually."
        )


def assert_arabic_support() -> None:
    if not ARABIC_SUPPORT:
        raise ArabicSupportMissingError(
            "arabic_reshaper / python-bidi are not installed. If any "
            "pending record has an Arabic name, rendering must not proceed."
        )


@dataclasses.dataclass
class LabelRecord:

    order_id: str
    student_name: str
    student_name_arabic: str
    school: str
    grade: str
    telephone: str
    custom_fields: Dict[str, str]
    template_name: str
    language: str

    def cache_key(self) -> str:
        payload = dataclasses.asdict(self)
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_label_config(self) -> LabelConfig:
        cf = dict(self.custom_fields)
        bg = cf.pop("background_path", "") or ""
        return LabelConfig(
            name=self.student_name,
            name_arabic=self.student_name_arabic,
            school=self.school,
            grade=self.grade,
            telephone=self.telephone,
            order_number=self.order_id,
            custom_fields=cf,
            template_name=self.template_name,
            language=self.language,
            background_path=bg,
        )


class ValuePackRenderer:
    def __init__(self, strict: bool = True, cache_size: int = 8):
        if not strict:
            raise ValueError(
                "core/render_engine.py's LabelGenerator is strict-only "
                "(§1.5). Use LabelGen's own engine.py for lenient/"
                "interactive rendering."
            )
        self.strict = strict
        self.cache_size = cache_size
        self._generator = LabelGenerator()
        self._cache: "OrderedDict[str, Image.Image]" = OrderedDict()

    def render(self, record: LabelRecord) -> Image.Image:
        key = record.cache_key()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        cfg = record.to_label_config()
        img = self._generator.generate(cfg)

        self._cache[key] = img
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
        return img

    def release(self, record: LabelRecord) -> None:
        pass

    def close(self) -> None:
        self._cache.clear()


class NameOnlyRenderer:

    def __init__(self, slug: str, geckodriver_path: str = None):
        from core.chromatix_renderer import ChromatixRenderer
        self._renderer = ChromatixRenderer.shared(
            slug, geckodriver_path=geckodriver_path)
        self._slug = slug

    @property
    def available(self) -> bool:
        return self._renderer.available

    def warm(self, records) -> None:
        names = list({r["student_name"] for r in records
                      if r.get("template_name", "").startswith("name_only")
                      and not r.get("blocked")})
        if names:
            self._renderer.warm(names)

    def render_record(self, record: "LabelRecord",
                      zone_w: int, zone_h: int) -> "Image.Image":
        grade = record.grade or ""
        return self._renderer.get(
            record.student_name,
            grade=grade,
            max_w=zone_w,
            max_h=zone_h,
        )

    def close(self):
        self._renderer.close()
