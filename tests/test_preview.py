from __future__ import annotations

import unittest
from pathlib import Path

from handwriting_doc.gfont import GFont
from handwriting_doc.preview import build_preview_geometry


ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "字体素材"


class PreviewTests(unittest.TestCase):
    def test_preview_uses_the_selected_fonts_original_strokes(self) -> None:
        selected = FONT_DIR / "楷体_kvenjoy_大孔龙.gfont"
        with GFont(selected) as font:
            geometry = build_preview_geometry(font, "中", 360, 120, padding=12)
        self.assertGreaterEqual(len(geometry.segments), 1)
        points = [point for segment in geometry.segments for point in segment]
        self.assertTrue(points)
        self.assertTrue(all(0 <= x <= 360 and 0 <= y <= 120 for x, y in points))

    def test_preview_rejects_missing_glyph(self) -> None:
        selected = FONT_DIR / "签名.gfont"
        with GFont(selected) as font:
            with self.assertRaises(ValueError):
                build_preview_geometry(font, "中", 300, 100)


if __name__ == "__main__":
    unittest.main()
