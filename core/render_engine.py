from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from core import paths
from core import templates as core_templates

log = logging.getLogger(__name__)

try:
    import arabic_reshaper
    from bidi.algorithm import get_display as bidi_display
    ARABIC_SUPPORT = True
except ImportError:
    ARABIC_SUPPORT = False


class MissingBackgroundError(RuntimeError):
    """Raised in strict mode when a template's background image cannot be
    resolved (D2). Never render a production sheet against a transparent
    fallback — that silently produces blank output indistinguishable from
    a successful export.
    """


class MissingFontError(RuntimeError):
    pass


@dataclass
class FontStyle:
    name:   str   = "DejaVuSans"
    size:   int   = 32
    bold:   bool  = False
    italic: bool  = False
    color:  Tuple[int, int, int] = (10, 10, 10)


@dataclass
class LabelConfig:
    name:         str = ""
    name_arabic:  str = ""
    school:       str = ""
    grade:        str = ""
    subtitle:     str = ""
    order_number: str = ""
    telephone:    str = ""
    custom_fields: Dict[str, str] = field(default_factory=dict)

    template_name:   str = "baby_minnie"
    background_path: str = ""
    language:        str = "en"

    font: FontStyle = field(default_factory=FontStyle)
    auto_font_by_language: bool = True

    row_overrides:  Dict[str, Dict] = field(default_factory=dict)
    zone_overrides: Dict[str, Dict] = field(default_factory=dict)

    auto_fit:     bool                = True
    active_rows:  Optional[List[str]] = None
    active_zones: Optional[List[str]] = None

    def effective_font_name(self, language: Optional[str] = None) -> str:
        lang = language or self.language
        if self.auto_font_by_language:
            return "DGSahabah-Regular" if lang == "ar" else "frozenberries"
        return self.font.name

    def row_language(self, row_id: str) -> str:
        return self.row_overrides.get(row_id, {}).get("language", self.language)

    def row_name(self, row_id: str) -> str:
        return self.row_overrides.get(row_id, {}).get("name", self.name)

    def row_grade(self, row_id: str) -> str:
        return self.row_overrides.get(row_id, {}).get("grade", self.grade)

    def global_field(self, source: str) -> str:
        builtin = {
            "name":         self.name,
            "name_english": self.name,
            "name_arabic":  self.name_arabic,
            "school":       self.school,
            "grade":        self.grade,
            "order_number": self.order_number,
            "telephone":    self.telephone,
        }
        if source in builtin:
            return builtin[source]
        return self.custom_fields.get(source, "")

    def zone_is_empty(self, zone_id: str) -> bool:
        return bool(self.zone_overrides.get(zone_id, {}).get("empty", False))

    def zone_source(self, zone_id: str, default_key: str = "name") -> str:
        return self.zone_overrides.get(zone_id, {}).get("source", default_key)

    def zone_text(self, zone_id: str, default_key: str = "name") -> str:
        zo = self.zone_overrides.get(zone_id, {})
        src = zo.get("source", default_key)
        if src == "custom":
            return (zo.get("text", "") or "").strip()
        return (self.global_field(src) or "").strip()

    def zone_language(self, zone_id: str) -> str:
        return self.zone_overrides.get(zone_id, {}).get("language") or self.language

    def zone_font_name(self, zone_id: str, language: str) -> str:
        fn = self.zone_overrides.get(zone_id, {}).get("font_name")
        return fn if fn else self.effective_font_name(language)

    def zone_fixed_size(self, zone_id: str) -> Optional[int]:
        sz = self.zone_overrides.get(zone_id, {}).get("font_size")
        return int(sz) if sz else None

    def zone_text_color(self, zone_id: str, zone_dict: dict) -> Tuple[int, int, int]:
        ovr = self.zone_overrides.get(zone_id, {})
        if "text_color" in ovr:
            c = ovr["text_color"]
            return (int(c[0]), int(c[1]), int(c[2]))
        if "text_color" in zone_dict:
            c = zone_dict["text_color"]
            return (int(c[0]), int(c[1]), int(c[2]))
        return self.font.color


class FontManager:

    _cache: Dict[str, ImageFont.FreeTypeFont] = {}
    _path_map: Optional[Dict[str, str]] = None

    BUNDLED_FONTS = {
        "Before the Rainbow":   "BeforeTheRainbow.otf",
        "Before":               "BeforeTheRainbow.otf",
        "KIDSPLAY":             "KIDSPLAY.otf",
        "frozenberries":        "FrozenBerries.ttf",
        "FrozenBerries":        "FrozenBerries.ttf",
        "DGSahabah-Regular":    "DGSahabah-Regular.ttf",
        "DGSahabah-Bold":       "DGSahabah-Bold.ttf",
        "DG Sahabah":           "DGSahabah-Regular.ttf",
        "DG Sahabah Reg":       "DGSahabah-Regular.ttf",
        "NotoSansArabic":       "NotoSansArabicCondensed.ttf",
        "NotoSansArabicCondensed": "NotoSansArabicCondensed.ttf",
        "DejaVuSans":           "DejaVuSans-Regular.ttf",
        "DejaVuSans Bold":      "DejaVuSans-Bold.ttf",
        "DejaVuSans Italic":    "DejaVuSans-Italic.ttf",
        "LiberationSans":       "LiberationSans-Regular.ttf",
        "LiberationSans Bold":  "LiberationSans-Bold.ttf",
        "Carlito":              "Carlito-Regular.ttf",
        "Carlito Bold":         "Carlito-Bold.ttf",
    }

    RECOMMENDATIONS: Dict[str, List[str]] = {
        "en": ["Before the Rainbow", "KIDSPLAY", "DejaVuSans"],
        "ar": ["NotoSansArabic", "DGSahabah-Regular", "DGSahabah-Bold"],
        "fr": ["Before the Rainbow", "DejaVuSans"],
        "de": ["Before the Rainbow", "DejaVuSans"],
    }

    @classmethod
    def _build_path_map(cls) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        bdir = paths.bundled_fonts_dir()
        for display, filename in cls.BUNDLED_FONTS.items():
            p = bdir / filename
            if p.exists():
                mapping[display] = str(p)
        return mapping

    @classmethod
    def path_map(cls) -> Dict[str, str]:
        if cls._path_map is None:
            cls._path_map = cls._build_path_map()
        return cls._path_map

    @classmethod
    def available_names(cls) -> List[str]:
        return sorted(cls.path_map().keys())

    @classmethod
    def assert_available(cls, names: List[str]) -> None:
        pm = cls.path_map()
        missing = [n for n in names if n not in pm]
        if missing:
            raise MissingFontError(
                f"Bundled font(s) not found in {paths.bundled_fonts_dir()}: {missing}"
            )

    @classmethod
    def load(cls, name: str, size: int,
             bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
        cache_key = f"{name}|{size}|{bold}|{italic}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]
        pm = cls.path_map()
        path: Optional[str] = pm.get(name)
        if path is None:
            suffix = (" Bold Italic" if bold and italic
                      else " Bold" if bold
                      else " Italic" if italic else "")
            if suffix and (name + suffix) in pm:
                path = pm[name + suffix]
        if path is None:
            raise MissingFontError(
                f"Font '{name}' is not a bundled font (strict mode). "
                f"Available: {sorted(pm.keys())}"
            )
        font = ImageFont.truetype(path, size)
        cls._cache[cache_key] = font
        return font

    @classmethod
    def recommendations(cls, language: str) -> List[str]:
        return cls.RECOMMENDATIONS.get(language, cls.RECOMMENDATIONS["en"])

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()
        cls._path_map = None


class TextProcessor:
    @staticmethod
    def validate(text: str, max_len: int = 50) -> str:
        return (text or "").strip()[:max_len]

    @staticmethod
    def process(text: str, language: str) -> str:
        if not text:
            return text
        if language == "ar":
            if not ARABIC_SUPPORT:
                raise RuntimeError(
                    "Arabic text requires arabic_reshaper + python-bidi, "
                    "which are not installed. Refusing to render "
                    "unreshaped Arabic — it would look plausible to a "
                    "non-reader but be wrong."
                )
            reshaped = arabic_reshaper.reshape(text)
            return bidi_display(reshaped)
        return text

    @staticmethod
    def measure(text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
        tmp = Image.new("RGBA", (1, 1))
        bb = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
        return bb[2] - bb[0], bb[3] - bb[1]


class TemplateLoader:

    @staticmethod
    def load(name: str) -> dict:
        return core_templates.load(name)

    @staticmethod
    def resolve_background(filename: str) -> Optional[Path]:
        return core_templates.resolve_background(filename)


NAME_CUTOUT_CLASS_STROKE_PX = 5


class LabelGenerator:

    def __init__(self) -> None:
        self._tp = TextProcessor()

    def generate(self, cfg: LabelConfig) -> Image.Image:
        img = self._load_background(cfg.template_name, cfg.background_path)
        draw = ImageDraw.Draw(img)
        for zone, row_id in self._active_zones_with_row(cfg):
            self._render_any(draw, zone, cfg, row_id=row_id)
        return img


    def _load_background(self, template_name: str, background_path: str = "") -> Image.Image:
        tpl    = TemplateLoader.load(template_name)
        canvas = tpl["canvas"]
        w, h   = canvas["width"], canvas["height"]

        if background_path:
            p = Path(background_path)
            if p.exists():
                img = Image.open(p).convert("RGBA")
                return img.resize((w, h), Image.LANCZOS)

        bg_file = canvas.get("background_image")
        bg_path = TemplateLoader.resolve_background(bg_file) if bg_file else None
        if bg_path and bg_path.exists():
            img = Image.open(bg_path).convert("RGBA")
            return img.resize((w, h), Image.LANCZOS)

        return Image.new("RGBA", (w, h), (0, 0, 0, 0))


    @staticmethod
    def _all_zones(tpl: dict) -> List[dict]:
        zones: List[dict] = []
        for row in tpl.get("label_rows", []):
            zones.extend(row.get("text_zones", []))
        for grp in tpl.get("extra_zones", []):
            zones.extend(grp.get("text_zones", []))
        return zones

    def _active_zones_with_row(self, cfg: LabelConfig) -> List[Tuple[dict, str]]:
        tpl = TemplateLoader.load(cfg.template_name)
        result = []
        for row in tpl.get("label_rows", []):
            rid = row["id"]
            if cfg.active_rows is not None and rid not in cfg.active_rows:
                continue
            for z in row.get("text_zones", []):
                if cfg.active_zones is not None and z.get("id") not in cfg.active_zones:
                    continue
                result.append((z, rid))
        for grp in tpl.get("extra_zones", []):
            for z in grp.get("text_zones", []):
                if cfg.active_zones is not None and z.get("id") not in cfg.active_zones:
                    continue
                result.append((z, ""))
        return result


    def _render_any(self, draw: ImageDraw.ImageDraw,
                    zone: dict, cfg: LabelConfig, row_id: str = "") -> None:
        zone_id = zone.get("id", "")
        if cfg.zone_is_empty(zone_id):
            return

        default_key = zone.get("text_key", "name")
        text = cfg.zone_text(zone_id, default_key)
        if not text:
            return

        lang = cfg.zone_language(zone_id)
        if lang == cfg.language and default_key.endswith("_arabic"):
            lang = "ar"

        ovr = cfg.zone_overrides.get(zone_id, {})

        _zone_font_name = (ovr.get("font_name") or zone.get("font_name") or "")
        _tmpl_type = cfg.custom_fields.get("template_type", "")
        _CHROMATIX_KEYS = {"first_name", "full_name", "nickname", "initials"}
        _is_name_cutout = (_tmpl_type == "name_cutout")
        _is_chromatix_key = (
            default_key in _CHROMATIX_KEYS or
            (default_key == "name" and _is_name_cutout)
        )
        if _is_chromatix_key and not _zone_font_name:
            self._render_name_cutout_zone(draw, text, zone, cfg)
            return

        _is_class_zone = (default_key == "grade" and _is_name_cutout
                          and not _zone_font_name)
        if _is_class_zone:
            self._render_name_cutout_class(draw, text, zone, cfg)
            return

        font_name = (ovr.get("font_name")
                     or zone.get("font_name")
                     or cfg.effective_font_name(lang))
        _sz = ovr.get("font_size") or zone.get("font_size")
        fixed_size = int(_sz) if _sz else None
        rotate = zone.get("rotate", 0)
        text_color = cfg.zone_text_color(zone_id, zone)
        max_wrap_w = zone.get("max_wrap_width", 0)

        self._render_text(draw, text, zone, cfg,
                          font_name=font_name, lang=lang,
                          fixed_size=fixed_size, rotate=rotate,
                          text_color=text_color, max_wrap_width=max_wrap_w)


    def _render_name_cutout_zone(
        self,
        draw: "ImageDraw.ImageDraw",
        text: str,
        zone: dict,
        cfg: "LabelConfig",
    ) -> None:
        try:
            from core.chromatix_renderer import (
                ChromatixRenderer, NameFontUnavailable, diagnose,
            )
            from core import name_fonts as nf
        except ImportError as exc:
            raise RuntimeError(
                f"name-cutout rendering requires core.chromatix_renderer: {exc}"
            ) from exc

        if not text:
            text = cfg.custom_fields.get("full_name", "")
        if not text:
            log.warning("name-cutout zone %r has no text for record %r — "
                        "leaving it blank", zone.get("id", ""),
                        cfg.custom_fields.get("theme", ""))
            return

        slug = cfg.custom_fields.get("theme", "")
        problem = diagnose(slug)
        if problem:
            raise NameFontUnavailable(
                f"Cannot render name-cutout label: {problem}."
            )
        entry = nf.get(slug)
        rdr = ChromatixRenderer.shared(slug)

        from core.chromatix_renderer import sanitize as _sanitize
        text_clean = _sanitize(text,
                               entry.get("force_uppercase", True),
                               entry.get("strip_pattern"),
                               entry.get("case_mode"))
        if not text_clean:
            raise NameFontUnavailable(
                f"Name {text!r} is empty after sanitising for theme '{slug}' "
                f"(strip_pattern={entry.get('strip_pattern')!r}). A non-Latin "
                f"or punctuation-only name cannot be cut in this font — handle "
                f"this order manually."
            )

        if text_clean not in rdr._cache:
            rdr.warm([text])

        raw = rdr._cache.get(text_clean)
        if raw is None:
            raise NameFontUnavailable(
                f"Renderer produced no glyphs for {text_clean!r} using theme "
                f"'{slug}'. The font may not cover these characters."
            )

        zw_raw = zone.get("w", 100)
        zh_raw = zone.get("h", 40)
        rotate_cw = int(zone.get("rotate", 0) or 0)

        if rotate_cw in (90, 270):
            render_w, render_h = zh_raw, zw_raw
        else:
            render_w, render_h = zw_raw, zh_raw

        spx = int(entry.get("stroke_px", 12) or 0)
        stroke_pad = 2 * (spx + 2) if spx > 0 else 0
        fit_w = max(1, render_w - stroke_pad)
        fit_h = max(1, render_h - stroke_pad)

        scale = min(fit_w / max(raw.width, 1), fit_h / max(raw.height, 1), 1.0)

        size_scale = entry.get("size_scale")
        if size_scale is not None:
            try:
                size_scale = float(size_scale)
            except (TypeError, ValueError):
                size_scale = None
            if size_scale is not None:
                size_scale = max(0.01, min(1.0, size_scale))
                scale *= size_scale

        if scale < 0.995:
            from PIL import Image
            raw = raw.resize(
                (max(1, int(raw.width * scale)),
                 max(1, int(raw.height * scale))), Image.LANCZOS)

        from PIL import Image
        from core.chromatix_renderer import _morpho_stroke, _hex
        sc  = _hex(entry.get("stroke_color", "#ffffff")) + (255,)
        img = _morpho_stroke(raw, spx, sc, entry.get("stroke_smooth"),
                             bool(entry.get("fill_counters", True)))

        if rotate_cw == 90:
            img = img.transpose(Image.Transpose.ROTATE_270)
        elif rotate_cw == 270:
            img = img.transpose(Image.Transpose.ROTATE_90)
        elif rotate_cw == 180:
            img = img.transpose(Image.Transpose.ROTATE_180)

        zw, zh = zw_raw, zh_raw
        canvas = draw._image
        zx = zone.get("x", 0); zy = zone.get("y", 0)
        paste_x = zx + max(0, (zw - img.width) // 2)
        paste_y = zy + max(0, (zh - img.height) // 2)
        if canvas.mode == "RGBA":
            canvas.alpha_composite(img, (paste_x, paste_y))
        else:
            canvas.paste(img, (paste_x, paste_y), img)


    def _render_name_cutout_class(
        self,
        draw: "ImageDraw.ImageDraw",
        text: str,
        zone: dict,
        cfg: "LabelConfig",
    ) -> None:
        from core import name_fonts as nf
        slug = cfg.custom_fields.get("theme", "")
        cfp  = nf.class_font_path(slug)

        if not cfp or not cfp.exists():
            cfp = nf.class_font_path("name cutout smile")
        if not cfp or not cfp.exists():
            from core.chromatix_renderer import NameFontUnavailable
            raise NameFontUnavailable(
                f"No class font for theme '{slug}': neither its own "
                f"class_font_file nor the 'name cutout smile' default is "
                f"present in {nf.name_fonts_dir()}. Printing the name without "
                f"its class strip would be wrong, so the batch is stopped."
            )

        zx, zy = zone.get("x", 0), zone.get("y", 0)
        zw, zh = zone.get("w", 200), zone.get("h", 40)
        align  = zone.get("align", "center")
        rotate_cw = int(zone.get("rotate", 0) or 0) % 360
        if rotate_cw not in (0, 90, 180, 270):
            rotate_cw = 0

        if rotate_cw in (90, 270):
            layout_w, layout_h = zh, zw
        else:
            layout_w, layout_h = zw, zh

        lo, hi, best_fs = 6, 200, 6
        while lo <= hi:
            mid = (lo + hi) // 2
            f   = ImageFont.truetype(str(cfp), mid)
            bb  = draw.textbbox((0, 0), text, font=f)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            if tw <= layout_w - 4 and th <= layout_h - 4:
                best_fs = mid; lo = mid + 1
            else:
                hi = mid - 1

        font = ImageFont.truetype(str(cfp), best_fs)
        bb   = draw.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]

        stroke_px = NAME_CUTOUT_CLASS_STROKE_PX
        sc = (255, 255, 255, 255)

        if rotate_cw == 0:
            if align == "center":
                tx = zx + (zw - tw) // 2 - bb[0]
            elif align == "right":
                tx = zx + zw - tw - 2 - bb[0]
            else:
                tx = zx + 2 - bb[0]
            ty = zy + (zh - th) // 2 - bb[1]
            draw.text((tx, ty), text, font=font, fill=sc,
                      stroke_width=stroke_px, stroke_fill=sc)
            draw.text((tx, ty), text, font=font, fill=(25, 25, 25, 255))
            return

        tile = Image.new("RGBA", (layout_w, layout_h), (0, 0, 0, 0))
        tile_draw = ImageDraw.Draw(tile)
        if align == "center":
            tx = (layout_w - tw) // 2 - bb[0]
        elif align == "right":
            tx = layout_w - tw - 2 - bb[0]
        else:
            tx = 2 - bb[0]
        ty = (layout_h - th) // 2 - bb[1]
        tile_draw.text((tx, ty), text, font=font, fill=sc,
                        stroke_width=stroke_px, stroke_fill=sc)
        tile_draw.text((tx, ty), text, font=font, fill=(25, 25, 25, 255))

        if rotate_cw == 90:
            tile = tile.transpose(Image.Transpose.ROTATE_270)
        elif rotate_cw == 270:
            tile = tile.transpose(Image.Transpose.ROTATE_90)
        elif rotate_cw == 180:
            tile = tile.transpose(Image.Transpose.ROTATE_180)

        canvas = draw._image
        paste_x = zx + max(0, (zw - tile.width) // 2)
        paste_y = zy + max(0, (zh - tile.height) // 2)
        if canvas.mode == "RGBA":
            canvas.alpha_composite(tile, (paste_x, paste_y))
        else:
            canvas.paste(tile, (paste_x, paste_y), tile)

    def _wrap_to_width(self, text: str, font: ImageFont.FreeTypeFont,
                       max_w: int) -> List[str]:
        words = text.split()
        if not words:
            return []
        lines: List[str] = []
        cur = words[0]
        for w in words[1:]:
            trial = cur + " " + w
            tw, _ = self._tp.measure(trial, font)
            if tw <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        return lines

    def _measure_lines(self, lines, font, line_gap):
        widths, heights = [], []
        for ln in lines:
            w, h = self._tp.measure(ln, font)
            widths.append(w)
            heights.append(h)
        block_w = max(widths) if widths else 0
        block_h = sum(heights) + line_gap * max(len(lines) - 1, 0)
        return block_w, block_h, heights

    def _render_text(self, draw: ImageDraw.ImageDraw, text: str,
                     zone: dict, cfg: LabelConfig,
                     font_name: str, lang: str = "",
                     fixed_size: Optional[int] = None,
                     rotate: int = 0, no_wrap: bool = False,
                     text_color: Optional[Tuple[int, int, int]] = None,
                     max_wrap_width: int = 0) -> None:
        _lang = lang or cfg.language
        style = cfg.font
        color = text_color if text_color is not None else style.color

        zx, zy = zone["x"], zone["y"]
        zw, zh = zone["w"], zone["h"]
        pad    = zone.get("padding", 8)
        max_fs = zone.get("max_font_size", 72)
        min_fs = zone.get("min_font_size", 8)

        if rotate:
            tmp = Image.new("RGBA", (zw, zh), (0, 0, 0, 0))
            tdraw = ImageDraw.Draw(tmp)
            fake = {"x": 0, "y": 0, "w": zw, "h": zh,
                    "padding": pad, "max_font_size": max_fs,
                    "min_font_size": min_fs,
                    "max_wrap_width": max_wrap_width}
            self._render_text(tdraw, text, fake, cfg, font_name,
                              lang=_lang, fixed_size=fixed_size,
                              rotate=0, text_color=color,
                              max_wrap_width=max_wrap_width)
            rotated = tmp.rotate(-rotate, expand=True, resample=Image.BICUBIC)
            cx = zx + zw // 2
            cy = zy + zh // 2
            px = cx - rotated.width // 2
            py = cy - rotated.height // 2
            draw._image.paste(rotated, (px, py), rotated)
            return

        inner_w = max(zw - pad * 2, 12)
        inner_h = max(zh - pad * 2, 12)

        if max_wrap_width > 0:
            wrap_w = min(inner_w, max_wrap_width)
        else:
            wrap_w = inner_w

        def build_lines(fs: int):
            font = FontManager.load(font_name, fs, style.bold, style.italic)
            if no_wrap:
                raw = [text]
            else:
                src = text if _lang == "ar" else self._tp.process(text, _lang)
                raw = self._wrap_to_width(text if _lang == "ar" else src, font, wrap_w)
                if not raw:
                    raw = [src]
            lines = [self._tp.process(l, _lang) if _lang == "ar" else l for l in raw]
            return font, lines

        if fixed_size:
            fs = max(min(fixed_size, max(max_fs, fixed_size)), min_fs)
            font, lines = build_lines(fs)
        else:
            best = None
            lo, hi = min_fs, max_fs
            while lo <= hi:
                mid = (lo + hi) // 2
                font, lines = build_lines(mid)
                line_gap = max(int(mid * 0.12), 2)
                bw, bh, _ = self._measure_lines(lines, font, line_gap)
                if bw <= inner_w and bh <= inner_h:
                    best = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            fs = best if best is not None else min_fs
            font, lines = build_lines(fs)

        line_gap = max(int(fs * 0.12), 2)
        bw, bh, heights = self._measure_lines(lines, font, line_gap)

        cy = zy + (zh - bh) // 2
        cy = max(zy + pad, cy)
        for i, ln in enumerate(lines):
            lw, _ = self._tp.measure(ln, font)
            lx = zx + (zw - lw) // 2
            draw.text((lx, cy), ln, font=font, fill=color)
            cy += heights[i] + line_gap
