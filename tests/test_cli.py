from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz

from handwriting_doc.cli import _parser, run_cli
from handwriting_doc.image_pdf import DEFAULT_IMAGE_PDF_DPI


class CliParserTests(unittest.TestCase):
    def test_restore_text_is_accepted_together_with_gui(self) -> None:
        args = _parser().parse_args(["--gui", "--restore-text", "restore.txt"])
        self.assertTrue(args.gui)
        self.assertEqual(args.restore_text, "restore.txt")

    def test_restore_text_is_internal_and_hidden_from_help(self) -> None:
        help_text = _parser().format_help()
        self.assertNotIn("--restore-text", help_text)

    def test_image_pdf_is_off_by_default(self) -> None:
        args = _parser().parse_args([])
        self.assertIsNone(args.image_pdf)
        self.assertEqual(args.image_pdf_dpi, DEFAULT_IMAGE_PDF_DPI)

    def test_image_pdf_flag_uses_an_automatic_name(self) -> None:
        args = _parser().parse_args(["--image-pdf"])
        self.assertEqual(args.image_pdf, "AUTO")

    def test_image_pdf_accepts_an_explicit_path_and_dpi(self) -> None:
        args = _parser().parse_args(
            ["--image-pdf", r"D:\out\print.pdf", "--image-pdf-dpi", "150"]
        )
        self.assertEqual(args.image_pdf, r"D:\out\print.pdf")
        self.assertEqual(args.image_pdf_dpi, 150)


class CliImagePdfTests(unittest.TestCase):
    def test_image_pdf_is_written_next_to_the_vector_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.txt"
            source.write_text("手写测试 handwriting 2026。", encoding="utf-8")
            output = root / "doc.pdf"
            args = _parser().parse_args(
                [
                    "--input",
                    str(source),
                    "--fonts",
                    "常用_kvenjoy_美文.gfont",
                    "--output",
                    str(output),
                    "--image-pdf",
                    "--image-pdf-dpi",
                    "72",
                    "--seed",
                    "1",
                ]
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_cli(args), 0)
            image_pdf = root / "doc_纯图片.pdf"
            self.assertTrue(output.is_file())
            self.assertTrue(image_pdf.is_file())
            document = fitz.open(image_pdf)
            try:
                self.assertEqual(document.page_count, 1)
                self.assertEqual(len(document[0].get_images()), 1)
                self.assertEqual(document[0].get_drawings(), [])
                self.assertEqual(document[0].get_text(), "")
            finally:
                document.close()


if __name__ == "__main__":
    unittest.main()
