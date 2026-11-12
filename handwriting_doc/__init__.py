"""A3 handwriting-style document renderer for KDraw .gfont files."""

from .gfont import GFont, GFontError, Glyph, discover_fonts
from .renderer import GenerationResult, generate_document

__all__ = [
    "GFont",
    "GFontError",
    "Glyph",
    "GenerationResult",
    "discover_fonts",
    "generate_document",
]
