"""把已有矢量 PDF 逐页栅格化，重建成“纯图片 PDF”。

部分打印机和打印服务处理不了包含数万个独立矢量笔画对象的 PDF，会把页面印成空白
或直接拒绝打印。纯图片版每页只有一张整页位图：丢失矢量精度，但几乎所有打印机都能
直接识别，代价是文字不能再放大或选中。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import pymupdf as fitz

DEFAULT_IMAGE_PDF_DPI = 300
MIN_IMAGE_PDF_DPI = 72
MAX_IMAGE_PDF_DPI = 600

PageProgress = Callable[[int, int], None]

_METADATA = {
    "title": "A3 随机手写字体文档（纯图片）",
    "author": "HandwrittenDocumentCreator",
    "subject": "逐页位图重建，打印兼容",
    "keywords": "handwriting, A3, image-only PDF",
}


def validate_image_pdf_dpi(dpi: int) -> None:
    """校验纯图片 PDF 的分辨率是否在支持范围内。"""
    if isinstance(dpi, bool) or not isinstance(dpi, int):
        raise ValueError("纯图片 PDF 的分辨率必须是整数")
    if not MIN_IMAGE_PDF_DPI <= dpi <= MAX_IMAGE_PDF_DPI:
        raise ValueError(
            f"纯图片 PDF 的分辨率必须在 {MIN_IMAGE_PDF_DPI} 到 "
            f"{MAX_IMAGE_PDF_DPI} dpi 之间"
        )


def export_pdf_pages_to_image_pdf(
    pdf_path: str | Path,
    image_pdf_path: str | Path,
    dpi: int = DEFAULT_IMAGE_PDF_DPI,
    progress: PageProgress | None = None,
) -> Path:
    """把 ``pdf_path`` 的每一页渲染成位图，再拼成一个新的纯图片 PDF。

    页面尺寸保持不变，每页只保留一整张灰度位图，不包含任何字体或矢量对象。
    ``progress`` 会在每页完成后以 ``(已完成页数, 总页数)`` 调用。
    """
    validate_image_pdf_dpi(dpi)
    source = Path(pdf_path)
    destination = Path(image_pdf_path)
    if not source.is_file():
        raise FileNotFoundError(f"找不到矢量 PDF：{source}")
    if source.resolve() == destination.resolve():
        raise ValueError("纯图片 PDF 不能与矢量 PDF 使用同一个文件")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.stem}.part{destination.suffix}")

    document = fitz.open(source)
    rebuilt = fitz.open()
    try:
        if document.page_count == 0:
            raise ValueError(f"矢量 PDF 没有页面：{source}")
        for index, page in enumerate(document):
            pixmap = page.get_pixmap(
                dpi=dpi,
                colorspace=fitz.csGRAY,
                alpha=False,
            )
            new_page = rebuilt.new_page(
                width=page.rect.width,
                height=page.rect.height,
            )
            new_page.insert_image(new_page.rect, stream=pixmap.tobytes("png"))
            if progress is not None:
                progress(index + 1, document.page_count)
        rebuilt.set_metadata(_METADATA)
        temporary.unlink(missing_ok=True)
        rebuilt.save(str(temporary), garbage=3, deflate=True)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        rebuilt.close()
        document.close()

    try:
        os.replace(temporary, destination)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return destination
