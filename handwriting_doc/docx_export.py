from __future__ import annotations

import io
import os
from pathlib import Path

import pymupdf as fitz
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.shared import Mm


def export_pdf_pages_to_docx(
    pdf_path: str | Path,
    docx_path: str | Path,
    dpi: int = 180,
) -> Path:
    """Embed each PDF page as a full A3-landscape image in Word."""
    source = Path(pdf_path)
    destination = Path(docx_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.stem}.part{destination.suffix}")

    pdf = fitz.open(source)
    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Mm(420)
    section.page_height = Mm(297)
    section.top_margin = Mm(0)
    section.bottom_margin = Mm(0)
    section.left_margin = Mm(0)
    section.right_margin = Mm(0)
    section.header_distance = Mm(0)
    section.footer_distance = Mm(0)

    try:
        for index, pdf_page in enumerate(pdf):
            pixmap = pdf_page.get_pixmap(
                dpi=dpi,
                colorspace=fitz.csRGB,
                alpha=False,
            )
            image = io.BytesIO(pixmap.tobytes("png"))
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_before = Mm(0)
            paragraph.paragraph_format.space_after = Mm(0)
            paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
            paragraph.add_run().add_picture(
                image,
                width=section.page_width,
                height=section.page_height,
            )
            if index < pdf.page_count - 1:
                document.add_page_break()

        document.core_properties.title = "A3 随机手写字体文档"
        document.core_properties.subject = "A3 横向双栏逐字随机手写排版"
        document.save(temporary)
    finally:
        pdf.close()

    os.replace(temporary, destination)
    return destination
