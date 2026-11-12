from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz
from docx import Document

from handwriting_doc.gfont import GFont
from handwriting_doc.layout import build_layout
from handwriting_doc.renderer import generate_document


ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "字体素材"


class PracticalDensityTests(unittest.TestCase):
    def test_practical_46_to_58_line_density(self) -> None:
        paths = (
            FONT_DIR / "常用_kvenjoy_美文.gfont",
            FONT_DIR / "超连笔快写-3500字_kvenjoy_gantry.gfont",
            FONT_DIR / "楷体_kvenjoy_大孔龙.gfont",
        )
        text = "中英文 mixed 文本，逐字随机手写排版。Handwriting 2026。" * 550
        sizes: dict[int, float] = {}
        with (
            GFont(paths[0]) as first,
            GFont(paths[1]) as second,
            GFont(paths[2]) as third,
        ):
            for lines_per_column in (46, 52, 58):
                layout = build_layout(
                    text,
                    [first, second, third],
                    lines_per_column=lines_per_column,
                    rng=random.Random(4600 + lines_per_column),
                )
                sizes[lines_per_column] = layout.metrics.font_size
                self.assertGreaterEqual(len(layout.lines), lines_per_column * 2)
                first_page = layout.pages[0]
                self.assertEqual(len(first_page.left_lines), lines_per_column)
                self.assertEqual(len(first_page.right_lines), lines_per_column)
                for item in layout.lines[0].items:
                    if item.char.isspace():
                        continue
                    self.assertGreaterEqual(item.angle, -10)
                    self.assertLessEqual(item.angle, 10)
                    self.assertLessEqual(
                        abs(item.offset_x), layout.metrics.font_size * 0.05
                    )
                    self.assertLessEqual(
                        abs(item.offset_y), layout.metrics.font_size * 0.05
                    )
        self.assertGreater(sizes[46], sizes[52])
        self.assertGreater(sizes[52], sizes[58])

    def test_full_text_is_preserved_across_wraps(self) -> None:
        paths = (
            FONT_DIR / "常用_kvenjoy_美文.gfont",
            FONT_DIR / "乐行书_kvenjoy_乐乐.gfont",
        )
        text = (
            "完整保留中文、English words、数字 2026 和标点。\n"
            "第二段 content must not disappear.\n\n"
            "最后一行 final line。"
        ) * 90
        with GFont(paths[0]) as first, GFont(paths[1]) as second:
            layout = build_layout(text, [first, second], 52, random.Random(7))
        rendered = "".join(
            item.char
            for line in layout.lines
            for item in line.items
            if not item.char.isspace()
        )
        expected = "".join(char for char in text if not char.isspace())
        self.assertEqual(rendered, expected)

    def test_15000_mixed_characters_at_52_lines(self) -> None:
        fonts = [
            FONT_DIR / "常用_kvenjoy_美文.gfont",
            FONT_DIR / "超连笔快写-3500字_kvenjoy_gantry.gfont",
            FONT_DIR / "楷体_kvenjoy_大孔龙.gfont",
            FONT_DIR / "乐行书_kvenjoy_乐乐.gfont",
        ]
        base = "数字化时代，文字承载节奏与温度。Handwriting is personal 2026。"
        text = (base * 500)[:15_000]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "stress.pdf"
            output_docx = Path(directory) / "stress.docx"
            result = generate_document(
                text,
                fonts,
                lines_per_column=52,
                output_pdf=output,
                output_docx=output_docx,
                seed=20261112,
            )
            self.assertEqual(
                result.character_count,
                sum(not char.isspace() for char in text),
            )
            self.assertGreaterEqual(result.page_count, 2)
            pdf = fitz.open(output)
            self.assertEqual(pdf.page_count, result.page_count)
            margin = 12.7 / 25.4 * 72
            for page in pdf:
                rects = [drawing["rect"] for drawing in page.get_drawings()]
                self.assertTrue(rects)
                self.assertGreaterEqual(min(rect.x0 for rect in rects), margin - 1)
                self.assertGreaterEqual(min(rect.y0 for rect in rects), margin - 1)
                self.assertLessEqual(
                    max(rect.x1 for rect in rects),
                    page.rect.width - margin + 1,
                )
                self.assertLessEqual(
                    max(rect.y1 for rect in rects),
                    page.rect.height - margin + 1,
                )
            pdf.close()
            word = Document(output_docx)
            self.assertEqual(len(word.inline_shapes), result.page_count)
            page_breaks = word.element.xpath(".//w:br[@w:type='page']")
            self.assertEqual(len(page_breaks), result.page_count - 1)
            for paragraph in word.paragraphs:
                if paragraph._element.xpath(".//w:br[@w:type='page']"):
                    self.assertTrue(paragraph._element.xpath(".//w:drawing"))


if __name__ == "__main__":
    unittest.main()
