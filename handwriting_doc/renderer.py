from __future__ import annotations

import os
import random
import secrets
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from .docx_export import export_pdf_pages_to_docx
from .gfont import GFont
from .layout import A3_LANDSCAPE, DocumentLayout, StyledChar, build_layout


ProgressCallback = Callable[[float, str], None]
_FALLBACK_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/simkai.ttf"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("C:/Windows/Fonts/simsun.ttc"),
)
_FALLBACK_FONT_NAME = "HandwritingFallbackCJK"


@dataclass(frozen=True, slots=True)
class GenerationResult:
    pdf_path: Path
    docx_path: Path | None
    seed: int
    page_count: int
    line_count: int
    character_count: int
    selected_fonts: tuple[str, ...]
    fallback_count: int
    missing_characters: tuple[str, ...]
    font_usage: tuple[tuple[str, int], ...]


def _notify(callback: ProgressCallback | None, fraction: float, message: str) -> None:
    if callback is not None:
        callback(max(0.0, min(1.0, fraction)), message)


def _register_fallback_font() -> str | None:
    if _FALLBACK_FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return _FALLBACK_FONT_NAME
    for candidate in _FALLBACK_FONT_CANDIDATES:
        if candidate.suffix.lower() != ".ttf" or not candidate.is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont(_FALLBACK_FONT_NAME, str(candidate)))
            return _FALLBACK_FONT_NAME
        except Exception:
            continue
    return None


def _draw_glyph(
    canvas: Canvas,
    styled: StyledChar,
    center_x: float,
    center_y: float,
    font_size: float,
) -> None:
    if styled.glyph is None or styled.font is None:
        return
    reference_size, reference_y = styled.font.reference
    scale = font_size / reference_size
    x_min, _, x_max, _ = styled.glyph.bounds
    glyph_center_x = (x_min + x_max) / 2
    line_width = max(0.24, font_size * 0.017)

    canvas.saveState()
    canvas.translate(center_x + styled.offset_x, center_y + styled.offset_y)
    canvas.rotate(styled.angle)
    canvas.setStrokeColor(HexColor("#111111"))
    canvas.setFillColor(HexColor("#111111"))
    canvas.setLineWidth(line_width)
    canvas.setLineCap(1)
    canvas.setLineJoin(1)
    for segment in styled.glyph.segments:
        if len(segment) == 1:
            x, y = segment[0]
            canvas.circle(
                (x - glyph_center_x) * scale,
                -(y - reference_y) * scale,
                line_width * 0.55,
                stroke=0,
                fill=1,
            )
            continue
        path = canvas.beginPath()
        for index, (x, y) in enumerate(segment):
            px = (x - glyph_center_x) * scale
            py = -(y - reference_y) * scale
            if index == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        canvas.drawPath(path, stroke=1, fill=0)
    canvas.restoreState()


def _draw_fallback_character(
    canvas: Canvas,
    styled: StyledChar,
    center_x: float,
    center_y: float,
    font_size: float,
    fallback_font: str | None,
) -> None:
    canvas.saveState()
    canvas.translate(center_x + styled.offset_x, center_y + styled.offset_y)
    canvas.rotate(styled.angle)
    canvas.setFillColor(HexColor("#111111"))
    if fallback_font is None:
        half = font_size * 0.2
        canvas.rect(-half, -half, half * 2, half * 2, stroke=1, fill=0)
    else:
        canvas.setFont(fallback_font, font_size * 0.88)
        canvas.drawCentredString(0, -font_size * 0.32, styled.char)
    canvas.restoreState()


def _draw_line(
    canvas: Canvas,
    items: Sequence[StyledChar],
    column_x: float,
    center_y: float,
    metrics,
    fallback_font: str | None,
) -> None:
    start_x = column_x + metrics.side_padding
    for styled in items:
        if styled.char.isspace():
            continue
        center_x = start_x + styled.center_x
        if styled.glyph is None:
            _draw_fallback_character(
                canvas,
                styled,
                center_x,
                center_y,
                metrics.font_size,
                fallback_font,
            )
        else:
            _draw_glyph(canvas, styled, center_x, center_y, metrics.font_size)


def render_pdf(
    layout: DocumentLayout,
    output_path: str | Path,
    seed: int,
    progress: ProgressCallback | None = None,
) -> tuple[int, tuple[tuple[str, int], ...]]:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.stem}.part.pdf")

    canvas = Canvas(
        str(temporary),
        pagesize=A3_LANDSCAPE,
        pageCompression=1,
        invariant=1,
    )
    canvas.setTitle("A3 随机手写字体文档")
    canvas.setSubject("A3 横向双栏逐字随机旋转与位移")
    canvas.setAuthor("HandwrittenDocumentCreator")
    fallback_font = _register_fallback_font()
    fallback_count = 0
    usage: Counter[str] = Counter()
    metrics = layout.metrics
    total_pages = len(layout.pages)
    try:
        for page_index, page in enumerate(layout.pages):
            for column_index, lines in enumerate(
                (page.left_lines, page.right_lines)
            ):
                column_x = metrics.column_x[column_index]
                top_y = metrics.page_height - metrics.margin
                for row_index, line in enumerate(lines):
                    center_y = top_y - (row_index + 0.5) * metrics.row_pitch
                    for styled in line.items:
                        if styled.font is not None:
                            usage[styled.font.name] += 1
                        if styled.uses_fallback and not styled.char.isspace():
                            fallback_count += 1
                    _draw_line(
                        canvas,
                        line.items,
                        column_x,
                        center_y,
                        metrics,
                        fallback_font,
                    )
            canvas.showPage()
            _notify(
                progress,
                0.15 + 0.8 * (page_index + 1) / max(1, total_pages),
                f"正在绘制第 {page_index + 1}/{total_pages} 页",
            )
        canvas.save()
    except Exception:
        try:
            canvas.save()
        except Exception:
            pass
        raise

    os.replace(temporary, destination)
    return fallback_count, tuple(usage.most_common())


def generate_document(
    text: str,
    font_paths: Sequence[str | Path],
    lines_per_column: int,
    output_pdf: str | Path,
    output_docx: str | Path | None = None,
    seed: int | None = None,
    progress: ProgressCallback | None = None,
) -> GenerationResult:
    if not text.strip():
        raise ValueError("输入文本不能为空")
    if not font_paths:
        raise ValueError("至少需要选择一种字体")
    resolved_seed = seed if seed is not None else secrets.randbits(31)
    rng = random.Random(resolved_seed)
    pdf_path = Path(output_pdf)
    docx_path = Path(output_docx) if output_docx else None
    fonts: list[GFont] = []
    try:
        _notify(progress, 0.01, "正在读取字体")
        fonts = [GFont(path) for path in font_paths]
        _notify(progress, 0.05, "正在计算 A3 双栏排版")
        layout = build_layout(text, fonts, lines_per_column, rng)
        _notify(
            progress,
            0.12,
            f"共 {len(layout.pages)} 页，开始绘制 {layout.total_characters} 个字符",
        )
        fallback_count, usage = render_pdf(layout, pdf_path, resolved_seed, progress)
        if docx_path is not None:
            _notify(progress, 0.96, "正在生成 Word 页面")
            export_pdf_pages_to_docx(pdf_path, docx_path)
        _notify(progress, 1.0, "生成完成")
        return GenerationResult(
            pdf_path=pdf_path,
            docx_path=docx_path,
            seed=resolved_seed,
            page_count=len(layout.pages),
            line_count=len(layout.lines),
            character_count=layout.total_characters,
            selected_fonts=tuple(font.name for font in fonts),
            fallback_count=fallback_count,
            missing_characters=layout.missing_characters,
            font_usage=usage,
        )
    finally:
        for font in fonts:
            font.close()
