from __future__ import annotations

from typing import List

from PIL import Image

from core.units import Rect


def propose_regions(background: Image.Image, alpha_threshold: int = 8,
                    min_area_px: int = 2000) -> List[Rect]:
    try:
        import numpy as np
        from scipy import ndimage
    except ImportError as e:
        raise ImportError(
            "Region auto-proposal requires numpy and scipy (optional "
            "dependencies, §12). Install them or use manual authoring "
            "(§6.2 Primary Implementation) instead."
        ) from e

    if background.mode != "RGBA":
        background = background.convert("RGBA")
    alpha = np.array(background.getchannel("A"))
    mask = alpha > alpha_threshold

    labeled, num_features = ndimage.label(mask)
    rects: List[Rect] = []
    for i in range(1, num_features + 1):
        ys, xs = np.where(labeled == i)
        if xs.size == 0:
            continue
        x1, x2 = int(xs.min()), int(xs.max()) + 1
        y1, y2 = int(ys.min()), int(ys.max()) + 1
        rect = Rect.from_corners(x1, y1, x2, y2)
        if rect.area >= min_area_px:
            rects.append(rect)
    return rects
