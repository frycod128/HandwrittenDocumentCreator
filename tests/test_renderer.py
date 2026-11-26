from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz

from handwriting_doc.renderer import generate_document, new_seed


ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "字体素材"


class RendererTests(unittest.TestCase):
    def test_new_seed_stays_in_the_documented_range(self) -> None:
        seeds = {new_seed() for _ in range(20)}
        self.assertTrue(all(isinstance(seed, int) for seed in seeds))
        self.assertTrue(all(0 <= seed < 2**31 for seed in seeds))
        self.assertGreater(len(seeds), 1)

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
            image_pdf = Path(directory) / "test_image.pdf"
            result = generate_document(
                text,
                fonts,
                lines_per_column=52,
                output_pdf=output,
                output_docx=docx,
                seed=20261112,
                output_image_pdf=image_pdf,
                image_pdf_dpi=72,
            )
            self.assertTrue(output.is_file())
            self.assertTrue(docx.is_file())
            self.assertTrue(image_pdf.is_file())
            self.assertEqual(result.image_pdf_path, image_pdf)
            pdf = fitz.open(output)
            self.assertEqual(pdf.page_count, result.page_count)
            rect = pdf[0].rect
            self.assertGreater(rect.width, rect.height)
            self.assertAlmostEqual(rect.width, 420 / 25.4 * 72, delta=1)
            self.assertAlmostEqual(rect.height, 297 / 25.4 * 72, delta=1)
            self.assertGreater(len(pdf[0].get_drawings()), 10)
            pdf.close()
            image_document = fitz.open(image_pdf)
            try:
                self.assertEqual(image_document.page_count, result.page_count)
                for page in image_document:
                    self.assertEqual(len(page.get_images()), 1)
                    self.assertEqual(page.get_drawings(), [])
                    self.assertEqual(page.get_text(), "")
            finally:
                image_document.close()
            self.assertGreater(docx.stat().st_size, 20_000)

    def test_image_pdf_options_are_validated_before_rendering(self) -> None:
        fonts = [FONT_DIR / "常用_kvenjoy_美文.gfont"]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "test.pdf"
            image_pdf = Path(directory) / "image.pdf"
            for options in (
                {"output_image_pdf": image_pdf, "image_pdf_dpi": 10},
                {"output_image_pdf": output},
            ):
                with self.subTest(options=options):
                    with self.assertRaises(ValueError):
                        generate_document(
                            "测试文本",
                            fonts,
                            lines_per_column=52,
                            output_pdf=output,
                            **options,
                        )
                    self.assertFalse(output.exists())
                    self.assertFalse(image_pdf.exists())

    def test_vector_pdf_is_discarded_when_not_requested(self) -> None:
        fonts = [FONT_DIR / "常用_kvenjoy_美文.gfont"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "dropped.pdf"
            image_pdf = root / "dropped_image.pdf"
            result = generate_document(
                "只保留纯图片 PDF 的测试文本。",
                fonts,
                lines_per_column=52,
                output_pdf=output,
                output_image_pdf=image_pdf,
                image_pdf_dpi=72,
                seed=3,
                keep_pdf=False,
            )
            self.assertIsNone(result.pdf_path)
            self.assertFalse(output.exists())
            self.assertTrue(image_pdf.is_file())
            self.assertEqual(
                sorted(item.name for item in root.iterdir()),
                [image_pdf.name],
            )

    def test_keep_pdf_false_requires_a_derived_output(self) -> None:
        fonts = [FONT_DIR / "常用_kvenjoy_美文.gfont"]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dropped.pdf"
            with self.assertRaises(ValueError):
                generate_document(
                    "测试文本",
                    fonts,
                    lines_per_column=52,
                    output_pdf=output,
                    keep_pdf=False,
                )
            self.assertFalse(output.exists())

    def test_temporary_vector_pdf_is_removed_after_a_failed_export(self) -> None:
        fonts = [FONT_DIR / "常用_kvenjoy_美文.gfont"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blocker = root / "blocker"
            blocker.write_text("not a directory", encoding="utf-8")
            with self.assertRaises(OSError):
                generate_document(
                    "测试文本",
                    fonts,
                    lines_per_column=52,
                    output_pdf=root / "dropped.pdf",
                    output_docx=blocker / "out.docx",
                    keep_pdf=False,
                )
            self.assertEqual(sorted(item.name for item in root.iterdir()), ["blocker"])

if __name__ == "__main__":
    unittest.main()
