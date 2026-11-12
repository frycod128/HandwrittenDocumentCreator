from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass
from typing import Sequence

from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm

from .gfont import GFont, Glyph


A3_LANDSCAPE = landscape(A3)
PAGE_WIDTH, PAGE_HEIGHT = A3_LANDSCAPE
PAGE_MARGIN = 12.7 * mm
COLUMN_GAP = 7.5 * mm
COLUMN_WIDTH = (PAGE_WIDTH - 2 * PAGE_MARGIN - COLUMN_GAP) / 2
BODY_HEIGHT = PAGE_HEIGHT - 2 * PAGE_MARGIN

MAX_LINES_PER_COLUMN = 100
MIN_LINES_PER_COLUMN = 1


@dataclass(frozen=True, slots=True)
class LayoutMetrics:
    page_width: float
    page_height: float
    margin: float
    column_gap: float
    column_width: float
    body_height: float
    lines_per_column: int
    row_pitch: float
    font_size: float
    glyph_box: float
    usable_line_width: float
    side_padding: float
    column_x: tuple[float, float]
    tracking: float


@dataclass(frozen=True, slots=True)
class StyledChar:
    char: str
    font: GFont | None
    glyph: Glyph | None
    center_x: float
    width: float
    angle: float
    offset_x: float
    offset_y: float
    uses_fallback: bool = False


@dataclass(frozen=True, slots=True)
class FlowLine:
    items: tuple[StyledChar, ...]
    width: float
    explicit_break: bool = False


@dataclass(frozen=True, slots=True)
class PageLayout:
    number: int
    left_lines: tuple[FlowLine, ...]
    right_lines: tuple[FlowLine, ...]


@dataclass(frozen=True, slots=True)
class DocumentLayout:
    pages: tuple[PageLayout, ...]
    lines: tuple[FlowLine, ...]
    metrics: LayoutMetrics
    total_characters: int
    missing_characters: tuple[str, ...]


def build_metrics(
    lines_per_column: int,
    page_width: float = PAGE_WIDTH,
    page_height: float = PAGE_HEIGHT,
    margin: float = PAGE_MARGIN,
    column_gap: float = COLUMN_GAP,
) -> LayoutMetrics:
    if not MIN_LINES_PER_COLUMN <= lines_per_column <= MAX_LINES_PER_COLUMN:
        raise ValueError(
            f"每栏行数必须在 {MIN_LINES_PER_COLUMN} 到 {MAX_LINES_PER_COLUMN} 之间"
        )
    column_width = (page_width - 2 * margin - column_gap) / 2
    body_height = page_height - 2 * margin
    row_pitch = body_height / lines_per_column
    # Include the 10-degree rotated square and the 5% translation in the cell.
    font_size = row_pitch / 1.35
    glyph_box = font_size * 0.92
    tracking = font_size * 0.025
    side_padding = font_size * 0.22
    return LayoutMetrics(
        page_width=page_width,
        page_height=page_height,
        margin=margin,
        column_gap=column_gap,
        column_width=column_width,
        body_height=body_height,
        lines_per_column=lines_per_column,
        row_pitch=row_pitch,
        font_size=font_size,
        glyph_box=glyph_box,
        usable_line_width=column_width - 2 * side_padding,
        side_padding=side_padding,
        column_x=(margin, margin + column_width + column_gap),
        tracking=tracking,
    )


def _is_wide(char: str) -> bool:
    return (
        unicodedata.east_asian_width(char) in {"W", "F"}
        or ord(char) >= 0x2E80
    )


def _advance_for(
    char: str,
    glyph: Glyph | None,
    font: GFont | None,
    metrics: LayoutMetrics,
) -> float:
    em = metrics.font_size
    if char.isspace():
        return em * 0.45
    if glyph is None or font is None:
        return em * (1.0 if _is_wide(char) else 0.55)
    x_min, _, x_max, _ = glyph.bounds
    natural_width = (x_max - x_min) * em / font.reference[0]
    if _is_wide(char):
        return max(em * 0.92, natural_width + metrics.tracking)
    if char.isalnum():
        return max(em * 0.31, natural_width + metrics.tracking)
    return max(em * 0.34, natural_width + metrics.tracking)


class _FlowBuilder:
    def __init__(
        self,
        fonts: Sequence[GFont],
        metrics: LayoutMetrics,
        rng: random.Random,
    ):
        self.fonts = fonts
        self.metrics = metrics
        self.rng = rng
        self.lines: list[FlowLine] = []
        self.current: list[StyledChar] = []
        self.cursor = 0.0
        self.missing: set[str] = set()
        self._support_cache: dict[str, tuple[GFont, ...]] = {}

    def _supporting_fonts(self, char: str) -> tuple[GFont, ...]:
        cached = self._support_cache.get(char)
        if cached is None:
            cached = tuple(font for font in self.fonts if font.supports(char))
            self._support_cache[char] = cached
        return cached

    def _styled_char(self, char: str) -> StyledChar:
        if char.isspace():
            return StyledChar(
                char=char,
                font=None,
                glyph=None,
                center_x=self.cursor + self.metrics.font_size * 0.225,
                width=self.metrics.font_size * 0.45,
                angle=0.0,
                offset_x=0.0,
                offset_y=0.0,
            )
        candidates = self._supporting_fonts(char)
        font: GFont | None = self.rng.choice(candidates) if candidates else None
        glyph = font.glyph(char) if font is not None else None
        if font is None:
            self.missing.add(char)
        width = _advance_for(char, glyph, font, self.metrics)
        amplitude = self.metrics.font_size * 0.05
        return StyledChar(
            char=char,
            font=font,
            glyph=glyph,
            center_x=self.cursor + width / 2,
            width=width,
            angle=self.rng.uniform(-10.0, 10.0),
            offset_x=self.rng.uniform(-amplitude, amplitude),
            offset_y=self.rng.uniform(-amplitude, amplitude),
            uses_fallback=font is None,
        )

    def _commit(self, explicit_break: bool) -> None:
        items = list(self.current)
        while items and items[-1].char.isspace():
            items.pop()
        width = items[-1].center_x + items[-1].width / 2 if items else 0.0
        self.lines.append(
            FlowLine(tuple(items), min(width, self.metrics.usable_line_width), explicit_break)
        )
        self.current = []
        self.cursor = 0.0

    def add(self, text: str) -> None:
        for char in text:
            if char in {"\r", "\f"}:
                continue
            if char == "\n":
                self._commit(explicit_break=True)
                continue
            styled = self._styled_char(char)
            if (
                self.current
                and self.cursor + styled.width > self.metrics.usable_line_width + 0.01
            ):
                self._commit(explicit_break=False)
                if char.isspace():
                    continue
                styled = self._styled_char(char)
            if not self.current and char.isspace():
                continue
            self.current.append(styled)
            self.cursor += styled.width
        if self.current or not self.lines:
            self._commit(explicit_break=False)


def build_layout(
    text: str,
    fonts: Sequence[GFont],
    lines_per_column: int,
    rng: random.Random,
) -> DocumentLayout:
    if not fonts:
        raise ValueError("至少需要选择一种字体")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    metrics = build_metrics(lines_per_column)
    builder = _FlowBuilder(fonts, metrics, rng)
    builder.add(normalized)
    lines = tuple(builder.lines)
    lines_per_page = lines_per_column * 2
    pages: list[PageLayout] = []
    for page_index, start in enumerate(range(0, len(lines), lines_per_page), start=1):
        chunk = lines[start : start + lines_per_page]
        pages.append(
            PageLayout(
                number=page_index,
                left_lines=tuple(chunk[:lines_per_column]),
                right_lines=tuple(chunk[lines_per_column:]),
            )
        )
    return DocumentLayout(
        pages=tuple(pages),
        lines=lines,
        metrics=metrics,
        total_characters=sum(1 for char in normalized if not char.isspace()),
        missing_characters=tuple(sorted(builder.missing)),
    )
