from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz
from reportlab.pdfgen.canvas import Canvas

from handwriting_doc.image_pdf import (
    DEFAULT_IMAGE_PDF_DPI,
    MAX_IMAGE_PDF_DPI,
    MIN_IMAGE_PDF_DPI,
    export_pdf_pages_to_image_pdf,
)
from handwriting_doc.layout import A3_LANDSCAPE


def write_vector_pdf(path: Path, pages: int = 3) -> None:
    canvas = Canvas(str(path), pagesize=A3_LANDSCAPE)
    canvas.setFont("Helvetica", 24)
    for index in range(pages):
        canvas.setLineWidth(0.6)
        canvas.line(40, 40, 500, 300)
        canvas.circle(320, 300, 80, stroke=1, fill=0)
        canvas.drawString(40, 520, f"vector page {index + 1}")
        canvas.showPage()
    canvas.save()


class ImagePdfTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "vector.pdf"
        self.destination = self.root / "image.pdf"
        write_vector_pdf(self.source, pages=3)

    def test_each_page_becomes_one_full_page_image(self) -> None:
        progress: list[tuple[int, int]] = []
        export_pdf_pages_to_image_pdf(
            self.source,
            self.destination,
            dpi=100,
            progress=lambda done, total: progress.append((done, total)),
        )
        self.assertEqual(progress, [(1, 3), (2, 3), (3, 3)])
        self.assertFalse((self.root / "image.part.pdf").exists())

        source = fitz.open(self.source)
        rebuilt = fitz.open(self.destination)
        try:
            self.assertEqual(rebuilt.page_count, source.page_count)
            for number, page in enumerate(rebuilt):
                self.assertAlmostEqual(
                    page.rect.width, source[number].rect.width, delta=0.01
                )
                self.assertAlmostEqual(
                    page.rect.height, source[number].rect.height, delta=0.01
                )
                images = page.get_images(full=True)
                self.assertEqual(len(images), 1)
                self.assertEqual(page.get_drawings(), [])
                self.assertEqual(page.get_text(), "")
                self.assertEqual(page.get_fonts(), [])
                self.assertLessEqual(
                    abs(images[0][2] - page.rect.width / 72 * 100), 1
                )
                self.assertLessEqual(
                    abs(images[0][3] - page.rect.height / 72 * 100), 1
                )
                info = rebuilt.extract_image(images[0][0])
                self.assertEqual(info["ext"], "png")
        finally:
            rebuilt.close()
            source.close()

    def test_default_dpi_is_print_quality(self) -> None:
        self.assertEqual(DEFAULT_IMAGE_PDF_DPI, 300)

    def test_pixel_size_follows_the_requested_dpi(self) -> None:
        export_pdf_pages_to_image_pdf(self.source, self.destination, dpi=72)
        rebuilt = fitz.open(self.destination)
        try:
            page = rebuilt[0]
            width, height = page.get_images(full=True)[0][2:4]
            self.assertLessEqual(abs(width - page.rect.width), 1)
            self.assertLessEqual(abs(height - page.rect.height), 1)
        finally:
            rebuilt.close()

    def test_rejects_overwriting_the_vector_source(self) -> None:
        with self.assertRaises(ValueError):
            export_pdf_pages_to_image_pdf(self.source, self.source)

    def test_rejects_dpi_outside_the_supported_range(self) -> None:
        for dpi in (MIN_IMAGE_PDF_DPI - 1, MAX_IMAGE_PDF_DPI + 1):
            with self.subTest(dpi=dpi):
                with self.assertRaises(ValueError):
                    export_pdf_pages_to_image_pdf(self.source, self.destination, dpi=dpi)

    def test_missing_source_fails_before_creating_output(self) -> None:
        with self.assertRaises(FileNotFoundError):
            export_pdf_pages_to_image_pdf(
                self.root / "missing.pdf", self.destination
            )
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
