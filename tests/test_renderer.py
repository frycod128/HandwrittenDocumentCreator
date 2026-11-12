from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz

from handwriting_doc.renderer import generate_document


ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "字体素材"


class RendererTests(unittest.TestCase):
    def test_generates_a3_pdf_and_docx(self) -> None:
        fonts = [
            FONT_DIR / "常用_kvenjoy_美文.gfont",
            FONT_DIR / "超连笔快写-3500字_kvenjoy_gantry.gfont",
            FONT_DIR / "楷体_kvenjoy_大孔龙.gfont",
        ]
        text = (
            "这是 A3 双栏随机手写排版测试。每个字符会选择不同字体，"
            "并随机旋转、移动。\n\n"
            "English and numbers 12345 should remain in the same character flow. "
        ) * 7
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "test.pdf"
            docx = Path(directory) / "test.docx"
            result = generate_document(
                text,
                fonts,
                lines_per_column=52,
                output_pdf=output,
                output_docx=docx,
                seed=20261112,
            )
            self.assertTrue(output.is_file())
            self.assertTrue(docx.is_file())
            pdf = fitz.open(output)
            self.assertEqual(pdf.page_count, result.page_count)
            rect = pdf[0].rect
            self.assertGreater(rect.width, rect.height)
            self.assertAlmostEqual(rect.width, 420 / 25.4 * 72, delta=1)
            self.assertAlmostEqual(rect.height, 297 / 25.4 * 72, delta=1)
            self.assertGreater(len(pdf[0].get_drawings()), 10)
            pdf.close()
            self.assertGreater(docx.stat().st_size, 20_000)

if __name__ == "__main__":
    unittest.main()
