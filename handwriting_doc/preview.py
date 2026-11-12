from __future__ import annotations

from dataclasses import dataclass

from .gfont import GFont


@dataclass(frozen=True, slots=True)
class PreviewGeometry:
    segments: tuple[tuple[tuple[float, float], ...], ...]


def build_preview_geometry(
    font: GFont,
    char: str,
    width: float,
    height: float,
    padding: float = 10.0,
) -> PreviewGeometry:
    """Scale one glyph's original vector strokes into a preview canvas."""
    if not font.supports(char):
        raise ValueError(f"{font.path.name} 缺少字符 {char!r}")
    glyph = font.glyph(char)
    reference_size, reference_y = font.reference
    x_min, _, x_max, _ = glyph.bounds
    glyph_center_x = (x_min + x_max) / 2
    target_size = max(1.0, min(width - padding * 2, height - padding * 2) * 0.9)
    scale = target_size / reference_size
    center_x = width / 2
    center_y = height / 2
    segments = tuple(
        tuple(
            (
                center_x + (x - glyph_center_x) * scale,
                center_y + (y - reference_y) * scale,
            )
            for x, y in segment
        )
        for segment in glyph.segments
    )
    return PreviewGeometry(segments=segments)
