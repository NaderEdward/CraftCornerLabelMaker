from __future__ import annotations

from dataclasses import dataclass


def mm_to_px(mm: float, dpi: int) -> int:
    return int(round(mm * dpi / 25.4))


def px_to_mm(px: int, dpi: int) -> float:
    return px * 25.4 / dpi


def scale_px(px: int, from_dpi: int, to_dpi: int) -> int:
    if from_dpi == to_dpi:
        return px
    return int(round(px * to_dpi / from_dpi))


@dataclass(frozen=True)
class Rect:

    x: int
    y: int
    w: int
    h: int

    def __post_init__(self) -> None:
        if self.w < 0 or self.h < 0:
            raise ValueError(f"Rect must have non-negative w,h: {self}")

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    @property
    def area(self) -> int:
        return self.w * self.h

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x2, self.y2)

    def intersects(self, other: "Rect") -> bool:
        return not (
            self.x2 <= other.x
            or other.x2 <= self.x
            or self.y2 <= other.y
            or other.y2 <= self.y
        )

    def contains(self, other: "Rect") -> bool:
        return (
            self.x <= other.x
            and self.y <= other.y
            and self.x2 >= other.x2
            and self.y2 >= other.y2
        )

    def scaled(self, from_dpi: int, to_dpi: int) -> "Rect":
        return Rect(
            x=scale_px(self.x, from_dpi, to_dpi),
            y=scale_px(self.y, from_dpi, to_dpi),
            w=scale_px(self.w, from_dpi, to_dpi),
            h=scale_px(self.h, from_dpi, to_dpi),
        )

    def inflated(self, by_px: int) -> "Rect":
        return Rect(
            x=self.x - by_px,
            y=self.y - by_px,
            w=self.w + 2 * by_px,
            h=self.h + 2 * by_px,
        )

    @classmethod
    def from_corners(cls, x1: int, y1: int, x2: int, y2: int) -> "Rect":
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        return cls(x=left, y=top, w=right - left, h=bottom - top)
