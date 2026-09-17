from __future__ import annotations

import atexit
import base64
import io
import logging
import math
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    import numpy as _np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


try:
    from fontTools.ttLib import TTFont
    _HAS_FONTTOOLS = True
except ImportError:
    _HAS_FONTTOOLS = False

try:
    import pymupdf as _fitz
    _HAS_FITZ = True
except ImportError:
    try:
        import fitz as _fitz
        _HAS_FITZ = True
    except ImportError:
        _HAS_FITZ = False

try:
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options as _FFOpts
    from selenium.webdriver.firefox.service import Service as _FFSvc
    _HAS_SELENIUM = True
except ImportError:
    _HAS_SELENIUM = False


FF_W         = 7600
FF_H         = 3100
RENDER_FS    = 1000


_driver = None

_driver_page_key = None

_page_nonce = 0


def _get_driver(geckodriver_path: Optional[str] = None):
    global _driver
    if _driver is not None:
        return _driver
    if not _HAS_SELENIUM:
        raise RuntimeError(
            "selenium is not installed. "
            "pip install selenium  and place geckodriver.exe on PATH."
        )
    opts = _FFOpts()
    opts.add_argument("-headless")
    opts.set_preference("gfx.font_rendering.cleartype_params.rendering_mode", 5)
    opts.set_preference("gfx.content.azure.backends", "skia")
    opts.set_preference("gfx.canvas.azure.backends", "skia")
    opts.set_preference("layers.acceleration.disabled", True)

    if geckodriver_path and Path(geckodriver_path).exists():
        svc = _FFSvc(executable_path=str(geckodriver_path))
    else:
        svc = _FFSvc()

    _driver = webdriver.Firefox(service=svc, options=opts)
    _driver.set_window_size(FF_W, FF_H)
    atexit.register(_close_driver)
    log.info("ChromatixRenderer: Firefox launched (PID %s)", _driver.service.process.pid
             if hasattr(_driver, 'service') else '?')
    return _driver


def _close_driver():
    global _driver, _driver_page_key
    if _driver:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None
        _driver_page_key = None


def _recover_alpha(img_b: "Image.Image",
                   img_w: "Image.Image") -> "Image.Image":
    w = min(img_b.width,  img_w.width)
    h = min(img_b.height, img_w.height)
    img_b = img_b.crop((0, 0, w, h))
    img_w = img_w.crop((0, 0, w, h))

    if _HAS_NUMPY:
        ab  = _np.asarray(img_b, dtype=_np.float64)
        aw  = _np.asarray(img_w, dtype=_np.float64)
        a_ch = _np.clip(255.0 - (aw - ab), 0, 255)
        safe = _np.maximum(a_ch, 1.0)
        rgb  = _np.clip(ab * 255.0 / safe, 0, 255)
        alpha = a_ch.max(axis=2)
        rgba  = _np.dstack([rgb, alpha]).astype(_np.uint8)
        out   = Image.fromarray(rgba, mode="RGBA")
    else:
        pb = img_b.load(); pw = img_w.load()
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        po  = out.load()
        for y in range(h):
            for x in range(w):
                rb, gb, bb_ = pb[x, y]
                rw, gw, bw  = pw[x, y]
                ar = max(0, min(255, 255 - (rw - rb)))
                ag = max(0, min(255, 255 - (gw - gb)))
                ab_= max(0, min(255, 255 - (bw - bb_)))
                a  = max(ar, ag, ab_)
                if a == 0:
                    continue
                po[x, y] = (min(255, int(rb  * 255 / max(ar,  1))),
                             min(255, int(gb  * 255 / max(ag,  1))),
                             min(255, int(bb_ * 255 / max(ab_, 1))), a)
    bbox = out.getbbox()
    return out.crop(bbox) if bbox else out


STROKE_CORNER_SMOOTH = 1.6


def _sq_dist_to_mask(mask: "_np.ndarray", max_r: float) -> "_np.ndarray":
    h, w = mask.shape
    R = int(math.ceil(max_r))
    BIG = float((R + 2) ** 2)

    xs = _np.arange(w, dtype=_np.float32)[None, :]
    left = _np.maximum.accumulate(
        _np.where(mask, xs, -_np.inf).astype(_np.float32), axis=1)
    right = _np.minimum.accumulate(
        _np.where(mask, xs, _np.inf).astype(_np.float32)[:, ::-1], axis=1)[:, ::-1]
    hx = _np.minimum(xs - left, right - xs)
    hx2 = _np.where(_np.isfinite(hx), hx * hx, BIG).astype(_np.float32)
    _np.clip(hx2, 0.0, BIG, out=hx2)

    best = hx2.copy()
    for dy in range(1, R + 1):
        dy2 = float(dy * dy)
        if dy2 > max_r * max_r:
            break
        shifted = _np.empty_like(hx2)
        shifted[dy:, :] = hx2[:-dy, :]
        shifted[:dy, :] = BIG
        _np.minimum(best, shifted + dy2, out=best)
        shifted = _np.empty_like(hx2)
        shifted[:-dy, :] = hx2[dy:, :]
        shifted[-dy:, :] = BIG
        _np.minimum(best, shifted + dy2, out=best)
    return best


def _fill_enclosed(alpha_f: "_np.ndarray") -> "_np.ndarray":
    solid = alpha_f >= 0.5
    if solid.all() or not solid.any():
        return alpha_f
    m = Image.fromarray(_np.where(solid, 255, 0).astype(_np.uint8), mode="L").copy()
    if m.getpixel((0, 0)) != 0:
        return alpha_f
    ImageDraw.floodfill(m, (0, 0), 128)
    arr = _np.asarray(m)
    if arr[0, 0] != 128:
        log.error("_fill_enclosed: flood fill had no effect; leaving counters "
                  "open rather than risking an opaque background.")
        return alpha_f
    holes = arr == 0
    if not holes.any():
        return alpha_f
    out = alpha_f.copy()
    out[holes] = 1.0
    return out


def _round_dilate_alpha(alpha_f: "_np.ndarray", radius: float) -> "_np.ndarray":
    if radius <= 0:
        return alpha_f
    inside = alpha_f >= 0.5
    if not inside.any():
        return alpha_f
    dist = _np.sqrt(_sq_dist_to_mask(inside, radius + 2.0))
    return _np.clip(radius + 0.5 - dist, 0.0, 1.0)


def _round_erode_alpha(alpha_f: "_np.ndarray", radius: float) -> "_np.ndarray":
    if radius <= 0:
        return alpha_f
    inside = alpha_f >= 0.5
    if inside.all() or not inside.any():
        return alpha_f
    dist = _np.sqrt(_sq_dist_to_mask(~inside, radius + 2.0))
    return _np.clip(dist - radius - 0.5, 0.0, 1.0)


def _morpho_stroke(glyph: "Image.Image", stroke_px: int,
                   colour: Tuple[int, int, int, int],
                   smooth_mult: Optional[float] = None,
                   fill_counters: bool = True) -> "Image.Image":
    r = max(0, int(stroke_px))
    if r <= 0:
        return glyph
    if not _HAS_NUMPY:
        log.error("numpy is unavailable — decorative strokes would be drawn "
                  "with a SQUARE kernel and print with flat, castellated "
                  "shoulders. Install numpy. Falling back for this run.")
        return _morpho_stroke_square(glyph, r, colour)

    mult = STROKE_CORNER_SMOOTH if smooth_mult is None else float(smooth_mult)
    smooth = max(0.0, round(r * max(0.0, mult)))
    pad = int(r + smooth + 2)
    w, h = glyph.size
    padded = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    padded.paste(glyph, (pad, pad))

    alpha_f = _np.asarray(padded.split()[3], dtype=_np.float32) / 255.0
    grown = _round_dilate_alpha(alpha_f, r + smooth)
    if smooth > 0:
        grown = _round_erode_alpha(grown, smooth)
    grown = _np.maximum(grown, alpha_f)
    if fill_counters:
        grown = _fill_enclosed(grown)

    stroke_layer = Image.new("RGBA", padded.size, tuple(colour[:3]) + (0,))
    stroke_layer.putalpha(
        Image.fromarray((grown * (colour[3] if len(colour) > 3 else 255))
                        .round().astype(_np.uint8), mode="L"))
    out = Image.alpha_composite(stroke_layer, padded)

    inset = pad - (r + 2)
    if inset > 0:
        out = out.crop((inset, inset, out.width - inset, out.height - inset))
    return out


def _morpho_stroke_square(glyph: "Image.Image", stroke_px: int,
                          colour: Tuple[int, int, int, int]) -> "Image.Image":
    w, h = glyph.size
    padded = Image.new("RGBA", (w + stroke_px * 2, h + stroke_px * 2), (0, 0, 0, 0))
    padded.paste(glyph, (stroke_px, stroke_px))
    alpha      = padded.split()[3]
    silhouette = alpha.point(lambda p: 255 if p > 20 else 0)
    size       = max(3, stroke_px * 2 + 1)
    dilated    = silhouette.filter(ImageFilter.MaxFilter(size))
    ring       = ImageChops.subtract(dilated, silhouette)
    sl         = Image.new("RGBA", padded.size, colour)
    fs         = Image.new("RGBA", padded.size, (0, 0, 0, 0))
    fs.paste(sl, mask=ring)
    return Image.alpha_composite(fs, padded)


_NICK_SPLIT = re.compile(
    r"""(
          \(.*?\)            # (Nickname)
        | \[.*?\]            # [Nickname]
        | ["“‘'].*?["”’']   # "Nickname" / 'Nickname'
        | \s+(?:aka|a\.k\.a\.?|or|/|\|)\s+.*$   # aka Nick / X or Y / X / Y
        | \s*&\s*.*$         # X & Y  (second child)
        | \s*\+\s*.*$        # X + Y
        | \s*,\s*.*$         # X, Y
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def primary_name(raw: str) -> str:
    if not raw:
        return ""
    s = str(raw).strip()
    s = _NICK_SPLIT.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip(" -–—,&+/|")
    return s


def _title_case(s: str) -> str:
    return re.sub(r"[A-Za-z]+",
                  lambda m: m.group(0)[:1].upper() + m.group(0)[1:].lower(),
                  s)


def sanitize(text: str, force_upper: bool = True,
             strip_pattern: Optional[str] = None,
             case_mode: Optional[str] = None) -> str:
    text = primary_name(text)
    mode = (case_mode or ("upper" if force_upper else "none")).strip().lower()
    if mode in ("upper", "uppercase", "caps"):
        s = text.upper()
    elif mode in ("title", "capitalize", "capitalise",
                  "capitalized", "capitalised"):
        s = _title_case(text)
    else:
        s = text
    if strip_pattern:
        s = re.sub(strip_pattern, "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class NameFontUnavailable(RuntimeError):
    pass


def diagnose(slug: str) -> str:
    from core import name_fonts as nf

    key = (slug or "").strip()
    if not key:
        return "the record has no theme slug in custom_fields['theme']"

    entry = nf.get(key)
    if not entry:
        return (f"theme '{key}' is not registered in data/name_fonts_config.json "
                f"(registered: {', '.join(nf.all_slugs()) or 'none'})")

    fp = nf.font_path(key)
    if not fp or not fp.exists():
        return (f"font file '{entry.get('font_file','?')}' for theme '{key}' is "
                f"missing from {nf.name_fonts_dir()}")

    if not _HAS_PIL:
        return "Pillow is not installed"

    try:
        rdr = ChromatixRenderer.shared(key)
    except Exception as exc:
        return f"renderer for theme '{key}' could not be built: {exc}"

    if rdr.available:
        return ""

    missing = []
    if not _HAS_FONTTOOLS:
        missing.append("fonttools")
    if not _HAS_FITZ:
        missing.append("pymupdf")
    if missing:
        return (f"theme '{key}': the offline SVG renderer needs "
                f"{' and '.join(missing)} (pip install {' '.join(missing)}), "
                f"and no Firefox/geckodriver fallback is available")
    if not _HAS_SELENIUM:
        return (f"font '{fp.name}' has no usable OpenType-SVG colour table and "
                f"selenium/Firefox is not installed for the fallback renderer")
    return f"theme '{key}': renderer reports itself unavailable"


def _words_to_html(text: str, space_w: int) -> str:
    spans = [f"<span>{w}</span>" for w in text.split()]
    return f"<span class='sp'></span>".join(spans)


class _SVGTableRenderer:

    def __init__(self, font_path: Path):
        self._path = font_path
        self._ok = False
        self._svg_docs = []
        self._cmap = {}
        self._gids = {}
        self._hmtx = {}
        self._upm = 1000
        self._ascent = 800
        self._descent = 200
        self._cache: Dict[Tuple[int, int], "Image.Image"] = {}
        self._load()

    def _load(self):
        if not (_HAS_FONTTOOLS and _HAS_FITZ and _HAS_PIL):
            return
        try:
            tt = TTFont(str(self._path))
            if "SVG " not in tt:
                return
            self._upm = tt["head"].unitsPerEm
            os2 = tt["OS/2"]
            self._ascent = os2.usWinAscent
            self._descent = os2.usWinDescent
            self._cmap = tt.getBestCmap() or {}
            self._gids = {n: i for i, n in enumerate(tt.getGlyphOrder())}
            self._hmtx = tt["hmtx"].metrics
            for (data, s, e) in tt["SVG "].docList:
                self._svg_docs.append(
                    (data if isinstance(data, str) else data.decode("utf-8"), s, e))
            self._ok = bool(self._svg_docs)
        except Exception as exc:
            log.warning("_SVGTableRenderer load failed for %s: %s", self._path, exc)

    @property
    def available(self) -> bool:
        return self._ok

    @property
    def _total_h(self) -> int:
        return self._ascent + self._descent

    def _svg_for(self, gid):
        for (svg, s, e) in self._svg_docs:
            if s <= gid <= e:
                return svg
        return None

    def _glyph(self, gid: int, px: int) -> "Image.Image":
        key = (gid, px)
        if key in self._cache:
            return self._cache[key]
        svg = self._svg_for(gid)
        scale = px / self._total_h
        w_px = max(1, int(self._upm * scale))
        if not svg:
            img = Image.new("RGBA", (w_px, px), (0, 0, 0, 0))
            self._cache[key] = img
            return img
        target_viewbox = f'viewBox="0 -{self._ascent} {self._upm} {self._total_h}"'
        if re.search(r'viewBox="[^"]*"', svg):
            fixed = re.sub(r'viewBox="[^"]*"', target_viewbox, svg, count=1)
        else:
            fixed = re.sub(r"(<svg\b)", rf"\1 {target_viewbox}", svg, count=1)
        SS = 4
        big_w, big_h = w_px * SS, px * SS
        sized = re.sub(r"(<svg\b[^>]*?)>",
                       lambda m: m.group(1) + f' width="{big_w}" height="{big_h}">',
                       fixed, count=1)
        try:
            doc = _fitz.open(stream=sized.encode(), filetype="svg")
            page = doc[0]
            sc = big_h / max(page.rect.height, 1)
            pix = page.get_pixmap(matrix=_fitz.Matrix(sc, sc), alpha=True)
            hi = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
            doc.close()
            img = hi.resize((w_px, px), Image.LANCZOS)
        except Exception as exc:
            log.warning("glyph %s render failed: %s", gid, exc)
            img = Image.new("RGBA", (w_px, px), (0, 0, 0, 0))
        self._cache[key] = img
        return img

    def _adv(self, gname, px):
        if gname in self._hmtx:
            return max(1, int(self._hmtx[gname][0] * px / self._total_h))
        return px // 2

    def render_line(self, text: str, px: int) -> "Image.Image":
        pieces = []
        total = 0
        for ch in text:
            gname = self._cmap.get(ord(ch))
            gid = self._gids.get(gname) if gname else None
            adv = self._adv(gname, px) if gname else px // 3
            img = (self._glyph(gid, px) if gid is not None
                   else Image.new("RGBA", (adv, px), (0, 0, 0, 0)))
            pieces.append((img, adv))
            total += adv
        if total <= 0:
            return Image.new("RGBA", (1, px), (0, 0, 0, 0))
        out = Image.new("RGBA", (total, px), (0, 0, 0, 0))
        x = 0
        for img, adv in pieces:
            out.alpha_composite(img, (x, 0))
            x += adv
        return out

    def render_lines(self, lines: List[str], px: int,
                     line_gap_mult: float = 1.0) -> "Image.Image":
        strips = []
        for ln in lines:
            strip = self.render_line(ln, px)
            bb = strip.getbbox()
            if bb:
                strips.append(strip.crop(bb))
        strips = [s for s in strips if s.width > 1]
        if not strips:
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        gap = int(px * 0.10 * line_gap_mult)
        w = max(s.width for s in strips)
        h = sum(s.height for s in strips) + gap * (len(strips) - 1)
        out = Image.new("RGBA", (w, max(1, h)), (0, 0, 0, 0))
        y = 0
        for s in strips:
            out.alpha_composite(s, ((w - s.width) // 2, max(0, y)))
            y += s.height + gap
        bb = out.getbbox()
        return out.crop(bb) if bb else out


class ChromatixRenderer:

    def __init__(
        self,
        font_path: Path,
        class_font_path: Optional[Path],
        stroke_px: int        = 12,
        stroke_color: str     = "#ffffff",
        line_gap_mult: float  = 1.0,
        gap_from_name: int    = 8,
        force_uppercase: bool = True,
        strip_pattern: Optional[str] = r"[^A-Z\s]",
        case_mode: Optional[str] = None,
        geckodriver_path: Optional[str] = None,
    ):
        self._font_path       = font_path
        self._cls_font_path   = class_font_path
        self._stroke_px       = stroke_px
        self._stroke_color    = stroke_color
        self._line_gap_mult   = line_gap_mult
        self._gap_from_name   = gap_from_name
        self._force_upper     = force_uppercase
        self._strip_pattern   = strip_pattern
        self._case_mode       = case_mode
        self._gecko           = geckodriver_path
        self._font_b64: Optional[str] = None
        self._page_key        = None
        self._page_nonce      = None
        self._cache: Dict[str, Image.Image] = {}
        self._offline = _SVGTableRenderer(font_path)
        self._use_firefox = False
        self._encode_font()
        if not self._offline.available:
            log.info("ChromatixRenderer: no usable SVG table in %s — "
                     "falling back to Firefox", font_path.name)
            self._use_firefox = True


    @classmethod
    def from_slug(cls, slug: str,
                  geckodriver_path: Optional[str] = None) -> "ChromatixRenderer":
        from core import name_fonts
        entry = name_fonts.get(slug)
        if not entry:
            raise ValueError(f"No name_fonts entry for slug '{slug}'")
        fp  = name_fonts.font_path(slug)
        cfp = name_fonts.class_font_path(slug)
        if not fp:
            raise FileNotFoundError(
                f"Font file '{entry['font_file']}' not found in "
                f"{name_fonts.name_fonts_dir()}"
            )
        return cls(
            font_path        = fp,
            class_font_path  = cfp,
            stroke_px        = entry.get("stroke_px",       12),
            stroke_color     = entry.get("stroke_color",    "#ffffff"),
            line_gap_mult    = entry.get("line_gap_mult",   1.0),
            gap_from_name    = entry.get("gap_from_name",   8),
            force_uppercase  = entry.get("force_uppercase", True),
            strip_pattern    = entry.get("strip_pattern",   None),
            case_mode        = entry.get("case_mode",       None),
            geckodriver_path = geckodriver_path,
        )

    _SHARED: Dict[str, "ChromatixRenderer"] = {}

    @classmethod
    def shared(cls, slug: str,
               geckodriver_path: Optional[str] = None) -> "ChromatixRenderer":
        key = slug.lower().strip()
        if key not in cls._SHARED:
            cls._SHARED[key] = cls.from_slug(key, geckodriver_path)
        return cls._SHARED[key]


    def _encode_font(self):
        if self._font_path and self._font_path.exists():
            with open(self._font_path, "rb") as fh:
                self._font_b64 = base64.b64encode(fh.read()).decode("utf-8")

    @property
    def available(self) -> bool:
        if not _HAS_PIL:
            return False
        if self._offline.available:
            return True
        return bool(self._font_b64) and _HAS_SELENIUM


    def _build_page(self, n_names: int, line_gap_mult: float):
        global _driver_page_key, _page_nonce
        key = (str(self._font_path), RENDER_FS, n_names, line_gap_mult)
        if (self._page_key == key and _driver_page_key == key
                and self._page_nonce == _page_nonce):
            return
        self._page_key = key
        _driver_page_key = key
        _page_nonce += 1
        self._page_nonce = _page_nonce

        font_url = f"data:font/opentype;base64,{self._font_b64}"
        gap_px   = int(RENDER_FS * 0.10 * line_gap_mult)
        space_w  = int(RENDER_FS * 0.30)

        divs = "\n".join(
            f'<div class="name-block">'
            f'<div id="L1_{i}" class="line"></div>'
            f'<div id="L2_{i}" class="line" style="margin-top:{gap_px}px"></div>'
            f'</div>'
            for i in range(n_names)
        )

        html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><style>
  @font-face {{
    font-family: 'ChromaFont';
    src: url('{font_url}') format('opentype');
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    background: var(--bg, #000000);
    width:{FF_W}px;
    overflow-x:hidden;
    padding: 20px 0;
  }}
  .name-block {{
    display:flex; flex-direction:column;
    align-items:center;
    padding: 30px 0;
    border-bottom: 1px solid transparent;
  }}
  .line {{
    font-family:'ChromaFont',sans-serif;
    font-size:{RENDER_FS}px;
    white-space:nowrap; color:black; line-height:1;
    font-variant-ligatures:common-ligatures discretionary-ligatures contextual;
    font-kerning:normal;
    text-rendering:optimizeLegibility;
    -webkit-font-smoothing:antialiased;
    display:inline-block;
  }}
  .sp {{ display:inline-block; width:{space_w}px; }}
</style></head>
<body data-page-nonce="{_page_nonce}">{divs}</body></html>"""

        import tempfile, os
        tmp = Path(tempfile.gettempdir()) / "_chromatix_batch.html"
        tmp.write_text(html, encoding="utf-8")
        drv = _get_driver(self._gecko)
        drv.get(f"file:///{str(tmp).replace(os.sep, '/')}")
        time.sleep(1.5)


    def warm(self, names: List[str]) -> None:
        if not self.available:
            log.warning("ChromatixRenderer.warm: renderer not available, skipping")
            return

        to_render: List[Tuple[str, List[str]]] = []
        seen_clean: set = set()
        for raw in names:
            clean = sanitize(raw, self._force_upper, self._strip_pattern, self._case_mode)
            if not clean or clean in self._cache or clean in seen_clean:
                continue
            seen_clean.add(clean)
            lines = _split_lines(clean)
            to_render.append((clean, lines))

        if not to_render:
            return

        log.info("ChromatixRenderer: warming %d names (%s)", len(to_render),
                 "offline SVG" if self._offline.available else "Firefox")

        if self._offline.available:
            for clean, lines in to_render:
                img = self._offline.render_lines(
                    lines, RENDER_FS, self._line_gap_mult)
                if img.width > 1:
                    self._cache[clean] = img
            log.info("ChromatixRenderer: warm complete (offline), %d cached",
                     len(self._cache))
            return

        self._build_page(len(to_render), self._line_gap_mult)
        drv = _get_driver(self._gecko)

        live_nonce = drv.execute_script(
            "return document.body ? document.body.dataset.pageNonce : null;")
        if live_nonce is None or int(live_nonce) != self._page_nonce:
            log.warning(
                "ChromatixRenderer: shared tab page mismatch (live=%r, "
                "expected=%r) — another renderer repointed it; rebuilding.",
                live_nonce, self._page_nonce)
            self._page_key = None
            global _driver_page_key
            _driver_page_key = None
            self._build_page(len(to_render), self._line_gap_mult)

        for i, (clean, lines) in enumerate(to_render):
            drv.execute_script(
                f"document.getElementById('L1_{i}').innerHTML = "
                f"{__import__('json').dumps(_words_to_html(lines[0], int(RENDER_FS*0.30)))};")
            if len(lines) > 1:
                drv.execute_script(
                    f"document.getElementById('L2_{i}').innerHTML = "
                    f"{__import__('json').dumps(_words_to_html(lines[1], int(RENDER_FS*0.30)))};")
        time.sleep(0.5)

        drv.execute_script("document.body.style.background='#000000'")
        time.sleep(0.1)
        png_b = drv.get_screenshot_as_png()
        drv.execute_script("document.body.style.background='#ffffff'")
        time.sleep(0.1)
        png_w = drv.get_screenshot_as_png()
        drv.execute_script("document.body.style.background='#000000'")

        img_b = Image.open(io.BytesIO(png_b)).convert("RGB")
        img_w = Image.open(io.BytesIO(png_w)).convert("RGB")

        for i, (clean, lines) in enumerate(to_render):
            r1 = drv.execute_script(
                f"var r=document.getElementById('L1_{i}').getBoundingClientRect();"
                "return [r.left,r.top,r.right,r.bottom];")
            r2 = drv.execute_script(
                f"var r=document.getElementById('L2_{i}').getBoundingClientRect();"
                "return [r.left,r.top,r.right,r.bottom];")

            if len(lines) > 1 and r2[3] > r2[1]:
                left  = int(min(r1[0], r2[0]))
                top   = int(min(r1[1], r2[1]))
                right = int(max(r1[2], r2[2]))
                bot   = int(max(r1[3], r2[3]))
            else:
                left, top, right, bot = int(r1[0]), int(r1[1]), int(r1[2]), int(r1[3])

            pad = 6
            box = (max(0, left-pad), max(0, top-pad),
                   min(img_b.width, right+pad), min(img_b.height, bot+pad))
            if box[2] <= box[0] or box[3] <= box[1]:
                log.warning("ChromatixRenderer: empty crop for '%s', skipping", clean)
                continue

            crop_b = img_b.crop(box)
            crop_w = img_w.crop(box)
            rgba   = _recover_alpha(crop_b, crop_w)
            self._cache[clean] = rgba
            log.debug("ChromatixRenderer: cached '%s' (%dx%d)", clean,
                      rgba.width, rgba.height)

        log.info("ChromatixRenderer: warm complete, %d in cache", len(self._cache))


    def get(
        self,
        raw_name: str,
        grade: str = "",
        max_w: int = 460,
        max_h: int = 220,
        stroke_px: Optional[int] = None,
        stroke_color: Optional[str] = None,
        overlap_px: Optional[int] = None,
    ) -> "Image.Image":
        clean  = sanitize(raw_name, self._force_upper, self._strip_pattern, self._case_mode)
        spx    = stroke_px    if stroke_px    is not None else self._stroke_px
        scol   = stroke_color if stroke_color is not None else self._stroke_color
        sc_rgb = _hex(scol) + (255,)
        ov     = overlap_px if overlap_px is not None else max(2, spx - 2)

        if clean not in self._cache:
            self.warm([raw_name])
        raw = self._cache.get(clean)
        if raw is None:
            log.error("ChromatixRenderer.get: failed to render %r", clean)
            return Image.new("RGBA", (max_w, max_h), (0, 0, 0, 0))

        cls_tile = None
        if grade and self._cls_font_path and self._cls_font_path.exists():
            target_h = max(12, int(raw.height * 0.30))
            d_tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
            fs, lo, hi = 8, 8, 400
            while lo <= hi:
                mid = (lo + hi) // 2
                f = _pil_font(self._cls_font_path, mid)
                _, th = _measure(d_tmp, grade, f)
                if th <= target_h:
                    fs = mid; lo = mid + 1
                else:
                    hi = mid - 1
            cf = _pil_font(self._cls_font_path, fs)
            bb = d_tmp.textbbox((0, 0), grade, font=cf)
            cw, ch = bb[2] - bb[0], bb[3] - bb[1]
            pad = 4
            cls_tile = Image.new("RGBA", (cw + pad * 2, ch + pad * 2), (0, 0, 0, 0))
            ImageDraw.Draw(cls_tile).text(
                (pad - bb[0], pad - bb[1]), grade, font=cf, fill=(25, 25, 25, 255))
            tb = cls_tile.getbbox()
            if tb:
                cls_tile = cls_tile.crop(tb)

        if cls_tile is not None:
            merged_w = max(raw.width, cls_tile.width)
            merged_h = raw.height + cls_tile.height - ov
            merged = Image.new("RGBA", (merged_w, max(1, merged_h)), (0, 0, 0, 0))
            merged.alpha_composite(raw, ((merged_w - raw.width) // 2, 0))
            cls_x = merged_w - cls_tile.width
            cls_y = raw.height - ov
            merged.alpha_composite(cls_tile, (max(0, cls_x), max(0, cls_y)))
        else:
            merged = raw

        avail_w = max(1, max_w - spx * 2 - 4)
        avail_h = max(1, max_h - spx * 2 - 4)
        scale = min(avail_w / max(merged.width, 1),
                    avail_h / max(merged.height, 1), 1.0)
        if scale < 0.995:
            merged = merged.resize(
                (max(1, int(merged.width * scale)),
                 max(1, int(merged.height * scale))), Image.LANCZOS)

        stroked = _morpho_stroke(merged, spx, sc_rgb)

        canvas = Image.new("RGBA", (max_w, max_h), (0, 0, 0, 0))
        canvas.alpha_composite(
            stroked,
            (max(0, (max_w - stroked.width) // 2),
             max(0, (max_h - stroked.height) // 2)))
        return canvas

    def close(self):
        self._cache.clear()


def _split_lines(text: str) -> List[str]:
    words = text.split()
    if len(words) <= 1:
        return words or [text]
    mid = len(words) // 2
    return [" ".join(words[:mid]), " ".join(words[mid:])]


def _hex(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _pil_font(path: Optional[Path], size: int) -> "ImageFont.FreeTypeFont":
    if path and path.exists():
        try:
            return ImageFont.truetype(str(path), max(1, size))
        except Exception:
            pass
    return ImageFont.load_default()


def _measure(draw, text, font) -> Tuple[int, int]:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]


def _autofit_cls(draw, text, font_path, zone_w, zone_h,
                 pad=4, min_fs=6, max_fs=80) -> Tuple["ImageFont.FreeTypeFont", int]:
    iw = max(zone_w - pad * 2, 4)
    ih = max(zone_h - pad * 2, 4)
    bf  = _pil_font(font_path, min_fs)
    bfs = min_fs
    lo, hi = min_fs, max_fs
    while lo <= hi:
        mid = (lo + hi) // 2
        f   = _pil_font(font_path, mid)
        tw, th = _measure(draw, text, f)
        if tw <= iw and th <= ih:
            bf, bfs = f, mid; lo = mid + 1
        else:
            hi = mid - 1
    return bf, bfs


def _rect_gap(r1: Tuple, r2: Tuple) -> float:
    hgap = max(r1[0] - r2[2], r2[0] - r1[2])
    vgap = max(r1[1] - r2[3], r2[1] - r1[3])
    if hgap >= 0 and vgap >= 0:
        return math.sqrt(hgap ** 2 + vgap ** 2)
    elif hgap >= 0:
        return hgap
    elif vgap >= 0:
        return vgap
    else:
        return max(hgap, vgap)


def _draw_class_strip(
    canvas: "Image.Image",
    grade: str,
    cls_font_path: Optional[Path],
    name_bb: Tuple[int, int, int, int],
    gap_px: int,
    stroke_px: int,
    stroke_col: str,
    label_w: int,
    label_h: int,
) -> None:
    draw = ImageDraw.Draw(canvas)
    d_tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    zone_w = int(label_w * 0.30)
    zone_h = int(label_h * 0.22)
    font, fs = _autofit_cls(d_tmp, grade, cls_font_path, zone_w, zone_h)

    tw, th = _measure(d_tmp, grade, font)
    sw = tw + stroke_px * 2 + 8
    sh = th + stroke_px * 2 + 6

    nx0, ny0, nx1, ny1 = name_bb
    cx = min(label_w - sw // 2, nx1 - sw // 4)
    cy = min(label_h - sh // 2, ny1 + gap_px + sh // 2)

    cx = max(sw // 2, min(label_w - sw // 2, cx))
    cy = max(sh // 2, min(label_h - sh // 2, cy))

    x0 = cx - sw // 2; y0 = cy - sh // 2
    sc = _hex(stroke_col) + (255,)
    draw.text((x0 - draw.textbbox((0, 0), grade, font=font)[0] + stroke_px + 4,
               y0 - draw.textbbox((0, 0), grade, font=font)[1] + stroke_px + 3),
              grade, font=font, fill=sc,
              stroke_width=stroke_px, stroke_fill=sc)
    draw.text((x0 - draw.textbbox((0, 0), grade, font=font)[0] + stroke_px + 4,
               y0 - draw.textbbox((0, 0), grade, font=font)[1] + stroke_px + 3),
              grade, font=font, fill=(30, 30, 30, 255))
