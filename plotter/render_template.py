from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from core import templates as core_templates
from core.render_engine import LabelConfig, LabelGenerator
from core.units import px_to_mm


_DEFAULTS = {
    "name":         "Ahmed Al-Rashidi",
    "name_arabic":  "أحمد الراشدي",
    "school":       "Greenfield International School",
    "grade":        "Grade 3",
    "order_number": "#TEST01",
    "telephone":    "+20100000001",
}


def render_template(
    template_name: str,
    out_path: Path,
    sample: dict | None = None,
    grid_spacing_px: int = 100,
    annotate: bool = True,
) -> Image.Image:
    fields = {**_DEFAULTS, **(sample or {})}

    cfg = LabelConfig(
        name=fields["name"],
        name_arabic=fields.get("name_arabic", ""),
        school=fields["school"],
        grade=fields["grade"],
        order_number=fields.get("order_number", ""),
        telephone=fields.get("telephone", ""),
        template_name=template_name,
    )

    generator = LabelGenerator()
    img = generator.generate(cfg)

    if annotate and grid_spacing_px > 0:
        _draw_grid(img, grid_spacing_px, template_name)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path), "PNG")
    return img


def _draw_grid(img: Image.Image, spacing: int, template_name: str) -> None:
    tpl = core_templates.load(template_name)
    native_dpi = tpl.get("canvas", {}).get("native_dpi", 300)

    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    grid_col = (0, 120, 200, 100)
    label_col = (20, 20, 20, 220)
    label_bg  = (255, 255, 255, 160)

    font_size = max(18, w // 120)
    try:
        from core import paths as core_paths
        font_path = core_paths.bundled_fonts_dir() / "DejaVuSans-Regular.ttf"
        font = ImageFont.truetype(str(font_path), font_size)
    except Exception:
        font = ImageFont.load_default()

    for x in range(0, w + 1, spacing):
        draw.line([(x, 0), (x, h)], fill=grid_col, width=1)
        mm = px_to_mm(x, native_dpi)
        label = f"{x}px / {mm:.0f}mm"
        bbox = draw.textbbox((0, 0), label, font=font)
        lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.rectangle([(x + 2, 2), (x + 2 + lw + 4, 2 + lh + 2)], fill=label_bg)
        draw.text((x + 4, 2), label, font=font, fill=label_col)

    for y in range(0, h + 1, spacing):
        draw.line([(0, y), (w, y)], fill=grid_col, width=1)
        mm = px_to_mm(y, native_dpi)
        label = f"{y}px / {mm:.0f}mm"
        bbox = draw.textbbox((0, 0), label, font=font)
        lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.rectangle([(2, y + 2), (2 + lw + 4, y + 2 + lh + 2)], fill=label_bg)
        draw.text((4, y + 2), label, font=font, fill=label_col)

    img.alpha_composite(overlay)
