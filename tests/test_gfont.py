from __future__ import annotations

import unittest
from pathlib import Path

from handwriting_doc.gfont import GFont, discover_fonts


ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "字体素材"


class GFontTests(unittest.TestCase):
    def test_reads_glyph_strokes(self) -> None:
        with GFont(FONT_DIR / "熊仔.gfont") as font:
            self.assertEqual(font.character_count, 49)
            self.assertTrue(font.supports("A"))
            glyph = font.glyph("A")
            self.assertGreaterEqual(len(glyph.segments), 1)
            self.assertGreater(glyph.bounds[2], glyph.bounds[0])
            self.assertGreater(glyph.bounds[3], glyph.bounds[1])

    def test_discovers_all_usable_fonts(self) -> None:
        infos = discover_fonts(FONT_DIR)
        self.assertEqual(len(infos), 80)
        usable = [info for info in infos if info.available]
        self.assertGreaterEqual(len(usable), 79)
        self.assertTrue(all(info.character_count > 0 for info in usable))

    def test_common_font_uses_normalized_metrics(self) -> None:
        with GFont(FONT_DIR / "常用_kvenjoy_美文.gfont") as font:
            self.assertTrue(font.supports("中"))
            reference_size, center_y = font.reference
            self.assertGreater(reference_size, 50)
            self.assertLess(reference_size, 1000)
            self.assertLess(center_y, 100)


if __name__ == "__main__":
    unittest.main()
